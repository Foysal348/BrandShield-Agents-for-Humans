"""Validated domain models shared by the risk engine, tools, and UI."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CatalogProduct(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sku: str = Field(min_length=1)
    brand: str = Field(min_length=1)
    official_title: str = Field(min_length=1)
    msrp: Decimal = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    authorized_sellers: list[str] = Field(default_factory=list)
    reference_image_url: HttpUrl | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class ListingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    listing_id: str = Field(min_length=1)
    marketplace: str = Field(min_length=1)
    title: str = Field(min_length=1)
    claimed_brand: str = Field(min_length=1)
    claimed_sku: str | None = None
    seller_id: str = Field(min_length=1)
    seller_name: str = Field(min_length=1)
    price: Decimal = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    listing_url: HttpUrl | None = None
    image_url: HttpUrl | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class RiskSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    label: str
    points: int = Field(ge=0, le=100)
    explanation: str
    evidence: dict[str, str | float | int | bool | None] = Field(default_factory=dict)


class RiskAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing_id: str
    catalog_sku: str
    score: int = Field(ge=0, le=100)
    level: RiskLevel
    signals: list[RiskSignal]
    recommended_action: str
    human_review_required: bool = True
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    methodology_version: str = "rules-v1"
    disclaimer: str = (
        "This assessment prioritizes listings for review; it does not determine that an item "
        "is counterfeit. A human must approve any enforcement action."
    )
