import os
import json
import argparse
import shutil
import subprocess


def _which_or_raise(binary_name: str) -> str:
    path = shutil.which(binary_name)
    if not path:
        raise FileNotFoundError(
            f"{binary_name} is not available on PATH. Install ffmpeg/ffprobe and retry "
            "(e.g., `choco install ffmpeg` on Windows, or add ffmpeg/bin to PATH)."
        )
    return path


def get_duration_seconds(input_path: str) -> float:
    ffprobe_path = _which_or_raise("ffprobe")
    cmd = [
        ffprobe_path,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        input_path,
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    duration = None

    # Prefer container duration
    fmt = data.get("format") or {}
    if "duration" in fmt:
        try:
            duration = float(fmt["duration"])
        except (TypeError, ValueError):
            duration = None

    # Fallback: first video stream duration
    if duration is None:
        for s in data.get("streams") or []:
            if s.get("codec_type") == "video" and "duration" in s:
                try:
                    duration = float(s["duration"])
                    break
                except (TypeError, ValueError):
                    continue

    if duration is None:
        raise RuntimeError("Could not determine video duration via ffprobe.")
    return duration


def trim_video(
    input_path: str,
    output_path: str,
    start_seconds: float = 0.0,
    end_seconds: float = 0.0,
    copy: bool = False,
):
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file does not exist: {input_path}")
    if start_seconds < 0 or end_seconds < 0:
        raise ValueError("--start and --end must be >= 0")

    ffmpeg_path = _which_or_raise("ffmpeg")
    duration = get_duration_seconds(input_path)
    out_duration = duration - float(start_seconds) - float(end_seconds)

    if out_duration <= 0:
        raise ValueError(
            f"Trim is too aggressive. duration={duration:.3f}s, "
            f"start={start_seconds:.3f}s, end={end_seconds:.3f}s"
        )

    # Fast + accurate enough: seek then output exact duration
    ffmpeg_cmd = [
        ffmpeg_path,
        "-y",
        "-ss",
        str(start_seconds),
        "-i",
        input_path,
        "-t",
        str(out_duration),
    ]

    if copy:
        # Note: stream copy cuts on keyframes; may be less precise.
        ffmpeg_cmd += ["-c", "copy"]
    else:
        ffmpeg_cmd += ["-c:v", "libx264", "-c:a", "aac", "-strict", "-2"]

    ffmpeg_cmd.append(output_path)

    print(f"Using ffmpeg at: {ffmpeg_path}")
    print(f"Detected duration: {duration:.3f}s")
    print("Running:", " ".join(ffmpeg_cmd))
    subprocess.run(ffmpeg_cmd, check=True)
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Trim N seconds from the start and M seconds from the end of a video."
    )
    parser.add_argument("--input", required=True, help="Path to the input video file.")
    parser.add_argument(
        "--output", required=True, help="Path to the output video file."
    )
    parser.add_argument(
        "--start",
        type=float,
        default=0.0,
        help="Seconds to remove from the start (default: 0).",
    )
    parser.add_argument(
        "--end",
        type=float,
        default=0.0,
        help="Seconds to remove from the end (default: 0).",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Use stream copy (faster, but cuts may be less precise).",
    )

    args = parser.parse_args()
    try:
        trim_video(
            input_path=args.input,
            output_path=args.output,
            start_seconds=args.start,
            end_seconds=args.end,
            copy=args.copy,
        )
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
