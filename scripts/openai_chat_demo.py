"""Small script to manually test the OpenAI chat API.

Usage (from project root):

    python -m scripts.openai_chat_demo

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

    print(f"Using chat model: {cfg.openai_model}")

    response = client.chat.completions.create(
        model=cfg.openai_model,
        messages=[
            {
                "role": "system",
                "content": "You are a very concise assistant. Respond in English.",
            },
            {
                "role": "user",
                "content": (
                    "Write a 3-line summary about the importance of teachers "
                    "in mathematics education."
                ),
            },
        ],
        max_completion_tokens=300,
        temperature=0.3,
    )

    content = response.choices[0].message.content or ""
    print("\n--- Model response ---\n")
    print(content.strip())


if __name__ == "__main__":
    main()

