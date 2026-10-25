"""Prompt application step using OpenAI text-generation APIs.

This module reads ``prompts.yaml`` and applies per‑video and main‑document
prompts to session outputs. GPT-6 models use the Responses API.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

import yaml
from openai import OpenAI

from .config import Config, DEFAULT_OPENAI_MODEL
from .manifest import add_manifest_file, load_manifest, sync_manifest_with_session
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


def _resolve_prompt_model(
    environment_model: str | None,
    session_model: str | None,
) -> str:
    """Resolve the environment override, then the session model, then the default."""
    return environment_model or session_model or DEFAULT_OPENAI_MODEL


def _responses_user_content(
    user_content: Union[str, List[dict]],
) -> Union[str, List[dict]]:
    """Translate the prompt content parts to the Responses API input format."""
    if isinstance(user_content, str):
        return user_content

    converted: List[dict] = []
    for part in user_content:
        if part.get("type") == "text":
            converted.append({"type": "input_text", "text": part.get("text", "")})
        elif part.get("type") == "file":
            file_part = part.get("file", {})
            converted.append(
                {
                    "type": "input_file",
                    "filename": file_part["filename"],
                    "file_data": file_part["file_data"],
                }
            )
        else:
            raise ValueError(f"Unsupported prompt content part: {part.get('type')!r}")
    return converted


def _chat(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_content: Union[str, List[dict]],
    temperature: float,
    max_tokens: int,
    reasoning_effort: str = "medium",
) -> str:
    if model.lower().startswith("gpt-6"):
        if reasoning_effort == "none" and model.lower().startswith(
            ("gpt-6.1", "gpt-6-astra")
        ):
            raise ValueError(f"{model} does not support reasoning effort 'none'.")

        create_kwargs = {
            "model": model,
            "instructions": system_prompt,
            "input": [
                {
                    "role": "user",
                    "content": _responses_user_content(user_content),
                }
            ],
            "reasoning": {"effort": reasoning_effort},
            "max_output_tokens": max_tokens,
        }
        # GPT-6 only accepts sampling controls with reasoning effort `none`.
        if reasoning_effort == "none":
            create_kwargs["temperature"] = temperature

        response = client.responses.create(**create_kwargs)
        if getattr(response, "status", "completed") != "completed":
            details = getattr(response, "incomplete_details", None)
            logger.warning(
                "Responses API returned status=%s (reason=%s, model=%s)",
                response.status,
                getattr(details, "reason", None),
                model,
            )
        usage = getattr(response, "usage", None)
        if usage is not None:
            output_details = getattr(usage, "output_tokens_details", None)
            logger.info(
                "OpenAI usage (model=%s, input_tokens=%s, output_tokens=%s, reasoning_tokens=%s)",
                model,
                getattr(usage, "input_tokens", None),
                getattr(usage, "output_tokens", None),
                getattr(output_details, "reasoning_tokens", None),
            )
        return response.output_text or ""

    # Keep existing model overrides working through Chat Completions.
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
    (config_path.parent). Missing or unreadable configured resources raise
    an exception to stop execution.
    Returns (text_extra, file_parts). When file_parts is non-empty, a
    vision-capable model (e.g. gpt-4o or GPT-6) is required for the request.
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
            raise ValueError(
                "include_resources key "
                f"{key!r} points to a missing or non-file path: {session.include_resources[key]!r} "
                f"(resolved to {path})"
            )
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
            raise ValueError(
                "include_resources key "
                f"{key!r} points to an unreadable file: {session.include_resources[key]!r} "
                f"(resolved to {path})"
            ) from e
    return "".join(text_parts), file_parts


def apply_prompts(config_path: Path, prompts_path: Path | None = None) -> None:
    """Apply prompts to per‑video transcripts and the main document."""

    session: SessionConfig = load_session_config(config_path)
    cfg = Config.from_env()
    model = _resolve_prompt_model(cfg.openai_model, session.llm_model)
    logger.info(
        "Using prompt model %s%s",
        model,
        f" with reasoning effort {cfg.openai_reasoning_effort}"
        if model.lower().startswith("gpt-6")
        else "",
    )
    client: OpenAI | None = None
    manifest_path = session.outputs_root / "manifest.json"

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
    manifest = sync_manifest_with_session(manifest_path, session)

    # Per‑video prompts.
    for entry in manifest["videos"]:
        if bool(entry.get("download_only")):
            continue

        index = int(entry["index"])
        prompt_names = list(entry.get("requested_prompts") or [])
        if not prompt_names:
            continue

        transcript_str = entry.get("transcript_path")
        if not transcript_str:
            raise FileNotFoundError(
                f"Manifest is missing transcript_path for video {index}. "
                "Run the transcription step first."
            )

        transcript_file = Path(transcript_str)
        if not transcript_file.is_file():
            raise FileNotFoundError(
                f"Transcript listed in manifest for video {index} not found: {transcript_file}"
            )

        raw_content = _read_text(transcript_file)
        content = _strip_transcript_header(raw_content)

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
                add_manifest_file(
                    manifest_path,
                    "prompt",
                    out_path,
                    index,
                    prompt_name=prompt_name,
                )
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
            if client is None:
                client = _get_client()
            answer = _chat(
                client=client,
                model=model,
                system_prompt=system_prompt,
                user_content=user_content,
                temperature=temperature,
                max_tokens=max_tokens,
                reasoning_effort=cfg.openai_reasoning_effort,
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
            
            add_manifest_file(
                manifest_path,
                "prompt",
                out_path,
                index,
                prompt_name=prompt_name,
            )

    # Main‑document prompts.
    manifest = load_manifest(manifest_path)
    main_prompt_names = list(manifest["session"].get("requested_main_prompts") or [])
    if not main_prompt_names:
        return

    main_doc_str = manifest["session"].get("main_doc_path")
    if not main_doc_str:
        raise FileNotFoundError(
            "Manifest is missing main_doc_path. Run the synthesis step first."
        )

    main_doc_path = Path(main_doc_str)
    if not main_doc_path.is_file():
        raise FileNotFoundError(f"Main document listed in manifest not found at {main_doc_path}")

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
            add_manifest_file(
                manifest_path,
                "prompt",
                out_path,
                prompt_name=prompt_name,
            )
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
        if client is None:
            client = _get_client()
        answer = _chat(
            client=client,
            model=model,
            system_prompt=system_prompt,
            user_content=user_content,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_effort=cfg.openai_reasoning_effort,
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
        
        add_manifest_file(
            manifest_path,
            "prompt",
            out_path,
            prompt_name=prompt_name,
        )


def main(args: List[str] | None = None) -> None:  # pragma: no cover - thin wrapper
    import argparse

    parser = argparse.ArgumentParser(
        description="Apply per‑video and main‑document prompts to a session."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to session YAML config file.",
    )
    parser.add_argument(
        "--prompts",
        default="prompts.yaml",
        help="Path to prompts.yaml (default: prompts.yaml in project root).",
    )
    parsed = parser.parse_args(args=args)
    apply_prompts(Path(parsed.config), Path(parsed.prompts))
