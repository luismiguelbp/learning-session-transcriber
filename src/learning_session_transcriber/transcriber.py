"""Transcription step using the OpenAI API.

Reads ``manifest.json`` written by :mod:`downloader` and produces
Markdown transcript files under::

    outputs/<content_name>/transcripts/

Each transcript file is named based on the session ``content_name`` and
video index, e.g.::

    <content_name>_index_<n>_transcript.md
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from openai import OpenAI

from .config import Config
from .manifest import add_manifest_file, sync_manifest_with_session
from .sessions import SessionConfig, load_session_config

logger = logging.getLogger(__name__)

def _get_client() -> OpenAI:
    cfg = Config.from_env()
    if cfg.openai_api_key:
        return OpenAI(api_key=cfg.openai_api_key)
    return OpenAI()


def _get_transcription_model() -> str:
    cfg = Config.from_env()
    return cfg.openai_transcription_model


def _split_audio_into_chunks(audio_path: Path, max_chunk_seconds: int = 1300) -> list[Path]:
    """Split an audio file into sequential chunks using ffmpeg.

    Returns a list of created chunk paths, in order.
    """

    # Chunks will live in a temporary directory next to the source file.
    tmp_dir = Path(
        tempfile.mkdtemp(prefix=f"{audio_path.stem}_chunks_", dir=str(audio_path.parent))
    )
    pattern = tmp_dir / "chunk_%03d.mp3"

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(audio_path),
        "-acodec",
        "copy",
        "-f",
        "segment",
        "-segment_time",
        str(max_chunk_seconds),
        "-reset_timestamps",
        "1",
        str(pattern),
    ]

    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed to split audio {audio_path} (exit {result.returncode})")

    chunks = sorted(tmp_dir.glob("chunk_*.mp3"))
    if not chunks:
        raise RuntimeError(f"ffmpeg did not produce any chunks for {audio_path}")

    return chunks


def _transcribe_file(client: OpenAI, model: str, audio_path: Path, language: str) -> str:
    """Transcribe a single audio file and return the text."""

    with audio_path.open("rb") as f:
        response = client.audio.transcriptions.create(
            model=model,
            file=f,
            response_format="text",
            language=language,
        )
    return str(response)


def transcribe_videos(config_path: Path, client: Optional[OpenAI] = None) -> None:
    """Main transcription routine."""

    session: SessionConfig = load_session_config(config_path)
    transcripts_dir = session.transcripts_output_dir
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = session.outputs_root / "manifest.json"
    manifest = sync_manifest_with_session(manifest_path, session)
    manifest_entries = manifest["videos"]

    if client is None:
        client = _get_client()
    model = _get_transcription_model()

    for entry in manifest_entries:
        index = int(entry["index"])

        # Prefer extracted audio if available; fall back to the original output_path.
        audio_str = entry.get("audio_path") or entry.get("output_path")
        if not audio_str:
            raise ValueError(f"Manifest entry for index {index} lacks audio/output path")

        audio_path = Path(audio_str)
        if not audio_path.is_file():
            raise FileNotFoundError(f"Audio for transcription not found: {audio_path}")

        transcript_path = transcripts_dir / f"{session.content_name}_index_{index}_transcript.md"
        
        # Check if transcript already exists - skip if it does
        if transcript_path.is_file():
            logger.info("Skipping transcription for video %d: transcript already exists at %s", index, transcript_path)
            add_manifest_file(manifest_path, "transcript", transcript_path, index)
            continue

        logger.info("Transcribing %s -> %s", audio_path, transcript_path)

        # Split long audio into chunks that respect the model's duration limit.
        # We always use the chunking helper; short files will just produce a single chunk.
        chunks: list[Path] = []
        try:
            chunks = _split_audio_into_chunks(audio_path)
            parts: list[str] = []
            for idx, chunk in enumerate(chunks, start=1):
                logger.info("Transcribing chunk %s (%d/%d)", chunk, idx, len(chunks))
                chunk_text = _transcribe_file(client, model, chunk, session.language)
                parts.append(chunk_text)
            text = "\n\n".join(parts)
        finally:
            # Clean up temporary chunk files and directories.
            for chunk in chunks:
                try:
                    chunk.unlink()
                except FileNotFoundError:
                    pass
            if chunks:
                try:
                    chunks[0].parent.rmdir()
                except OSError:
                    # Directory not empty or already removed; ignore.
                    pass
        # Write raw transcription text only; metadata for this video already lives
        # in ``session.yaml`` and ``manifest.json`` and does not need to be
        # embedded as a header in the transcript file itself.
        with transcript_path.open("w", encoding="utf-8") as out:
            out.write(text)

        logger.info("Wrote transcript to %s", transcript_path)
        add_manifest_file(manifest_path, "transcript", transcript_path, index)


def main(args: List[str] | None = None) -> None:  # pragma: no cover - thin wrapper
    import argparse

    parser = argparse.ArgumentParser(description="Transcribe session videos.")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to session YAML config file.",
    )
    parsed = parser.parse_args(args=args)
    transcribe_videos(Path(parsed.config))


