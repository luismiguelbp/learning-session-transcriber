---
name: session-run
description: Run a learning-session-transcriber session from a session name or a path to a session folder or session.yaml. Use when the user asks to run, execute, resume, or re-run a session, a content_name under sessions/, or the learning session pipeline. Check the session name, video URLs, and PDF before starting.
---

# Run Session

Execute an existing session. Do not edit pipeline code.

## Parameter

Require one argument: a session name or a session path.

- Session name: the folder under `sessions/`, which is also `content_name`. Resolve it to `sessions/<name>/session.yaml`. A fragment such as `Tema30` is fine when exactly one folder contains it.
- Session path: a path to that folder, or to its `session.yaml`. Use the path as given.

Work from the repo root. If the argument is missing or matches more than one session, stop and ask for one name or path. Do not pick a session yourself.

Stop if the folder has no `session.yaml`. Some folders under `sessions/` hold only `audio_metadata.yaml` and belong to the audio joiner, not this pipeline.

`command.md` in the session folder is a reminder only. Build the command from the resolved `session.yaml`. Do not edit the session files.

## Preflight

Read `session.yaml` and the prompts file it names. Stop before any command and name what is missing. Do not invent a name, a URL, or a PDF path, and do not move or write files to fill a gap.

The session must already have:

- `content_name`, matching the folder name
- a non-empty `url` (or `local_path`) on every video, and at least one video. An empty `url: ""` counts as missing
- `include_resources.pdf` pointing at a real `.pdf` file beside the session. Compare the path with the filesystem, not string equality; macOS may store a different Unicode form of the same filename

Also stop if:

- `prompts_file` is set and that file is missing beside the session
- a named prompt in `postprocess_prompts` or `main_postprocess_prompts` is absent from the prompts file

Confirm `ffmpeg` and `yt-dlp` are on `PATH` when the run includes `download`. Transcription and prompts need `OPENAI_API_KEY` in the environment or `.env`. Do not print the key.

Tell the user the content name, steps, and that the run calls OpenAI. Start only after they confirm.

## Run

From the repo root, one command:

```bash
learning-session-transcriber --config "sessions/<content_name>/session.yaml"
```

If that entry point is missing:

```bash
python -m learning_session_transcriber.run_session --config "sessions/<content_name>/session.yaml"
```

Default steps are `download,transcribe,synthesize,prompts`. Pass `--steps` only when the user asks for a subset. Valid names: `download`, `transcribe`, `pdf`, `synthesize`, `prompts`.

The pipeline is long and resumable. Existing videos, audio, transcripts, the main document, and prompt outputs are skipped. Do not delete `outputs/<content_name>/` unless the user explicitly asks to redo a step.

An online `url` is passed through to `yt-dlp`. If a download fails, stop and report that video. Do not rewrite the URL.

## After the run

Report the exit code and the files written under `outputs/<content_name>/`. On failure, quote the error and name the step. Do not commit `sessions/` or `outputs/`.
