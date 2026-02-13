
"""Configuration loaded from OS environment and optional .env file."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

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
    openai_model: str
    openai_transcription_model: str

    @classmethod
    def from_env(cls) -> "Config":
        """Build config from environment variables."""
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            openai_transcription_model=os.getenv(
                "OPENAI_TRANSCRIPTION_MODEL", "gpt-4o-transcribe"
            ),
        )

