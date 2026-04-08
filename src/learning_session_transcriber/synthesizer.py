"""Main document synthesis step.

This step concatenates ordered transcripts into one main Markdown file for
the session. Extra material (e.g. slides, notes) is not appended here; use
include_resources in session config and prompts to attach it when running prompts.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from .manifest import add_manifest_file
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

    if not outputs_root.is_dir():
        raise FileNotFoundError(f"Outputs directory not found: {outputs_root}")

    # Collect transcripts in index order based on filename suffix.
    transcript_files = sorted(outputs_root.glob("*_transcript.md"))
    if not transcript_files:
        raise FileNotFoundError(f"No transcript files found in {outputs_root}")

    main_path = session.main_markdown_path
    main_path.parent.mkdir(parents=True, exist_ok=True)

    # Check if main document already exists - skip if it does
    if main_path.is_file():
        logger.info("Skipping synthesis: main document already exists at %s", main_path)
        add_manifest_file(session.outputs_root / "manifest.json", "main_doc", main_path)
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
    for transcript_file in sorted(transcript_files):
        # Extract index from filename prefix if possible.
        name = transcript_file.stem
        try:
            index_str, *_ = name.split("_", maxsplit=1)
            index_int = int(index_str)
        except Exception:
            index_int = None

        title = f"Video {index_int}" if index_int is not None else "Video"

        lines.append(f"## {title}")
        lines.append("")
        lines.append(_read_text(transcript_file))
        lines.append("")

    with main_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info("Wrote main document to %s", main_path)
    add_manifest_file(session.outputs_root / "manifest.json", "main_doc", main_path)
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


