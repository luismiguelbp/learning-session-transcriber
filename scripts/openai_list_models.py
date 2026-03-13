"""Small script to list available OpenAI models for this API key.

Usage (from project root):

    python -m scripts.openai_list_models

It uses configuration from ``learning_session_transcriber.config.Config``.
"""

from __future__ import annotations

from typing import NoReturn

from openai import OpenAI

from learning_session_transcriber.config import Config


def main() -> NoReturn:
    cfg = Config.from_env()
    if not cfg.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is not configured (OS env or .env).")

    client = OpenAI(api_key=cfg.openai_api_key)

    print("Fetching models from OpenAI...")
    response = client.models.list()

    models = sorted((model.id for model in response.data), key=str)

    print("\n--- Available models ---\n")
    for model_id in models:
        print(model_id)


if __name__ == "__main__":
    main()

