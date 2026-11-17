import os
import argparse
import shutil
import subprocess


def convert_to_portrait(
    input_path,
    output_path,
    width=480,
    height=854,
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
        raise FileNotFoundError("ffmpeg not found in PATH")

    print(f"Using ffmpeg at: {ffmpeg_path}")

    # Base scale (fit inside portrait)
    base_scale = (
        f"scale='min({width},iw*{height}/ih)':'min({height},ih*{width}/iw)':"
        "force_original_aspect_ratio=decrease"
    )

    ffmpeg_cmd = [ffmpeg_path, "-y", "-i", input_path]

    # -------------------------
    # 🎬 BUILD VIDEO CHAIN SAFELY
    # -------------------------
    video_chain = "[0:v]"

    # Crop
    if crop_left > 0 or crop_right > 0:
        video_chain += f"crop=iw-{crop_left + crop_right}:ih:{crop_left}:0,"

    # Rotate
    if rotate in (90, 180, 270):
        transpose_map = {
            90: "transpose=1,",
            180: "transpose=2,transpose=2,",
            270: "transpose=2,",
        }
        video_chain += transpose_map[rotate]

    # -------------------------
    # 🎨 BACKGROUND MODES
    # -------------------------

    if bg_image:
        # Add background image input
        ffmpeg_cmd += ["-loop", "1", "-i", bg_image]

        filter_complex = (
            f"{video_chain}{base_scale}[fg];"
            f"[1:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}:(iw-{width})/2:(ih-{height})/2[bg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
        )

        ffmpeg_cmd += ["-filter_complex", filter_complex, "-shortest"]

    elif bg_blur:
        # Split foreground & background
        video_chain += "split[fg][bg];"

        filter_complex = (
            f"{video_chain}"
            f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}:(iw-{width})/2:(ih-{height})/2,"
            f"boxblur=luma_radius=20:luma_power=1:chroma_radius=20[bgblur];"
            f"[fg]{base_scale}[fgs];"
            f"[bgblur][fgs]overlay=(W-w)/2:(H-h)/2"
        )

        ffmpeg_cmd += ["-filter_complex", filter_complex]

    else:
        # Simple padding mode
        vf_filters = []

        if crop_left > 0 or crop_right > 0:
            vf_filters.append(f"crop=iw-{crop_left + crop_right}:ih:{crop_left}:0")

        if rotate == 90:
            vf_filters.append("transpose=1")
        elif rotate == 180:
            vf_filters.append("transpose=2,transpose=2")
        elif rotate == 270:
            vf_filters.append("transpose=2")

        vf_filters.append(base_scale)
        vf_filters.append(f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:{bg_color}")

        ffmpeg_cmd += ["-vf", ",".join(vf_filters)]

    # -------------------------
    # 🎥 OUTPUT SETTINGS
    # -------------------------
    ffmpeg_cmd += [
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        output_path,
    ]

    print("Running command:\n", " ".join(ffmpeg_cmd))
    subprocess.run(ffmpeg_cmd, check=True)

    print(f"✅ Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert video to portrait (9:16) for Shorts/Reels"
    )

    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)

    parser.add_argument("--width", type=int, default=480)
    parser.add_argument("--height", type=int, default=854)

    parser.add_argument("--rotate", type=int, choices=[90, 180, 270])

    parser.add_argument("--crop_left", type=int, default=0)
    parser.add_argument("--crop_right", type=int, default=0)

    parser.add_argument("--bg_color", default="black")
    parser.add_argument("--bg_image")
    parser.add_argument("--bg_blur", action="store_true")

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
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
