"""Small script to manually test OpenAI text generation.

Usage (from project root):

    python -m scripts.openai_chat_demo

It uses configuration from ``learning_session_transcriber.config.Config``.
"""

from __future__ import annotations

from typing import NoReturn

from openai import OpenAI

from learning_session_transcriber.config import (
    DEFAULT_OPENAI_MODEL,
    Config,
)


def main() -> NoReturn:
    cfg = Config.from_env()
    if not cfg.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is not configured (OS env or .env).")

    client = OpenAI(api_key=cfg.openai_api_key)
    model = cfg.openai_model or DEFAULT_OPENAI_MODEL

    print(f"Using model: {model}")

    instructions = "You are a very concise assistant. Respond in English."
    prompt = (
        "Write a 3-line summary about the importance of teachers "
        "in mathematics education."
    )
    if model.lower().startswith("gpt-6"):
        response = client.responses.create(
            model=model,
            instructions=instructions,
            input=prompt,
            reasoning={"effort": cfg.openai_reasoning_effort},
            max_output_tokens=300,
        )
        content = response.output_text or ""
    else:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=300,
            temperature=0.3,
        )
        content = response.choices[0].message.content or ""
    print("\n--- Model response ---\n")
    print(content.strip())


if __name__ == "__main__":
    main()
