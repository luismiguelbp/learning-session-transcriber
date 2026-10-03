"""Tests for prompts module (include_resources resolution)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from learning_session_transcriber.prompts import (
    _chat,
    _resolve_include_resources,
    _resolve_prompt_model,
)
from learning_session_transcriber.sessions import load_session_config


def _write_session_yaml(path: Path, content_name: str, include_resources: dict | None = None) -> None:
    data = {
        "content_name": content_name,
        "topic": "Test Topic",
        "language": "es",
        "videos": [
            {"index": 1, "title": "Test Class 1", "url": "https://example.com/v1"},
        ],
    }
    if include_resources is not None:
        data["include_resources"] = include_resources
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_resolve_include_resources_returns_empty_when_no_session_resources(tmp_path: Path) -> None:
    """When session has no include_resources, return empty text and no file parts."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    config_path = session_dir / "session.yaml"
    _write_session_yaml(config_path, "test_run", include_resources=None)
    session = load_session_config(config_path)
    assert session.include_resources is None
    text_extra, file_parts = _resolve_include_resources(session, config_path, ["pdf"])
    assert text_extra == ""
    assert file_parts == []


def test_resolve_include_resources_returns_empty_when_keys_empty(tmp_path: Path) -> None:
    """When include_resources_keys is empty, return empty text and no file parts."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    config_path = session_dir / "session.yaml"
    _write_session_yaml(config_path, "test_run", include_resources={"notes": "material.txt"})
    (session_dir / "material.txt").write_text("notes", encoding="utf-8")
    session = load_session_config(config_path)
    text_extra, file_parts = _resolve_include_resources(session, config_path, [])
    assert text_extra == ""
    assert file_parts == []


def test_resolve_include_resources_includes_file_content(tmp_path: Path) -> None:
    """When key is in session and file exists (text), return heading and content in text_extra."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    config_path = session_dir / "session.yaml"
    _write_session_yaml(config_path, "test_run", include_resources={"notes": "material.txt"})
    (session_dir / "material.txt").write_text("Slide 1 content\nSlide 2 content", encoding="utf-8")
    session = load_session_config(config_path)
    text_extra, file_parts = _resolve_include_resources(session, config_path, ["notes"])
    assert "## Resource: notes" in text_extra
    assert "Slide 1 content" in text_extra
    assert "Slide 2 content" in text_extra
    assert file_parts == []


def test_resolve_include_resources_skips_missing_key(tmp_path: Path) -> None:
    """When prompt requests a key not in session, skip it (and log warning)."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    config_path = session_dir / "session.yaml"
    _write_session_yaml(config_path, "test_run", include_resources={"pdf": "material.pdf"})
    (session_dir / "material.pdf").write_bytes(b"%PDF-1.4\n%\n")
    session = load_session_config(config_path)
    text_extra, file_parts = _resolve_include_resources(session, config_path, ["notes"])
    assert text_extra == ""
    assert file_parts == []


def test_session_validate_include_resources_file_must_exist(tmp_path: Path) -> None:
    """Session raises ValueError when include_resources points to a missing file."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    config_path = session_dir / "session.yaml"
    _write_session_yaml(config_path, "test_run", include_resources={"pdf": "missing.pdf"})
    with pytest.raises(ValueError, match="points to missing file"):
        load_session_config(config_path)


def test_resolve_include_resources_pdf_returns_file_part(tmp_path: Path) -> None:
    """When resource is a .pdf file, return base64 file part and no text."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    config_path = session_dir / "session.yaml"
    _write_session_yaml(config_path, "test_run", include_resources={"pdf": "material.pdf"})
    (session_dir / "material.pdf").write_bytes(b"%PDF-1.4\n%\n")
    session = load_session_config(config_path)
    text_extra, file_parts = _resolve_include_resources(session, config_path, ["pdf"])
    assert text_extra == ""
    assert len(file_parts) == 1
    assert file_parts[0]["type"] == "file"
    assert file_parts[0]["file"]["filename"] == "material.pdf"
    assert file_parts[0]["file"]["file_data"].startswith("data:application/pdf;base64,")


def test_chat_uses_responses_for_gpt6_and_converts_pdf_input() -> None:
    captured: dict = {}
    fake_response = SimpleNamespace(status="completed", output_text="study guide")

    def create(**kwargs):
        captured.update(kwargs)
        return fake_response

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    result = _chat(
        client=client,
        model="gpt-6-luna",
        system_prompt="Create a study guide.",
        user_content=[
            {"type": "text", "text": "Transcript"},
            {
                "type": "file",
                "file": {
                    "filename": "slides.pdf",
                    "file_data": "data:application/pdf;base64,ZmFrZQ==",
                },
            },
        ],
        temperature=0.3,
        max_tokens=1200,
        reasoning_effort="low",
    )

    assert result == "study guide"
    assert captured["model"] == "gpt-6-luna"
    assert captured["instructions"] == "Create a study guide."
    assert captured["reasoning"] == {"effort": "low"}
    assert captured["max_output_tokens"] == 1200
    assert "temperature" not in captured
    assert captured["input"][0]["content"] == [
        {"type": "input_text", "text": "Transcript"},
        {
            "type": "input_file",
            "filename": "slides.pdf",
            "file_data": "data:application/pdf;base64,ZmFrZQ==",
        },
    ]


def test_resolve_prompt_model_precedence() -> None:
    assert _resolve_prompt_model("gpt-6.1-sol", "gpt-6-luna") == "gpt-6.1-sol"
    assert _resolve_prompt_model(None, "gpt-6-sol") == "gpt-6-sol"
    assert _resolve_prompt_model(None, None) == "gpt-6-luna"


def test_chat_allows_temperature_for_gpt6_luna_with_no_reasoning() -> None:
    captured: dict = {}
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **kwargs: (
                captured.update(kwargs)
                or SimpleNamespace(status="completed", output_text="summary")
            )
        )
    )

    result = _chat(
        client=client,
        model="gpt-6-luna",
        system_prompt="Summarize.",
        user_content="Transcript",
        temperature=0.3,
        max_tokens=300,
        reasoning_effort="none",
    )

    assert result == "summary"
    assert captured["reasoning"] == {"effort": "none"}
    assert captured["temperature"] == 0.3


def test_chat_rejects_none_reasoning_for_gpt61_sol() -> None:
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **_: pytest.fail("request should be rejected before API call")
        )
    )

    with pytest.raises(ValueError, match="does not support reasoning effort 'none'"):
        _chat(
            client=client,
            model="gpt-6.1-sol",
            system_prompt="Summarize.",
            user_content="Transcript",
            temperature=0.3,
            max_tokens=300,
            reasoning_effort="none",
        )


def test_chat_keeps_legacy_chat_completions_for_non_gpt6_override() -> None:
    captured: dict = {}
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="legacy output"))]
    )

    def create(**kwargs):
        captured.update(kwargs)
        return fake_response

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    result = _chat(
        client=client,
        model="gpt-5-mini",
        system_prompt="Summarize.",
        user_content="Transcript",
        temperature=0.3,
        max_tokens=500,
    )

    assert result == "legacy output"
    assert captured["temperature"] == 0.3
    assert captured["max_completion_tokens"] == 500


def test_resolve_include_resources_multiple_keys(tmp_path: Path) -> None:
    """Multiple keys: PDF goes to file_parts, text to text_extra."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    config_path = session_dir / "session.yaml"
    _write_session_yaml(
        config_path,
        "test_run",
        include_resources={"pdf": "material.pdf", "notes": "apuntes.txt"},
    )
    (session_dir / "material.pdf").write_bytes(b"%PDF-1.4\n%\n")
    (session_dir / "apuntes.txt").write_text("Notes text", encoding="utf-8")
    session = load_session_config(config_path)
    text_extra, file_parts = _resolve_include_resources(session, config_path, ["pdf", "notes"])
    assert "## Resource: notes" in text_extra
    assert "Notes text" in text_extra
    assert len(file_parts) == 1
    assert file_parts[0]["type"] == "file"
    assert file_parts[0]["file"]["file_data"].startswith("data:application/pdf;base64,")


def test_session_validate_pdf_requires_pdf_extension(tmp_path: Path) -> None:
    """Session raises ValueError when include_resources key 'pdf' points to non-.pdf file."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    config_path = session_dir / "session.yaml"
    _write_session_yaml(config_path, "test_run", include_resources={"pdf": "material.txt"})
    with pytest.raises(ValueError, match="include_resources key 'pdf' must point to a .pdf file"):
        load_session_config(config_path)


def test_session_validate_notes_requires_txt_extension(tmp_path: Path) -> None:
    """Session raises ValueError when include_resources key 'notes' points to non-.txt file."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    config_path = session_dir / "session.yaml"
    _write_session_yaml(config_path, "test_run", include_resources={"notes": "material.pdf"})
    with pytest.raises(ValueError, match="include_resources key 'notes' must point to a .txt file"):
        load_session_config(config_path)
