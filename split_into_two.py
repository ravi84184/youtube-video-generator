import subprocess
import sys
import os
import math

# Usage:
#   python split_into_two.py input.mp4 <num_parts> [parts]
#   python split_into_two.py input.mp4 --minutes <minutes_per_part> [parts]
# [parts] is optional: e.g. '3' or '2,4,7' or '2-5' (default: all)

def get_video_length(filename):
    result = subprocess.run([
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', filename
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return float(result.stdout.strip())

def parse_parts(parts_str, num_parts):
    if not parts_str:
        return list(range(1, num_parts+1))
    parts = set()
    for part in parts_str.split(','):
        part = part.strip()
        if '-' in part:
            start, end = part.split('-')
            parts.update(range(int(start), int(end)+1))
        else:
            parts.add(int(part))
    # Filter out-of-range
    return sorted([p for p in parts if 1 <= p <= num_parts])

def split_video_by_parts(input_file, num_parts, selected_parts):
    total_duration = get_video_length(input_file)
    part_duration = total_duration / num_parts
    base, ext = os.path.splitext(input_file)

    print(f"Splitting {input_file} into {num_parts} parts of ~{part_duration:.2f} seconds each.")
    for i in range(num_parts):
        part_num = i + 1
        if part_num not in selected_parts:
            continue
        start = part_duration * i
        # For the last part, go to the end to avoid rounding issues
        if i == num_parts - 1:
            duration = total_duration - start
        else:
            duration = part_duration
        out = f"{base}_part{part_num}.mp4"
        cmd = [
            'ffmpeg', '-y', '-i', input_file, '-ss', str(start), '-t', str(duration), '-c', 'copy', out
        ]
        print(f"  {out} ({start:.2f} to {start+duration:.2f} seconds)")
        subprocess.run(cmd, check=True)
    print("Done!")

def split_video_by_minutes(input_file, minutes_per_part, selected_parts):
    total_duration = get_video_length(input_file)
    part_duration = minutes_per_part * 60
    num_parts = math.ceil(total_duration / part_duration)
    base, ext = os.path.splitext(input_file)

    print(f"Splitting {input_file} into {num_parts} parts of {minutes_per_part} minutes (~{part_duration:.2f} seconds) each.")
    for i in range(num_parts):
        part_num = i + 1
        if part_num not in selected_parts:
            continue
        start = part_duration * i
        # For the last part, go to the end to avoid rounding issues
        if i == num_parts - 1:
            duration = total_duration - start
        else:
            duration = part_duration
        out = f"{base}_part{part_num}.mp4"
        cmd = [
            'ffmpeg', '-y', '-i', input_file, '-ss', str(start), '-t', str(duration), '-c', 'copy', out
        ]
        print(f"  {out} ({start:.2f} to {start+duration:.2f} seconds)")
        subprocess.run(cmd, check=True)
    print("Done!")

if __name__ == "__main__":
    # Parse arguments
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python split_into_two.py <input_video> <num_parts> [parts]")
        print("  python split_into_two.py <input_video> --minutes <minutes_per_part> [parts]")
        print("    [parts] is optional: e.g. '3' or '2,4,7' or '2-5' (default: all)")
        sys.exit(1)
    input_file = sys.argv[1]
    if sys.argv[2] == '--minutes':
        if len(sys.argv) < 4:
            print("You must specify the number of minutes per part after --minutes.")
            sys.exit(1)
        try:
            minutes_per_part = float(sys.argv[3])
            if minutes_per_part <= 0:
                raise ValueError
        except ValueError:
            print("<minutes_per_part> must be a positive number.")
            sys.exit(1)
        parts_str = sys.argv[4] if len(sys.argv) == 5 else None
        total_duration = get_video_length(input_file)
        part_duration = minutes_per_part * 60
        num_parts = math.ceil(total_duration / part_duration)
        try:
            selected_parts = parse_parts(parts_str, num_parts)
            if not selected_parts:
                raise ValueError
        except Exception:
            print("[parts] must be a comma-separated list or range of integers within the number of parts.")
            sys.exit(1)
        split_video_by_minutes(input_file, minutes_per_part, selected_parts)
    else:
        try:
            num_parts = int(sys.argv[2])
            if num_parts < 1:
                raise ValueError
        except ValueError:
            print("<num_parts> must be a positive integer.")
            sys.exit(1)
        parts_str = sys.argv[3] if len(sys.argv) == 4 else None
        try:
            selected_parts = parse_parts(parts_str, num_parts)
            if not selected_parts:
                raise ValueError
        except Exception:
            print("[parts] must be a comma-separated list or range of integers within the number of parts.")
            sys.exit(1)
        split_video_by_parts(input_file, num_parts, selected_parts) 