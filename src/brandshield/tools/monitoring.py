"""Strands tool for autonomous, failure-isolated listing feed monitoring."""

from __future__ import annotations

from typing import Any

from strands import tool

from brandshield.config import Settings
from brandshield.monitoring import MonitoringService
from brandshield.storage import SQLiteCaseRepository
from brandshield.workflow import CaseWorkflow


@tool
def monitor_listing_batch(
    listings: list[dict[str, Any]],
    catalog_products: list[dict[str, Any]],
) -> dict[str, Any]:
    """Scan a listing batch, open only review-worthy cases, and audit repeats.

    Malformed items are isolated as errors so the remaining feed continues. This tool can
    create cases but cannot approve, reject, close, simulate, or send enforcement actions.
    """
    settings = Settings.from_env()
    workflow = CaseWorkflow(SQLiteCaseRepository(settings.database_path))
    run = MonitoringService(workflow).scan_batch(
        listings,
        catalog_products,
        actor="brandshield-agent",
    )
    return run.model_dump(mode="json")
