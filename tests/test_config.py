"""Tests for config module."""

from io import StringIO

import pytest
from dotenv import load_dotenv

from learning_session_transcriber.config import Config


def test_config_from_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Config uses defaults when env vars are unset."""
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("OPENAI_TRANSCRIPTION_MODEL", raising=False)
    config = Config.from_env()
    assert config.app_env == "development"
    assert config.log_level == "INFO"
    assert config.openai_api_key is None
    assert config.openai_model is None
    assert config.openai_reasoning_effort == "medium"
    assert config.openai_transcription_model == "gpt-transcribe"


def test_config_from_env_custom(monkeypatch: pytest.MonkeyPatch) -> None:
    """Config reads APP_ENV and LOG_LEVEL from environment."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-custom")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "low")
    monkeypatch.setenv("OPENAI_TRANSCRIPTION_MODEL", "whisper-custom")
    config = Config.from_env()
    assert config.app_env == "production"
    assert config.log_level == "DEBUG"
    assert config.openai_api_key == "test-key"
    assert config.openai_model == "gpt-custom"
    assert config.openai_reasoning_effort == "low"
    assert config.openai_transcription_model == "whisper-custom"


def test_config_supports_same_name_os_env_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    """The .env alias resolves the existing OS OPENAI_API_KEY without replacing it."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    load_dotenv(
        stream=StringIO("OPENAI_API_KEY=${OPENAI_API_KEY}\n"),
        override=False,
    )

    assert Config.from_env().openai_api_key == "test-key"
