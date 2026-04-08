"""Tests for session configuration loading."""

from __future__ import annotations

from pathlib import Path

import yaml

from learning_session_transcriber.sessions import load_session_config


def _write_valid_session(path: Path, content_name: str = "test_session") -> None:
    data = {
        "content_name": content_name,
        "topic": "Test Topic",
        "videos": [
            {
                "index": 1,
                "title": "Test Class 1",
                "url": "https://example.com/video-1",
            }
        ],
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_load_session_config_accepts_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "session.yaml"
    _write_valid_session(config_path, content_name="yaml_ok")

    session = load_session_config(config_path)

    assert session.content_name == "yaml_ok"
    assert len(session.videos) == 1
    assert session.videos[0].index == 1


def test_load_session_config_accepts_yml(tmp_path: Path) -> None:
    config_path = tmp_path / "session.yml"
    _write_valid_session(config_path, content_name="yml_ok")

    session = load_session_config(config_path)

    assert session.content_name == "yml_ok"
    assert session.videos[0].title == "Test Class 1"
