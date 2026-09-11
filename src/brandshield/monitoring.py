"""Resilient autonomous batch monitoring over marketplace listing feeds."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from brandshield.models import (
    CatalogProduct,
    ListingInput,
    MonitoringItemResult,
    MonitoringOutcome,
    MonitoringRun,
)
from brandshield.workflow import CaseWorkflow


def _utc_now() -> datetime:
    return datetime.now(UTC)


class MonitoringService:
    """Scan every item independently so one malformed listing cannot stop a run."""

    def __init__(self, workflow: CaseWorkflow) -> None:
        self.workflow = workflow

    def scan_batch(
        self,
        listings: list[dict[str, Any]],
        catalog_products: list[dict[str, Any] | CatalogProduct],
        *,
        actor: str = "brandshield-agent",
    ) -> MonitoringRun:
        started_at = _utc_now()
        products = [
            item if isinstance(item, CatalogProduct) else CatalogProduct.model_validate(item)
            for item in catalog_products
        ]
        product_by_sku = {product.sku.casefold(): product for product in products}
        results: list[MonitoringItemResult] = []

        for index, raw_listing in enumerate(listings, start=1):
            fallback_id = str(raw_listing.get("listing_id") or f"item-{index}")
            try:
                listing = ListingInput.model_validate(raw_listing)
                if not listing.claimed_sku:
                    raise ValueError("Listing does not provide a catalog SKU.")
                product = product_by_sku.get(listing.claimed_sku.casefold())
                if product is None:
                    raise ValueError(
                        f"No catalog product matches SKU {listing.claimed_sku}."
                    )

                assessment = self.workflow.risk_engine.assess(listing, product)
                if assessment.score < self.workflow.review_threshold:
                    results.append(
                        MonitoringItemResult(
                            listing_id=listing.listing_id,
                            outcome=MonitoringOutcome.LOW_RISK,
                            risk_score=assessment.score,
                            message="Below the investigation threshold; monitoring continues.",
                        )
                    )
                    continue

                existing = self.workflow.repository.find_case_by_listing_id(
                    listing.listing_id
                )
                case = self.workflow.open_case(listing, product, actor=actor)
                if existing is not None:
                    outcome = MonitoringOutcome.DUPLICATE
                    message = "Existing case reused; a duplicate observation was audited."
                elif case.reappeared_from_case_id:
                    outcome = MonitoringOutcome.REAPPEARANCE
                    message = "New listing linked to a prior seller/product investigation."
                else:
                    outcome = MonitoringOutcome.CASE_CREATED
                    message = "New investigation case created for human review."

                results.append(
                    MonitoringItemResult(
                        listing_id=listing.listing_id,
                        outcome=outcome,
                        risk_score=assessment.score,
                        case_id=case.case_id,
                        related_case_id=case.reappeared_from_case_id,
                        message=message,
                    )
                )
            except (ValidationError, ValueError) as exc:
                results.append(
                    MonitoringItemResult(
                        listing_id=fallback_id,
                        outcome=MonitoringOutcome.ERROR,
                        message=str(exc),
                    )
                )

        run = MonitoringRun(
            run_id=f"RUN-{uuid4().hex[:12].upper()}",
            started_at=started_at,
            completed_at=_utc_now(),
            total_listings=len(listings),
            low_risk_count=self._count(results, MonitoringOutcome.LOW_RISK),
            cases_created_count=self._count(results, MonitoringOutcome.CASE_CREATED),
            duplicate_count=self._count(results, MonitoringOutcome.DUPLICATE),
            reappearance_count=self._count(results, MonitoringOutcome.REAPPEARANCE),
            error_count=self._count(results, MonitoringOutcome.ERROR),
            results=results,
        )
        return self.workflow.repository.save_monitoring_run(run)

    @staticmethod
    def _count(
        results: list[MonitoringItemResult], outcome: MonitoringOutcome
    ) -> int:
        return sum(item.outcome is outcome for item in results)
