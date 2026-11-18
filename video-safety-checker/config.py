"""User-facing settings for the local video safety checker.

Edit the constants below, or override the common ones from the command line.
Thresholds are internal starting points for your own labelled videos. They are
not Instagram, Meta, or Google moderation thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# Folder of videos to scan. Leave empty and pass --input on the command line.
INPUT_FOLDER = ""

# Reports, JSON, and flagged-frame images are written here.
OUTPUT_FOLDER = "output"

# Scan subfolders when True. The --recursive flag turns this on for one run.
RECURSIVE_SCAN = False

# One frame every 2 seconds. --interval sets the same value in seconds.
FRAME_INTERVAL_SECONDS = 1.0

# Enough for a one-minute video at a 2-second interval, plus the end frame.
MAX_FRAMES_PER_VIDEO = 400

# Analysed frames are scaled down to this width. Aspect ratio is preserved.
MAX_FRAME_WIDTH = 480

# NudeNet v3.4.2 320n weights. See README for the licence conflict.
MODEL_PATH = "models/local_model.onnx"

# Detector operating point (candidate_score, nms_*) follows NudeNet 3.4.2.
# flag_score and the multipliers are this project's calibration knobs.
MODEL_THRESHOLDS = {
    "candidate_score": 0.20,
    "nms_score": 0.25,
    "nms_iou": 0.45,
    "flag_score": 0.50,
    "intimate_score_multiplier": 100.0,
    "nudity_score_multiplier": 80.0,
    "repeat_bonus_2": 4.0,
    "repeat_bonus_3": 8.0,
}

GENERATE_PDF = True
GENERATE_HTML = True

# Clear JPEGs of flagged frames, so each hit can be checked by eye.
SAVE_EVIDENCE_FRAMES = True

# This build always scans one video at a time. Higher values are ignored.
MAX_CONCURRENT_VIDEOS = 1

# Optional extra samples. Off by default so a scan stays on the interval grid.
SCENE_CHANGE_DETECTION = False
SCENE_THRESHOLD = 0.40

# After a flagged frame, also sample a couple of seconds on either side.
SUSPICIOUS_RESAMPLE = True
RESAMPLE_OFFSETS_SECONDS = (-2.0, 2.0)

SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}

MODEL_INFO = {
    "name": "NudeNet 320n",
    "version": "3.4.2",
    "file": "local_model.onnx",
    "sha256": "c15d8273adad2d0a92f014cc69ab2d6c311a06777a55545f2c4eb46f51911f0f",
    "architecture": "Ultralytics YOLOv8n object detector, 320x320 input",
    "runtime": "ONNX Runtime CPUExecutionProvider",
    "source": "https://github.com/notAI-tech/NudeNet",
    "weights": "nudenet/320n.onnx shipped inside the nudenet 3.4.2 wheel",
}

# Requested checks this model cannot perform. They are never invented.
UNSUPPORTED_CATEGORIES = [
    {
        "id": "partial_nudity",
        "reason": (
            "The model has COVERED body-part classes, but those fire on "
            "swimwear and ordinary clothing. They are recorded as context "
            "and do not raise the risk score."
        ),
    },
    {
        "id": "sexual_imagery",
        "reason": "The model detects body parts. It does not detect sexual acts.",
    },
    {
        "id": "sexualized_poses",
        "reason": "No pose classifier is included.",
    },
    {
        "id": "suggestive_imagery",
        "reason": "Clothed suggestive images are outside this detector's labels.",
    },
    {
        "id": "graphic_violence",
        "reason": "No violence classifier is included.",
    },
    {
        "id": "child_safety_or_age",
        "reason": (
            "Age is not a model output. This tool does not try to identify "
            "minors and does not build a preview for a restricted result."
        ),
    },
]

DISCLAIMER = (
    "This is an internal sampling screen, not an official Instagram, Meta, or "
    "Google moderation decision. The score bands are initial internal "
    "thresholds and need calibration on videos you have labelled yourself. "
    "NudeNet 320n reports a fixed list of body-part classes. It does not "
    "detect graphic violence, sexual activity as such, sexualized poses, "
    "suggestive clothed imagery, or a person's age. Covered body parts, "
    "including many swimwear and fitness images, do not raise the score. "
    "Medical, educational, and art images can still be false positives when "
    "the detector marks exposed breast, buttocks, genitalia, or anus. A low "
    "result only means the sampled frames had no scoring detection. Frames "
    "between samples were not analysed. Failed and incomplete scans are not "
    "approvals. This tool does not identify minors. It will not create a "
    "preview, and it has no approval override, for a restricted critical "
    "result. If a file may contain illegal content, do not upload it."
)

RESTRICTED_RECOMMENDATION = (
    "Block. Restricted critical incident. No approval override and no preview."
)

# Tokens that must never receive an ordinary approval path or a thumbnail.
RESTRICTED_CATEGORY_IDS = {
    "child_safety",
    "child_safety_or_age",
    "restricted_critical",
}


@dataclass
class AppConfig:
    """Runtime settings after config.py defaults and command-line overrides."""

    input_folder: Path
    output_folder: Path
    recursive_scan: bool
    frame_interval_seconds: float
    max_frames_per_video: int
    max_frame_width: int
    model_path: Path
    model_thresholds: dict[str, float]
    generate_pdf: bool
    generate_html: bool
    save_evidence_frames: bool
    max_concurrent_videos: int
    scene_change_detection: bool
    scene_threshold: float
    suspicious_resample: bool
    resample_offsets_seconds: tuple[float, ...]
    force_rescan: bool = False

    def settings_fingerprint(self) -> dict[str, object]:
        """Values that change a result. A mismatch invalidates the JSON cache."""
        return {
            "model_sha256": MODEL_INFO["sha256"],
            "frame_interval_seconds": self.frame_interval_seconds,
            "max_frames_per_video": self.max_frames_per_video,
            "max_frame_width": self.max_frame_width,
            "model_thresholds": self.model_thresholds,
            "scene_change_detection": self.scene_change_detection,
            "scene_threshold": self.scene_threshold,
            "suspicious_resample": self.suspicious_resample,
            "resample_offsets_seconds": list(self.resample_offsets_seconds),
        }


def default_config() -> AppConfig:
    return AppConfig(
        input_folder=Path(INPUT_FOLDER) if INPUT_FOLDER else Path(),
        output_folder=Path(OUTPUT_FOLDER),
        recursive_scan=RECURSIVE_SCAN,
        frame_interval_seconds=float(FRAME_INTERVAL_SECONDS),
        max_frames_per_video=int(MAX_FRAMES_PER_VIDEO),
        max_frame_width=int(MAX_FRAME_WIDTH),
        model_path=Path(MODEL_PATH),
        model_thresholds={key: float(value) for key, value in MODEL_THRESHOLDS.items()},
        generate_pdf=GENERATE_PDF,
        generate_html=GENERATE_HTML,
        save_evidence_frames=SAVE_EVIDENCE_FRAMES,
        max_concurrent_videos=int(MAX_CONCURRENT_VIDEOS),
        scene_change_detection=SCENE_CHANGE_DETECTION,
        scene_threshold=float(SCENE_THRESHOLD),
        suspicious_resample=SUSPICIOUS_RESAMPLE,
        resample_offsets_seconds=tuple(float(v) for v in RESAMPLE_OFFSETS_SECONDS),
    )
