"""KISS-style integration test for the transcription step."""

from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime

import pytest
import yaml

from learning_session_transcriber.transcriber import transcribe_videos


def _write_session_yaml(path: Path, content_name: str) -> None:
    data = {
        "content_name": content_name,
        "topic": "Test Topic",
        "language": "es",
        "videos": [
            {
                "index": 1,
                "title": "Test Class 1",
                "url": "https://example.com/video",
            }
        ],
        "pdf": {"title": "Dummy PDF", "path": "dummy.pdf"},
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


@pytest.mark.integration
def test_transcribe_videos_with_openai_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide a path to an mp4 file and call the real OpenAI API.

    If `OPENAI_API_KEY` is not configured, the test is skipped so it can
    be enabled only in environments where the API is available.
    """

    if "OPENAI_API_KEY" not in os.environ:
        pytest.skip("OPENAI_API_KEY not set; skipping OpenAI integration test")

    audio_path_env = os.getenv("TEST_AUDIO_PATH")
    if not audio_path_env:
        pytest.skip("TEST_AUDIO_PATH not set; skipping OpenAI integration test")

    audio_path = Path(audio_path_env)
    if not audio_path.is_file():
        pytest.skip(f"TEST_AUDIO_PATH does not point to a file: {audio_path}")

    monkeypatch.chdir(tmp_path)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_test_transcriber"

    session_dir = tmp_path / "sessions" / run_id
    session_dir.mkdir(parents=True, exist_ok=True)

    config_path = session_dir / "session.yaml"
    _write_session_yaml(config_path, run_id)

    outputs_root = tmp_path / "outputs" / run_id

    manifest = [
        {
            "index": 1,
            "title": "Test Class 1",
            "url": "https://example.com/video",
            "local_source": str(audio_path),
            "output_path": str(audio_path),
            "audio_path": str(audio_path),
        }
    ]
    manifest_path = outputs_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    transcribe_videos(config_path)

    files = list(outputs_root.glob("*_transcript.md"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert content.strip(), "Transcript file should not be empty"


