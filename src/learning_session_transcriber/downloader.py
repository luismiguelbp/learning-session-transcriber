"""Video acquisition step.

Reads a ``session.yaml`` via :mod:`learning_session_transcriber.sessions`
and materialises local ``.mp4`` files under::

    outputs/<content_name>/videos/

For each video entry:

- If ``local_path`` is provided, the file is copied into the videos folder.
- Otherwise, ``yt-dlp`` is used to download the video from ``url``.

A ``manifest.json`` file is written to ``outputs/<content_name>/manifest.json``
with the resolved paths for later steps.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List

from .manifest import add_manifest_file, load_manifest, save_manifest
from .sessions import SessionConfig, VideoConfig, load_session_config

logger = logging.getLogger(__name__)


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _build_video_filename(session: SessionConfig, video: VideoConfig) -> str:
    """Build the output filename for a video.

    Filenames are based on the session content_name plus the video index, e.g.:

        <content_name>_index_<n>_video.mp4
    """
    return f"{session.content_name}_index_{video.index}_video.mp4"


def _download_with_ytdlp(url: str, target_path: Path) -> None:
    """Download a single video using yt-dlp."""
    logger.info("Downloading %s -> %s", url, target_path)
    cmd = [
        "yt-dlp",
        "--no-warnings",
        "--quiet",
        "--output",
        str(target_path),
        "--format",
        "mp4",
        url,
    ]
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed for {url} with code {result.returncode}")


def _copy_local_video(src: Path, target_path: Path) -> None:
    if not src.is_file():
        raise FileNotFoundError(f"Local video not found: {src}")
    logger.info("Copying local video %s -> %s", src, target_path)
    shutil.copy2(src, target_path)


def _extract_audio(video_path: Path, audio_path: Path) -> None:
    """Extract an MP3 audio track from a video using ffmpeg."""

    logger.info("Extracting audio %s -> %s", video_path, audio_path)
    cmd = [
        "ffmpeg",
        "-y",  # overwrite if exists
        "-i",
        str(video_path),
        "-vn",  # no video
        "-acodec",
        "libmp3lame",
        str(audio_path),
    ]
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0 or not audio_path.is_file():
        raise RuntimeError(
            f"ffmpeg failed to extract audio from {video_path} to {audio_path} "
            f"(exit code {result.returncode})"
        )


def download_videos(config_path: Path) -> Path:
    """Main entrypoint for the downloader step.

    Returns the path to the created ``manifest.json``.
    """

    session = load_session_config(config_path)
    videos_dir = session.videos_output_dir
    _ensure_dir(videos_dir)

    manifest_path = session.outputs_root / "manifest.json"
    manifest_entries = load_manifest(manifest_path)

    for video in session.videos:
        filename = _build_video_filename(session, video)
        target = videos_dir / filename

        # Name pattern: <content_name>_index_<n>_audio.mp3
        audio_path = target.with_name(
            f"{session.content_name}_index_{video.index}_audio.mp3"
        )

        # Check if files already exist - skip if both exist
        video_exists = target.is_file()
        audio_exists = audio_path.is_file()

        if video_exists and audio_exists:
            logger.info("Skipping video %d: files already exist (%s, %s)", video.index, target, audio_path)
        else:
            # Download or copy video if needed
            if not video_exists:
                if video.local_path:
                    _copy_local_video(Path(video.local_path), target)
                elif video.url:
                    _download_with_ytdlp(video.url, target)
                else:  # pragma: no cover - already validated
                    raise ValueError(
                        f"Video {video.index} has neither 'local_path' nor 'url' defined"
                    )
            else:
                logger.info("Video file already exists: %s", target)

            # Extract audio if needed
            if not audio_exists:
                _extract_audio(target, audio_path)
            else:
                logger.info("Audio file already exists: %s", audio_path)

        # Update manifest entry with all metadata
        entry_idx = None
        for idx, entry in enumerate(manifest_entries):
            if entry.get("index") == video.index:
                entry_idx = idx
                break
        
        if entry_idx is not None:
            manifest_entries[entry_idx].update({
                "title": video.title,
                "url": video.url or "",
                "local_source": video.local_path or "",
                "output_path": str(target),
                "audio_path": str(audio_path),
            })
        else:
            manifest_entries.append(
                {
                    "index": video.index,
                    "title": video.title,
                    "url": video.url or "",
                    "local_source": video.local_path or "",
                    "output_path": str(target),
                    "audio_path": str(audio_path),
                }
            )

    # Sort by index and save final manifest
    manifest_entries.sort(key=lambda e: e.get("index", 0))
    save_manifest(manifest_path, manifest_entries)
    return manifest_path


def main(args: List[str] | None = None) -> None:  # pragma: no cover - thin wrapper
    import argparse

    parser = argparse.ArgumentParser(description="Download or collect session videos.")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to session.yaml file.",
    )
    parsed = parser.parse_args(args=args)
    download_videos(Path(parsed.config))


