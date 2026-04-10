# AGENTS.md

Repository guide for AI agents working on `learning-session-transcriber`.

Keep changes small, explicit, and aligned with the existing KISS pipeline.

## Purpose

Use lightweight Spec Driven Development (SDD) practices for this repo:

1. Understand existing behavior first.
2. Define scope for non-trivial changes.
3. Implement with minimal impact.
4. Verify with relevant tests.
5. Update docs only when behavior changes.

This is a minimal SDD layer for agent consistency, not a full process framework.

## Source Of Truth

Read these in this order:

1. `ARCHITECTURE.md`
2. `README.md`
3. `src/learning_session_transcriber/run_session.py`
4. `src/learning_session_transcriber/manifest.py`
5. `tests/test_manifest_consumers.py`
6. `pyproject.toml`

If docs and code disagree, follow code and update docs in the same change.

## Repo Commands

- Install deps: `pip install -r requirements.txt`
- Install editable dev package: `pip install -e ".[dev]"`
- Run pipeline: `python -m learning_session_transcriber.run_session --config sessions/<content_name>/session.yaml`
- Preferred CLI (after install): `learning-session-transcriber --config sessions/<content_name>/session.yaml`
- Run unit tests: `pytest`
- Run integration tests only when explicitly needed: `pytest -m integration`

Do not assume `python -m learning_session_transcriber` works unless `__main__.py` is aligned with `run_session.main`.

## Architecture Constraints

- `manifest.json` is the contract between pipeline steps.
- Keep output layout flat in `outputs/<content_name>/`.
- Preserve resumable and idempotent behavior where possible.
- `sessions/` and `outputs/` are user data and are gitignored.
- External runtime dependencies matter for behavior:
  - `ffmpeg`
  - `yt-dlp`
  - `OPENAI_API_KEY` (for OpenAI-backed paths)

## Lightweight SDD Rules

Use no extra SDD artifact for:
- small bug fixes
- small refactors
- straightforward doc updates

Use a tiny `spec.md` and `plan.md` (temporary or in PR notes) for:
- changes touching multiple pipeline stages
- changes to manifest schema/contract
- changes with testing strategy tradeoffs

Keep those artifacts short and focused on:
- what changes
- why it changes
- how to verify

## Testing And Verification

- Prefer fast offline tests first.
- Avoid network/OpenAI-dependent tests by default.
- If changing manifest producers/consumers, run tests that cover both sides.
- If behavior changes, update `README.md` or `ARCHITECTURE.md` (not both unless needed).

## Custom Skill

For repeated pipeline-maintenance tasks, use:
- `.agents/skills/session-pipeline-maintenance/SKILL.md`

If the skill is unavailable, follow this file directly.
