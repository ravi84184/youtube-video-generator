"""Scan a folder of videos with a local NudeNet model and write one report."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

import frame_extractor
import report_html
import report_pdf
import video_processor
from config import (
    DISCLAIMER,
    MODEL_INFO,
    UNSUPPORTED_CATEGORIES,
    AppConfig,
    default_config,
)
from moderation import INTIMATE_LABELS, NUDITY_LABELS, LocalModerator, ModelError
from risk_engine import (
    assess_frames,
    empty_failure,
    enforce_restricted_policy,
    evidence_allowed,
    format_timestamp,
)

ROOT = Path(__file__).resolve().parent
LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL", "RESTRICTED", "INCOMPLETE", "FAILED")
logger = logging.getLogger("video_safety_checker")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    config = default_config()
    try:
        config = apply_arguments(config, argv)
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else 2

    problem = validate(config)
    if problem:
        print(problem, file=sys.stderr)
        return 2

    output_dir = _resolve_output(config.output_folder)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "frames").mkdir(parents=True, exist_ok=True)
    except PermissionError:
        print(f"Cannot write to the output folder: {output_dir}", file=sys.stderr)
        return 1
    except OSError as exc:
        if _is_disk_full(exc):
            print("Not enough disk space to create the output folder.", file=sys.stderr)
        else:
            print(f"Cannot create the output folder: {exc}", file=sys.stderr)
        return 1

    _configure_logging(output_dir / "scan.log")
    if config.max_concurrent_videos != 1:
        print("This build scans one video at a time. MAX_CONCURRENT_VIDEOS is ignored.")

    input_dir = config.input_folder.expanduser()
    if not input_dir.is_absolute():
        input_dir = (Path.cwd() / input_dir).resolve()
    else:
        input_dir = input_dir.resolve()
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"Input folder does not exist or is not a folder: {input_dir}", file=sys.stderr)
        return 1
    try:
        input_dir.iterdir()
    except PermissionError:
        print(f"Permission denied reading the input folder: {input_dir}", file=sys.stderr)
        return 1

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        print("FFmpeg and FFprobe must be on PATH. Neither paid APIs nor a bundled player are used.", file=sys.stderr)
        return 1

    model_path = config.model_path
    if not model_path.is_absolute():
        model_path = (ROOT / model_path).resolve()
    if not model_path.is_file():
        print(
            "Model file not found: "
            f"{model_path}\n"
            "Expected the NudeNet 3.4.2 320n weights at models/local_model.onnx.",
            file=sys.stderr,
        )
        return 1

    try:
        free = shutil.disk_usage(output_dir).free
    except OSError as exc:
        print(f"Cannot check free disk space: {exc}", file=sys.stderr)
        return 1
    if free < 100 * 1024 * 1024:
        print("Not enough free disk space (under 100 MB) to scan and write reports.", file=sys.stderr)
        return 1

    try:
        videos = video_processor.discover_videos(
            input_dir,
            recursive=config.recursive_scan,
            exclude=output_dir,
        )
    except PermissionError:
        print(f"Permission denied while listing videos in {input_dir}", file=sys.stderr)
        return 1

    print("VIDEO SAFETY CHECKER")
    print()
    print(f"Model: {MODEL_INFO['name']} ({MODEL_INFO['version']})")
    print(f"Videos discovered: {len(videos)}")
    print()
    if not videos:
        print("No supported videos found in the folder.")
        print("Supported formats: MP4, MOV, MKV, AVI, WEBM, M4V.")
        return 1

    try:
        moderator = LocalModerator(str(model_path), config.model_thresholds)
    except ModelError as exc:
        print(f"Model failed to load: {exc}", file=sys.stderr)
        logger.error("Model load failed: %s", exc)
        return 1
    except OSError as exc:
        if _is_disk_full(exc):
            print("Not enough disk space to load the model.", file=sys.stderr)
        else:
            print(f"Cannot read the model file: {exc}", file=sys.stderr)
        return 1

    cache = {} if config.force_rescan else _load_cache(output_dir / "scan_results.json", config)
    results: list[dict] = []
    interrupted = False
    try:
        for index, path in enumerate(videos, start=1):
            relative = video_processor.relative_posix(path, input_dir)
            print(f"[{index}/{len(videos)}] {relative}", flush=True)
            result = _scan_one(
                path=path,
                relative=relative,
                config=config,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                moderator=moderator,
                output_dir=output_dir,
                cache=cache,
                order=index,
            )
            results.append(result)
            _print_result(result)
    except KeyboardInterrupt:
        interrupted = True
        print()
        print("Scan interrupted. Reports include only the videos finished so far.")

    if not results and interrupted:
        return 130

    payload = _payload(config, input_dir, output_dir, results, interrupted)
    report_errors: list[str] = []
    json_path = output_dir / "scan_results.json"
    try:
        _write_json(json_path, payload)
    except OSError as exc:
        message = "Not enough disk space for scan_results.json." if _is_disk_full(exc) else str(exc)
        print(f"Could not write JSON results: {message}", file=sys.stderr)
        return 1

    if config.generate_pdf:
        try:
            report_pdf.write_pdf_report(payload, output_dir / "video_safety_report.pdf")
        except PermissionError:
            report_errors.append("PDF: permission denied.")
        except OSError as exc:
            report_errors.append(
                "PDF: not enough disk space." if _is_disk_full(exc) else f"PDF: {exc}"
            )
        except Exception as exc:
            logger.exception("PDF generation failed")
            report_errors.append(f"PDF: {exc}")
    if config.generate_html:
        try:
            report_html.write_html_report(payload, output_dir / "video_safety_report.html")
        except PermissionError:
            report_errors.append("HTML: permission denied.")
        except OSError as exc:
            report_errors.append(
                "HTML: not enough disk space." if _is_disk_full(exc) else f"HTML: {exc}"
            )
        except Exception as exc:
            logger.exception("HTML generation failed")
            report_errors.append(f"HTML: {exc}")

    _print_summary(results, output_dir, config, report_errors, interrupted)
    return 130 if interrupted else 0


def apply_arguments(config: AppConfig, argv: list[str] | None) -> AppConfig:
    parser = argparse.ArgumentParser(
        description="Scan videos locally and write a PDF and HTML safety report."
    )
    parser.add_argument("--input", help="Folder of videos to scan.")
    parser.add_argument("--output", help="Folder for the PDF, HTML, JSON, and frames.")
    parser.add_argument("--recursive", action="store_true", help="Scan nested folders.")
    parser.add_argument(
        "--force-rescan",
        action="store_true",
        help="Ignore scan_results.json and analyse every video again.",
    )
    parser.add_argument("--pdf-only", action="store_true", help="Write the PDF and JSON, not the HTML.")
    parser.add_argument("--html-only", action="store_true", help="Write the HTML and JSON, not the PDF.")
    parser.add_argument("--max-frames", type=int, help="Maximum frames analysed per video.")
    parser.add_argument(
        "--interval",
        type=float,
        help="Seconds between sampled frames. Default is 2.",
    )
    args = parser.parse_args(argv)

    if args.input:
        config.input_folder = Path(args.input)
    if args.output:
        config.output_folder = Path(args.output)
    if args.recursive:
        config.recursive_scan = True
    if args.force_rescan:
        config.force_rescan = True
    if args.pdf_only and not args.html_only:
        config.generate_pdf = True
        config.generate_html = False
    elif args.html_only and not args.pdf_only:
        config.generate_pdf = False
        config.generate_html = True
    if args.max_frames is not None:
        config.max_frames_per_video = args.max_frames
    if args.interval is not None:
        config.frame_interval_seconds = args.interval
    return config


def validate(config: AppConfig) -> str | None:
    if not str(config.input_folder):
        return 'Provide a folder with --input, or set INPUT_FOLDER in config.py.'
    if config.max_frames_per_video < 1:
        return "--max-frames must be at least 1."
    if config.frame_interval_seconds <= 0:
        return "--interval must be greater than 0."
    if config.max_frame_width < 32:
        return "MAX_FRAME_WIDTH must be at least 32."
    flag = config.model_thresholds.get("flag_score", 0.5)
    if not 0 < flag <= 1:
        return "MODEL_THRESHOLDS flag_score must be between 0 and 1."
    return None


def _scan_one(
    path: Path,
    relative: str,
    config: AppConfig,
    ffmpeg: str,
    ffprobe: str,
    moderator: LocalModerator,
    output_dir: Path,
    cache: dict[str, dict],
    order: int,
) -> dict:
    filename = path.name
    try:
        stat_before = path.stat()
        info = video_processor.probe_video(path, ffprobe)
    except video_processor.VideoAccessError as exc:
        logger.warning("Probe failed for %s: %s", relative, exc)
        return empty_failure(filename, relative, str(exc))
    except OSError as exc:
        return empty_failure(filename, relative, f"Cannot read video: {exc.strerror or exc}")

    cached = cache.get(info.sha256)
    if cached and _cache_usable(cached, output_dir):
        reused = json.loads(json.dumps(cached))
        reused["relative_path"] = relative
        reused["filename"] = filename
        logger.info("Reusing cached result for %s", relative)
        return reused

    metadata = {
        "duration_seconds": info.duration_seconds,
        "width": info.width,
        "height": info.height,
        "codec": info.codec,
        "fps": None if info.fps is None else round(info.fps, 3),
        "size_bytes": info.size_bytes,
        "format_name": info.format_name,
    }
    try:
        with tempfile.TemporaryDirectory(prefix="vsc_") as temp_name:
            temp_dir = Path(temp_name)
            extracted, coverage, warnings = frame_extractor.extract_sample_frames(
                video=path,
                ffmpeg=ffmpeg,
                destination=temp_dir,
                duration=info.duration_seconds,
                interval=config.frame_interval_seconds,
                budget=config.max_frames_per_video,
                max_width=config.max_frame_width,
                stream_index=info.stream_index,
                scene_detection=config.scene_change_detection,
                scene_threshold=config.scene_threshold,
            )
            classified, infer_warnings = _classify_frames(
                extracted,
                moderator,
                config.max_frame_width,
            )
            warnings.extend(infer_warnings)
            if not classified:
                return _failed_with_metadata(
                    filename, relative, info.sha256, metadata, "Every extracted frame failed."
                )
            if infer_warnings and coverage == "sampled":
                coverage = "incomplete"

            remaining = config.max_frames_per_video - len(classified)
            if config.suspicious_resample and remaining > 0:
                extra_times = _resample_times(
                    classified,
                    existing=[item["timestamp_seconds"] for item in classified],
                    offsets=config.resample_offsets_seconds,
                    duration=info.duration_seconds,
                    flag_score=float(config.model_thresholds.get("flag_score", 0.5)),
                    limit=remaining,
                )
                if extra_times:
                    extra_frames, extra_warnings = frame_extractor.extract_at_timestamps(
                        video=path,
                        ffmpeg=ffmpeg,
                        destination=temp_dir / "resample",
                        timestamps=extra_times,
                        max_width=config.max_frame_width,
                        stream_index=info.stream_index,
                        duration=info.duration_seconds,
                    )
                    warnings.extend(extra_warnings)
                    extra_classified, extra_infer = _classify_frames(
                        extra_frames,
                        moderator,
                        config.max_frame_width,
                    )
                    warnings.extend(extra_infer)
                    classified.extend(extra_classified)
                    classified.sort(key=lambda item: item["timestamp_seconds"])

            assessed = assess_frames(
                classified,
                coverage=coverage,
                thresholds=config.model_thresholds,
                interval_seconds=config.frame_interval_seconds,
                warnings=warnings,
            )
            if config.save_evidence_frames and evidence_allowed(assessed):
                _attach_evidence(assessed, classified, output_dir, order)
            previous_evidence = list(assessed.get("evidence") or [])
            assessed = enforce_restricted_policy(assessed)
            if previous_evidence and not assessed.get("evidence"):
                for item in previous_evidence:
                    preview = output_dir / str(item.get("path", ""))
                    if preview.is_file():
                        preview.unlink()
    except frame_extractor.FrameExtractError as exc:
        logger.warning("Frame extraction failed for %s: %s", relative, exc)
        return _failed_with_metadata(filename, relative, info.sha256, metadata, str(exc))
    except ModelError as exc:
        logger.exception("Inference failed for %s", relative)
        return _failed_with_metadata(filename, relative, info.sha256, metadata, str(exc))
    except PermissionError as exc:
        return _failed_with_metadata(
            filename, relative, info.sha256, metadata, f"Permission error: {exc}"
        )
    except OSError as exc:
        if _is_disk_full(exc):
            message = "Not enough disk space while scanning this video."
        else:
            message = f"File error: {exc.strerror or exc}"
        return _failed_with_metadata(filename, relative, info.sha256, metadata, message)
    except Exception as exc:
        logger.error("Unexpected failure on %s\n%s", relative, traceback.format_exc())
        return _failed_with_metadata(filename, relative, info.sha256, metadata, str(exc))

    stat_after = path.stat()
    if stat_after.st_mtime != stat_before.st_mtime or stat_after.st_size != stat_before.st_size:
        logger.error("Original video changed during the scan: %s", relative)

    assessed["filename"] = filename
    assessed["relative_path"] = relative
    assessed["sha256"] = info.sha256
    assessed["metadata"] = metadata
    return assessed


def _classify_frames(frames, moderator: LocalModerator, max_width: int) -> tuple[list[dict], list[str]]:
    classified: list[dict] = []
    warnings: list[str] = []
    for frame in frames:
        try:
            image = frame_extractor.load_frame(frame.path, max_width)
            detections = moderator.classify(image)
        except (frame_extractor.FrameExtractError, ModelError, OSError) as exc:
            warnings.append(
                f"Frame at {format_timestamp(frame.timestamp_seconds)} was skipped: {exc}"
            )
            continue
        classified.append(
            {
                "timestamp_seconds": frame.timestamp_seconds,
                "source": frame.source,
                "image_path": frame.path,
                "detections": [
                    {"label": detection.label, "score": detection.score}
                    for detection in detections
                ],
            }
        )
    return classified, warnings


def _resample_times(
    classified: list[dict],
    existing: list[float],
    offsets: tuple[float, ...],
    duration: float | None,
    flag_score: float,
    limit: int,
) -> list[float]:
    wanted: list[float] = []
    occupied = list(existing)
    for frame in classified:
        scoring = [
            detection
            for detection in frame["detections"]
            if detection["label"] in INTIMATE_LABELS | NUDITY_LABELS
            and float(detection["score"]) >= flag_score
        ]
        if not scoring:
            continue
        for offset in offsets:
            timestamp = float(frame["timestamp_seconds"]) + float(offset)
            if timestamp < 0:
                continue
            if duration is not None and timestamp > max(0.0, duration - 0.05):
                continue
            if any(abs(timestamp - other) < 1.0 for other in occupied):
                continue
            wanted.append(timestamp)
            occupied.append(timestamp)
            if len(wanted) >= limit:
                return wanted
    return wanted


def _attach_evidence(result: dict, classified: list[dict], output_dir: Path, order: int) -> None:
    by_time = {round(float(item["timestamp_seconds"]), 3): item for item in classified}
    flagged = [frame for frame in result["frames"] if frame["flagged"]]
    flagged.sort(key=lambda frame: frame["score"], reverse=True)
    stem = "".join(
        character if character.isalnum() else "_" for character in Path(result.get("filename", "video")).stem
    )[:40] or "video"
    evidence: list[dict] = []
    for frame in flagged[:8]:
        source = by_time.get(round(float(frame["timestamp_seconds"]), 3))
        if source is None:
            continue
        try:
            image = frame_extractor.load_frame(source["image_path"], 480)
            millis = int(round(float(frame["timestamp_seconds"]) * 1000))
            name = f"{order:04d}_{stem}_{millis:09d}.jpg"
            destination = output_dir / "frames" / name
            frame_extractor.write_evidence_frame(image, destination)
        except (frame_extractor.FrameExtractError, OSError) as exc:
            result.setdefault("warnings", []).append(f"Preview was not saved: {exc}")
            continue
        evidence.append(
            {
                "timestamp": frame["timestamp"],
                "path": f"frames/{name}",
                "categories": frame["categories"],
            }
        )
    result["evidence"] = evidence


def _failed_with_metadata(filename, relative, sha256, metadata, message: str) -> dict:
    result = empty_failure(filename, relative, message, sha256=sha256)
    result["metadata"] = metadata
    return result


def _cache_usable(cached: dict, output_dir: Path) -> bool:
    if cached.get("risk_level") in {"FAILED", "INCOMPLETE"}:
        return False
    if cached.get("analysis_completeness") in {"failed", "incomplete"}:
        return False
    for item in cached.get("evidence") or []:
        if not (output_dir / str(item.get("path", ""))).is_file():
            return False
    return True


def _load_cache(path: Path, config: AppConfig) -> dict[str, dict]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Ignoring unreadable previous results at %s", path)
        return {}
    if payload.get("settings_fingerprint") != config.settings_fingerprint():
        return {}
    cached: dict[str, dict] = {}
    for video in payload.get("videos") or []:
        digest = video.get("sha256")
        if digest:
            cached[digest] = video
    return cached


def _payload(config, input_dir, output_dir, results, interrupted: bool) -> dict:
    from datetime import datetime

    summary = {level: 0 for level in LEVELS}
    summary["total"] = len(results)
    for result in results:
        level = str(result.get("risk_level") or "FAILED")
        summary[level] = summary.get(level, 0) + 1
    return {
        "generated_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
        "input_folder": str(input_dir),
        "output_folder": str(output_dir),
        "recursive": config.recursive_scan,
        "interrupted": interrupted,
        "model": MODEL_INFO,
        "unsupported_categories": UNSUPPORTED_CATEGORIES,
        "disclaimer": DISCLAIMER,
        "settings": {
            "frame_interval_seconds": config.frame_interval_seconds,
            "max_frames_per_video": config.max_frames_per_video,
            "max_frame_width": config.max_frame_width,
            "scene_change_detection": config.scene_change_detection,
            "suspicious_resample": config.suspicious_resample,
        },
        "settings_fingerprint": config.settings_fingerprint(),
        "summary": summary,
        "videos": results,
    }


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _print_result(result: dict) -> None:
    print(f"Frames analysed: {result['frames_analysed']}", flush=True)
    print(f"Risk: {result['risk_level']}", flush=True)
    timestamps = result.get("flagged_timestamps") or []
    if timestamps:
        print(f"Flagged timestamps: {', '.join(timestamps)}", flush=True)
    if result.get("error"):
        print(f"Error: {result['error']}", flush=True)
    print(flush=True)


def _print_summary(results, output_dir: Path, config: AppConfig, report_errors: list[str], interrupted: bool) -> None:
    counts = {level: 0 for level in LEVELS}
    for result in results:
        level = str(result.get("risk_level") or "FAILED")
        counts[level] = counts.get(level, 0) + 1
    print("SCAN COMPLETED" if not interrupted else "SCAN INTERRUPTED")
    print()
    print(f"Total: {len(results)}")
    print(f"LOW: {counts['LOW']}")
    print(f"MEDIUM: {counts['MEDIUM']}")
    print(f"HIGH: {counts['HIGH']}")
    print(f"CRITICAL: {counts['CRITICAL']}")
    if counts["RESTRICTED"]:
        print(f"RESTRICTED: {counts['RESTRICTED']}")
    print(f"INCOMPLETE: {counts['INCOMPLETE']}")
    print(f"FAILED: {counts['FAILED']}")
    print()
    print("Reports generated:")
    written = [output_dir / "scan_results.json"]
    if config.generate_pdf and not any(item.startswith("PDF") for item in report_errors):
        written.append(output_dir / "video_safety_report.pdf")
    if config.generate_html and not any(item.startswith("HTML") for item in report_errors):
        written.append(output_dir / "video_safety_report.html")
    for path in written:
        print(f"- {path.name}")
    if report_errors:
        print("Report errors:")
        for item in report_errors:
            print(f"- {item}")


def _resolve_output(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (ROOT / path).resolve()


def _configure_logging(path: Path) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(path, encoding="utf-8")],
        force=True,
    )


def _is_disk_full(exc: OSError) -> bool:
    winerror = getattr(exc, "winerror", None)
    return exc.errno == 28 or winerror == 112


if __name__ == "__main__":
    sys.exit(main())
