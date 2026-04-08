"""Tests for manifest-driven pipeline consumers."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from learning_session_transcriber.prompts import apply_prompts
from learning_session_transcriber.synthesizer import build_main_document


def _write_session_yaml(path: Path, content_name: str) -> None:
    data = {
        "content_name": content_name,
        "topic": "Manifest Driven Session",
        "language": "es",
        "videos": [
            {
                "index": 1,
                "title": "Primera parte",
                "url": "https://example.com/video-1",
                "postprocess_prompts": ["summary"],
            },
            {
                "index": 2,
                "title": "Segunda parte",
                "url": "https://example.com/video-2",
            },
        ],
        "main_postprocess_prompts": ["study_guide"],
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _write_prompts_yaml(path: Path) -> None:
    data = {
        "per_video": [
            {
                "name": "summary",
                "system_prompt": "Resume el contenido.",
                "temperature": 0.1,
                "max_tokens": 100,
            }
        ],
        "main_document": [
            {
                "name": "study_guide",
                "system_prompt": "Crea una guia de estudio.",
                "temperature": 0.1,
                "max_tokens": 100,
            }
        ],
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_build_main_document_uses_manifest_transcript_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    run_id = "20260408_120000_manifest_synth"
    session_dir = tmp_path / "sessions" / run_id
    session_dir.mkdir(parents=True, exist_ok=True)
    config_path = session_dir / "session.yaml"
    _write_session_yaml(config_path, run_id)

    outputs_root = tmp_path / "outputs" / run_id
    outputs_root.mkdir(parents=True, exist_ok=True)

    first_part = outputs_root / "part-a.md"
    second_part = outputs_root / "part-b.md"
    first_part.write_text("Contenido A", encoding="utf-8")
    second_part.write_text("Contenido B", encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "session": {
            "content_name": run_id,
            "topic": "Manifest Driven Session",
            "language": "es",
            "llm_model": "",
            "prompts_path": "prompts.yaml",
            "include_resources": {},
            "requested_main_prompts": ["study_guide"],
            "main_doc_path": None,
            "pdf_path": None,
            "prompt_outputs": [],
        },
        "videos": [
            {
                "index": 1,
                "title": "Primera parte",
                "url": "https://example.com/video-1",
                "local_source": "",
                "requested_prompts": ["summary"],
                "output_path": None,
                "audio_path": None,
                "transcript_path": str(first_part),
                "prompt_outputs": [],
            },
            {
                "index": 2,
                "title": "Segunda parte",
                "url": "https://example.com/video-2",
                "local_source": "",
                "requested_prompts": [],
                "output_path": None,
                "audio_path": None,
                "transcript_path": str(second_part),
                "prompt_outputs": [],
            },
        ],
    }
    (outputs_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    main_path = build_main_document(config_path)

    content = main_path.read_text(encoding="utf-8")
    assert "## Primera parte" in content
    assert "Contenido A" in content
    assert "## Segunda parte" in content
    assert "Contenido B" in content


def test_apply_prompts_uses_manifest_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    run_id = "20260408_120001_manifest_prompts"
    session_dir = tmp_path / "sessions" / run_id
    session_dir.mkdir(parents=True, exist_ok=True)
    config_path = session_dir / "session.yaml"
    _write_session_yaml(config_path, run_id)
    _write_prompts_yaml(tmp_path / "prompts.yaml")

    outputs_root = tmp_path / "outputs" / run_id
    outputs_root.mkdir(parents=True, exist_ok=True)

    transcript_source = outputs_root / "custom-transcript-source.md"
    main_doc_source = outputs_root / "custom-main-source.md"
    transcript_source.write_text("Transcripcion base", encoding="utf-8")
    main_doc_source.write_text("Documento principal", encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "session": {
            "content_name": run_id,
            "topic": "Manifest Driven Session",
            "language": "es",
            "llm_model": "",
            "prompts_path": "prompts.yaml",
            "include_resources": {},
            "requested_main_prompts": ["study_guide"],
            "main_doc_path": str(main_doc_source),
            "pdf_path": None,
            "prompt_outputs": [],
        },
        "videos": [
            {
                "index": 1,
                "title": "Primera parte",
                "url": "https://example.com/video-1",
                "local_source": "",
                "requested_prompts": ["summary"],
                "output_path": None,
                "audio_path": None,
                "transcript_path": str(transcript_source),
                "prompt_outputs": [],
            },
            {
                "index": 2,
                "title": "Segunda parte",
                "url": "https://example.com/video-2",
                "local_source": "",
                "requested_prompts": [],
                "output_path": None,
                "audio_path": None,
                "transcript_path": None,
                "prompt_outputs": [],
            },
        ],
    }
    manifest_path = outputs_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setattr("learning_session_transcriber.prompts._get_client", lambda: object())
    monkeypatch.setattr("learning_session_transcriber.prompts._chat", lambda **_: "generated")

    apply_prompts(config_path)

    video_output = outputs_root / f"{run_id}_index_1_summary.md"
    main_output = outputs_root / f"{run_id}_main_study_guide.md"
    assert video_output.is_file()
    assert main_output.is_file()

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_data["videos"][0]["prompt_outputs"][0]["name"] == "summary"
    assert manifest_data["session"]["prompt_outputs"][0]["name"] == "study_guide"
