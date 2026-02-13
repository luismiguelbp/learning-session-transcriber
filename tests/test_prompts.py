"""Tests for prompts module (include_resources resolution)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from learning_session_transcriber.prompts import _resolve_include_resources
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


def test_resolve_include_resources_skips_missing_file(tmp_path: Path) -> None:
    """When session lists a path that does not exist, skip that resource."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    config_path = session_dir / "session.yaml"
    _write_session_yaml(config_path, "test_run", include_resources={"pdf": "missing.pdf"})
    session = load_session_config(config_path)
    text_extra, file_parts = _resolve_include_resources(session, config_path, ["pdf"])
    assert text_extra == ""
    assert file_parts == []


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
