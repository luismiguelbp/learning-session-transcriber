"""CLI orchestrator for running a full session pipeline."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import List

from .config import Config
from .downloader import download_videos
from .extract_pdf import extract_pdf_text
from .prompts import apply_prompts
from .sessions import load_session_config
from .synthesizer import build_main_document
from .transcriber import transcribe_videos

logger = logging.getLogger(__name__)


ALL_STEPS = ["download", "transcribe", "synthesize", "prompts"]


def run_session(config_path: Path, steps: List[str] | None = None) -> None:
    """Run the requested pipeline steps for a session."""

    if steps is None or not steps:
        steps = list(ALL_STEPS)

    # Validate config early.
    session = load_session_config(config_path)
    logger.info("Running session %s", session.content_name)

    norm_steps = [step.strip().lower() for step in steps]

    if "download" in norm_steps:
        download_videos(config_path)

    if "transcribe" in norm_steps:
        transcribe_videos(config_path)

    if "pdf" in norm_steps:
        try:
            extract_pdf_text(config_path)
        except ValueError as e:
            logger.warning("Skipping PDF extraction: %s", e)

    if "synthesize" in norm_steps:
        try:
            build_main_document(config_path)
        except (FileNotFoundError, ValueError) as e:
            logger.warning("Skipping synthesis: %s", e)

    if "prompts" in norm_steps:
        apply_prompts(config_path)

    logger.info("Completed steps: %s", ", ".join(norm_steps))


def main(args: List[str] | None = None) -> None:  # pragma: no cover - thin wrapper
    import argparse

    # Setup logging before anything else.
    config = Config.from_env()
    level = getattr(logging, config.log_level, logging.INFO)
    # Use force=True if available (Python 3.8+), otherwise just configure normally
    try:
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            stream=sys.stdout,
            force=True,
        )
    except TypeError:
        # Python < 3.8 doesn't support force parameter
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            stream=sys.stdout,
        )
    
    # Get logger after setup - also print to ensure output is visible
    print("Starting session pipeline", flush=True)
    logger.info("Starting session pipeline")

    parser = argparse.ArgumentParser(
        description="Run the video session transcription and synthesis pipeline."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to session.yaml file.",
    )
    parser.add_argument(
        "--steps",
        default="download,transcribe,synthesize,prompts",
        help=(
            "Comma‑separated list of steps to run. "
            "Available: download,transcribe,synthesize,prompts. "
            "Default: download,transcribe,synthesize,prompts."
        ),
    )
    parsed = parser.parse_args(args=args)

    try:
        steps = [s for s in parsed.steps.split(",") if s.strip()]
        run_session(Path(parsed.config), steps)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception("Failed to run session pipeline: %s", e)
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

