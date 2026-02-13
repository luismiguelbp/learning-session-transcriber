"""Prompt application step using the OpenAI Chat API.

This module reads ``prompts.yaml`` and applies per‑video and main‑document
prompts to session outputs.
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

import yaml
from openai import OpenAI

from .config import Config
from .manifest import add_manifest_file
from .sessions import SessionConfig, load_session_config

logger = logging.getLogger(__name__)


def _get_client() -> OpenAI:
    cfg = Config.from_env()
    if cfg.openai_api_key:
        return OpenAI(api_key=cfg.openai_api_key)
    return OpenAI()


def _load_prompts_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8") as f:
        return f.read()


def _strip_transcript_header(text: str) -> str:
    """Remove the synthetic transcript header if present.

    Older transcripts were written with a Markdown/YAML‑style header such as:

        # Transcript for video 1: ...
        - content_name: ...
        - source_audio: ...
        ---

    For prompt application we only want the spoken content, since metadata
    already lives in ``session.yaml`` and ``manifest.json``.
    """
    stripped = text.lstrip()
    if stripped.startswith("# Transcript for video"):
        # Split on the first '---' separator line.
        parts = stripped.split("\n---\n", 1)
        if len(parts) == 2:
            # Return everything after the separator, trimming leading newlines.
            return parts[1].lstrip("\n")
    return text

def _requires_max_completion_tokens(model: str) -> bool:
    """Check if model requires max_completion_tokens instead of max_tokens."""
    model_lower = model.lower()
    return (
        model_lower.startswith("o1")
        or model_lower.startswith("o3")
        or model_lower.startswith("gpt-5")
    )


def _chat(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_content: Union[str, List[dict]],
    temperature: float,
    max_tokens: int,
) -> str:
    create_kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
    }
    
    if _requires_max_completion_tokens(model):
        create_kwargs["max_completion_tokens"] = max_tokens
    else:
        create_kwargs["max_tokens"] = max_tokens
    
    response = client.chat.completions.create(**create_kwargs)
    content = response.choices[0].message.content or ""
    logger.debug(
        "Received chat completion (model=%s, max_tokens=%s, length=%d)",
        model,
        max_tokens,
        len(content),
    )
    return content


def _resolve_include_resources(
    session: SessionConfig,
    config_path: Path,
    include_resources_keys: List[str],
) -> Tuple[str, List[dict]]:
    """Build extra user content from session include_resources for requested keys.

    Paths in session.include_resources are relative to the session directory
    (config_path.parent). Missing files are skipped with a warning.
    Returns (text_extra, file_parts). When file_parts is non-empty, a
    vision-capable model (e.g. gpt-4o, gpt-5) is required for the request.
    """
    if not include_resources_keys:
        return "", []
    if not session.include_resources:
        return "", []
    session_dir = config_path.parent
    text_parts: List[str] = []
    file_parts: List[dict] = []
    for key in include_resources_keys:
        if key not in session.include_resources:
            logger.warning(
                "Prompt requested include_resources key %r but session does not define it; skipping.",
                key,
            )
            continue
        path = (session_dir / session.include_resources[key]).resolve()
        if not path.is_file():
            logger.warning(
                "include_resources %r path %s does not exist or is not a file; skipping.",
                key,
                path,
            )
            continue
        try:
            if path.suffix.lower() == ".pdf":
                data = path.read_bytes()
                b64_str = base64.b64encode(data).decode("utf-8")
                file_parts.append({
                    "type": "file",
                    "file": {
                        "filename": path.name,
                        "file_data": f"data:application/pdf;base64,{b64_str}",
                    },
                })
            else:
                text = _read_text(path)
                text_parts.append(f"\n\n## Resource: {key}\n\n{text}")
        except OSError as e:
            logger.warning("Failed to read include_resources %r from %s: %s", key, path, e)
    return "".join(text_parts), file_parts


def apply_prompts(config_path: Path, prompts_path: Path | None = None) -> None:
    """Apply prompts to per‑video transcripts and the main document."""

    session: SessionConfig = load_session_config(config_path)
    cfg = Config.from_env()
    client = _get_client()
    model = cfg.openai_model or session.llm_model

    # Use session.prompts_path if set, otherwise use passed prompts_path or default
    if session.prompts_path is not None and session.prompts_path.is_file():
        prompts_path = session.prompts_path
    elif prompts_path is None:
        prompts_path = Path("prompts.yaml")
    prompts_cfg = _load_prompts_config(prompts_path)

    per_video_cfg = prompts_cfg.get("per_video", [])
    main_cfg = prompts_cfg.get("main_document", [])

    prompts_dir = session.prompts_output_dir
    prompts_dir.mkdir(parents=True, exist_ok=True)

    # Per‑video prompts.
    transcript_files = sorted(session.transcripts_output_dir.glob("*_transcript.md"))
    for transcript_file in transcript_files:
        raw_content = _read_text(transcript_file)
        content = _strip_transcript_header(raw_content)

        # Derive index from filename pattern: <content_name>_index_<N>_transcript.md
        name = transcript_file.stem
        # Look for "_index_" pattern and extract the number after it
        index = 0
        if "_index_" in name:
            try:
                parts = name.split("_index_")
                if len(parts) > 1:
                    index_str = parts[1].split("_")[0]
                    index = int(index_str)
            except (ValueError, IndexError):
                index = 0

        prompt_names = session.get_video_postprocess_prompts(index)
        if not prompt_names:
            continue

        for prompt in per_video_cfg:
            prompt_name = prompt["name"]
            if prompt_name not in prompt_names:
                continue
            system_prompt = prompt.get("system_prompt", "")
            temperature = float(prompt.get("temperature", 0.3))
            max_tokens = int(prompt.get("max_tokens", 800))

            out_path = prompts_dir / f"{session.content_name}_index_{index}_{prompt_name}.md"
            
            # Check if prompt output already exists - skip if it does
            if out_path.is_file():
                logger.info(
                    "Skipping per‑video prompt %s for video %d: output already exists at %s",
                    prompt_name, index, out_path
                )
                add_manifest_file(session.outputs_root / "manifest.json", "prompt", out_path, index)
                continue

            include_resources_raw = prompt.get("include_resources")
            if isinstance(include_resources_raw, list):
                include_resources_keys = [str(k) for k in include_resources_raw if str(k).strip()]
            else:
                include_resources_keys = []
            text_extra, file_parts = _resolve_include_resources(session, config_path, include_resources_keys)
            if not file_parts:
                user_content = content + text_extra
            else:
                user_content = [{"type": "text", "text": content + text_extra}] + file_parts

            logger.info(
                "Running per‑video prompt %s on transcript %s", prompt_name, transcript_file
            )
            answer = _chat(
                client=client,
                model=model,
                system_prompt=system_prompt,
                user_content=user_content,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if not answer.strip():
                logger.warning(
                    "Per‑video prompt %s for video %d returned empty content; "
                    "writing diagnostic message instead of blank file.",
                    prompt_name,
                    index,
                )
                answer = (
                    f"[No content returned by model for per‑video prompt "
                    f"'{prompt_name}' on video index {index}. Check logs.]"
                )
            with out_path.open("w", encoding="utf-8") as f:
                f.write(answer)
            
            add_manifest_file(session.outputs_root / "manifest.json", "prompt", out_path, index)

    # Main‑document prompts.
    main_prompt_names = session.get_main_postprocess_prompts()
    if not main_prompt_names:
        return

    main_doc_path = session.main_markdown_path
    if not main_doc_path.is_file():
        raise FileNotFoundError(f"Main document not found at {main_doc_path}")

    main_content = _read_text(main_doc_path)
    for prompt in main_cfg:
        prompt_name = prompt["name"]
        if prompt_name not in main_prompt_names:
            continue
        system_prompt = prompt.get("system_prompt", "")
        temperature = float(prompt.get("temperature", 0.3))
        max_tokens = int(prompt.get("max_tokens", 1500))

        # Main‑document prompt outputs follow:
        #   <content_name>_main_<prompt_name>.md
        out_path = prompts_dir / f"{session.content_name}_main_{prompt_name}.md"
        
        # Check if prompt output already exists - skip if it does
        if out_path.is_file():
            logger.info(
                "Skipping main‑document prompt %s: output already exists at %s",
                prompt_name, out_path
            )
            add_manifest_file(session.outputs_root / "manifest.json", "prompt", out_path)
            continue

        include_resources_raw = prompt.get("include_resources")
        if isinstance(include_resources_raw, list):
            include_resources_keys = [str(k) for k in include_resources_raw if str(k).strip()]
        else:
            include_resources_keys = []
        text_extra, file_parts = _resolve_include_resources(session, config_path, include_resources_keys)
        if not file_parts:
            user_content = main_content + text_extra
        else:
            user_content = [{"type": "text", "text": main_content + text_extra}] + file_parts

        logger.info("Running main‑document prompt %s", prompt_name)
        answer = _chat(
            client=client,
            model=model,
            system_prompt=system_prompt,
            user_content=user_content,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if not answer.strip():
            logger.warning(
                "Main‑document prompt %s returned empty content; "
                "writing diagnostic message instead of blank file.",
                prompt_name,
            )
            answer = (
                f"[No content returned by model for main‑document prompt "
                f"'{prompt_name}'. Check logs.]"
            )

        with out_path.open("w", encoding="utf-8") as f:
            f.write(answer)
        
        add_manifest_file(session.outputs_root / "manifest.json", "prompt", out_path)


def main(args: List[str] | None = None) -> None:  # pragma: no cover - thin wrapper
    import argparse

    parser = argparse.ArgumentParser(
        description="Apply per‑video and main‑document prompts to a session."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to session.yaml file.",
    )
    parser.add_argument(
        "--prompts",
        default="prompts.yaml",
        help="Path to prompts.yaml (default: prompts.yaml in project root).",
    )
    parsed = parser.parse_args(args=args)
    apply_prompts(Path(parsed.config), Path(parsed.prompts))


