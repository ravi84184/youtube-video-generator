#!/usr/bin/env python

from __future__ import print_function

import csv
import json
import math
import os
import shlex
import subprocess
from optparse import OptionParser


def split_by_manifest(
    filename,
    manifest,
    output_dir=None,
    vcodec="copy",
    acodec="copy",
    extra="",
    **kwargs,
):
    """Split video into segments based on the given manifest file.

    Arguments:
        filename (str)      - Location of the video.
        manifest (str)      - Location of the manifest file.
        output_dir (str)    - Directory to save the split files.
        vcodec (str)        - Controls the video codec for the ffmpeg video
                            output.
        acodec (str)        - Controls the audio codec for the ffmpeg video
                            output.
        extra (str)         - Extra options for ffmpeg.
    """
    if not os.path.exists(manifest):
        print("File does not exist: %s" % manifest)
        raise SystemExit

    # Ensure the output directory exists
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(manifest) as manifest_file:
        manifest_type = manifest.split(".")[-1]
        if manifest_type == "json":
            config = json.load(manifest_file)
        elif manifest_type == "csv":
            config = csv.DictReader(manifest_file)
        else:
            print("Format not supported. File must be a csv or json file")
            raise SystemExit

        split_cmd = [
            "ffmpeg",
            "-i",
            filename,
            "-vcodec",
            vcodec,
            "-acodec",
            acodec,
            "-y",
        ] + shlex.split(extra)
        try:
            fileext = filename.split(".")[-1]
        except IndexError as e:
            raise IndexError("No . in filename. Error: " + str(e))

        for video_config in config:
            split_args = []
            try:
                split_start = video_config["start_time"]
                split_length = video_config.get("end_time", None)
                if not split_length:
                    split_length = video_config["length"]
                filebase = video_config["rename_to"]
                if fileext in filebase:
                    filebase = ".".join(filebase.split(".")[:-1])

                output_path = (
                    os.path.join(output_dir, filebase + ".mp4")
                    if output_dir
                    else filebase + ".mp4"
                )

                split_args += [
                    "-ss",
                    str(split_start),
                    "-t",
                    str(split_length),
                    output_path,
                ]
                print("########################################################")
                print("About to run: " + " ".join(split_cmd + split_args))
                print("########################################################")
                subprocess.check_output(split_cmd + split_args)
            except KeyError as e:
                print("############# Incorrect format ##############")
                if manifest_type == "json":
                    print("The format of each json array should be:")
                    print("{start_time: <int>, length: <int>, rename_to: <string>}")
                elif manifest_type == "csv":
                    print("start_time,length,rename_to should be the first line ")
                    print("in the csv file.")
                print("#############################################")
                print(e)
                raise SystemExit


def get_video_length(filename):
    output = subprocess.check_output(
        (
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            filename,
        )
    ).strip()
    video_length = int(float(output))
    print("Video length in seconds: " + str(video_length))

    return video_length


def ceildiv(a, b):
    return int(math.ceil(a / float(b)))


def split_by_seconds(
    filename,
    split_length,
    output_dir=None,
    vcodec="libx264",
    acodec="aac",
    extra="",
    video_length=None,
    **kwargs,
):
    if split_length and split_length <= 0:
        print("Split length can't be 0")
        raise SystemExit

    if not video_length:
        video_length = get_video_length(filename)
    split_count = ceildiv(video_length, split_length)
    if split_count == 1:
        print("Video length is less then the target split length.")
        raise SystemExit

    # Ensure the output directory exists
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    split_cmd = [
        "ffmpeg",
        "-i",
        filename,
        "-vcodec",
        vcodec,
        "-acodec",
        acodec,
    ] + shlex.split(extra)
    try:
        filebase = ".".join(filename.split(".")[:-1])
        fileext = filename.split(".")[-1]
    except IndexError as e:
        raise IndexError("No . in filename. Error: " + str(e))
    for n in range(0, split_count):
        split_args = []
        if n == 0:
            split_start = 0
        else:
            split_start = split_length * n

        output_path = (
            os.path.join(output_dir, f"{filebase}-{n+1}-of-{split_count}.mp4")
            if output_dir
            else f"{filebase}-{n+1}-of-{split_count}.mp4"
        )

        split_args += ["-ss", str(split_start), "-t", str(split_length), output_path]
        print("About to run: " + " ".join(split_cmd + split_args))
        subprocess.check_output(split_cmd + split_args)


def main():
    parser = OptionParser()

    parser.add_option(
        "-f",
        "--file",
        dest="filename",
        help="File to split, for example sample.avi",
        type="string",
        action="store",
    )
    parser.add_option(
        "-s",
        "--split-size",
        dest="split_length",
        help="Split or chunk size in seconds, for example 10",
        type="int",
        action="store",
    )
    parser.add_option(
        "-c",
        "--split-chunks",
        dest="split_chunks",
        help="Number of chunks to split to",
        type="int",
        action="store",
    )
    parser.add_option(
        "-S",
        "--split-filesize",
        dest="split_filesize",
        help="Split or chunk size in bytes (approximate)",
        type="int",
        action="store",
    )
    parser.add_option(
        "--filesize-factor",
        dest="filesize_factor",
        help="with --split-filesize, use this factor in time to"
        " size heuristics [default: %default]",
        type="float",
        action="store",
        default=0.95,
    )
    parser.add_option(
        "--chunk-strategy",
        dest="chunk_strategy",
        help="with --split-filesize, allocate chunks according to"
        " given strategy (eager or even)",
        type="choice",
        action="store",
        choices=["eager", "even"],
        default="eager",
    )
    parser.add_option(
        "-m",
        "--manifest",
        dest="manifest",
        help="Split video based on a json manifest file. ",
        type="string",
        action="store",
    )
    parser.add_option(
        "-o",
        "--output-dir",
        dest="output_dir",
        help="Directory to save split files.",
        type="string",
        action="store",
    )
    parser.add_option(
        "-v",
        "--vcodec",
        dest="vcodec",
        help="Video codec to use. ",
        type="string",
        default="copy",
        action="store",
    )
    parser.add_option(
        "-a",
        "--acodec",
        dest="acodec",
        help="Audio codec to use. ",
        type="string",
        default="copy",
        action="store",
    )
    parser.add_option(
        "-e",
        "--extra",
        dest="extra",
        help="Extra options for ffmpeg, e.g. '-e -threads 8'. ",
        type="string",
        default="",
        action="store",
    )
    parser.add_option(
        "-T",
        "--text",
        dest="text",
        help="Text to overlay on top of the video.",
        type="string",
        default=None,
        action="store",
    )
    parser.add_option(
        "--top-text",
        dest="top_text",
        help="Text to show at the top of the video (e.g., movie name).",
        type="string",
        default=None,
        action="store",
    )
    parser.add_option(
        "--bottom-text",
        dest="bottom_text",
        help="Text to show at the bottom of the video (e.g., part number, use {part} and {total} as placeholders).",
        type="string",
        default=None,
        action="store",
    )
    parser.add_option(
        "--top-fontsize",
        dest="top_fontsize",
        help="Font size for top text (default 48)",
        type="int",
        default=48,
        action="store",
    )
    parser.add_option(
        "--top-text-x",
        dest="top_text_x",
        help="X position for top text. Default centers; if --top-icon is set, you may want a fixed X like 120.",
        type="string",
        default=None,
        action="store",
    )
    parser.add_option(
        "--top-text-y",
        dest="top_text_y",
        help="Y position for top text (default 200)",
        type="int",
        default=200,
        action="store",
    )
    parser.add_option(
        "--top-icon",
        dest="top_icon",
        help="Path to an image (png/jpg) to overlay next to the top text.",
        type="string",
        default=None,
        action="store",
    )
    parser.add_option(
        "--top-icon-height",
        dest="top_icon_height",
        help="Icon height in pixels (default 64). Width auto-scales to preserve aspect ratio.",
        type="int",
        default=64,
        action="store",
    )
    parser.add_option(
        "--top-icon-x",
        dest="top_icon_x",
        help="X position for icon overlay (default 20)",
        type="int",
        default=20,
        action="store",
    )
    parser.add_option(
        "--top-icon-y",
        dest="top_icon_y",
        help="Y position for icon overlay (default 200)",
        type="int",
        default=200,
        action="store",
    )
    parser.add_option(
        "--font",
        dest="font",
        help="Font file path for text rendering (supports Hindi/Unicode)",
        type="string",
        default="/System/Library/Fonts/Arial Unicode MS.ttf",
        action="store",
    )
    parser.add_option(
        "--bg-music",
        dest="bg_music",
        help="Path to background music file to mix with video audio.",
        type="string",
        default=None,
        action="store",
    )
    parser.add_option(
        "--parts",
        dest="parts",
        help="Comma-separated list or range of parts to extract (e.g., 5,6,8 or 5-10)",
        type="string",
        default=None,
        action="store",
    )
    parser.add_option(
        "--metadata",
        dest="metadata",
        help="Comma-separated metadata key=value pairs applied to outputs. Supports {part} and {total} placeholders (e.g., title='Clip {part}/{total}',artist='My Channel').",
        type="string",
        default=None,
        action="store",
    )
    (options, args) = parser.parse_args()

    def bailout():
        parser.print_help()
        raise SystemExit

    if not options.filename:
        bailout()

    # If text is provided, add drawtext filter to extra
    if options.text:
        drawtext = f"drawtext=text='{options.text}':fontfile='{options.font}':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=20"
        if options.extra:
            if "-vf" in options.extra:
                options.extra = options.extra.replace("-vf ", f'-vf "{drawtext},')
            else:
                options.extra += f' -vf "{drawtext}"'
        else:
            options.extra = f'-vf "{drawtext}"'

    # If any overlay is requested, force vcodec/acodec unless user set them
    if options.text or options.top_text or options.bottom_text or options.top_icon:
        if not options.vcodec or options.vcodec == "copy":
            options.vcodec = "libx264"
        if not options.acodec or options.acodec == "copy":
            options.acodec = "aac"

    # Prepare drawtext filters for top and bottom text
    def build_drawtext_filters(
        top_text=None,
        bottom_text=None,
        part=None,
        total=None,
        top_fontsize=48,
        font=None,
        top_text_x=None,
        top_text_y=200,
    ):
        filters = []
        if top_text:
            x_expr = top_text_x if top_text_x else "(w-text_w)/2"
            filters.append(
                f"drawtext=text='{top_text}':fontfile='{font}':fontcolor=white:fontsize={top_fontsize}"
                f":x={x_expr}:y={top_text_y}:box=1:boxcolor=black@0.5:boxborderw=10"
            )
        if bottom_text:
            # Replace placeholders if present
            if part is not None and total is not None:
                text_val = bottom_text.replace("{part}", str(part)).replace(
                    "{total}", str(total)
                )
            else:
                text_val = bottom_text
            filters.append(
                f"drawtext=text='{text_val}':fontfile='{font}':fontcolor=white:fontsize=40:x=(w-text_w)/2:y=h-text_h-200:box=1:boxcolor=black@0.5:boxborderw=10"
            )
        return ",".join(filters) if filters else None

    def parse_metadata(metadata_str):
        """Parse metadata string like key=val,key2=val2 into list of (k, v)."""
        if not metadata_str:
            return []
        items = []
        for pair in metadata_str.split(","):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            k, v = pair.split("=", 1)
            items.append((k.strip(), v.strip().strip('"').strip("'")))
        return items

    def build_metadata_args(metadata_items, part=None, total=None):
        """Return flat list of ['-metadata','key=value', ...] with placeholders resolved."""
        if not metadata_items:
            return []
        args = []
        for k, v in metadata_items:
            val = v
            if part is not None:
                val = val.replace("{part}", str(part))
            if total is not None:
                val = val.replace("{total}", str(total))
            args.extend(["-metadata", f"{k}={val}"])
        return args

    metadata_items = parse_metadata(options.metadata)

    # Helper to build ffmpeg audio filter for background music
    def build_audio_filter(bg_music_path, video_audio_stream="0:a", music_stream="1:a"):
        # Lower background music to 0.3 volume, keep video audio at 1.0
        # [0:a] is video audio, [1:a] is bg music
        # Use filter_complex: [0:a]volume=1.0[a0];[1:a]volume=0.3[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]
        return f"[0:a]volume=1.0[a0];[1:a]volume=0.2[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]"

    # Helper to build ffmpeg input list if bg music is present
    def build_ffmpeg_inputs(filename, bg_music):
        if bg_music:
            return ["-i", filename, "-i", bg_music]
        else:
            return ["-i", filename]

    # Helper to build ffmpeg map options if bg music is present
    def build_ffmpeg_maps(bg_music):
        if bg_music:
            return ["-map", "0:v", "-map", "[aout]"]
        else:
            return []

    def build_filter_complex(
        bg_music=None,
        top_icon=None,
        top_icon_height=64,
        top_icon_x=20,
        top_icon_y=200,
        drawtext_filters=None,
        music_input_index=1,
        icon_input_index=1,
    ):
        """
        Build a single filter_complex that can produce:
          - [vout] (when top_icon is provided)
          - [aout] (when bg_music is provided)

        Notes:
          - If top_icon is not provided, video filters should be applied via -vf (existing behavior).
          - If bg_music is not provided, audio is passed through via normal mapping (existing behavior).
        """
        parts = []
        vlabel_in = "[0:v]"
        vlabel_cur = vlabel_in

        # Apply drawtext in the complex graph if we need complex anyway (icon path).
        if drawtext_filters:
            parts.append(f"{vlabel_cur}{drawtext_filters}[vtxt]") 
            vlabel_cur = "[vtxt]"

        if top_icon:
            # Scale icon to a fixed height; keep aspect ratio
            parts.append(f"[{icon_input_index}:v]scale=-1:{int(top_icon_height)}[icon]")
            parts.append(
                f"{vlabel_cur}[icon]overlay=x={int(top_icon_x)}:y={int(top_icon_y)}[vout]"
            )

        if bg_music:
            # Reuse existing audio mix, but allow dynamic music index
            parts.append(
                f"[0:a]volume=1.0[a0];[{music_input_index}:a]volume=0.2[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )

        return ";".join(parts) if parts else None

    if options.manifest:
        # For manifest, we can't know part/total easily, so just use static text
        drawtext_filters = None
        if options.top_text or options.bottom_text:
            drawtext_filters = build_drawtext_filters(
                options.top_text,
                options.bottom_text,
                top_fontsize=options.top_fontsize,
                font=options.font,
                top_text_x=options.top_text_x,
                top_text_y=options.top_text_y,
            )
            # If we're NOT using an icon, keep the original -vf approach.
            if drawtext_filters and not options.top_icon:
                if options.extra:
                    options.extra += f' -vf "{drawtext_filters}"'
                else:
                    options.extra = f'-vf "{drawtext_filters}"'

        # Patch split_by_manifest to support bg music
        def split_by_manifest_with_bg_music(**kwargs):
            filename = kwargs["filename"]
            manifest = kwargs["manifest"]
            output_dir = kwargs.get("output_dir", None)
            vcodec = kwargs.get("vcodec", "copy")
            acodec = kwargs.get("acodec", "copy")
            extra = kwargs.get("extra", "")
            bg_music = kwargs.get("bg_music", None)
            top_icon = kwargs.get("top_icon", None)
            top_icon_height = kwargs.get("top_icon_height", 64)
            top_icon_x = kwargs.get("top_icon_x", 20)
            top_icon_y = kwargs.get("top_icon_y", 200)
            top_text = kwargs.get("top_text", None)
            bottom_text = kwargs.get("bottom_text", None)
            top_fontsize = kwargs.get("top_fontsize", 48)
            font = kwargs.get("font", "/System/Library/Fonts/Arial Unicode MS.ttf")
            top_text_x = kwargs.get("top_text_x", None)
            top_text_y = kwargs.get("top_text_y", 200)
            if not os.path.exists(manifest):
                print("File does not exist: %s" % manifest)
                raise SystemExit
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
            with open(manifest) as manifest_file:
                manifest_type = manifest.split(".")[-1]
                if manifest_type == "json":
                    config = json.load(manifest_file)
                elif manifest_type == "csv":
                    config = csv.DictReader(manifest_file)
                else:
                    print("Format not supported. File must be a csv or json file")
                    raise SystemExit
                try:
                    fileext = filename.split(".")[-1]
                except IndexError as e:
                    raise IndexError("No . in filename. Error: " + str(e))
                for video_config in config:
                    split_args = []
                    try:
                        split_start = video_config["start_time"]
                        split_length = video_config.get("end_time", None)
                        if not split_length:
                            split_length = video_config["length"]
                        filebase = video_config["rename_to"]
                        if fileext in filebase:
                            filebase = ".".join(filebase.split(".")[:-1])
                        output_path = (
                            os.path.join(output_dir, filebase + ".mp4")
                            if output_dir
                            else filebase + ".mp4"
                        )
                        split_args += [
                            "-ss",
                            str(split_start),
                            "-t",
                            str(split_length),
                            output_path,
                        ]
                        # Build ffmpeg command (support icon + bg music)
                        inputs = ["-i", filename]
                        music_idx = None
                        icon_idx = None
                        if bg_music:
                            music_idx = 1
                            inputs += ["-i", bg_music]
                        if top_icon:
                            icon_idx = 2 if bg_music else 1
                            inputs += ["-i", top_icon]

                        ffmpeg_cmd = ["ffmpeg"] + inputs + ["-vcodec", vcodec, "-y"]

                        # If icon is used, we must use filter_complex for video (and optionally audio).
                        if top_icon:
                            this_drawtext = build_drawtext_filters(
                                top_text,
                                bottom_text,
                                top_fontsize=top_fontsize,
                                font=font,
                                top_text_x=top_text_x,
                                top_text_y=top_text_y,
                            )
                            fc = build_filter_complex(
                                bg_music=bg_music,
                                top_icon=top_icon,
                                top_icon_height=top_icon_height,
                                top_icon_x=top_icon_x,
                                top_icon_y=top_icon_y,
                                drawtext_filters=this_drawtext,
                                music_input_index=(
                                    music_idx if music_idx is not None else 1
                                ),
                                icon_input_index=(
                                    icon_idx if icon_idx is not None else 1
                                ),
                            )
                            if fc:
                                ffmpeg_cmd += ["-filter_complex", fc]
                                ffmpeg_cmd += ["-map", "[vout]"]
                                if bg_music:
                                    ffmpeg_cmd += ["-map", "[aout]"]
                                    ffmpeg_cmd += ["-acodec", acodec]
                                else:
                                    ffmpeg_cmd += ["-map", "0:a?", "-acodec", acodec]
                        else:
                            # No icon: keep previous audio-mix behavior for bg music, and allow -vf via extra.
                            ffmpeg_cmd += shlex.split(extra)
                            if bg_music:
                                audio_filter = build_audio_filter(bg_music)
                                ffmpeg_cmd += ["-filter_complex", audio_filter]
                                ffmpeg_cmd += build_ffmpeg_maps(bg_music)
                            ffmpeg_cmd += ["-acodec", acodec]

                        # Append extra options last when icon is used too (avoid clobbering our -filter_complex/-map).
                        if top_icon and extra:
                            ffmpeg_cmd += shlex.split(extra)
                        ffmpeg_cmd += build_metadata_args(metadata_items)
                        print(
                            "########################################################"
                        )
                        print("About to run: " + " ".join(ffmpeg_cmd + split_args))
                        print(
                            "########################################################"
                        )
                        subprocess.check_output(ffmpeg_cmd + split_args)
                    except KeyError as e:
                        print("############# Incorrect format ##############")
                        if manifest_type == "json":
                            print("The format of each json array should be:")
                            print(
                                "{start_time: <int>, length: <int>, rename_to: <string>}"
                            )
                        elif manifest_type == "csv":
                            print(
                                "start_time,length,rename_to should be the first line "
                            )
                            print("in the csv file.")
                        print("#############################################")
                        print(e)
                        raise SystemExit

        split_by_manifest_with_bg_music(**options.__dict__)
    else:
        video_length = None
        if not options.split_length:
            video_length = get_video_length(options.filename)
            file_size = os.stat(options.filename).st_size
            split_filesize = None
            if options.split_filesize:
                split_filesize = int(options.split_filesize * options.filesize_factor)
            if split_filesize and options.chunk_strategy == "even":
                options.split_chunks = ceildiv(file_size, split_filesize)
            if options.split_chunks:
                options.split_length = ceildiv(video_length, options.split_chunks)
            if not options.split_length and split_filesize:
                options.split_length = int(
                    split_filesize / float(file_size) * video_length
                )
        if not options.split_length:
            bailout()

        # For split_by_seconds, we know part/total, so we need to inject drawtext per split
        def split_by_seconds_with_text_and_bg_music(**kwargs):
            filename = kwargs["filename"]
            split_length = kwargs["split_length"]
            output_dir = kwargs.get("output_dir", None)
            vcodec = kwargs.get("vcodec", "libx264")
            acodec = kwargs.get("acodec", "aac")
            extra = kwargs.get("extra", "")
            video_length = kwargs.get("video_length", None)
            top_text = kwargs.get("top_text", None)
            bottom_text = kwargs.get("bottom_text", None)
            top_fontsize = kwargs.get("top_fontsize", 48)
            font = kwargs.get("font", "/System/Library/Fonts/Arial Unicode MS.ttf")
            bg_music = kwargs.get("bg_music", None)
            top_icon = kwargs.get("top_icon", None)
            top_icon_height = kwargs.get("top_icon_height", 64)
            top_icon_x = kwargs.get("top_icon_x", 20)
            top_icon_y = kwargs.get("top_icon_y", 200)
            top_text_x = kwargs.get("top_text_x", None)
            top_text_y = kwargs.get("top_text_y", 200)
            parts = kwargs.get("parts", None)
            # Parse parts option
            selected_parts = None
            if parts:
                selected_parts = set()
                for part_item in parts.split(","):
                    part_item = part_item.strip()
                    if "-" in part_item:
                        start, end = part_item.split("-")
                        selected_parts.update(range(int(start), int(end) + 1))
                    else:
                        selected_parts.add(int(part_item))
            if split_length and split_length <= 0:
                print("Split length can't be 0")
                raise SystemExit
            if not video_length:
                video_length = get_video_length(filename)
            split_count = ceildiv(video_length, split_length)
            if split_count == 1:
                print("Video length is less then the target split length.")
                raise SystemExit
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
            try:
                filebase = ".".join(filename.split(".")[:-1])
                fileext = filename.split(".")[-1]
            except IndexError as e:
                raise IndexError("No . in filename. Error: " + str(e))
            for n in range(0, split_count):
                part_number = n + 1
                if selected_parts and part_number not in selected_parts:
                    continue
                split_args = []
                split_start = split_length * n if n != 0 else 0
                output_path = (
                    os.path.join(output_dir, f"{filebase}-{n+1}-of-{split_count}.mp4")
                    if output_dir
                    else f"{filebase}-{n+1}-of-{split_count}.mp4"
                )
                # Build drawtext filter for this part
                drawtext_filters = build_drawtext_filters(
                    top_text,
                    bottom_text,
                    part=n + 1,
                    total=split_count,
                    top_fontsize=top_fontsize,
                    font=font,
                    top_text_x=top_text_x,
                    top_text_y=top_text_y,
                )

                # Build ffmpeg command (support icon + bg music)
                inputs = ["-i", filename]
                music_idx = None
                icon_idx = None
                if bg_music:
                    music_idx = 1
                    inputs += ["-i", bg_music]
                if top_icon:
                    icon_idx = 2 if bg_music else 1
                    inputs += ["-i", top_icon]

                ffmpeg_cmd = ["ffmpeg"] + inputs + ["-vcodec", vcodec]

                if top_icon:
                    fc = build_filter_complex(
                        bg_music=bg_music,
                        top_icon=top_icon,
                        top_icon_height=top_icon_height,
                        top_icon_x=top_icon_x,
                        top_icon_y=top_icon_y,
                        drawtext_filters=drawtext_filters,
                        music_input_index=music_idx if music_idx is not None else 1,
                        icon_input_index=icon_idx if icon_idx is not None else 1,
                    )
                    if fc:
                        ffmpeg_cmd += ["-filter_complex", fc]
                        ffmpeg_cmd += ["-map", "[vout]"]
                        if bg_music:
                            ffmpeg_cmd += ["-map", "[aout]"]
                            ffmpeg_cmd += ["-acodec", acodec]
                        else:
                            ffmpeg_cmd += ["-map", "0:a?", "-acodec", acodec]
                    if extra:
                        ffmpeg_cmd += shlex.split(extra)
                else:
                    # No icon: keep existing behavior using -vf injected into extra when needed
                    this_extra = extra
                    if drawtext_filters:
                        if "-vf" in this_extra:
                            this_extra = this_extra.replace(
                                "-vf ", f'-vf "{drawtext_filters},'
                            )
                        else:
                            this_extra += f' -vf "{drawtext_filters}"'
                    if bg_music:
                        audio_filter = build_audio_filter(bg_music)
                        ffmpeg_cmd += ["-filter_complex", audio_filter]
                        ffmpeg_cmd += build_ffmpeg_maps(bg_music)
                    ffmpeg_cmd += ["-acodec", acodec]
                    ffmpeg_cmd += shlex.split(this_extra)
                ffmpeg_cmd += build_metadata_args(
                    metadata_items, part=part_number, total=split_count
                )
                split_args += [
                    "-ss",
                    str(split_start),
                    "-t",
                    str(split_length),
                    output_path,
                ]
                print("About to run: " + " ".join(ffmpeg_cmd + split_args))
                subprocess.check_output(ffmpeg_cmd + split_args)

        split_by_seconds_with_text_and_bg_music(
            video_length=video_length, **options.__dict__
        )


if __name__ == "__main__":
    main()
