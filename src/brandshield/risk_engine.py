"""Transparent, deterministic risk scoring for product listings."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from brandshield.models import (
    CatalogProduct,
    ListingInput,
    RiskAssessment,
    RiskLevel,
    RiskSignal,
)


SUSPICIOUS_PHRASES = (
    "1:1",
    "copy",
    "inspired",
    "mirror quality",
    "replica",
)


def _normalized(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _level_for(score: int) -> RiskLevel:
    if score >= 75:
        return RiskLevel.CRITICAL
    if score >= 50:
        return RiskLevel.HIGH
    if score >= 25:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _action_for(level: RiskLevel) -> str:
    return {
        RiskLevel.LOW: "Monitor; no enforcement action recommended.",
        RiskLevel.MEDIUM: "Queue for routine human review.",
        RiskLevel.HIGH: "Open an investigation case and request evidence review.",
        RiskLevel.CRITICAL: "Prioritize urgent human review; draft a platform report if verified.",
    }[level]


class RiskEngine:
    """Score observable listing signals without making a legal determination."""

    methodology_version = "rules-v1"

    def assess(
        self,
        listing: ListingInput,
        product: CatalogProduct,
    ) -> RiskAssessment:
        signals: list[RiskSignal] = []

        if _normalized(listing.claimed_brand) != _normalized(product.brand):
            signals.append(
                RiskSignal(
                    code="brand_mismatch",
                    label="Claimed brand mismatch",
                    points=25,
                    explanation="The listing's claimed brand does not match the catalog brand.",
                    evidence={
                        "claimed_brand": listing.claimed_brand,
                        "catalog_brand": product.brand,
                    },
                )
            )

        if listing.claimed_sku and _normalized(listing.claimed_sku) != _normalized(product.sku):
            signals.append(
                RiskSignal(
                    code="sku_mismatch",
                    label="SKU mismatch",
                    points=20,
                    explanation="The listing's claimed SKU differs from the matched catalog SKU.",
                    evidence={
                        "claimed_sku": listing.claimed_sku,
                        "catalog_sku": product.sku,
                    },
                )
            )

        authorized = {
            _normalized(value) for value in product.authorized_sellers
        }
        seller_candidates = {_normalized(listing.seller_id), _normalized(listing.seller_name)}
        if not authorized.intersection(seller_candidates):
            signals.append(
                RiskSignal(
                    code="unauthorized_seller",
                    label="Seller is not authorized",
                    points=30,
                    explanation=(
                        "Neither the seller ID nor seller name appears in the catalog allowlist."
                    ),
                    evidence={"seller_id": listing.seller_id, "seller_name": listing.seller_name},
                )
            )

        if listing.currency == product.currency:
            price_ratio = float(listing.price / product.msrp)
            if price_ratio < 0.40:
                signals.append(
                    RiskSignal(
                        code="extreme_price_discount",
                        label="Extreme price discount",
                        points=35,
                        explanation=(
                            "The price is below 40% of the catalog MSRP."
                        ),
                        evidence={"price_to_msrp_ratio": round(price_ratio, 3)},
                    )
                )
            elif price_ratio < 0.70:
                signals.append(
                    RiskSignal(
                        code="large_price_discount",
                        label="Large price discount",
                        points=20,
                        explanation="The price is below 70% of the catalog MSRP.",
                        evidence={"price_to_msrp_ratio": round(price_ratio, 3)},
                    )
                )
        else:
            signals.append(
                RiskSignal(
                    code="currency_mismatch",
                    label="Currency cannot be compared",
                    points=5,
                    explanation=(
                        "Listing and catalog currencies differ, so the price signal needs review."
                    ),
                    evidence={
                        "listing_currency": listing.currency,
                        "catalog_currency": product.currency,
                    },
                )
            )

        normalized_title = _normalized(listing.title)
        found_phrases = [phrase for phrase in SUSPICIOUS_PHRASES if phrase in normalized_title]
        if found_phrases:
            signals.append(
                RiskSignal(
                    code="suspicious_language",
                    label="Suspicious listing language",
                    points=30,
                    explanation=(
                        "The title contains wording commonly used to signal imitation goods."
                    ),
                    evidence={"matched_phrases": ", ".join(found_phrases)},
                )
            )

        title_similarity = SequenceMatcher(
            None, normalized_title, _normalized(product.official_title)
        ).ratio()
        if title_similarity < 0.45:
            title_points = 20
        elif title_similarity < 0.65:
            title_points = 10
        else:
            title_points = 0
        if title_points:
            signals.append(
                RiskSignal(
                    code="title_mismatch",
                    label="Catalog title mismatch",
                    points=title_points,
                    explanation=(
                        "The listing title has low similarity to the official catalog title."
                    ),
                    evidence={"title_similarity": round(title_similarity, 3)},
                )
            )

        score = min(100, sum(signal.points for signal in signals))
        level = _level_for(score)
        return RiskAssessment(
            listing_id=listing.listing_id,
            catalog_sku=product.sku,
            score=score,
            level=level,
            signals=signals,
            recommended_action=_action_for(level),
            methodology_version=self.methodology_version,
        )


def render_case_file(
    listing: ListingInput,
    product: CatalogProduct,
    assessment: RiskAssessment,
) -> str:
    """Render an auditable Markdown case file suitable for human review."""
    signal_lines = "\n".join(
        f"- **{signal.label} (+{signal.points})** — {signal.explanation}"
        for signal in assessment.signals
    ) or "- No risk signals were triggered."

    return f"""# BrandShield Investigation Case

## Case summary

- Listing ID: `{listing.listing_id}`
- Marketplace: {listing.marketplace}
- Seller: {listing.seller_name} (`{listing.seller_id}`)
- Catalog product: {product.official_title} (`{product.sku}`)
- Risk score: **{assessment.score}/100 ({assessment.level.value})**
- Methodology: `{assessment.methodology_version}`

## Observed signals

{signal_lines}

## Recommended next step

{assessment.recommended_action}

## Human-governance notice

{assessment.disclaimer}
"""
