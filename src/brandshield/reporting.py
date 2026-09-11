"""Human-reviewed marketplace report drafting."""

from __future__ import annotations

from datetime import datetime, timezone

from brandshield.models import InvestigationCase


def draft_takedown_report(case: InvestigationCase) -> str:
    """Draft an evidence-rich platform review request from an approved case."""
    signal_lines: list[str] = []
    for signal in case.assessment.signals:
        evidence = ", ".join(
            f"{key.replace('_', ' ')}: {value}"
            for key, value in signal.evidence.items()
        )
        evidence_suffix = f" Evidence: {evidence}." if evidence else ""
        signal_lines.append(
            f"- **{signal.label} (+{signal.points})**: "
            f"{signal.explanation}{evidence_suffix}"
        )

    signals = "\n".join(signal_lines) or "- No configured risk signals were triggered."
    listing_url = str(case.listing.listing_url) if case.listing.listing_url else "Not provided"
    price_ratio = float(case.listing.price / case.product.msrp)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    evidence_hash = case.evidence.sha256 if case.evidence else "Not captured"
    evidence_path = case.evidence.relative_path if case.evidence else "Not captured"
    reappearance = case.reappeared_from_case_id or "No prior linked case"

    return f"""# DRAFT - Marketplace Listing Review Request

**Do not send without a final human legal/policy review.**

- Generated at: {generated_at}
- Assessment version: `{case.assessment.methodology_version}`

## Reference

- BrandShield case: `{case.case_id}`
- Listing: `{case.listing.listing_id}`
- Listing title: {case.listing.title}
- Marketplace: {case.listing.marketplace}
- Listing URL: {listing_url}
- Seller: {case.listing.seller_name} (`{case.listing.seller_id}`)
- Referenced product: {case.product.official_title} (`{case.product.sku}`)

## Evidence snapshot

- Claimed brand: {case.listing.claimed_brand}
- Claimed SKU: {case.listing.claimed_sku or "Not provided"}
- Listing price: {case.listing.price} {case.listing.currency}
- Catalog MSRP: {case.product.msrp} {case.product.currency}
- Price-to-MSRP ratio: {price_ratio:.1%}
- Authorized sellers checked: {", ".join(case.product.authorized_sellers) or "None configured"}

## Request

Please review this listing under your intellectual-property and prohibited-products policies.
Our internal triage identified observable inconsistencies that require platform review.

## Supporting observations

{signals}

## Internal review record

- Risk-priority score: {case.assessment.score}/100 ({case.assessment.level.value})
- Reviewer: {case.reviewer_name or "Not recorded"}
- Reviewer note: {case.reviewer_note or "Not recorded"}
- Assessment evaluated at: {case.assessment.evaluated_at.isoformat(timespec="seconds")}
- Evidence SHA-256: `{evidence_hash}`
- Evidence snapshot: `{evidence_path}`
- Reappearance link: {reappearance}

## Required before sending

- Verify the listing and evidence are still available.
- Attach authorized rights-ownership documentation.
- Check the target marketplace's current reporting policy.
- Obtain final approval from an authorized human representative.

This draft does not assert that the item is counterfeit and is not legal advice.
"""
