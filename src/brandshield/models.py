"""Validated domain models shared by the risk engine, tools, and UI."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CaseStatus(StrEnum):
    NEW = "new"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CLOSED = "closed"


class MonitoringOutcome(StrEnum):
    LOW_RISK = "low_risk"
    CASE_CREATED = "case_created"
    DUPLICATE = "duplicate"
    REAPPEARANCE = "reappearance"
    ERROR = "error"


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


class EvidenceArtifact(BaseModel):
    """Content-addressed evidence captured when an investigation case is opened."""

    model_config = ConfigDict(extra="forbid")

    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    relative_path: str = Field(min_length=1)
    identity_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_type: Literal["synthetic_listing_snapshot"] = "synthetic_listing_snapshot"


class InvestigationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    listing: ListingInput
    product: CatalogProduct
    assessment: RiskAssessment
    evidence: EvidenceArtifact | None = None
    reappeared_from_case_id: str | None = None
    status: CaseStatus = CaseStatus.NEW
    reviewer_name: str | None = None
    reviewer_note: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = Field(default=1, ge=1)


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: int
    case_id: str
    event_type: str
    actor: str
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    occurred_at: datetime


class MonitoringItemResult(BaseModel):
    """Outcome for one item in a resilient monitoring cycle."""

    model_config = ConfigDict(extra="forbid")

    listing_id: str
    outcome: MonitoringOutcome
    risk_score: int | None = Field(default=None, ge=0, le=100)
    case_id: str | None = None
    related_case_id: str | None = None
    message: str


class MonitoringRun(BaseModel):
    """Persisted summary of one autonomous batch-monitoring cycle."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    started_at: datetime
    completed_at: datetime
    total_listings: int = Field(ge=0)
    low_risk_count: int = Field(ge=0)
    cases_created_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    reappearance_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    results: list[MonitoringItemResult]
