"""KISS-style tests for the downloader step."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

import pytest
import yaml

from learning_session_transcriber import downloader


def _write_session_yaml(path: Path, content_name: str, url: str) -> None:
    data = {
        "content_name": content_name,
        "topic": "Test Topic",
        "videos": [
            {
                "index": 1,
                "title": "Test Class 1",
                "url": url,
            }
        ],
        "pdf": {"title": "Dummy PDF", "path": "dummy.pdf"},
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_download_videos_uses_url_and_writes_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Downloader should take a URL and create an mp4, mp3 plus manifest.json."""

    monkeypatch.chdir(tmp_path)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_test_downloader"

    session_dir = tmp_path / "sessions" / run_id
    session_dir.mkdir(parents=True, exist_ok=True)

    config_path = session_dir / "session.yaml"
    url = "https://example.com/video"
    _write_session_yaml(config_path, run_id, url)

    # Monkeypatch the internal yt-dlp helper so the test stays offline.
    def fake_download(url_arg: str, target_path: Path) -> None:  # type: ignore[no-redef]
        assert url_arg == url
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(b"dummy video data")

    monkeypatch.setattr(downloader, "_download_with_ytdlp", fake_download)

    # Monkeypatch audio extraction so the test does not require ffmpeg.
    def fake_extract_audio(src: Path, target_path: Path) -> None:  # type: ignore[no-redef]
        assert src.is_file()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(b"dummy audio data")

    monkeypatch.setattr(downloader, "_extract_audio", fake_extract_audio)

    manifest_path = downloader.download_videos(config_path)

    assert manifest_path.is_file()
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest_data) == 1

    entry = manifest_data[0]
    output_path = Path(entry["output_path"])
    assert output_path.is_file()
    assert output_path.read_bytes() == b"dummy video data"

    audio_path = Path(entry["audio_path"])
    assert audio_path.is_file()
    assert audio_path.read_bytes() == b"dummy audio data"


