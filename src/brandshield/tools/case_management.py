"""Strands tools for case creation, inspection, and approved report drafting."""

from __future__ import annotations

from typing import Any

from strands import tool

from brandshield.config import Settings
from brandshield.models import CatalogProduct, CaseStatus, ListingInput
from brandshield.storage import SQLiteCaseRepository
from brandshield.workflow import CaseWorkflow


def _workflow() -> CaseWorkflow:
    settings = Settings.from_env()
    return CaseWorkflow(SQLiteCaseRepository(settings.database_path))


@tool
def open_investigation_case(
    listing: dict[str, Any],
    catalog_product: dict[str, Any],
) -> dict[str, Any]:
    """Create an auditable investigation case from validated listing and catalog data.

    This tool may open a case but cannot approve, reject, close, or externally report it.
    """
    case = _workflow().open_case(
        ListingInput.model_validate(listing),
        CatalogProduct.model_validate(catalog_product),
        actor="brandshield-agent",
    )
    return case.model_dump(mode="json")


@tool
def get_investigation_case(case_id: str) -> dict[str, Any]:
    """Return one investigation case and its complete append-only audit trail."""
    workflow = _workflow()
    case = workflow.repository.get_case(case_id)
    events = workflow.repository.list_events(case_id)
    return {
        "case": case.model_dump(mode="json"),
        "audit_events": [event.model_dump(mode="json") for event in events],
    }


@tool
def list_investigation_cases(status: str | None = None) -> list[dict[str, Any]]:
    """List investigation cases, optionally filtering by an exact case status."""
    parsed_status = CaseStatus(status) if status else None
    cases = _workflow().repository.list_cases(parsed_status)
    return [case.model_dump(mode="json") for case in cases]


@tool
def draft_case_report(case_id: str) -> str:
    """Draft a marketplace review request only for a case already approved by a human."""
    return _workflow().create_report_draft(case_id, actor="brandshield-agent")
