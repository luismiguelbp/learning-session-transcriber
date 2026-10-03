---
name: project-test
description: Check learning-session-transcriber dependencies and run the test suite. Use when the user asks to test the project, run pytest, check packages, or verify ffmpeg, yt-dlp, and the OpenAI setup.
---

# Test Project

Check the installed tools and run the tests. Work from the repo root, using `.venv` when it exists. Do not print `OPENAI_API_KEY`. Do not edit code unless a test fails and the user asks for a fix.

## Packages

Confirm each runtime dependency in `requirements.txt` and each dev dependency in `pyproject.toml` imports in the active environment. Run `pip check`.

Confirm the binaries the downloader calls:

```bash
ffmpeg -version
yt-dlp --version
```

`OPENAI_API_KEY` is required only for live transcription and prompt calls. Report whether it is set. Do not print the value.

## Tests

Run the full suite:

```bash
pytest
```

`pytest` includes tests marked `integration`. `tests/test_transcriber.py` skips that test when `OPENAI_API_KEY` or `TEST_AUDIO_PATH` is unset. Treat that skip as a skip, not a failure.

Do not pass `-m integration` unless the user asks to run only those tests.

## Finish

Report `pip check`, the `ffmpeg` and `yt-dlp` versions, whether `OPENAI_API_KEY` is set, and the pytest summary including any skips. Quote the first failing test when the run fails.
