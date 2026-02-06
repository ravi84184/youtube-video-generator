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
    bg_color="black",
    bg_image=None,
    bg_blur=False,
):
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file does not exist: {input_path}")
    if bg_image and not os.path.exists(bg_image):
        raise FileNotFoundError(f"Background image does not exist: {bg_image}")
    if bg_image and bg_blur:
        raise ValueError("Choose only one background option: image or blur.")
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise FileNotFoundError(
            "ffmpeg is not available on PATH. Install it and retry "
            "(e.g., `choco install ffmpeg` on Windows, or add ffmpeg/bin to PATH)."
        )
    # Helpful to log the exact binary being used
    print(f"Using ffmpeg at: {ffmpeg_path}")
    # Build filters
    base_scale = (
        f"scale='min({width},iw*{height}/ih)':'min({height},ih*{width}/iw)':"
        "force_original_aspect_ratio=decrease"
    )

    ffmpeg_cmd = [ffmpeg_path, "-y", "-i", input_path]

    if bg_image:
        # Use external image as background
        ffmpeg_cmd += ["-loop", "1", "-i", bg_image]
        filter_complex = (
            f"[1:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}:(iw-{width})/2:(ih-{height})/2[bg];"
            f"[0:v]{base_scale}[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
        )
        if rotate in (90, 180, 270):
            # rotate foreground before overlay if requested
            transpose_map = {
                90: "transpose=1",
                180: "transpose=2,transpose=2",
                270: "transpose=2",
            }
            filter_complex = filter_complex.replace(
                "[0:v]", f"[0:v]{transpose_map[rotate]}"
            )
        if crop_left > 0 or crop_right > 0:
            crop_expr = f"crop=iw-{crop_left + crop_right}:{'ih'}:{crop_left}:0"
            filter_complex = filter_complex.replace("[0:v]", f"[0:v]{crop_expr}")
        ffmpeg_cmd += ["-filter_complex", filter_complex, "-shortest"]
    elif bg_blur:
        # Use blurred copy of the same video as background
        blur_filter = (
            f"[0:v]split[fg][bg];"
            f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}:(iw-{width})/2:(ih-{height})/2,"
            f"boxblur=luma_radius=20:luma_power=1:chroma_radius=20[bgblur];"
            f"[fg]{base_scale}[fgs];"
            f"[bgblur][fgs]overlay=(W-w)/2:(H-h)/2"
        )
        if rotate in (90, 180, 270):
            transpose_map = {
                90: "transpose=1",
                180: "transpose=2,transpose=2",
                270: "transpose=2",
            }
            blur_filter = blur_filter.replace(
                "[0:v]", f"[0:v]{transpose_map[rotate]}", 1
            )
        if crop_left > 0 or crop_right > 0:
            crop_expr = f"crop=iw-{crop_left + crop_right}:{'ih'}:{crop_left}:0"
            blur_filter = blur_filter.replace("[0:v]", f"[0:v]{crop_expr}", 1)
        ffmpeg_cmd += ["-filter_complex", blur_filter]
    else:
        # Simple color padding
        vf_filters = []
        if rotate == 90:
            vf_filters.append("transpose=1")
        elif rotate == 180:
            vf_filters.append("transpose=2,transpose=2")
        elif rotate == 270:
            vf_filters.append("transpose=2")
        if crop_left > 0 or crop_right > 0:
            crop_expr = f"crop=iw-{crop_left + crop_right}:{'ih'}:{crop_left}:0"
            vf_filters.append(crop_expr)
        vf_filters.append(base_scale)
        # pad color can be any ffmpeg color (e.g. "white", "0x112233", "black@0.8")
        vf_filters.append(f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:{bg_color}")
        vf_str = ",".join(vf_filters)
        ffmpeg_cmd += ["-vf", vf_str]

    ffmpeg_cmd += [
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
    parser.add_argument(
        "--bg_color",
        default="black",
        help="Pad/background color (ffmpeg color name or 0xRRGGBB, e.g., white, 0xff00aa, black@0.5).",
    )
    parser.add_argument(
        "--bg_image",
        help="Path to an image to use as the background (will be scaled/cropped to fit).",
    )
    parser.add_argument(
        "--bg_blur",
        action="store_true",
        help="Use a blurred copy of the video itself as the background.",
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
            args.bg_color,
            args.bg_image,
            args.bg_blur,
        )
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
