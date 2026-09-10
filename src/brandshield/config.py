"""Environment-backed settings for BrandShield."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _as_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings. Secret values are intentionally not stored here."""

    demo_mode: bool = True
    data_dir: Path = Path("data")
    aws_region: str = "us-east-1"
    aws_profile: str | None = None
    bedrock_model_id: str = "us.amazon.nova-lite-v1:0"

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        profile = os.getenv("AWS_PROFILE", "").strip() or None
        return cls(
            demo_mode=_as_bool(os.getenv("BRANDSHIELD_DEMO_MODE"), default=True),
            data_dir=Path(os.getenv("BRANDSHIELD_DATA_DIR", "data")),
            aws_region=os.getenv("AWS_REGION", "us-east-1"),
            aws_profile=profile,
            bedrock_model_id=os.getenv(
                "BEDROCK_MODEL_ID", "us.amazon.nova-lite-v1:0"
            ),
        )
