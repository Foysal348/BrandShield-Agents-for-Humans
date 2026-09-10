"""Optional Strands agent factory for Bedrock-generated reviewer narratives."""

from __future__ import annotations

import boto3
from strands import Agent
from strands.models import BedrockModel

from brandshield.config import Settings
from brandshield.tools import assess_listing


SYSTEM_PROMPT = """You are BrandShield, a brand-protection investigation assistant.
Use the assess_listing tool for scoring. Clearly separate observed evidence from inference.
Never call an item counterfeit as a fact. Never send a takedown or make an enforcement
decision. Produce a concise reviewer narrative and require human approval.
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
    return Agent(model=model, tools=[assess_listing], system_prompt=SYSTEM_PROMPT)


def generate_reviewer_narrative(case_file: str, settings: Settings | None = None) -> str:
    """Generate an optional narrative through Amazon Bedrock (may incur AWS usage)."""
    agent = build_agent(settings)
    result = agent(
        "Review the following deterministic case file. Summarize the evidence, identify "
        "uncertainties, and propose human verification steps. Do not make a counterfeit "
        f"determination.\n\n{case_file}"
    )
    return str(result)
