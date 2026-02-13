"""Small script to manually test the OpenAI audio transcription API.

Usage (from project root):

    python -m scripts.openai_audio_transcription_demo path/to/audio_or_video.mp4

The file should contain spoken audio (e.g. a short clip). The script uses
configuration from ``learning_session_transcriber.config.Config``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import NoReturn

from openai import OpenAI

from learning_session_transcriber.config import Config


def main() -> NoReturn:
    if len(sys.argv) < 2:
        raise SystemExit(
            "Usage: python -m scripts.openai_audio_transcription_demo path/to/file.mp4"
        )

    audio_path = Path(sys.argv[1])
    if not audio_path.is_file():
        raise SystemExit(f"File not found: {audio_path}")

    cfg = Config.from_env()
    if not cfg.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is not configured (OS env or .env).")

    client = OpenAI(api_key=cfg.openai_api_key)

    model = cfg.openai_transcription_model
    print(f"Using transcription model: {model}")
    print(f"Transcribing file: {audio_path}")

    with audio_path.open("rb") as f:
        response = client.audio.transcriptions.create(
            model=model,
            file=f,
            response_format="text",
            language="es",
        )

    text = str(response)

    print("\n--- Transcripción ---\n")
    print(text.strip())


if __name__ == "__main__":
    main()

