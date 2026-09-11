"""Optional Strands agent factory for Bedrock-generated reviewer narratives."""

from __future__ import annotations

import boto3
from strands import Agent
from strands.models import BedrockModel

from brandshield.config import Settings
from brandshield.interventions import DraftReportApprovalIntervention
from brandshield.tools import (
    assess_listing,
    draft_case_report,
    get_investigation_case,
    list_investigation_cases,
    monitor_listing_batch,
    open_investigation_case,
)


SYSTEM_PROMPT = """You are BrandShield, a brand-protection investigation assistant.
Use the deterministic tools for batch monitoring, scoring, and case management. Clearly separate observed
evidence from inference. You may open a case and draft a report for an already human-approved
case. Never call an item counterfeit as a fact. Never approve, reject, close, or send a
takedown. Produce concise reviewer output and explicitly require human approval.
"""


def build_agent(settings: Settings | None = None) -> Agent:
    """Build the Strands agent without invoking it or creating AWS resources."""
    settings = settings or Settings.from_env()
    session = boto3.Session(
        profile_name=settings.aws_profile,
        region_name=settings.aws_region,
    )
    model = BedrockModel(
        boto_session=session,
        model_id=settings.bedrock_model_id,
        temperature=0.1,
    )
    return Agent(
        model=model,
        tools=[
            assess_listing,
            open_investigation_case,
            get_investigation_case,
            list_investigation_cases,
            monitor_listing_batch,
            draft_case_report,
        ],
        interventions=[DraftReportApprovalIntervention()],
        system_prompt=SYSTEM_PROMPT,
    )


def generate_reviewer_narrative(case_file: str, settings: Settings | None = None) -> str:
    """Generate an optional narrative through Amazon Bedrock (may incur AWS usage)."""
    agent = build_agent(settings)
    result = agent(
        "Review the following deterministic case file. Summarize the evidence, identify "
        "uncertainties, and propose human verification steps. Do not make a counterfeit "
        f"determination.\n\n{case_file}"
    )
    return str(result)
