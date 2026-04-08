"""Main document synthesis step.

This step concatenates ordered transcripts into one main Markdown file for
the session. Extra material (e.g. slides, notes) is not appended here; use
include_resources in session config and prompts to attach it when running prompts.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from .manifest import add_manifest_file, sync_manifest_with_session
from .sessions import SessionConfig, load_session_config

logger = logging.getLogger(__name__)


def _read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8") as f:
        return f.read()


def build_main_document(config_path: Path) -> Path:
    """Create the main combined Markdown document for a session.

    Returns the path to the created main document.
    """

    session: SessionConfig = load_session_config(config_path)
    outputs_root = session.outputs_root
    manifest_path = session.outputs_root / "manifest.json"

    if not outputs_root.is_dir():
        raise FileNotFoundError(f"Outputs directory not found: {outputs_root}")

    manifest = sync_manifest_with_session(manifest_path, session)
    video_entries = manifest["videos"]
    if not video_entries:
        raise FileNotFoundError(f"No video entries found in manifest at {manifest_path}")

    transcript_entries: list[dict] = []
    missing_indices: list[str] = []
    for entry in video_entries:
        transcript_str = entry.get("transcript_path")
        if not transcript_str:
            missing_indices.append(str(entry["index"]))
            continue

        transcript_path = Path(transcript_str)
        if not transcript_path.is_file():
            raise FileNotFoundError(
                f"Transcript listed in manifest for video {entry['index']} not found: "
                f"{transcript_path}"
            )
        transcript_entries.append({"entry": entry, "path": transcript_path})

    if missing_indices:
        joined = ", ".join(missing_indices)
        raise FileNotFoundError(
            f"Manifest is missing transcript_path for videos: {joined}. "
            "Run the transcription step first."
        )

    main_path = session.main_markdown_path
    main_path.parent.mkdir(parents=True, exist_ok=True)

    # Check if main document already exists - skip if it does
    if main_path.is_file():
        logger.info("Skipping synthesis: main document already exists at %s", main_path)
        add_manifest_file(manifest_path, "main_doc", main_path)
        return main_path

    logger.info("Building main document at %s", main_path)

    lines: list[str] = []
    lines.append(f"# {session.topic}")
    lines.append("")
    lines.append(f"- content_name: {session.content_name}")
    lines.append(f"- language: {session.language}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Section per video.
    for item in transcript_entries:
        entry = item["entry"]
        transcript_file = item["path"]
        title = (entry.get("title") or "").strip() or f"Video {entry['index']}"

        lines.append(f"## {title}")
        lines.append("")
        lines.append(_read_text(transcript_file))
        lines.append("")

    with main_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info("Wrote main document to %s", main_path)
    add_manifest_file(manifest_path, "main_doc", main_path)
    return main_path


def main(args: List[str] | None = None) -> None:  # pragma: no cover - thin wrapper
    import argparse

    parser = argparse.ArgumentParser(
        description="Compose the main markdown document for a session."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to session YAML config file.",
    )
    parsed = parser.parse_args(args=args)
    build_main_document(Path(parsed.config))


