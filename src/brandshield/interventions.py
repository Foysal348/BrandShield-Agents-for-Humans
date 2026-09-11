"""Strands human-in-the-loop controls for sensitive BrandShield tool calls."""

from __future__ import annotations

from strands import InterventionHandler
from strands.hooks import BeforeToolCallEvent
from strands.interventions import Confirm, Proceed


class DraftReportApprovalIntervention(InterventionHandler):
    """Pause the agent before it drafts an enforcement-adjacent document."""

    name = "brandshield-draft-report-confirmation"

    def before_tool_call(self, event: BeforeToolCallEvent) -> Confirm | Proceed:
        if event.tool_use["name"] != "draft_case_report":
            return Proceed()
        case_id = event.tool_use.get("input", {}).get("case_id", "unknown")
        return Confirm(
            prompt=(
                "A human-approved case is about to be converted into a marketplace "
                f"report draft ({case_id}). Confirm with yes to continue. BrandShield "
                "will not send the report."
            )
        )
