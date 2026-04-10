---
name: session-pipeline-maintenance
description: Maintain the learning session pipeline safely across manifest producers and consumers. Use when editing downloader, transcriber, synthesizer, prompts, run_session orchestration, or manifest schema/paths, and when deciding whether a lightweight spec-first step is needed.
---

# Session Pipeline Maintenance

## Goal

Make safe, minimal changes to the pipeline while preserving:
- manifest contract integrity
- flat output layout in `outputs/<content_name>/`
- resumable/idempotent behavior

## Read First

1. `AGENTS.md`
2. `ARCHITECTURE.md`
3. `src/learning_session_transcriber/run_session.py`
4. `src/learning_session_transcriber/manifest.py`
5. `tests/test_manifest_consumers.py`
6. `README.md` (only sections relevant to your change)

## When To Use Lightweight SDD

Skip extra artifacts for:
- small bug fixes
- local refactors
- focused tests/docs edits

Create a tiny spec/plan note before coding when:
- touching multiple pipeline modules
- changing manifest fields or artifact paths
- introducing behavior with test strategy tradeoffs

Use this short template:

```markdown
## spec
- what changes
- why it changes
- out of scope

## plan
- files to update
- compatibility/rollback notes
- verification steps
```

## Safe Change Checklist

1. Identify whether the change is a manifest producer, consumer, or both.
2. Keep filenames and path conventions stable unless explicitly changing them.
3. If schema or field semantics change, update all affected readers/writers.
4. Keep CLI behavior consistent with `run_session.py` and documented commands.
5. Update docs only where behavior changed; avoid duplicating architecture docs.

## Verification

- Run `pytest` for fast validation.
- Run targeted tests for touched areas, especially `tests/test_manifest_consumers.py`.
- Run integration tests only when explicitly needed: `pytest -m integration`.
- If commands/flows changed, update `AGENTS.md` and relevant `README.md` section.

## Boundaries

- Do not treat `sessions/` or `outputs/` as versioned source code.
- Do not introduce process-heavy SDD scaffolding by default.
- Prefer small, reviewable diffs with clear intent.
