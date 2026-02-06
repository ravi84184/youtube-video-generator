import os
import argparse
import shutil
import subprocess
from pathlib import Path


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


def _which_or_raise(binary_name: str) -> str:
    path = shutil.which(binary_name)
    if not path:
        raise FileNotFoundError(
            f"{binary_name} is not available on PATH. Install ffmpeg and retry "
            "(e.g., `choco install ffmpeg` on Windows, or add ffmpeg/bin to PATH)."
        )
    return path


def change_speed_single(
    ffmpeg_path: str,
    input_path: Path,
    output_path: Path,
    speed: float,
):
    """
    Change playback speed of a single file.

    - speed > 1.0: faster (e.g. 1.1x)
    - speed < 1.0: slower (e.g. 0.5x)
    """
    # Video speed via setpts (timebase): new_pts = old_pts / speed
    setpts_expr = f"{1/speed}*PTS"

    # Audio speed via atempo:
    # atempo supports 0.5x–2.0x; our expected values (0.5, 1.0, 1.1, etc.) are fine.
    atempo_filters = []
    remaining = speed
    # If someone passes extreme values, chain filters in 0.5–2.0 range
    while remaining < 0.5 or remaining > 2.0:
        if remaining > 2.0:
            atempo_filters.append("atempo=2.0")
            remaining /= 2.0
        else:  # remaining < 0.5
            atempo_filters.append("atempo=0.5")
            remaining /= 0.5
    atempo_filters.append(f"atempo={remaining}")
    atempo_str = ",".join(atempo_filters)

    filter_complex = f"[0:v]setpts={setpts_expr}[v];[0:a]{atempo_str}[a]"

    cmd = [
        ffmpeg_path,
        "-y",
        "-i",
        str(input_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-strict",
        "-2",
        str(output_path),
    ]

    print(
        f"Changing speed for: {input_path.name} -> {output_path.name} (speed={speed}x)"
    )
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def change_speed_folder(input_dir: str, output_dir: str, speed: float, overwrite: bool):
    if speed <= 0:
        raise ValueError(
            "Speed must be > 0 (e.g. 1.1 for 10% faster, 0.5 for half speed)."
        )

    in_path = Path(input_dir)
    out_path = Path(output_dir)

    if not in_path.exists():
        raise FileNotFoundError(f"Input folder does not exist: {in_path}")
    out_path.mkdir(parents=True, exist_ok=True)

    ffmpeg_path = _which_or_raise("ffmpeg")

    video_files = [
        p for p in sorted(in_path.iterdir()) if p.suffix.lower() in VIDEO_EXTENSIONS
    ]

    if not video_files:
        print(
            f"No video files found in {in_path} with extensions {sorted(VIDEO_EXTENSIONS)}"
        )
        return

    print(f"Using ffmpeg at: {ffmpeg_path}")
    print(f"Found {len(video_files)} video(s) in {in_path}")

    for src in video_files:
        dst = out_path / src.name
        if dst.exists() and not overwrite:
            print(f"Skipping existing file (use --overwrite to replace): {dst}")
            continue

        try:
            change_speed_single(ffmpeg_path, src, dst, speed)
        except subprocess.CalledProcessError as e:
            print(f"Failed to process {src}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Batch change playback speed for all videos in a folder "
            "(e.g. 1.1x faster or 0.5x slower)."
        )
    )
    parser.add_argument(
        "--input_dir",
        required=True,
        help="Folder containing source videos.",
    )
    parser.add_argument(
        "--output_dir",
        required=True,
        help="Folder where converted videos will be written.",
    )
    parser.add_argument(
        "--speed",
        type=float,
        required=True,
        help="Speed factor (e.g. 1.1 for about 10%% faster, 0.5 for half speed). Must be > 0.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing files in output_dir.",
    )

    args = parser.parse_args()
    try:
        change_speed_folder(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            speed=args.speed,
            overwrite=args.overwrite,
        )
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
