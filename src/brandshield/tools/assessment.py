"""Strands tool wrappers around deterministic BrandShield capabilities."""

from __future__ import annotations

from typing import Any

from strands import tool

from brandshield.models import CatalogProduct, ListingInput
from brandshield.risk_engine import RiskEngine


@tool
def assess_listing(
    listing: dict[str, Any],
    catalog_product: dict[str, Any],
) -> dict[str, Any]:
    """Assess one product listing against one official catalog product.

    Args:
        listing: Listing fields including ID, seller, title, brand, price, and currency.
        catalog_product: Official product fields including SKU, brand, MSRP, and sellers.

    Returns:
        A transparent risk assessment. It is a review-priority score, not a counterfeit verdict.
    """
    parsed_listing = ListingInput.model_validate(listing)
    parsed_product = CatalogProduct.model_validate(catalog_product)
    result = RiskEngine().assess(parsed_listing, parsed_product)
    return result.model_dump(mode="json")
