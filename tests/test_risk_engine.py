from decimal import Decimal

import pytest
from pydantic import ValidationError

from brandshield.models import CatalogProduct, ListingInput, RiskLevel
from brandshield.risk_engine import RiskEngine, render_case_file


@pytest.fixture
def product() -> CatalogProduct:
    return CatalogProduct(
        sku="BS-100",
        brand="Northstar",
        official_title="Northstar Trail Runner Pro",
        msrp=Decimal("100.00"),
        currency="USD",
        authorized_sellers=["seller-official", "Northstar Store"],
    )


def make_listing(**overrides: object) -> ListingInput:
    values: dict[str, object] = {
        "listing_id": "LIST-001",
        "marketplace": "DemoMarket",
        "title": "Northstar Trail Runner Pro",
        "claimed_brand": "Northstar",
        "claimed_sku": "BS-100",
        "seller_id": "seller-official",
        "seller_name": "Northstar Store",
        "price": Decimal("100.00"),
        "currency": "USD",
    }
    values.update(overrides)
    return ListingInput.model_validate(values)


def test_authorized_listing_is_low_risk(product: CatalogProduct) -> None:
    result = RiskEngine().assess(make_listing(), product)

    assert result.score == 0
    assert result.level is RiskLevel.LOW
    assert result.signals == []
    assert result.human_review_required is True


def test_unauthorized_deep_discount_is_high_risk(product: CatalogProduct) -> None:
    listing = make_listing(
        seller_id="unknown-77",
        seller_name="Unknown Deals",
        price=Decimal("30.00"),
    )

    result = RiskEngine().assess(listing, product)

    assert result.score == 65
    assert result.level is RiskLevel.HIGH
    assert {signal.code for signal in result.signals} == {
        "unauthorized_seller",
        "extreme_price_discount",
    }


def test_multiple_signals_are_capped_at_one_hundred(product: CatalogProduct) -> None:
    listing = make_listing(
        title="Replica mirror quality copy",
        claimed_brand="Other Brand",
        claimed_sku="WRONG-SKU",
        seller_id="unknown-88",
        seller_name="Replica Warehouse",
        price=Decimal("10.00"),
    )

    result = RiskEngine().assess(listing, product)

    assert result.score == 100
    assert result.level is RiskLevel.CRITICAL
    assert result.human_review_required is True


def test_currency_mismatch_skips_price_comparison(product: CatalogProduct) -> None:
    result = RiskEngine().assess(make_listing(currency="EUR"), product)

    assert result.score == 5
    assert [signal.code for signal in result.signals] == ["currency_mismatch"]


def test_case_file_is_auditable(product: CatalogProduct) -> None:
    listing = make_listing(seller_id="unknown", seller_name="Unknown")
    result = RiskEngine().assess(listing, product)

    case_file = render_case_file(listing, product, result)

    assert "LIST-001" in case_file
    assert "rules-v1" in case_file
    assert "human must approve" in case_file.lower()


def test_non_positive_price_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_listing(price=Decimal("0"))
