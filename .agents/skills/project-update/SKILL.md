---
name: project-update
description: Update learning-session-transcriber dependencies. Use when the user asks to update or upgrade project packages, requirements.txt, pyproject.toml, ffmpeg, yt-dlp, the openai package, or OpenAI model references.
---

# Update Project

Update installed tools and the versions declared in this repo. Work from the repo root. Do not edit pipeline behavior, session files, or `.env`. Do not print `OPENAI_API_KEY`.

## Python packages

Read runtime dependencies from `requirements.txt` and `pyproject.toml`. They must stay the same set with the same version specifiers. Also update `[project.optional-dependencies].dev` and `[build-system].requires` in `pyproject.toml`.

For each package, find the latest release that still satisfies any existing upper bound. Raise the lower bound to that version. Keep the existing operator style and any upper bound.

Install from the repo root:

```bash
pip install -U -r requirements.txt
pip install -U -e ".[dev]"
```

## Binaries

The downloader calls `ffmpeg` and `yt-dlp` on `PATH`, not as Python modules.

- `ffmpeg`: upgrade it with the manager that installed it (`brew upgrade ffmpeg` when Homebrew owns it).
- `yt-dlp`: upgrade the pip package with the other Python dependencies, and upgrade the `PATH` binary when it comes from another manager.

Report the versions before and after: `ffmpeg -version`, `yt-dlp --version`.

## OpenAI references

Upgrade the `openai` package with the other Python dependencies.

If `OPENAI_API_KEY` is set, list models with:

```bash
python -m scripts.openai_list_models
```

Compare that list with model ids in:

- `DEFAULT_OPENAI_MODEL` and the `OPENAI_TRANSCRIPTION_MODEL` default in `src/learning_session_transcriber/config.py`
- `env.example`
- `README.md` and `ARCHITECTURE.md` where they name a default model

Leave an id unchanged when it is still listed. If an id is missing, report it and the nearest current model, and change it only after the user confirms. Do not change `llm_model` inside `sessions/`.

## Finish

Run `pytest`. Skip `pytest -m integration`.

Report each package and binary that changed, and any OpenAI model id that is no longer listed. Do not commit unless the user asks.
