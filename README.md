# Learning Session Transcriber

Simple, KISS-style tool to help you download/collect learning session videos, transcribe them with the OpenAI API, and organise the outputs (videos, transcripts, prompts) by session.

Everything is file-based and explicit: you describe a session in a `session.yaml`, then run small, focused steps.

---

## Project layout

- `src/learning_session_transcriber/`
  - `config.py` – env-based configuration (OpenAI models, log level, etc.).
  - `sessions.py` – `SessionConfig` models and `session.yaml` loader/validation.
  - `run_session.py` – high-level pipeline entry point that orchestrates all steps for a session.
  - `downloader.py` – video acquisition step (copy local files or download via `yt-dlp`).
  - `transcriber.py` – transcription step using OpenAI audio transcription.
  - `extract_pdf.py` – optional PDF extraction step for attaching PDF content to prompts.
  - `synthesizer.py` – builds the combined main document from per-video transcripts.
  - `prompts.py` – applies per-video and main-document prompts defined in `prompts.yaml`.
  - `manifest.py` – manages `manifest.json` tracking all generated artifacts.
  - `audio_joiner.py` – standalone module to convert WAV to MP3 and join session audio with silence gaps and ID3 metadata.
- `tests/` – pytest tests
  - `test_config.py` – unit tests for `Config.from_env`.
  - `test_downloader.py` – offline test for the downloader.
  - `test_transcriber.py` – integration test for OpenAI transcription (opt‑in).
  - `tests/__init__.py` – test package marker.
- `scripts/`
  - `openai_chat_demo.py` – manual script to test OpenAI chat.
  - `openai_audio_transcription_demo.py` – manual script to test audio transcription.
- `pyproject.toml` – project metadata and tool config.
- `requirements.txt` – pinned dependencies (mirrors `pyproject.toml`).
- `env.example` – example env vars (copy to `.env`).

---

## Installation and setup

1. **Create and activate a virtual environment**

   Unix/macOS:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   Windows:
   ```bash
   py -m venv .venv
   .venv\Scripts\activate
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   pip install -e ".[dev]"
   ```

3. **Configure environment variables**

   Copy the example file and edit it:

   ```bash
   cp env.example .env
   ```

   The important variables are:

   - `APP_ENV` – e.g. `development`, `production`. Defaults to `development`.
   - `LOG_LEVEL` – e.g. `INFO`, `DEBUG`. Defaults to `INFO` (uppercased by code).
   - `OPENAI_API_KEY` – your OpenAI API key.
   - `OPENAI_MODEL` – chat model (e.g. `gpt-5-mini` by default, or another `gpt-5.x` model).
   - `OPENAI_TRANSCRIPTION_MODEL` – audio transcription model (e.g. `gpt-4o-transcribe`).

   The `Config` class in `config.py` reads from the OS environment and `.env` (via `python-dotenv`) without overwriting existing OS variables.

---

## Defining a learning session

Each learning session is described in a configuration file (YAML or CSV), typically under:

- `sessions/<content_name>/session.yaml` or `sessions/<content_name>/session.csv`

Where `content_name` follows the pattern:

- `YYYYMMDD_HHmmss_session-topic`

**Example:**

- Content name: `YYYYMMDD_HHmmss_session-topic`
- Folder: `sessions/YYYYMMDD_HHmmss_session-topic/`
- Config file: `sessions/YYYYMMDD_HHmmss_session-topic/session.yaml` or `sessions/YYYYMMDD_HHmmss_session-topic/session.csv`

### YAML Format

See `session.example.yaml` for a complete, up‑to‑date example including:

- Basic fields (`content_name`, `topic`, `language`, `llm_model`).
- Optional `prompts_file` (path relative to session directory) to specify which prompts YAML file to use; if omitted, defaults to `prompts.yaml` at project root.
- `videos` list with `index`, `title`, `url` (and optional `local_path`).
- Optional `postprocess_prompts` per video (a list) to choose one or more per‑video prompts from the prompts file.
- Optional `main_postprocess_prompts` (a list) to choose one or more main‑document prompts from the prompts file.
- Optional `include_resources` (key → path, relative to session directory) to attach extra material (e.g. slides, notes) to prompts.

### CSV Format

Alternatively, you can use CSV format with semicolon (`;`) delimiter. See `session.example.csv` for a complete example.

The CSV format uses three columns: `index`, `field`, `value`:

- Rows with `index=0` (or empty) represent session-level metadata (e.g., `content_name`, `topic`, `language`, `llm_model`, `main_postprocess_prompts`).
- Rows with `index>=1` represent video entries. Each video must include an `index` field, plus fields like `title`, `url`, `local_path`, `postprocess_prompts`.

**Notes:**
- List fields (`postprocess_prompts`, `main_postprocess_prompts`) can use comma-separated values in the `value` column (e.g., `summary,key_concepts`).
- Empty `index` values are treated as `0` (session metadata).
- All fields supported in YAML format are also supported in CSV format.

The `SessionConfig` model in `sessions.py` validates this structure and exposes helper properties such as:

- `outputs_root` – `outputs/<content_name>/` (all artifacts for a session live here in a flattened layout)

---

## Workflow: from `session.yaml` to transcripts

### 1. Download or collect videos

The downloader reads your `session.yaml`, then:

- Copies local files when `local_path` is provided, or
- Uses `yt-dlp` to download from `url`.

For each video it:

- Writes an `.mp4` file into `outputs/<content_name>/` named:
  - `<content_name>_index_<n>_video.mp4`
- Extracts an `.mp3` audio file from that video using `ffmpeg`, named:
  - `<content_name>_index_<n>_audio.mp3`
- Records both paths in a `manifest.json` at `outputs/<content_name>/manifest.json`:
  - `output_path` – path to the `.mp4` video.
  - `audio_path` – path to the extracted `.mp3` audio (preferred for transcription).

You normally do not need to call the downloader directly; instead, use the unified pipeline entry point described below. For advanced/manual usage you can still run:

```bash
python -m learning_session_transcriber.downloader --config sessions/YYYYMMDD_HHmmss_session-topic/session.yaml
```

### 2. Transcribe videos with OpenAI

The transcriber:

- Loads the same `session.yaml`.
- Reads `manifest.json` produced by the downloader.
- For each entry, prefers the extracted `.mp3` in `audio_path` (falling back to `output_path`).
- Splits long audio files into sequential chunks using `ffmpeg` so they respect the model’s
  maximum duration per request.
- Calls the OpenAI audio transcription API for each chunk and concatenates the partial
  transcripts.
- Writes Markdown transcripts directly into `outputs/<content_name>/` with filenames:
  - `<content_name>_index_<n>_transcript.md`

Again, the recommended way is to use the unified pipeline. For manual control you can run:

```bash
python -m learning_session_transcriber.transcriber --config sessions/YYYYMMDD_HHmmss_session-topic/session.yaml
```

Internally, this calls `transcribe_videos(config_path: Path)`, which uses:

- `Config.from_env()` to obtain the transcription model.
- An `OpenAI` client (with `OPENAI_API_KEY` from env).
- `ffmpeg` to split audio into smaller chunks when needed.

---

### 3. (Optional) Post‑process transcripts and main document

If you configure `postprocess_prompts` per video and/or `main_postprocess_prompts` in your `session.yaml`, you can run an additional step that applies prompt templates defined in your prompts file (default: `prompts.yaml` at project root, or the file specified by `prompts_file` in your session):

- `per_video:` prompts are used for individual transcripts (e.g. `summary`, `key_concepts`).
- `main_document:` prompts are used for the combined main document (e.g. `study_guide`, `executive_summary`).

Run the prompt application step:

```bash
python -m learning_session_transcriber.prompts --config sessions/YYYYMMDD_HHmmss_session-topic/session.yaml
```

For each video where `postprocess_prompts` contains one or more prompt names, this will:

- For each prompt name, append a `## Postprocess: <prompt_name>` section to `<content_name>_index_<n>_transcript.md`.
- Write sibling files `<content_name>_index_<n>_<prompt_name>.md` in `outputs/<content_name>/`.

If `main_postprocess_prompts` is set and the main document already exists, it will:

- For each prompt name, append a `## Postprocess: <prompt_name>` section to `<content_name>_main.md`.
- Write sibling files `<content_name>_main_<prompt_name>.md` in `outputs/<content_name>/`.

---

## Unified pipeline (`run_session`)

For most use cases you will want to run the whole pipeline for a session with a single command:

```bash
python -m learning_session_transcriber.run_session --config sessions/<content_name>/session.yaml
```

Or with CSV format:

```bash
python -m learning_session_transcriber.run_session --config sessions/<content_name>/session.csv
```

Or, after installing the package (e.g. `pip install -e .`), via the console script:

```bash
learning-session-transcriber --config sessions/<content_name>/session.yaml
# or
learning-session-transcriber --config sessions/<content_name>/session.csv
```

This will, in order:

- Download or copy videos according to your `session.yaml`.
- Transcribe audio into per-video transcripts.
- Optionally extract PDFs if configured.
- Synthesize a main document from all transcripts.
- Apply any configured per-video and main-document prompts.

Steps can be selectively enabled/disabled via command-line arguments; see the module docstring in `run_session.py` for details.

---

## Audio joiner (standalone)

The **audio joiner** is a separate module for folders that contain only audio files (WAV or MP3). It does not use `session.yaml`; it uses its own `audio_metadata.yaml` in the session folder.

**Use case:** You have a folder of numbered WAV (or MP3) files and want to convert WAVs to MP3, then join all MP3s into a single file with a configurable silence gap between segments and ID3v1 metadata.

1. Create a folder under `sessions/` (e.g. `sessions/MyAudioSession/`).
2. Put your WAV and/or MP3 files in that folder (any names; they are processed in alphabetical order).
3. Copy `audio_metadata.example.yaml` into the folder as `audio_metadata.yaml` and edit:
   - `silence_gap_seconds` – seconds of silence between each segment.
   - `output_filename` – name of the final joined file (see template variables below).
   - `per_file` – ID3v1 tags applied to each individual MP3 when converting WAV to MP3.
   - `joined` – ID3v1 tags applied to the final joined MP3.

   **Template variables** (resolved at runtime via Python `str.format()`):
   - **per_file** section: `{index}` (1-based position), `{filename}` (original filename without extension), `{session_name}` (folder name).
   - **joined** section and **output_filename**: `{session_name}` (folder name), `{total_files}` (number of audio files).

4. Run:

```bash
python -m learning_session_transcriber.audio_joiner --session sessions/MyAudioSession/
```

Output is written to `outputs/MyAudioSession/`: converted/copied per-file MP3s and one joined MP3. Requires `ffmpeg` on your PATH.

---

## Repository and generated data

- The `sessions/` and `outputs/` directories are treated as **user data** (per-session configs and generated artifacts) and are ignored by git via `.gitignore`.
- The canonical configuration and documentation files tracked in the repository are:
  - `session.example.yaml` – template for new session configs.
  - `audio_metadata.example.yaml` – template for audio joiner metadata (ID3 and silence gap).
  - `env.example` – template for environment variables.
  - `prompts.yaml` – shared prompt definitions.
  - `README.md` – this documentation.

---

## Manual OpenAI smoke tests (`scripts/`)

You can quickly verify OpenAI connectivity and models using the small scripts in `scripts/`.

- **Chat demo**

  ```bash
  python -m scripts.openai_chat_demo
  ```

  Uses `OPENAI_API_KEY` and `OPENAI_MODEL` to send a short prompt (in Spanish) and print the response.

- **Audio transcription demo**

  ```bash
  python -m scripts.openai_audio_transcription_demo path/to/audio_or_video.mp4
  ```

  Uses `OPENAI_TRANSCRIPTION_MODEL` to transcribe a single file and print the text.

These scripts are **for manual testing only** and are not part of the automated pytest suite.

---

## Running tests

- **Unit tests (fast, CI‑friendly):**

  ```bash
  pytest
  ```

  This runs tests in `tests/` such as:

  - `test_config.py` – configuration defaults and custom env handling.
  - `test_downloader.py` – downloader behaviour using a fake `yt-dlp`.

- **Coverage:**

  ```bash
  pytest --cov=src/learning_session_transcriber
  ```

- **OpenAI integration test (optional):**

  `tests/test_transcriber.py` is marked as an integration test and:

  - Skips automatically when `OPENAI_API_KEY` is not set.
  - Calls the real OpenAI transcription API with a small dummy video file.

  To run only integration tests, set your key and use a marker, for example:

  ```bash
  export OPENAI_API_KEY=sk-...
  pytest -m integration
  ```

  (You can further customise markers in `pytest.ini` if needed.)

---

## Design principles

- **KISS**: prefer simple, explicit steps and file structures over heavy frameworks.
- **Layered**: keep configuration, session description, downloading, and transcription separated.
- **Config via env**: `Config.from_env()` is the single source of truth; no secrets in code.
- **Testable**: downloader is testable without network; OpenAI integration is opt‑in and clearly marked.
- **Scriptable**: small `python -m ...` entry points instead of complex CLIs, so you can compose steps however you like.

