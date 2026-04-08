"""PDF extraction step.

This step expects that the user has manually copied the related PDF file
into the same folder as ``session.yaml`` and referenced it via
``pdf.path`` in the config.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from pypdf import PdfReader

from .manifest import add_manifest_file
from .sessions import SessionConfig, load_session_config

logger = logging.getLogger(__name__)


def extract_pdf_text(config_path: Path) -> Path:
    """Extract text from the session PDF into the outputs folder.

    Returns the path to the extracted text file.
    """

    session: SessionConfig = load_session_config(config_path)
    session_dir = config_path.parent

    if session.pdf is None:
        raise ValueError(
            "session.yaml does not define a 'pdf' section; cannot extract PDF text."
        )

    pdf_source = session_dir / session.pdf.path
    if not pdf_source.is_file():
        raise FileNotFoundError(f"PDF not found at {pdf_source}")

    pdf_output_dir = session.pdf_output_dir
    pdf_output_dir.mkdir(parents=True, exist_ok=True)

    # Flattened layout: write a single PDF text file into outputs_root.
    text_path = pdf_output_dir / f"{session.content_name}_pdf.txt"

    # Check if PDF text already exists - skip if it does
    if text_path.is_file():
        logger.info("Skipping PDF extraction: text file already exists at %s", text_path)
        add_manifest_file(session.outputs_root / "manifest.json", "pdf", text_path)
        return text_path

    logger.info("Extracting text from PDF %s -> %s", pdf_source, text_path)
    reader = PdfReader(str(pdf_source))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")

    with text_path.open("w", encoding="utf-8") as f:
        f.write("\n\n".join(parts))

    logger.info("Wrote extracted PDF text to %s", text_path)
    add_manifest_file(session.outputs_root / "manifest.json", "pdf", text_path)
    return text_path


def main(args: List[str] | None = None) -> None:  # pragma: no cover - thin wrapper
    import argparse

    parser = argparse.ArgumentParser(description="Extract text from a session PDF.")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to session YAML config file.",
    )
    parsed = parser.parse_args(args=args)
    extract_pdf_text(Path(parsed.config))


