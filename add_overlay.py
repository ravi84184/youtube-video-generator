import os
import argparse
import shutil
import subprocess
import json


def _which_or_raise(binary_name: str) -> str:
    path = shutil.which(binary_name)
    if not path:
        raise FileNotFoundError(
            f"{binary_name} is not available on PATH. Install it and retry "
            "(e.g., `choco install ffmpeg` on Windows, or add ffmpeg/bin to PATH)."
        )
    return path


def get_video_duration(input_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    ffprobe_path = _which_or_raise("ffprobe")
    cmd = [
        ffprobe_path,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        input_path,
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    duration = data.get("format", {}).get("duration")
    if duration:
        return float(duration)
    raise RuntimeError("Could not determine video duration.")


def add_overlay(
    input_video: str,
    overlay_file: str,
    output_video: str,
    x: int = None,
    y: int = None,
    width: int = None,
    height: int = None,
    scale: float = None,
    animate: str = None,
    speed: float = 50.0,
    loop_duration: float = None,
):
    """
    Add an overlay (GIF, PNG, etc.) to a video with optional animation.

    Args:
        input_video: Path to input video
        overlay_file: Path to overlay image/GIF
        output_video: Path to output video
        x: Static X position (pixels from left). Required if animate is None.
        y: Static Y position (pixels from top). Required if animate is None.
        width: Overlay width in pixels (maintains aspect if only width or height set)
        height: Overlay height in pixels
        scale: Scale factor (e.g., 0.5 for half size, 2.0 for double)
        animate: Animation type: 'horizontal' (left-right), 'vertical' (top-bottom),
                 'horizontal_reverse' (right-left), 'vertical_reverse' (bottom-top)
        speed: Animation speed in pixels per second (default: 50)
        loop_duration: Duration in seconds for one animation cycle (overrides speed if set)
    """
    if not os.path.exists(input_video):
        raise FileNotFoundError(f"Input video does not exist: {input_video}")
    if not os.path.exists(overlay_file):
        raise FileNotFoundError(f"Overlay file does not exist: {overlay_file}")

    ffmpeg_path = _which_or_raise("ffmpeg")
    print(f"Using ffmpeg at: {ffmpeg_path}")

    # Get video duration to limit processing
    try:
        video_duration = get_video_duration(input_video)
        print(f"Video duration: {video_duration:.2f} seconds")
    except Exception as e:
        print(
            f"Warning: Could not get video duration: {e}. Processing may take longer."
        )
        video_duration = None

    # Build overlay filter
    overlay_filters = []

    # Scale overlay if needed
    if scale is not None:
        overlay_filters.append(f"scale=iw*{scale}:ih*{scale}")
    elif width is not None or height is not None:
        if width and height:
            overlay_filters.append(f"scale={width}:{height}")
        elif width:
            overlay_filters.append(f"scale={width}:-1")
        elif height:
            overlay_filters.append(f"scale=-1:{height}")

    # Build overlay expression for position
    if animate:
        # Format speed as integer if whole number, otherwise keep as float
        speed_str = str(int(speed)) if speed == int(speed) else str(speed)
        loop_dur_str = str(loop_duration) if loop_duration else None

        # Animated movement - use proper modulo calculation
        # For looping: use fractional part of time to create smooth looping
        if animate == "horizontal":
            # Left to right, looping
            if loop_duration:
                # Use fractional part: (t/loop_duration) - floor(t/loop_duration) gives 0-1 range
                x_expr = f"((t/{loop_dur_str})-floor(t/{loop_dur_str}))*(W-w)"
            else:
                # Simple modulo using fractional part: ensures smooth looping
                # Use fractional part of (t*speed / (W-w)) to get 0-1 range, then multiply by (W-w)
                x_expr = f"((t*{speed_str}/(W-w))-floor(t*{speed_str}/(W-w)))*(W-w)"
            y_expr = str(y) if y is not None else "0"
        elif animate == "horizontal_reverse":
            # Right to left, looping
            if loop_duration:
                x_expr = f"(W-w)*(1-((t/{loop_dur_str})-floor(t/{loop_dur_str})))"
            else:
                x_expr = f"(W-w)*(1-((t*{speed_str}/(W-w))-floor(t*{speed_str}/(W-w))))"
            y_expr = str(y) if y is not None else "0"
        elif animate == "vertical":
            # Top to bottom, looping
            x_expr = str(x) if x is not None else "0"
            if loop_duration:
                y_expr = f"((t/{loop_dur_str})-floor(t/{loop_dur_str}))*(H-h)"
            else:
                y_expr = f"((t*{speed_str}/(H-h))-floor(t*{speed_str}/(H-h)))*(H-h)"
        elif animate == "vertical_reverse":
            # Bottom to top, looping
            x_expr = str(x) if x is not None else "0"
            if loop_duration:
                y_expr = f"(H-h)*(1-((t/{loop_dur_str})-floor(t/{loop_dur_str})))"
            else:
                y_expr = f"(H-h)*(1-((t*{speed_str}/(H-h))-floor(t*{speed_str}/(H-h))))"
        else:
            raise ValueError(
                f"Invalid animate value: {animate}. "
                "Use 'horizontal', 'vertical', 'horizontal_reverse', or 'vertical_reverse'"
            )
    else:
        # Static position
        if x is None or y is None:
            raise ValueError(
                "For static overlay, both --x and --y must be provided, "
                "or use --animate for animated movement."
            )
        x_expr = str(x)
        y_expr = str(y)

    # Build filter_complex
    # Input 0: video, Input 1: overlay
    if overlay_filters:
        # Scale overlay first, then overlay on video
        scale_filter = "[1:v]" + ",".join(overlay_filters) + "[overlay_scaled]"
        overlay_filter = (
            f"{scale_filter};[0:v][overlay_scaled]overlay={x_expr}:{y_expr}"
        )
    else:
        # Direct overlay without scaling
        overlay_filter = f"[0:v][1:v]overlay={x_expr}:{y_expr}"

    # Check if overlay is a GIF (needs looping)
    overlay_ext = os.path.splitext(overlay_file)[1].lower()
    is_gif = overlay_ext == ".gif"

    ffmpeg_cmd = [ffmpeg_path, "-y", "-i", input_video]

    if is_gif:
        # For GIFs, use ignore_loop to respect GIF's loop setting
        ffmpeg_cmd += ["-ignore_loop", "0", "-i", overlay_file]
    else:
        # For static images, loop it so it appears on every frame
        # The -t flag below will limit the output duration
        ffmpeg_cmd += ["-loop", "1", "-i", overlay_file]

    ffmpeg_cmd += [
        "-filter_complex",
        overlay_filter,
        "-c:v",
        "libx264",
        "-c:a",
        "copy",  # Copy audio as-is
    ]

    # Explicitly limit duration to video length to prevent infinite processing
    if video_duration:
        ffmpeg_cmd += ["-t", str(video_duration)]
    else:
        # Fallback: use shortest input
        ffmpeg_cmd += ["-shortest"]

    ffmpeg_cmd.append(output_video)

    print("Running:", " ".join(ffmpeg_cmd))
    subprocess.run(ffmpeg_cmd, check=True)
    print(f"Saved: {output_video}")


def main():
    parser = argparse.ArgumentParser(
        description="Add an overlay (GIF, PNG, etc.) to a video with optional animated movement."
    )
    parser.add_argument("--input", required=True, help="Path to input video file.")
    parser.add_argument(
        "--overlay", required=True, help="Path to overlay image/GIF file."
    )
    parser.add_argument("--output", required=True, help="Path to output video file.")
    parser.add_argument(
        "--x",
        type=int,
        help="X position (pixels from left). Required for static overlay, optional for animation.",
    )
    parser.add_argument(
        "--y",
        type=int,
        help="Y position (pixels from top). Required for static overlay, optional for animation.",
    )
    parser.add_argument(
        "--width",
        type=int,
        help="Overlay width in pixels (maintains aspect if only width set).",
    )
    parser.add_argument(
        "--height",
        type=int,
        help="Overlay height in pixels (maintains aspect if only height set).",
    )
    parser.add_argument(
        "--scale",
        type=float,
        help="Scale factor (e.g., 0.5 for half size, 2.0 for double). Alternative to --width/--height.",
    )
    parser.add_argument(
        "--animate",
        choices=["horizontal", "vertical", "horizontal_reverse", "vertical_reverse"],
        help="Animation type: 'horizontal' (left-right), 'vertical' (top-bottom), "
        "'horizontal_reverse' (right-left), 'vertical_reverse' (bottom-top). "
        "Animation loops continuously.",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=50.0,
        help="Animation speed in pixels per second (default: 50). Ignored if --loop_duration is set.",
    )
    parser.add_argument(
        "--loop_duration",
        type=float,
        help="Duration in seconds for one complete animation cycle (e.g., 5.0 for 5-second loop). "
        "Overrides --speed if set.",
    )

    args = parser.parse_args()

    try:
        add_overlay(
            args.input,
            args.overlay,
            args.output,
            args.x,
            args.y,
            args.width,
            args.height,
            args.scale,
            args.animate,
            args.speed,
            args.loop_duration,
        )
    except Exception as e:
        print(f"Error: {e}")
        return 1
    return 0


if __name__ == "__main__":
    exit(main())
