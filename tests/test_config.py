"""Tests for config module."""

import pytest

from learning_session_transcriber.config import Config


def test_config_from_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Config uses defaults when env vars are unset."""
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_TRANSCRIPTION_MODEL", raising=False)
    config = Config.from_env()
    assert config.app_env == "development"
    assert config.log_level == "INFO"
    assert config.openai_api_key is None
    assert config.openai_model == "gpt-5-mini"
    assert config.openai_transcription_model == "gpt-4o-transcribe"


def test_config_from_env_custom(monkeypatch: pytest.MonkeyPatch) -> None:
    """Config reads APP_ENV and LOG_LEVEL from environment."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-custom")
    monkeypatch.setenv("OPENAI_TRANSCRIPTION_MODEL", "whisper-custom")
    config = Config.from_env()
    assert config.app_env == "production"
    assert config.log_level == "DEBUG"
    assert config.openai_api_key == "test-key"
    assert config.openai_model == "gpt-custom"
    assert config.openai_transcription_model == "whisper-custom"

