---
name: project-install
description: Install and configure learning-session-transcriber. Use when the user asks to install, set up, or configure the project, its Python dependencies, ffmpeg, yt-dlp, or the local .env file.
---

# Install Project

Install dependencies and local config. Work from the repo root. Do not print `OPENAI_API_KEY`. Do not commit `.env`.

## Python

Create `.venv` when it is missing, then install into it:

```bash
python3 -m venv .venv
```

```bash
pip install -r requirements.txt
```

```bash
pip install -e ".[dev]"
```

Use that virtualenv for the remaining checks. On Windows the activate script is `.venv\Scripts\activate`.

## Binaries

The downloader calls `ffmpeg` and `yt-dlp` on `PATH`.

- `yt-dlp` comes from `requirements.txt`. Confirm `yt-dlp --version` works in the virtualenv.
- `ffmpeg` is not a Python package. If it is missing, install it with the platform package manager (`brew install ffmpeg` on macOS).

## Environment

If `.env` is missing, copy `env.example` to `.env`. If `.env` already exists, leave it.

`OPENAI_API_KEY` must be set in the OS environment. `env.example` references it as `${OPENAI_API_KEY}` and does not store a key. Confirm the variable is set without printing its value. Leave `OPENAI_MODEL`, `OPENAI_REASONING_EFFORT`, and `OPENAI_TRANSCRIPTION_MODEL` as copied unless the user asks to change them.

## Finish

Run `pytest`. Skip `pytest -m integration`.

Report whether the virtualenv, `ffmpeg`, `yt-dlp`, and `OPENAI_API_KEY` are present. Name anything still missing.
