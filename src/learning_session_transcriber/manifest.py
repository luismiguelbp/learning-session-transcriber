"""Manifest management for tracking generated files.

The manifest is a versioned JSON document that captures both the configured
session metadata and the artifacts produced by each pipeline stage.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .sessions import SessionConfig


MANIFEST_SCHEMA_VERSION = 1


def _empty_session_section() -> Dict[str, Any]:
    return {
        "content_name": "",
        "topic": "",
        "language": "",
        "llm_model": "",
        "prompts_path": "",
        "include_resources": {},
        "requested_main_prompts": [],
        "main_doc_path": None,
        "pdf_path": None,
        "prompt_outputs": [],
    }


def _new_video_entry(index: int) -> Dict[str, Any]:
    return {
        "index": index,
        "title": "",
        "url": "",
        "local_source": "",
        "requested_prompts": [],
        "output_path": None,
        "audio_path": None,
        "transcript_path": None,
        "prompt_outputs": [],
    }


def _empty_manifest() -> Dict[str, Any]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "session": _empty_session_section(),
        "videos": [],
    }


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_path(file_path: Path) -> str:
    if file_path.is_absolute():
        try:
            file_path = file_path.relative_to(Path.cwd())
        except ValueError:
            pass
    return str(file_path)


def _infer_prompt_name(path_str: str, index: int | None = None) -> str:
    stem = Path(path_str).stem
    if index is not None:
        marker = f"_index_{index}_"
        if marker in stem:
            inferred = stem.split(marker, maxsplit=1)[1].strip()
            if inferred:
                return inferred
    if "_main_" in stem:
        inferred = stem.split("_main_", maxsplit=1)[1].strip()
        if inferred:
            return inferred
    return stem


def _normalize_prompt_output(
    value: Any,
    *,
    default_scope: str,
    fallback_name: str = "",
) -> Dict[str, str] | None:
    if isinstance(value, dict):
        path = _optional_str(value.get("path"))
        name = _optional_str(value.get("name")) or fallback_name
        scope = _optional_str(value.get("scope")) or default_scope
    else:
        path = _optional_str(value)
        name = fallback_name
        scope = default_scope

    if not path:
        return None

    if not name:
        name = _infer_prompt_name(path)

    return {
        "name": name,
        "path": path,
        "scope": scope,
    }


def _dedupe_prompt_outputs(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    deduped: list[Dict[str, str]] = []
    seen_paths: set[str] = set()
    for item in items:
        path = item.get("path", "")
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        deduped.append(item)
    deduped.sort(key=lambda item: (item["name"], item["path"]))
    return deduped


def _normalize_session_section(raw: Any) -> Dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    prompt_outputs: list[Dict[str, str]] = []

    for item in data.get("prompt_outputs") or []:
        normalized = _normalize_prompt_output(item, default_scope="main_document")
        if normalized is not None:
            prompt_outputs.append(normalized)

    for legacy_path in data.get("prompt_files") or []:
        normalized = _normalize_prompt_output(
            legacy_path,
            default_scope="main_document",
            fallback_name=_infer_prompt_name(str(legacy_path)),
        )
        if normalized is not None:
            prompt_outputs.append(normalized)

    include_resources = data.get("include_resources")
    if isinstance(include_resources, dict):
        include_resources = {
            str(key): str(value).strip()
            for key, value in include_resources.items()
            if str(value).strip()
        }
    else:
        include_resources = {}

    return {
        "content_name": str(data.get("content_name") or ""),
        "topic": str(data.get("topic") or ""),
        "language": str(data.get("language") or ""),
        "llm_model": str(data.get("llm_model") or ""),
        "prompts_path": str(data.get("prompts_path") or ""),
        "include_resources": include_resources,
        "requested_main_prompts": _normalize_str_list(data.get("requested_main_prompts")),
        "main_doc_path": _optional_str(data.get("main_doc_path")),
        "pdf_path": _optional_str(data.get("pdf_path")),
        "prompt_outputs": _dedupe_prompt_outputs(prompt_outputs),
    }


def _normalize_video_entry(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict) or "index" not in raw:
        raise ValueError("Manifest video entry must be a dict with an 'index'")

    index = int(raw["index"])
    prompt_outputs: list[Dict[str, str]] = []

    for item in raw.get("prompt_outputs") or []:
        normalized = _normalize_prompt_output(item, default_scope="per_video")
        if normalized is not None:
            prompt_outputs.append(normalized)

    for legacy_path in raw.get("prompt_files") or []:
        normalized = _normalize_prompt_output(
            legacy_path,
            default_scope="per_video",
            fallback_name=_infer_prompt_name(str(legacy_path), index),
        )
        if normalized is not None:
            prompt_outputs.append(normalized)

    normalized_entry = _new_video_entry(index)
    normalized_entry.update(
        {
            "title": str(raw.get("title") or ""),
            "url": str(raw.get("url") or ""),
            "local_source": str(raw.get("local_source") or ""),
            "requested_prompts": _normalize_str_list(raw.get("requested_prompts")),
            "output_path": _optional_str(raw.get("output_path")),
            "audio_path": _optional_str(raw.get("audio_path")),
            "transcript_path": _optional_str(raw.get("transcript_path")),
            "prompt_outputs": _dedupe_prompt_outputs(prompt_outputs),
        }
    )
    return normalized_entry


def _normalize_manifest_dict(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Manifest must be a JSON object")

    schema_version = raw.get("schema_version")
    if schema_version not in (None, MANIFEST_SCHEMA_VERSION):
        raise ValueError(
            f"Unsupported manifest schema version: {schema_version!r}. "
            f"Expected {MANIFEST_SCHEMA_VERSION}."
        )

    manifest = _empty_manifest()
    manifest["session"] = _normalize_session_section(raw.get("session"))
    manifest["videos"] = sorted(
        [_normalize_video_entry(item) for item in raw.get("videos") or []],
        key=lambda item: item["index"],
    )
    return manifest


def _legacy_entries_to_manifest(entries: Any) -> Dict[str, Any]:
    if not isinstance(entries, list):
        raise ValueError("Legacy manifest must be a JSON array")

    manifest = _empty_manifest()
    session_section = manifest["session"]
    videos_by_index: dict[int, Dict[str, Any]] = {}

    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("Legacy manifest entries must be JSON objects")

        if "index" in item:
            normalized = _normalize_video_entry(item)
            videos_by_index[normalized["index"]] = normalized
            continue

        if item.get("main_doc_path"):
            session_section["main_doc_path"] = _optional_str(item.get("main_doc_path"))
        if item.get("pdf_path"):
            session_section["pdf_path"] = _optional_str(item.get("pdf_path"))

        session_prompts = list(session_section.get("prompt_outputs") or [])
        for legacy_path in item.get("prompt_files") or []:
            normalized = _normalize_prompt_output(
                legacy_path,
                default_scope="main_document",
                fallback_name=_infer_prompt_name(str(legacy_path)),
            )
            if normalized is not None:
                session_prompts.append(normalized)
        session_section["prompt_outputs"] = _dedupe_prompt_outputs(session_prompts)

    manifest["videos"] = sorted(videos_by_index.values(), key=lambda item: item["index"])
    return manifest


def load_manifest(manifest_path: Path) -> Dict[str, Any]:
    """Load manifest.json if it exists, returning the normalized schema."""
    if not manifest_path.is_file():
        return _empty_manifest()

    with manifest_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, list):
        return _legacy_entries_to_manifest(raw)
    return _normalize_manifest_dict(raw)


def save_manifest(manifest_path: Path, manifest: Dict[str, Any]) -> None:
    """Save a normalized manifest document to manifest.json."""
    normalized = _normalize_manifest_dict(manifest)
    normalized["schema_version"] = MANIFEST_SCHEMA_VERSION
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    logger.info("Updated manifest at %s", manifest_path)


def _ensure_video_entry(manifest: Dict[str, Any], index: int) -> Dict[str, Any]:
    for entry in manifest["videos"]:
        if entry["index"] == index:
            return entry

    new_entry = _new_video_entry(index)
    manifest["videos"].append(new_entry)
    manifest["videos"].sort(key=lambda item: item["index"])
    return new_entry


def sync_manifest_with_session(
    manifest_path: Path,
    session: "SessionConfig",
) -> Dict[str, Any]:
    """Ensure the manifest mirrors the current session configuration."""
    manifest = load_manifest(manifest_path)
    session_section = manifest["session"]
    session_section.update(
        {
            "content_name": session.content_name,
            "topic": session.topic,
            "language": session.language,
            "llm_model": session.llm_model,
            "prompts_path": str(session.prompts_path or "prompts.yaml"),
            "include_resources": dict(session.include_resources or {}),
            "requested_main_prompts": list(session.get_main_postprocess_prompts()),
        }
    )

    existing_videos = {entry["index"]: entry for entry in manifest["videos"]}
    synced_videos: list[Dict[str, Any]] = []
    for video in session.videos:
        entry = existing_videos.get(video.index, _new_video_entry(video.index))
        entry.update(
            {
                "index": video.index,
                "title": video.title,
                "url": video.url or "",
                "local_source": video.local_path or "",
                "requested_prompts": list(video.postprocess_prompts or []),
            }
        )
        synced_videos.append(_normalize_video_entry(entry))

    manifest["videos"] = sorted(synced_videos, key=lambda item: item["index"])
    save_manifest(manifest_path, manifest)
    return manifest


def update_manifest_entry(
    manifest_path: Path,
    index: int,
    updates: Dict[str, Any],
) -> None:
    """Update a specific video entry by index, or create it if it doesn't exist."""
    manifest = load_manifest(manifest_path)
    entry = _ensure_video_entry(manifest, index)
    merged = dict(entry)
    merged.update(updates)

    for idx, current in enumerate(manifest["videos"]):
        if current["index"] == index:
            manifest["videos"][idx] = _normalize_video_entry(merged)
            break

    save_manifest(manifest_path, manifest)


def add_manifest_file(
    manifest_path: Path,
    file_type: str,
    file_path: Path,
    index: int | None = None,
    prompt_name: str | None = None,
) -> None:
    """Add a generated artifact reference to the manifest."""
    file_path_str = _normalize_path(file_path)

    if file_type == "video" and index is not None:
        update_manifest_entry(manifest_path, index, {"output_path": file_path_str})
        return

    if file_type == "audio" and index is not None:
        update_manifest_entry(manifest_path, index, {"audio_path": file_path_str})
        return

    if file_type == "transcript" and index is not None:
        update_manifest_entry(manifest_path, index, {"transcript_path": file_path_str})
        return

    manifest = load_manifest(manifest_path)

    if file_type == "pdf":
        manifest["session"]["pdf_path"] = file_path_str
        save_manifest(manifest_path, manifest)
        return

    if file_type == "main_doc":
        manifest["session"]["main_doc_path"] = file_path_str
        save_manifest(manifest_path, manifest)
        return

    if file_type == "prompt":
        if index is not None:
            target = _ensure_video_entry(manifest, index)
            outputs = list(target.get("prompt_outputs") or [])
            normalized = _normalize_prompt_output(
                {
                    "name": prompt_name or _infer_prompt_name(file_path_str, index),
                    "path": file_path_str,
                    "scope": "per_video",
                },
                default_scope="per_video",
            )
            if normalized is not None:
                outputs.append(normalized)
            target["prompt_outputs"] = _dedupe_prompt_outputs(outputs)
        else:
            outputs = list(manifest["session"].get("prompt_outputs") or [])
            normalized = _normalize_prompt_output(
                {
                    "name": prompt_name or _infer_prompt_name(file_path_str),
                    "path": file_path_str,
                    "scope": "main_document",
                },
                default_scope="main_document",
            )
            if normalized is not None:
                outputs.append(normalized)
            manifest["session"]["prompt_outputs"] = _dedupe_prompt_outputs(outputs)

        save_manifest(manifest_path, manifest)
        logger.debug("Prompt file tracked: %s (index: %s)", file_path_str, index)
        return

    raise ValueError(f"Unsupported manifest file_type: {file_type!r}")
