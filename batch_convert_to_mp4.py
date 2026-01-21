import os
import sys
import subprocess

def convert_folder_to_mp4(input_folder, output_folder):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    for filename in os.listdir(input_folder):
        if not filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.mpeg', '.mpg')):
            continue
        input_path = os.path.join(input_folder, filename)
        base, _ = os.path.splitext(filename)
        output_path = os.path.join(output_folder, base + ".mp4")
        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-c:v", "libx264",
            "-c:a", "aac",
            "-strict", "experimental",
            "-y",  # Overwrite output file if exists
            output_path
        ]
        print("Converting:", input_path, "->", output_path)
        subprocess.run(cmd, check=True)
    print("All conversions complete.")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python batch_convert_to_mp4.py <input_folder> <output_folder>")
        sys.exit(1)
    input_folder = sys.argv[1]
    output_folder = sys.argv[2]
    convert_folder_to_mp4(input_folder, output_folder)