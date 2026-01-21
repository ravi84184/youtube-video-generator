import os
import argparse
import shutil
import subprocess


def convert_to_portrait(
    input_path,
    output_path,
    width=1080,
    height=1920,
    rotate=None,
    crop_left=0,
    crop_right=0,
):
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file does not exist: {input_path}")
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise FileNotFoundError(
            "ffmpeg is not available on PATH. Install it and retry "
            "(e.g., `choco install ffmpeg` on Windows, or add ffmpeg/bin to PATH)."
        )
    # Helpful to log the exact binary being used
    print(f"Using ffmpeg at: {ffmpeg_path}")
    # Prepare ffmpeg filter for portrait conversion with padding (no cropping)
    vf_filters = []
    if rotate == 90:
        vf_filters.append("transpose=1")
    elif rotate == 180:
        vf_filters.append("transpose=2,transpose=2")
    elif rotate == 270:
        vf_filters.append("transpose=2")
    # Add crop filter if needed
    if crop_left > 0 or crop_right > 0:
        crop_expr = f"crop=iw-{crop_left + crop_right}:{'ih'}:{crop_left}:0"
        vf_filters.append(crop_expr)
    # Scale to fit inside portrait, then pad with black
    vf_filters.append(
        f"scale='min({width},iw*{height}/ih)':'min({height},ih*{width}/iw)':force_original_aspect_ratio=decrease"
    )
    vf_filters.append(f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black")
    vf_str = ",".join(vf_filters)
    ffmpeg_cmd = [
        ffmpeg_path,
        "-y",
        "-i",
        input_path,
        "-vf",
        vf_str,
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-strict",
        "-2",
        output_path,
    ]
    print("Running:", " ".join(ffmpeg_cmd))
    subprocess.run(ffmpeg_cmd, check=True)
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert a video to 9:16 portrait format (vertical) for Shorts/Reels, adding black bars if needed."
    )
    parser.add_argument("--input", required=True, help="Path to the input video file.")
    parser.add_argument(
        "--output", required=True, help="Path to save the portrait video."
    )
    parser.add_argument(
        "--width", type=int, default=480, help="Output video width (default: 1080)"
    )
    parser.add_argument(
        "--height", type=int, default=854, help="Output video height (default: 1920)"
    )
    parser.add_argument(
        "--rotate",
        type=int,
        choices=[90, 180, 270],
        help="Rotate video by degrees (90, 180, 270)",
    )
    parser.add_argument(
        "--crop_left",
        type=int,
        default=0,
        help="Crop this many pixels from the left side of the video before processing.",
    )
    parser.add_argument(
        "--crop_right",
        type=int,
        default=0,
        help="Crop this many pixels from the right side of the video before processing.",
    )
    args = parser.parse_args()
    try:
        convert_to_portrait(
            args.input,
            args.output,
            args.width,
            args.height,
            args.rotate,
            args.crop_left,
            args.crop_right,
        )
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
