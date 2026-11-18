"""Discover videos and read metadata. Original files are opened read-only."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from config import SUPPORTED_EXTENSIONS


class VideoAccessError(Exception):
    """The file cannot be read or is not a usable video."""


class ProbeError(VideoAccessError):
    """ffprobe could not read the file."""


@dataclass
class VideoInfo:
    path: Path
    relative_path: str
    size_bytes: int
    sha256: str
    duration_seconds: float | None
    width: int | None
    height: int | None
    codec: str | None
    fps: float | None
    format_name: str | None
    stream_index: int | None


def discover_videos(
    root: Path,
    recursive: bool,
    exclude: Path | None = None,
) -> list[Path]:
    """Return supported videos in a stable order. Does not follow directory links."""
    root = root.resolve()
    exclude_resolved = exclude.resolve() if exclude is not None else None
    found: list[Path] = []

    if not recursive:
        for path in root.iterdir():
            if _is_candidate(path, exclude_resolved):
                found.append(path)
    else:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            current = Path(dirpath)
            resolved = current.resolve()
            if exclude_resolved is not None and (
                resolved == exclude_resolved or exclude_resolved in resolved.parents
            ):
                dirnames.clear()
                continue
            if exclude_resolved is not None:
                dirnames[:] = [
                    name
                    for name in dirnames
                    if (current / name).resolve() != exclude_resolved
                ]
            for name in filenames:
                path = current / name
                if _is_candidate(path, exclude_resolved):
                    found.append(path)

    found.sort(key=lambda path: str(path.relative_to(root)).lower())
    return found


def _is_candidate(path: Path, exclude_resolved: Path | None) -> bool:
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return False
    if not path.is_file():
        return False
    if exclude_resolved is not None:
        resolved = path.resolve()
        if resolved == exclude_resolved or exclude_resolved in resolved.parents:
            return False
    return True


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_posix(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def probe_video(path: Path, ffprobe: str) -> VideoInfo:
    """Verify the file and collect ffprobe metadata. The file is not modified."""
    try:
        stat = path.stat()
    except OSError as exc:
        raise VideoAccessError(f"Cannot read file: {exc.strerror or exc}") from exc
    if stat.st_size <= 0:
        raise VideoAccessError("File is empty.")

    try:
        digest = sha256_file(path)
    except OSError as exc:
        raise VideoAccessError(f"Cannot hash file: {exc.strerror or exc}") from exc

    command = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=60,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        raise ProbeError("ffprobe timed out.") from exc
    except OSError as exc:
        raise ProbeError(f"ffprobe failed to start: {exc.strerror or exc}") from exc

    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        lines = [line.strip() for line in detail.splitlines() if line.strip()]
        raise ProbeError(" ".join(lines[-3:])[:500] or "ffprobe rejected the file.")

    try:
        payload = json.loads(completed.stdout.decode("utf-8", errors="replace") or "{}")
    except json.JSONDecodeError as exc:
        raise ProbeError("ffprobe returned invalid JSON.") from exc

    video_streams = [
        stream
        for stream in payload.get("streams", [])
        if stream.get("codec_type") == "video"
    ]
    if not video_streams:
        raise ProbeError("No video stream found.")

    stream = video_streams[0]
    fmt = payload.get("format") or {}
    duration = _first_float(fmt.get("duration"), stream.get("duration"))
    width = _first_int(stream.get("width"))
    height = _first_int(stream.get("height"))
    fps = _parse_rate(str(stream.get("avg_frame_rate") or "")) or _parse_rate(
        str(stream.get("r_frame_rate") or "")
    )
    stream_index = stream.get("index")
    return VideoInfo(
        path=path,
        relative_path="",
        size_bytes=stat.st_size,
        sha256=digest,
        duration_seconds=duration,
        width=width,
        height=height,
        codec=stream.get("codec_name"),
        fps=fps,
        format_name=fmt.get("format_name"),
        stream_index=int(stream_index) if stream_index is not None else None,
    )


def _first_float(*values: object) -> float | None:
    for value in values:
        if value in (None, "", "N/A"):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number >= 0:
            return number
    return None


def _first_int(value: object) -> int | None:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _parse_rate(value: str) -> float | None:
    if not value or value in {"0/0", "N/A"}:
        return None
    if "/" not in value:
        try:
            number = float(value)
        except ValueError:
            return None
        return number if number > 0 else None
    numerator, denominator = value.split("/", 1)
    try:
        den = float(denominator)
        num = float(numerator)
    except ValueError:
        return None
    if den == 0:
        return None
    rate = num / den
    return rate if rate > 0 else None
