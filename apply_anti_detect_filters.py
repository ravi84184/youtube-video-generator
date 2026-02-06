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


def apply_anti_detect_filters(
    input_video: str,
    output_video: str,
    brightness: float = 0.02,
    contrast: float = 1.05,
    saturation: float = 1.08,
    hue: float = 0.5,
    noise: float = 0.5,
    sharpen: float = 0.3,
    rotate: float = 0.0,
    scale_factor: float = 1.0,
    fps: float = None,
    crop: str = None,
    mirror: bool = False,
    flip: bool = False,
):
    """
    Apply various filters to video to avoid copyright detection.

    Args:
        input_video: Path to input video
        output_video: Path to output video
        brightness: Brightness adjustment (-1.0 to 1.0, default: 0.02)
        contrast: Contrast multiplier (0.0 to 3.0, default: 1.05)
        saturation: Saturation multiplier (0.0 to 3.0, default: 1.08)
        hue: Hue shift in degrees (default: 0.5)
        noise: Noise/grain amount (0.0 to 1.0, default: 0.5)
        sharpen: Sharpen amount (0.0 to 1.0, default: 0.3)
        rotate: Rotation angle in degrees (default: 0.0)
        scale_factor: Scale video (e.g., 1.01 for 1% larger, default: 1.0)
        fps: Change frame rate (default: None, keeps original)
        crop: Crop video (format: "width:height:x:y" or "iw-10:ih-10:5:5")
        mirror: Mirror video horizontally (default: False)
        flip: Flip video vertically (default: False)
    """
    if not os.path.exists(input_video):
        raise FileNotFoundError(f"Input video does not exist: {input_video}")

    # Check if input and output are the same file
    input_abs = os.path.abspath(input_video)
    output_abs = os.path.abspath(output_video)
    if input_abs == output_abs:
        raise ValueError(
            f"Input and output files cannot be the same: {input_video}\n"
            f"Please use a different output filename (e.g., add '_filtered' suffix)."
        )

    ffmpeg_path = _which_or_raise("ffmpeg")
    print(f"Using ffmpeg at: {ffmpeg_path}")

    # Build video filters
    vf_filters = []

    # Rotation (if specified)
    if rotate != 0.0:
        vf_filters.append(f"rotate={rotate}*PI/180:fillcolor=black@0:ow=iw:oh=ih")

    # Mirror/Flip
    if mirror:
        vf_filters.append("hflip")
    if flip:
        vf_filters.append("vflip")

    # Scale (slight zoom to avoid edge detection)
    if scale_factor != 1.0:
        vf_filters.append(f"scale=iw*{scale_factor}:ih*{scale_factor}")
        # After scaling, crop back to original size (centered)
        # Crop to 1/scale_factor of the scaled size, centered
        inv_scale = 1.0 / scale_factor
        # Inline expressions for crop
        vf_filters.append(
            f"crop=iw*{inv_scale}:ih*{inv_scale}:(iw-iw*{inv_scale})/2:(ih-ih*{inv_scale})/2"
        )

    # Crop (if explicitly specified by user - must be a non-empty string)
    # Only add if crop is a string and not None/empty
    if crop is not None and isinstance(crop, str) and crop.strip():
        vf_filters.append(f"crop={crop}")

    # Color adjustments
    color_filters = []

    # Brightness/Contrast
    if brightness != 0.0 or contrast != 1.0:
        color_filters.append(f"eq=brightness={brightness}:contrast={contrast}")

    # Saturation
    if saturation != 1.0:
        color_filters.append(f"eq=saturation={saturation}")

    # Hue shift
    if hue != 0.0:
        color_filters.append(f"hue=h={hue}")

    if color_filters:
        vf_filters.extend(color_filters)

    # Sharpen (subtle)
    if sharpen > 0.0:
        vf_filters.append(f"unsharp=5:5:{sharpen}:5:5:0.0")

    # Noise/Grain (subtle to avoid detection)
    if noise > 0.0:
        vf_filters.append(f"noise=alls={noise}:allf=t+u")

    # Build filter chain
    vf_str = ",".join(vf_filters) if vf_filters else None

    # Build ffmpeg command
    ffmpeg_cmd = [ffmpeg_path, "-y", "-i", input_video]

    if vf_str:
        ffmpeg_cmd += ["-vf", vf_str]

    # Frame rate change (if specified)
    if fps:
        ffmpeg_cmd += ["-r", str(fps)]

    # Video codec settings
    ffmpeg_cmd += [
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "23",  # Good quality
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",  # Web optimization
        output_video,
    ]

    print("Running:", " ".join(ffmpeg_cmd))
    subprocess.run(ffmpeg_cmd, check=True)
    print(f"Saved: {output_video}")


def apply_preset(preset_name: str):
    """Return filter values for a preset."""
    presets = {
        "subtle": {
            "brightness": 0.02,
            "contrast": 1.05,
            "saturation": 1.08,
            "hue": 0.5,
            "noise": 0.3,
            "sharpen": 0.2,
            "scale": 1.01,
        },
        "medium": {
            "brightness": 0.05,
            "contrast": 1.1,
            "saturation": 1.15,
            "hue": 1.0,
            "noise": 0.5,
            "sharpen": 0.3,
            "scale": 1.02,
        },
        "aggressive": {
            "brightness": 0.1,
            "contrast": 1.15,
            "saturation": 1.2,
            "hue": 2.0,
            "noise": 0.7,
            "sharpen": 0.4,
            "scale": 1.03,
            "rotate": 0.2,
        },
        "minimal": {
            "brightness": 0.01,
            "contrast": 1.02,
            "saturation": 1.05,
            "hue": 0.3,
            "noise": 0.2,
            "sharpen": 0.1,
            "scale": 1.005,
        },
    }
    return presets.get(preset_name.lower(), {})


def main():
    parser = argparse.ArgumentParser(
        description="Apply anti-detection filters to video to avoid copyright detection."
    )
    parser.add_argument("--input", required=True, help="Path to input video file.")
    parser.add_argument("--output", required=True, help="Path to output video file.")

    # Preset mode
    parser.add_argument(
        "--preset",
        choices=["subtle", "medium", "aggressive", "minimal"],
        help="Use a preset filter combination (overrides individual filter settings)",
    )

    # Color adjustments
    parser.add_argument(
        "--brightness",
        type=float,
        default=0.02,
        help="Brightness adjustment (-1.0 to 1.0, default: 0.02)",
    )
    parser.add_argument(
        "--contrast",
        type=float,
        default=1.05,
        help="Contrast multiplier (0.0 to 3.0, default: 1.05)",
    )
    parser.add_argument(
        "--saturation",
        type=float,
        default=1.08,
        help="Saturation multiplier (0.0 to 3.0, default: 1.08)",
    )
    parser.add_argument(
        "--hue",
        type=float,
        default=0.5,
        help="Hue shift in degrees (default: 0.5)",
    )

    # Visual effects
    parser.add_argument(
        "--noise",
        type=float,
        default=0.5,
        help="Noise/grain amount (0.0 to 1.0, default: 0.5)",
    )
    parser.add_argument(
        "--sharpen",
        type=float,
        default=0.3,
        help="Sharpen amount (0.0 to 1.0, default: 0.3)",
    )

    # Transformations
    parser.add_argument(
        "--rotate",
        type=float,
        default=0.0,
        help="Rotation angle in degrees (default: 0.0)",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Scale factor (e.g., 1.01 for 1%% larger, default: 1.0)",
    )
    parser.add_argument(
        "--crop",
        type=str,
        help="Crop video (format: 'width:height:x:y' or 'iw-10:ih-10:5:5')",
    )
    parser.add_argument(
        "--mirror",
        action="store_true",
        help="Mirror video horizontally",
    )
    parser.add_argument(
        "--flip",
        action="store_true",
        help="Flip video vertically",
    )

    # Frame rate
    parser.add_argument(
        "--fps",
        type=float,
        help="Change frame rate (e.g., 29.97, 30, 60). Keeps original if not set.",
    )

    args = parser.parse_args()

    # Apply preset if specified
    if args.preset:
        preset_values = apply_preset(args.preset)
        print(f"Using preset: {args.preset}")
        # Use preset values, but user-provided values override preset
        brightness = preset_values.get("brightness", args.brightness)
        contrast = preset_values.get("contrast", args.contrast)
        saturation = preset_values.get("saturation", args.saturation)
        hue = preset_values.get("hue", args.hue)
        noise = preset_values.get("noise", args.noise)
        sharpen = preset_values.get("sharpen", args.sharpen)
        rotate = preset_values.get("rotate", args.rotate)
        scale = preset_values.get("scale", args.scale)
    else:
        brightness = args.brightness
        contrast = args.contrast
        saturation = args.saturation
        hue = args.hue
        noise = args.noise
        sharpen = args.sharpen
        rotate = args.rotate
        scale = args.scale

    try:
        apply_anti_detect_filters(
            args.input,
            args.output,
            brightness,
            contrast,
            saturation,
            hue,
            noise,
            sharpen,
            rotate,
            scale,
            args.crop,
            args.mirror,
            args.flip,
            args.fps,
        )
    except Exception as e:
        print(f"Error: {e}")
        return 1
    return 0


if __name__ == "__main__":
    exit(main())
