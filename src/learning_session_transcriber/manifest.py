"""Manifest management for tracking generated files.

The manifest.json file tracks all generated artifacts for a session.
This module provides helpers to read and update the manifest.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def load_manifest(manifest_path: Path) -> List[Dict[str, Any]]:
    """Load manifest.json if it exists, return empty list if not."""
    if not manifest_path.is_file():
        return []
    with manifest_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_manifest(manifest_path: Path, entries: List[Dict[str, Any]]) -> None:
    """Save manifest entries to manifest.json."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    logger.info("Updated manifest at %s", manifest_path)


def update_manifest_entry(
    manifest_path: Path,
    index: int,
    updates: Dict[str, Any],
) -> None:
    """Update a specific manifest entry by index, or create it if it doesn't exist."""
    entries = load_manifest(manifest_path)
    
    # Find existing entry or create new one
    entry_idx = None
    for idx, entry in enumerate(entries):
        if entry.get("index") == index:
            entry_idx = idx
            break
    
    if entry_idx is not None:
        entries[entry_idx].update(updates)
    else:
        # Create new entry
        new_entry = {"index": index}
        new_entry.update(updates)
        entries.append(new_entry)
        # Sort by index
        entries.sort(key=lambda e: e.get("index", 0))
    
    save_manifest(manifest_path, entries)


def add_manifest_file(
    manifest_path: Path,
    file_type: str,
    file_path: Path,
    index: int | None = None,
) -> None:
    """Add a file reference to the manifest.
    
    Args:
        manifest_path: Path to manifest.json
        file_type: Type of file (e.g., 'video', 'audio', 'transcript', 'pdf', 'main_doc', 'prompt')
        file_path: Path to the file (relative or absolute)
        index: Optional video index for video-related files
    """
    # Convert to relative path if possible
    if file_path.is_absolute():
        try:
            file_path = file_path.relative_to(Path.cwd())
        except ValueError:
            pass
    
    file_path_str = str(file_path)
    
    if file_type == "video" and index is not None:
        update_manifest_entry(manifest_path, index, {"output_path": file_path_str})
    elif file_type == "audio" and index is not None:
        update_manifest_entry(manifest_path, index, {"audio_path": file_path_str})
    elif file_type == "transcript" and index is not None:
        update_manifest_entry(manifest_path, index, {"transcript_path": file_path_str})
    elif file_type == "pdf":
        # PDF doesn't have an index, store it separately
        entries = load_manifest(manifest_path)
        # Check if we already have a pdf entry
        pdf_entry = next((e for e in entries if "pdf_path" in e), None)
        if pdf_entry:
            pdf_entry["pdf_path"] = file_path_str
        else:
            entries.append({"pdf_path": file_path_str})
        save_manifest(manifest_path, entries)
    elif file_type == "main_doc":
        entries = load_manifest(manifest_path)
        main_doc_entry = next((e for e in entries if "main_doc_path" in e), None)
        if main_doc_entry:
            main_doc_entry["main_doc_path"] = file_path_str
        else:
            entries.append({"main_doc_path": file_path_str})
        save_manifest(manifest_path, entries)
    elif file_type == "prompt":
        # Track prompt files alongside their corresponding section:
        # - For per‑video prompts, attach under the video entry (by index)
        # - For main‑document prompts, attach under the main_doc entry
        entries = load_manifest(manifest_path)

        if index is not None:
            # Per‑video prompt: attach to the video entry for this index.
            target_entry = next((e for e in entries if e.get("index") == index), None)
            if target_entry is None:
                target_entry = {"index": index}
                entries.append(target_entry)

            prompt_list = target_entry.get("prompt_files") or []
            if file_path_str not in prompt_list:
                prompt_list.append(file_path_str)
            target_entry["prompt_files"] = prompt_list
        else:
            # Main‑document prompt: attach to the main_doc entry.
            target_entry = next((e for e in entries if "main_doc_path" in e), None)
            if target_entry is None:
                target_entry = {}
                entries.append(target_entry)

            prompt_list = target_entry.get("prompt_files") or []
            if file_path_str not in prompt_list:
                prompt_list.append(file_path_str)
            target_entry["prompt_files"] = prompt_list

        save_manifest(manifest_path, entries)
        logger.debug("Prompt file tracked: %s (index: %s)", file_path_str, index)
