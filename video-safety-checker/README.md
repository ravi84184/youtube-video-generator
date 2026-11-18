# Video Safety Checker

Scan a folder of videos on this PC and write one PDF report, one standalone HTML report, and a JSON results file. Frame samples are classified locally with NudeNet 320n through ONNX Runtime. Nothing is uploaded, and the original video files are only opened for reading.

Python 3.12 is the intended version. This machine does not have 3.12 installed, so the checker was run with Python 3.13.11. The code does not use 3.13-only syntax.

## Model

The detector is **NudeNet 320n, package version 3.4.2** (notAI-tech). The weights file is `models/local_model.onnx`, copied from `nudenet/320n.onnx` inside the `nudenet==3.4.2` wheel.

| | |
|---|---|
| Architecture | Ultralytics YOLOv8n, input 320×320 |
| Runtime | ONNX Runtime, `CPUExecutionProvider` only |
| Weights SHA-256 | `c15d8273adad2d0a92f014cc69ab2d6c311a06777a55545f2c4eb46f51911f0f` |
| Source | https://github.com/notAI-tech/NudeNet |

The adapter in `moderation.py` uses the label order and letterbox published with NudeNet 3.4.2: pad to a square with black borders, scale pixels to 0–1, and pass RGB in a `[1, 3, 320, 320]` tensor. Output rows are `cx, cy, w, h` plus 18 class scores. A check against the 3.4.2 preprocessing function matched the input tensor within `1e-6`.

### Labels the model actually outputs

```
FEMALE_GENITALIA_COVERED, FACE_FEMALE, BUTTOCKS_EXPOSED,
FEMALE_BREAST_EXPOSED, FEMALE_GENITALIA_EXPOSED, MALE_BREAST_EXPOSED,
ANUS_EXPOSED, FEET_EXPOSED, BELLY_COVERED, FEET_COVERED,
ARMPITS_COVERED, ARMPITS_EXPOSED, FACE_MALE, BELLY_EXPOSED,
MALE_GENITALIA_EXPOSED, ANUS_COVERED, FEMALE_BREAST_COVERED,
BUTTOCKS_COVERED
```

### What is scored

Only detections at or above `flag_score` (default 0.50) affect the risk score.

| Model label | Report category |
|---|---|
| `FEMALE_GENITALIA_EXPOSED`, `MALE_GENITALIA_EXPOSED`, `ANUS_EXPOSED` | Exposed intimate areas and explicit nudity |
| `FEMALE_BREAST_EXPOSED`, `BUTTOCKS_EXPOSED` | Explicit nudity |

Frame score for an intimate label is `confidence × 100`. Frame score for exposed breast or buttocks is `confidence × 80`. The video score is the highest frame score. Two flagged frames add 4 points. Three or more add 8. The result is capped at 100. A scoring hit is at least 25, so it cannot land in LOW.

| Score | Level | Recommendation |
|---|---|---|
| 0–24 | LOW | Eligible for manual approval |
| 25–49 | MEDIUM | Review |
| 50–74 | HIGH | Do not upload pending review |
| 75–100 | CRITICAL | Block and escalate |

These bands are internal starting points. They are not Instagram, Meta, or Google thresholds. Calibrate `MODEL_THRESHOLDS` in `config.py` on videos you have labelled yourself.

### What is detected but not scored

Covered body parts, faces, exposed belly, feet, armpits, and male chest are listed as context when their confidence reaches `flag_score`. They do not raise the score. That is deliberate: covered breast and buttocks are common on swimwear and fitness footage, and this detector cannot tell medical or educational context from anything else.

### What this model cannot do

Do not treat a result as a judgement on any of these. They are listed in both reports:

- Partial nudity as an automatic fail. Covered classes exist, and using them would flag ordinary clothing.
- Sexual imagery. The model finds body parts, not sexual acts.
- Sexualized poses. There is no pose model.
- Suggestive clothed imagery.
- Graphic violence. There is no violence model.
- Age or child safety. NudeNet has no age output. This checker does not try to identify minors. A restricted critical result, which this model never produces on its own, gets no thumbnail and no approval override.

Exposed anatomy in medical, educational, or art footage can still score as explicit nudity. That is a known false-positive mode.

### Licence

The licence files shipped inside the `nudenet` 3.4.2 wheel (`LICENSE` and `LICENSE.md`) are the GNU Affero General Public License v3. The same AGPL-3.0 text is the `LICENSE` file on the GitHub repository. A copy is stored next to the weights at `models/NUDENET-AGPL-3.0.txt`.

The PyPI metadata for 3.4.2 says `License: MIT`, and the package classifier says MIT. The MIT text is not the text in those licence files. This project does not resolve that conflict.

YOLOv8, which 320n is built on, is also distributed by Ultralytics under AGPL-3.0.

The checker is a local command-line tool. Do not put it behind a network service without resolving the NudeNet and YOLOv8 licence terms. The Python in this folder is an inference adapter written for this project. It is not a copy of `nudenet.py`.

## Hardware used for the timing check

- Windows, Intel Core i7-12700, 16 GB RAM
- Intel UHD Graphics 770 is not used
- ONNX Runtime 1.32.0, CPU only

Thirty sequential inferences of a 480×270 frame averaged **11.5 ms per frame** after one warmup pass. Decoding the video and writing the reports takes longer than the model. One video is processed at a time so the batch stays inside 16 GB of RAM. `MAX_CONCURRENT_VIDEOS` above 1 is ignored.

## Install

FFmpeg and FFprobe must both be on `PATH`.

```powershell
cd video-safety-checker
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Use `py -3.12` instead if you have 3.12.

## Run

```powershell
python main.py --input "D:\InstagramVideos"
```

Optional arguments:

```powershell
python main.py --input "D:\InstagramVideos" --output "D:\InstagramVideos\SafetyReport" --recursive
python main.py --input "D:\InstagramVideos" --max-frames 40 --interval 2
python main.py --input "D:\InstagramVideos" --force-rescan
python main.py --input "D:\InstagramVideos" --pdf-only
python main.py --input "D:\InstagramVideos" --html-only
```

`--interval 2` takes one frame every 2 seconds. JSON is always written. A previous `scan_results.json` is reused when the file SHA-256 and the scan settings still match. Failed and incomplete videos are scanned again. `--force-rescan` ignores the cache.

The console prints the discovered count, the file in progress, frames analysed, the risk level, flagged timestamps, and a final tally.

## Sampling

Default sampling is one frame every 2 seconds, up to 40 frames per video, 480 pixels wide, JPEG, original aspect ratio. The interval pass walks the file once and records each frame's real timestamp. An extra frame near the end is included when the budget allows. Flagged timestamps can pull in samples two seconds earlier and later, still inside the frame cap.

`SCENE_CHANGE_DETECTION` in `config.py` is off by default. Turn it on to also keep frames where FFmpeg's scene score exceeds `SCENE_THRESHOLD` (default 0.40), up to the same frame cap.

A LOW result only means the sampled frames had no scoring detection. Content between samples was not seen. If the frame cap stops the scan before the video ends, the level is INCOMPLETE rather than LOW. A failed or incomplete scan is never LOW.

## Output

The output folder is `output/` next to `main.py`, unless `--output` or `OUTPUT_FOLDER` says otherwise.

```
output/
    video_safety_report.pdf
    video_safety_report.html
    scan_results.json
    frames/
```

`frames/` holds clear JPEGs of flagged frames so you can confirm each hit. The HTML report uses those relative paths and has no remote images, fonts, or scripts, so it opens offline in Chrome or Edge. The page has summary cards, search, risk filters, sorting, and expandable details.

A restricted result still gets no image and no approval path.

## Configuration

Edit the constants at the top of `config.py`:

- `INPUT_FOLDER`
- `OUTPUT_FOLDER`
- `RECURSIVE_SCAN`
- `FRAME_INTERVAL_SECONDS`
- `MAX_FRAMES_PER_VIDEO`
- `MAX_FRAME_WIDTH`
- `MODEL_PATH`
- `MODEL_THRESHOLDS`
- `GENERATE_PDF`
- `GENERATE_HTML`
- `SAVE_EVIDENCE_FRAMES`
- `MAX_CONCURRENT_VIDEOS`

Supported extensions are MP4, MOV, MKV, AVI, WEBM, and M4V, including nested folders when the recursive option is on.

## Errors

One bad file does not stop the batch. The checker reports a per-video failure for an unreadable, empty, or corrupt file, a missing video stream, a frame-extract failure, or an inference error. It stops before scanning if the input folder is missing or empty of supported videos, FFmpeg or FFprobe is missing, the ONNX file is missing or will not load, the output folder is not writable, or free disk space is under 100 MB. PDF and HTML failures are reported after the JSON file is written.

## Privacy

Videos and frames stay on this machine. The checker does not call a moderation API, does not use a database, and does not start a web server.
