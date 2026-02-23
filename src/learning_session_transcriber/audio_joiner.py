"""Audio joiner: convert WAV/M4A to MP3, join MP3s with silence gaps and ID3 metadata.

Invoked via: python -m learning_session_transcriber.audio_joiner --session sessions/<name>/

Reads audio_metadata.yaml from the session folder. Converts WAV and M4A files to MP3,
optionally applies per-file ID3 metadata, then joins all MP3s into one file
with configurable silence between segments and joined ID3 metadata.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

AUDIO_METADATA_FILENAME = "audio_metadata.yaml"
DEFAULT_SILENCE_GAP_SECONDS = 3
DEFAULT_OUTPUT_FILENAME = "{session_name}_joined.mp3"

# ffmpeg metadata key: YAML key (year -> date for ffmpeg)
FFMPEG_METADATA_KEYS = {
    "title": "title",
    "artist": "artist",
    "album": "album",
    "year": "date",
    "comment": "comment",
    "genre": "genre",
}


def load_audio_metadata(session_dir: Path) -> dict[str, Any]:
    """Read audio_metadata.yaml from session_dir.

    Returns a dict with:
      - silence_gap_seconds (default 3)
      - output_filename (default "{session_name}_joined.mp3")
      - per_file (dict, optional)
      - joined (dict, optional)
    """
    path = session_dir / AUDIO_METADATA_FILENAME
    if not path.is_file():
        return {
            "silence_gap_seconds": DEFAULT_SILENCE_GAP_SECONDS,
            "output_filename": DEFAULT_OUTPUT_FILENAME,
            "per_file": None,
            "joined": None,
        }
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return {
        "silence_gap_seconds": raw.get("silence_gap_seconds", DEFAULT_SILENCE_GAP_SECONDS),
        "output_filename": raw.get("output_filename", DEFAULT_OUTPUT_FILENAME),
        "per_file": raw.get("per_file"),
        "joined": raw.get("joined"),
    }


class _PlaceholderDict(dict):
    """Dict that returns '{key}' for missing keys so format_map leaves placeholders as-is."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def resolve_metadata_variables(metadata_section: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    """Resolve {var} placeholders in metadata section values via format_map.

    Unresolved placeholders are left as-is.
    """
    if not metadata_section:
        return {}
    merged = _PlaceholderDict((k, str(v)) for k, v in variables.items())
    result = {}
    for k, v in metadata_section.items():
        if isinstance(v, str):
            result[k] = v.format_map(merged)
        else:
            result[k] = v
    return result


def _safe_format_map(template: str, variables: dict[str, Any]) -> str:
    """Format template with variables; unknown keys stay as {key}."""
    merged = _PlaceholderDict((k, str(v)) for k, v in variables.items())
    return template.format_map(merged)


def scan_audio_files(session_dir: Path) -> list[Path]:
    """Find all .wav, .m4a and .mp3 files in session_dir, sorted alphabetically."""
    paths = []
    for p in session_dir.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() in (".wav", ".m4a", ".mp3"):
            paths.append(p)
    return sorted(paths, key=lambda p: p.name.lower())


def _build_ffmpeg_metadata_args(metadata: dict[str, Any]) -> list[str]:
    """Build -metadata key=value args for ffmpeg from ID3-style dict."""
    args = []
    for yaml_key, ffmpeg_key in FFMPEG_METADATA_KEYS.items():
        value = metadata.get(yaml_key)
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        args.extend(["-metadata", f"{ffmpeg_key}={str(value).strip()}"])
    return args


def convert_to_mp3(
    source_path: Path, output_path: Path, metadata: dict[str, Any] | None
) -> None:
    """Convert a single WAV or M4A file to MP3 using ffmpeg; optionally apply ID3 metadata.

    Skips if output_path already exists.
    """
    if output_path.is_file():
        logger.info("Skipping conversion, output exists: %s", output_path)
        return
    logger.info("Converting %s -> %s", source_path, output_path)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_path),
        "-acodec",
        "libmp3lame",
        "-q:a",
        "2",
    ]
    if metadata:
        cmd.extend(_build_ffmpeg_metadata_args(metadata))
    cmd.append(str(output_path))
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0 or not output_path.is_file():
        raise RuntimeError(
            f"ffmpeg failed to convert {source_path} to {output_path} (exit code {result.returncode})"
        )


def prepare_audio_files(
    session_dir: Path,
    output_dir: Path,
    meta: dict[str, Any],
) -> list[Path]:
    """Convert WAV/M4A to MP3 and copy existing MP3s to output_dir; return ordered MP3 paths.

    meta must contain at least the loaded config; per_file metadata is resolved
    per file with index, filename, session_name.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    session_name = session_dir.name
    per_file_template = meta.get("per_file") or {}
    files = scan_audio_files(session_dir)
    mp3_paths = []
    for index, src in enumerate(files, start=1):
        filename_stem = src.stem
        dest = output_dir / f"{filename_stem}.mp3"
        if src.suffix.lower() in (".wav", ".m4a"):
            variables = {
                "index": index,
                "filename": filename_stem,
                "session_name": session_name,
            }
            per_file_resolved = resolve_metadata_variables(per_file_template, variables)
            convert_to_mp3(src, dest, per_file_resolved if per_file_resolved else None)
        else:
            if not dest.is_file() or dest.stat().st_mtime < src.stat().st_mtime:
                logger.info("Copying %s -> %s", src, dest)
                shutil.copy2(src, dest)
            else:
                logger.info("Skipping copy, output up to date: %s", dest)
        mp3_paths.append(dest)
    return mp3_paths


def generate_silence(duration_seconds: float, output_path: Path) -> None:
    """Generate a silent MP3 of the given duration using ffmpeg."""
    logger.info("Generating %s seconds silence -> %s", duration_seconds, output_path)
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=stereo",
        "-t", str(duration_seconds),
        "-acodec", "libmp3lame",
        "-q:a", "9",
        str(output_path),
    ]
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0 or not output_path.is_file():
        raise RuntimeError(
            f"ffmpeg failed to generate silence at {output_path} (exit code {result.returncode})"
        )


def join_mp3_files(
    mp3_paths: list[Path],
    silence_path: Path,
    output_path: Path,
    metadata: dict[str, Any] | None,
) -> None:
    """Concat MP3s with silence between each; apply ID3 metadata to the final file."""
    if not mp3_paths:
        raise ValueError("No MP3 files to join")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        concat_path = Path(f.name)
        try:
            for i, mp3 in enumerate(mp3_paths):
                path_str = str(mp3.resolve())
                if "'" in path_str:
                    path_str = path_str.replace("'", "'\\''")
                f.write(f"file '{path_str}'\n")
                if i < len(mp3_paths) - 1:
                    silence_str = str(silence_path.resolve()).replace("'", "'\\''")
                    f.write(f"file '{silence_str}'\n")
        except Exception:
            concat_path.unlink(missing_ok=True)
            raise

    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_path),
            "-acodec", "libmp3lame",
            "-q:a", "2",
        ]
        if metadata:
            cmd.extend(_build_ffmpeg_metadata_args(metadata))
        cmd.append(str(output_path))
        logger.info("Joining %d segments -> %s", len(mp3_paths), output_path)
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0 or not output_path.is_file():
            raise RuntimeError(
                f"ffmpeg failed to join audio to {output_path} (exit code {result.returncode})"
            )
    finally:
        concat_path.unlink(missing_ok=True)


def run_audio_joiner(session_dir: Path) -> Path:
    """Run the full pipeline: load config, prepare MP3s, generate silence, join.

    session_dir is the path to the session folder (e.g. sessions/MyAudioSession).
    Output is written to outputs/<session_name>/.

    Returns the path to the joined MP3 file.
    """
    session_dir = session_dir.resolve()
    if not session_dir.is_dir():
        raise FileNotFoundError(f"Session directory not found: {session_dir}")

    session_name = session_dir.name
    output_dir = Path("outputs") / session_name
    meta = load_audio_metadata(session_dir)

    files = scan_audio_files(session_dir)
    if not files:
        raise ValueError(f"No WAV, M4A or MP3 files found in {session_dir}")

    mp3_paths = prepare_audio_files(session_dir, output_dir, meta)

    silence_gap = float(meta.get("silence_gap_seconds", DEFAULT_SILENCE_GAP_SECONDS))
    silence_path = output_dir / "_silence_gap.mp3"
    if silence_gap > 0:
        generate_silence(silence_gap, silence_path)
    else:
        silence_path = None

    output_filename_raw = meta.get("output_filename") or DEFAULT_OUTPUT_FILENAME
    joined_vars = {"session_name": session_name, "total_files": len(mp3_paths)}
    output_filename = _safe_format_map(output_filename_raw, joined_vars)
    output_filename = Path(output_filename).name
    if not output_filename.lower().endswith(".mp3"):
        output_filename += ".mp3"
    joined_path = output_dir / output_filename

    joined_meta = meta.get("joined")
    joined_resolved = resolve_metadata_variables(joined_meta, joined_vars) if joined_meta else None

    if silence_path is not None and silence_path.is_file():
        join_mp3_files(mp3_paths, silence_path, joined_path, joined_resolved)
    else:
        join_mp3_files_no_silence(mp3_paths, joined_path, joined_resolved)

    if silence_path and silence_path.is_file():
        try:
            silence_path.unlink()
        except OSError:
            pass
    logger.info("Joined audio written to %s", joined_path)
    return joined_path


def join_mp3_files_no_silence(
    mp3_paths: list[Path],
    output_path: Path,
    metadata: dict[str, Any] | None,
) -> None:
    """Concat MP3s without silence (used when silence_gap_seconds is 0)."""
    if not mp3_paths:
        raise ValueError("No MP3 files to join")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        concat_path = Path(f.name)
        try:
            for mp3 in mp3_paths:
                path_str = str(mp3.resolve()).replace("'", "'\\''")
                f.write(f"file '{path_str}'\n")
        except Exception:
            concat_path.unlink(missing_ok=True)
            raise
    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_path),
            "-acodec", "libmp3lame",
            "-q:a", "2",
        ]
        if metadata:
            cmd.extend(_build_ffmpeg_metadata_args(metadata))
        cmd.append(str(output_path))
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0 or not output_path.is_file():
            raise RuntimeError(
                f"ffmpeg failed to join audio to {output_path} (exit code {result.returncode})"
            )
    finally:
        concat_path.unlink(missing_ok=True)


def main(args: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert WAV/M4A to MP3 and join all session audio files with silence gaps and ID3 metadata."
    )
    parser.add_argument(
        "--session",
        required=True,
        help="Path to the session folder (e.g. sessions/MyAudioSession)",
    )
    parsed = parser.parse_args(args=args)
    session_path = Path(parsed.session).resolve()
    try:
        run_audio_joiner(session_path)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        logger.exception("Audio joiner failed: %s", e)
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
