"""Session configuration models and loader.

A *session* represents one logical set of videos and optional configuration.
Users create one YAML configuration file per session, typically placed under
``sessions/<content_name>/session.yaml``
where ``content_name`` follows the pattern::

    YYYYMMDD_HHmmss_session-topic

See ``session.example.yaml`` for a complete example.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml


@dataclass
class VideoConfig:
    """Configuration for a single video in a session."""

    index: int
    title: str
    url: Optional[str] = None
    local_path: Optional[str] = None
    # Optional list of per-video postprocess prompt names defined in
    # prompts.yaml under the ``per_video`` section.
    postprocess_prompts: Optional[List[str]] = None

    def slug(self) -> str:
        """Return a filesystem‑friendly slug based on the title."""
        base = self.title.strip().lower().replace(" ", "-")
        safe = "".join(ch for ch in base if ch.isalnum() or ch in ("-", "_"))
        return safe or f"video-{self.index}"


@dataclass
class PdfConfig:
    """Configuration for the related PDF."""

    title: str
    path: str  # path relative to the session folder


@dataclass
class SessionConfig:
    """Top‑level session configuration.

    All generated artifacts for a session live directly under
    ``outputs/<content_name>/`` in a flattened layout. Helper properties
    that mention specific subdirectories (videos, transcripts, pdf, prompts)
    currently all resolve to this root folder. Paths in ``include_resources``
    are relative to the session directory (same as ``pdf.path``).
    """

    content_name: str
    topic: str
    videos: List[VideoConfig]
    # PDF is optional so that users can run steps that only need videos,
    # such as the downloader, without configuring a PDF up front.
    pdf: Optional[PdfConfig] = None
    language: str = "es"
    llm_model: str = "gpt-5-mini"
    # Optional list of main-document postprocess prompt names defined in
    # prompts.yaml under the ``main_document`` section.
    main_postprocess_prompts: Optional[List[str]] = None
    # Optional path to prompts.yaml file (resolved relative to session directory).
    # If None, the default prompts.yaml will be used.
    prompts_path: Optional[Path] = None
    # Optional mapping of resource key to path (relative to session directory).
    # Used by prompts that declare include_resources in prompts.yaml.
    include_resources: Optional[Dict[str, str]] = None

    @property
    def outputs_root(self) -> Path:
        """Root output folder for this session."""
        return Path("outputs") / self.content_name

    @property
    def videos_output_dir(self) -> Path:
        # Flattened layout: keep everything under outputs_root.
        return self.outputs_root

    @property
    def transcripts_output_dir(self) -> Path:
        # Flattened layout: keep everything under outputs_root.
        return self.outputs_root

    @property
    def pdf_output_dir(self) -> Path:
        # Flattened layout: keep everything under outputs_root.
        return self.outputs_root

    @property
    def prompts_output_dir(self) -> Path:
        # Flattened layout: keep everything under outputs_root.
        return self.outputs_root

    @property
    def main_markdown_path(self) -> Path:
        return self.outputs_root / f"{self.content_name}_main.md"

    # --- Helpers for post-processing configuration ---

    def get_video_postprocess_prompts(self, index: int) -> List[str]:
        """Return the list of postprocess prompt names for a given video index."""

        for video in self.videos:
            if video.index == index and video.postprocess_prompts:
                return video.postprocess_prompts
        return []

    def get_main_postprocess_prompts(self) -> List[str]:
        """Return the list of postprocess prompt names for the main document."""

        return self.main_postprocess_prompts or []


def _validate_and_build(raw: dict, config_path: Path) -> SessionConfig:
    """Validate a raw dict from YAML and build a SessionConfig.
    
    Args:
        raw: Parsed YAML content as a dictionary.
        config_path: Path to the session.yaml file (used to resolve relative paths).
    """

    if "content_name" not in raw or "topic" not in raw:
        raise ValueError("Session configuration must contain 'content_name' and 'topic'")

    if "videos" not in raw or not isinstance(raw["videos"], list) or not raw["videos"]:
        raise ValueError("Session configuration must contain a non‑empty 'videos' list")

    videos: List[VideoConfig] = []
    seen_indices: set[int] = set()
    for item in raw["videos"]:
        try:
            index = int(item["index"])
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError(f"Invalid video index in {item!r}") from exc

        if index in seen_indices:
            raise ValueError(f"Duplicate video index {index} in videos list")
        seen_indices.add(index)

        # Title is optional; if empty, downstream code will fall back to a
        # generic slug based on the video index.
        title = str(item.get("title") or "").strip()

        url = item.get("url")
        local_path = item.get("local_path")
        if not url and not local_path:
            raise ValueError(
                f"Video {index} must define at least one of 'url' or 'local_path'"
            )

        raw_pp = item.get("postprocess_prompts", item.get("postprocess_prompt"))
        if isinstance(raw_pp, list):
            postprocess_prompts = [str(name) for name in raw_pp if str(name).strip()]
        elif raw_pp:
            postprocess_prompts = [str(raw_pp)]
        else:
            postprocess_prompts = None

        videos.append(
            VideoConfig(
                index=index,
                title=title,
                url=str(url) if url else None,
                local_path=str(local_path) if local_path else None,
                postprocess_prompts=postprocess_prompts,
            )
        )

    # Optional PDF configuration.
    pdf_cfg: Optional[PdfConfig] = None
    pdf_raw = raw.get("pdf")
    if isinstance(pdf_raw, dict):
        pdf_title = str(pdf_raw.get("title") or "").strip()
        pdf_path = str(pdf_raw.get("path") or "").strip()
        # Allow empty PDF title; only the path is strictly required when
        # a PDF section is present.
        if not pdf_path:
            raise ValueError("pdf.path is required in session configuration when 'pdf' is defined")
        pdf_cfg = PdfConfig(title=pdf_title, path=pdf_path)

    language = str(raw.get("language") or "es")
    llm_model = str(raw.get("llm_model") or "gpt-5-mini")

    raw_main_pp = raw.get("main_postprocess_prompts", raw.get("main_postprocess_prompt"))
    if isinstance(raw_main_pp, list):
        main_postprocess_prompts = [
            str(name) for name in raw_main_pp if str(name).strip()
        ]
    elif raw_main_pp:
        main_postprocess_prompts = [str(raw_main_pp)]
    else:
        main_postprocess_prompts = None

    # Optional prompts_file: resolve relative to session directory (config_path.parent).
    prompts_path: Optional[Path] = None
    prompts_file = raw.get("prompts_file")
    if prompts_file:
        prompts_file_str = str(prompts_file).strip()
        if prompts_file_str:
            # Resolve relative to the session directory
            session_dir = config_path.parent
            resolved_path = (session_dir / prompts_file_str).resolve()
            prompts_path = resolved_path

    # Optional include_resources: key -> path (relative to session directory).
    include_resources: Optional[Dict[str, str]] = None
    ir_raw = raw.get("include_resources")
    if isinstance(ir_raw, dict) and ir_raw:
        include_resources = {
            str(k): str(v).strip()
            for k, v in ir_raw.items()
            if str(v).strip()
        }
        if not include_resources:
            include_resources = None
        else:
            # Key-specific extension validation.
            for key, path_str in include_resources.items():
                suffix = Path(path_str).suffix.lower()
                if key == "pdf" and suffix != ".pdf":
                    raise ValueError(
                        f"include_resources key 'pdf' must point to a .pdf file; got: {path_str!r}"
                    )
                if key == "notes" and suffix != ".txt":
                    raise ValueError(
                        f"include_resources key 'notes' must point to a .txt file; got: {path_str!r}"
                    )

    return SessionConfig(
        content_name=str(raw["content_name"]),
        topic=str(raw["topic"]),
        videos=sorted(videos, key=lambda v: v.index),
        pdf=pdf_cfg,
        language=language,
        llm_model=llm_model,
        main_postprocess_prompts=main_postprocess_prompts,
        prompts_path=prompts_path,
        include_resources=include_resources,
    )


def load_session_config(config_path: Path) -> SessionConfig:
    """Load and validate a session configuration file from disk.

    Supports YAML (``.yaml``, ``.yml``) format.

    ``config_path`` points to the configuration file itself. The caller is responsible
    for keeping track of the *session folder* (``config_path.parent``) when
    resolving relative paths, such as the PDF path.
    
    Args:
        config_path: Path to the session configuration file (YAML).
        
    Returns:
        SessionConfig instance.
        
    Raises:
        ValueError: If file format is unsupported or configuration is invalid.
    """
    suffix = config_path.suffix.lower()
    
    if suffix in (".yaml", ".yml"):
        with config_path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    else:
        raise ValueError(
            f"Unsupported file format: {suffix}. "
            f"Supported formats: .yaml, .yml"
        )

    return _validate_and_build(raw, config_path)

