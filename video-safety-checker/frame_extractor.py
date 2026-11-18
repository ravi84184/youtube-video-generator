"""Extract JPEG frames with FFmpeg and load them with OpenCV.

Temporary frames stay in the caller's temp directory. This module never
writes beside the original video.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

_PTS_TIME = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")


class FrameExtractError(Exception):
    """FFmpeg could not produce frames for a video."""


@dataclass
class ExtractedFrame:
    path: Path
    timestamp_seconds: float
    source: str


def extract_sample_frames(
    video: Path,
    ffmpeg: str,
    destination: Path,
    duration: float | None,
    interval: float,
    budget: int,
    max_width: int,
    stream_index: int | None,
    scene_detection: bool,
    scene_threshold: float,
) -> tuple[list[ExtractedFrame], str, list[str]]:
    """Sample on a fixed interval, then optionally add the end and scene cuts.

    Returns frames, a coverage label (sampled, limited_sample, incomplete),
    and non-fatal warnings.
    """
    destination.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    if budget < 1:
        raise FrameExtractError("Frame budget must be at least 1.")
    if interval <= 0:
        raise FrameExtractError("Frame interval must be greater than 0.")

    endpoint_reserve = 1 if budget > 1 and duration and duration > 0.5 else 0
    interval_budget = max(1, budget - endpoint_reserve)
    interval_dir = destination / "interval"
    interval_frames, interval_error = _extract_interval(
        video=video,
        ffmpeg=ffmpeg,
        destination=interval_dir,
        interval=interval,
        budget=interval_budget,
        max_width=max_width,
        stream_index=stream_index,
        duration=duration,
    )
    if not interval_frames and stream_index is not None:
        interval_frames, retry_error = _extract_interval(
            video=video,
            ffmpeg=ffmpeg,
            destination=interval_dir,
            interval=interval,
            budget=interval_budget,
            max_width=max_width,
            stream_index=None,
            duration=duration,
        )
        interval_error = None if interval_frames else (retry_error or interval_error)

    frames: list[ExtractedFrame] = list(interval_frames)
    estimate_only = bool(
        interval_error
        and interval_error.startswith("Some frame timestamps were estimated")
    )
    coverage = _coverage(
        frame_count=len(interval_frames),
        budget=interval_budget,
        last_timestamp=interval_frames[-1].timestamp_seconds if interval_frames else None,
        duration=duration,
        interval=interval,
        extractor_failed=bool(interval_error) and not estimate_only and not frames,
    )
    if estimate_only:
        warnings.append(interval_error or "")
        interval_error = None
    if interval_error and frames:
        warnings.append(interval_error)
        coverage = "incomplete"
    elif interval_error and not frames:
        fallback, fallback_error = _extract_single(
            video=video,
            ffmpeg=ffmpeg,
            destination=destination / "fallback_0001.jpg",
            timestamp=0.0,
            max_width=max_width,
            stream_index=stream_index,
            duration=duration,
        )
        if fallback is None:
            detail = fallback_error or interval_error
            raise FrameExtractError(detail)
        frames.append(
            ExtractedFrame(path=fallback, timestamp_seconds=0.0, source="fallback")
        )
        warnings.append(interval_error)
        coverage = "sampled" if duration is not None and duration <= interval else "incomplete"

    if endpoint_reserve and duration is not None and len(frames) < budget:
        end_ts = max(0.0, duration - 0.75)
        if _far_from(end_ts, frames, gap=0.5):
            end_path, end_error = _extract_single(
                video=video,
                ffmpeg=ffmpeg,
                destination=destination / "endpoint.jpg",
                timestamp=end_ts,
                max_width=max_width,
                stream_index=stream_index,
                duration=duration,
                from_end=True,
            )
            if end_path is not None:
                frames.append(
                    ExtractedFrame(path=end_path, timestamp_seconds=end_ts, source="endpoint")
                )
            elif end_error:
                warnings.append(f"End frame was not extracted: {end_error}")

    remaining = budget - len(frames)
    if scene_detection and remaining > 0:
        scene_frames, scene_error = _extract_scene_changes(
            video=video,
            ffmpeg=ffmpeg,
            destination=destination / "scene",
            threshold=scene_threshold,
            budget=remaining,
            max_width=max_width,
            stream_index=stream_index,
            duration=duration,
        )
        if scene_error:
            warnings.append(scene_error)
        for frame in scene_frames:
            if len(frames) >= budget:
                break
            if _far_from(frame.timestamp_seconds, frames, gap=1.0):
                frames.append(frame)

    frames.sort(key=lambda item: item.timestamp_seconds)
    if not frames:
        raise FrameExtractError("No frames could be extracted.")
    return frames, coverage, warnings


def extract_at_timestamps(
    video: Path,
    ffmpeg: str,
    destination: Path,
    timestamps: list[float],
    max_width: int,
    stream_index: int | None,
    duration: float | None,
) -> tuple[list[ExtractedFrame], list[str]]:
    """Extract specific extra timestamps. Failures are returned as warnings."""
    destination.mkdir(parents=True, exist_ok=True)
    frames: list[ExtractedFrame] = []
    warnings: list[str] = []
    for index, timestamp in enumerate(timestamps):
        path, error = _extract_single(
            video=video,
            ffmpeg=ffmpeg,
            destination=destination / f"extra_{index:03d}.jpg",
            timestamp=timestamp,
            max_width=max_width,
            stream_index=stream_index,
            duration=duration,
        )
        if path is None:
            warnings.append(error or f"Could not extract frame at {timestamp:.2f}s.")
            continue
        frames.append(
            ExtractedFrame(path=path, timestamp_seconds=timestamp, source="resample")
        )
    return frames, warnings


def load_frame(path: Path, max_width: int) -> np.ndarray:
    """Load a JPEG as BGR and scale it down, preserving aspect ratio."""
    image = _imread(path)
    if image is None:
        raise FrameExtractError(f"OpenCV could not read {path.name}.")
    height, width = image.shape[:2]
    if width > max_width and width > 0:
        new_height = max(2, int(round(height * (max_width / float(width)))))
        if new_height % 2:
            new_height -= 1
        new_height = max(2, new_height)
        image = cv2.resize(image, (max_width, new_height), interpolation=cv2.INTER_AREA)
    return image


def write_evidence_frame(image: np.ndarray, destination: Path) -> None:
    """Save a clear JPEG of a flagged frame so it can be checked by eye."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    _imwrite(destination, image, quality=85)


def _coverage(
    frame_count: int,
    budget: int,
    last_timestamp: float | None,
    duration: float | None,
    interval: float,
    extractor_failed: bool,
) -> str:
    if extractor_failed or frame_count == 0 or duration is None or last_timestamp is None:
        return "incomplete"
    remaining = duration - last_timestamp
    hit_cap = frame_count >= budget and remaining > interval * 1.05
    if hit_cap:
        return "limited_sample"
    return "sampled"


def _far_from(timestamp: float, frames: list[ExtractedFrame], gap: float) -> bool:
    return all(abs(timestamp - frame.timestamp_seconds) >= gap for frame in frames)


def _extract_interval(
    video: Path,
    ffmpeg: str,
    destination: Path,
    interval: float,
    budget: int,
    max_width: int,
    stream_index: int | None,
    duration: float | None,
) -> tuple[list[ExtractedFrame], str | None]:
    destination.mkdir(parents=True, exist_ok=True)
    select = (
        f"select='if(isnan(prev_selected_t),1,gte(t-prev_selected_t,{interval:.6f}))',"
        f"scale='min({max_width},iw)':-2,showinfo"
    )
    command = _base_command(ffmpeg, video, stream_index)
    command.extend(
        [
            "-vf",
            select,
            "-fps_mode",
            "vfr",
            "-frames:v",
            str(budget),
            "-q:v",
            "3",
            str(destination / "frame_%04d.jpg"),
        ]
    )
    completed, error = _run_ffmpeg(command, _timeout(duration))
    files = sorted(destination.glob("frame_*.jpg"))
    if error and not files:
        return [], error
    timestamps = _pts_times(completed.stderr if completed is not None else b"")
    frames: list[ExtractedFrame] = []
    estimated = False
    for index, file_path in enumerate(files):
        if index < len(timestamps):
            timestamp = timestamps[index]
        else:
            timestamp = index * interval
            estimated = True
        frames.append(
            ExtractedFrame(path=file_path, timestamp_seconds=timestamp, source="interval")
        )
    if estimated:
        note = "Some frame timestamps were estimated from the interval."
        error = f"{error} {note}".strip() if error else note
    return frames, error


def _extract_scene_changes(
    video: Path,
    ffmpeg: str,
    destination: Path,
    threshold: float,
    budget: int,
    max_width: int,
    stream_index: int | None,
    duration: float | None,
) -> tuple[list[ExtractedFrame], str | None]:
    destination.mkdir(parents=True, exist_ok=True)
    select = (
        f"select='gt(scene,{threshold:.4f})',"
        f"scale='min({max_width},iw)':-2,showinfo"
    )
    command = _base_command(ffmpeg, video, stream_index)
    command.extend(
        [
            "-vf",
            select,
            "-fps_mode",
            "vfr",
            "-frames:v",
            str(budget),
            "-q:v",
            "3",
            str(destination / "scene_%04d.jpg"),
        ]
    )
    completed, error = _run_ffmpeg(command, _timeout(duration))
    files = sorted(destination.glob("scene_*.jpg"))
    if not files:
        if error:
            return [], "Scene detection did not add frames."
        return [], None
    timestamps = _pts_times(completed.stderr if completed is not None else b"")
    frames: list[ExtractedFrame] = []
    for index, file_path in enumerate(files):
        if index >= len(timestamps):
            break
        frames.append(
            ExtractedFrame(
                path=file_path,
                timestamp_seconds=timestamps[index],
                source="scene",
            )
        )
    return frames, None


def _extract_single(
    video: Path,
    ffmpeg: str,
    destination: Path,
    timestamp: float,
    max_width: int,
    stream_index: int | None,
    duration: float | None,
    from_end: bool = False,
) -> tuple[Path | None, str | None]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
    ]
    if from_end:
        command.extend(["-sseof", "-0.75"])
    else:
        command.extend(["-ss", f"{max(0.0, timestamp):.3f}"])
    command.extend(["-i", str(video)])
    if stream_index is not None:
        command.extend(["-map", f"0:{stream_index}"])
    command.extend(
        [
            "-frames:v",
            "1",
            "-vf",
            f"scale='min({max_width},iw)':-2",
            "-q:v",
            "3",
            "-y",
            str(destination),
        ]
    )
    _completed, error = _run_ffmpeg(command, min(180.0, _timeout(duration)))
    if destination.is_file() and destination.stat().st_size > 0:
        return destination, None
    if stream_index is not None:
        return _extract_single(
            video=video,
            ffmpeg=ffmpeg,
            destination=destination,
            timestamp=timestamp,
            max_width=max_width,
            stream_index=None,
            duration=duration,
            from_end=from_end,
        )
    return None, error or "FFmpeg produced no frame."


def _base_command(ffmpeg: str, video: Path, stream_index: int | None) -> list[str]:
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "info",
        "-i",
        str(video),
    ]
    if stream_index is not None:
        command.extend(["-map", f"0:{stream_index}"])
    return command


def _run_ffmpeg(
    command: list[str],
    timeout: float,
) -> tuple[subprocess.CompletedProcess[bytes] | None, str | None]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return None, "FFmpeg timed out while extracting frames."
    except OSError as exc:
        return None, f"FFmpeg failed to start: {exc.strerror or exc}"
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        # showinfo writes to stderr even on success; a non-zero code is the failure.
        tail = _compact_ffmpeg_error(detail)
        return completed, tail or f"FFmpeg exited with code {completed.returncode}."
    return completed, None


def _compact_ffmpeg_error(stderr: str) -> str:
    lines = [
        line.strip()
        for line in stderr.splitlines()
        if line.strip() and "pts_time:" not in line and not line.startswith("frame=")
    ]
    if not lines:
        return ""
    return " ".join(lines[-4:])[:500]


def _pts_times(stderr: bytes) -> list[float]:
    text = stderr.decode("utf-8", errors="replace")
    times: list[float] = []
    for match in _PTS_TIME.finditer(text):
        try:
            times.append(float(match.group(1)))
        except ValueError:
            continue
    return times


def _timeout(duration: float | None) -> float:
    if duration is None or duration <= 0:
        return 300.0
    return float(min(1800.0, max(90.0, duration * 3.0)))


def _imread(path: Path) -> np.ndarray | None:
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def _imwrite(path: Path, image: np.ndarray, quality: int = 85) -> None:
    ok, encoded = cv2.imencode(
        ".jpg",
        image,
        [int(cv2.IMWRITE_JPEG_QUALITY), quality],
    )
    if not ok:
        raise FrameExtractError(f"Could not encode thumbnail {path.name}.")
    encoded.tofile(str(path))
