
"""Configuration loaded from OS environment and optional .env file."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_OPENAI_MODEL = "gpt-6-luna"
DEFAULT_REASONING_EFFORT = "medium"

# Load variables from .env **without** overwriting anything that is already
# present in the real OS environment. This keeps KISS and ensures that
# explicit OS env vars always win.
load_dotenv(override=False)


@dataclass(frozen=True)
class Config:
    """Application configuration."""

    app_env: str
    log_level: str
    openai_api_key: str | None
    openai_model: str | None
    openai_reasoning_effort: str
    openai_transcription_model: str

    @classmethod
    def from_env(cls) -> "Config":
        """Build config from environment variables."""
        reasoning_effort = (
            os.getenv("OPENAI_REASONING_EFFORT") or DEFAULT_REASONING_EFFORT
        ).strip().lower()
        allowed_efforts = {"none", "low", "medium", "high", "xhigh", "max"}
        if reasoning_effort not in allowed_efforts:
            raise ValueError(
                "OPENAI_REASONING_EFFORT must be one of: "
                + ", ".join(sorted(allowed_efforts))
            )
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_model=os.getenv("OPENAI_MODEL", "").strip() or None,
            openai_reasoning_effort=reasoning_effort,
            openai_transcription_model=os.getenv(
                "OPENAI_TRANSCRIPTION_MODEL", "gpt-4o-transcribe"
            ),
        )
