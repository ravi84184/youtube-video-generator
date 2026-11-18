"""Local NudeNet 320n inference via ONNX Runtime.

Class order and the 320x320 letterbox (black padding, pixels scaled to 0–1,
RGB) match NudeNet 3.4.2 so the published labels stay attached to the right
scores. This file is an inference adapter. It is not the NudeNet package.

The detector does not understand age, violence, sexual acts, or intent.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

import cv2
import numpy as np
import onnxruntime as ort

from config import MODEL_INFO

logger = logging.getLogger(__name__)

# Official NudeNet 3.4.2 label order. Do not sort or extend this list.
LABELS: tuple[str, ...] = (
    "FEMALE_GENITALIA_COVERED",
    "FACE_FEMALE",
    "BUTTOCKS_EXPOSED",
    "FEMALE_BREAST_EXPOSED",
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_BREAST_EXPOSED",
    "ANUS_EXPOSED",
    "FEET_EXPOSED",
    "BELLY_COVERED",
    "FEET_COVERED",
    "ARMPITS_COVERED",
    "ARMPITS_EXPOSED",
    "FACE_MALE",
    "BELLY_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "ANUS_COVERED",
    "FEMALE_BREAST_COVERED",
    "BUTTOCKS_COVERED",
)

# Classes that can raise the risk score. Everything else is context only.
INTIMATE_LABELS = {
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "ANUS_EXPOSED",
}
NUDITY_LABELS = {
    "FEMALE_BREAST_EXPOSED",
    "BUTTOCKS_EXPOSED",
}
SCORING_LABELS = INTIMATE_LABELS | NUDITY_LABELS


class ModelError(Exception):
    """The ONNX model is missing, incompatible, or failed during inference."""


@dataclass(frozen=True)
class Detection:
    label: str
    score: float


class LocalModerator:
    """One NudeNet session reused for every frame in the batch."""

    def __init__(self, model_path: str, thresholds: dict[str, float]) -> None:
        self.model_path = model_path
        self.candidate_score = float(thresholds.get("candidate_score", 0.20))
        self.nms_score = float(thresholds.get("nms_score", 0.25))
        self.nms_iou = float(thresholds.get("nms_iou", 0.45))
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        available = set(ort.get_available_providers())
        if "CPUExecutionProvider" not in available:
            raise ModelError("ONNX Runtime has no CPUExecutionProvider.")
        try:
            self.session = ort.InferenceSession(
                model_path,
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
        except Exception as exc:
            raise ModelError(f"Could not load the ONNX model: {exc}") from exc

        inputs = self.session.get_inputs()
        if not inputs:
            raise ModelError("The ONNX model has no inputs.")
        self.input_name = inputs[0].name
        self.input_size = _square_size(inputs[0].shape)
        self._warn_if_hash_differs(model_path)
        self._warmup()

    def classify(self, image_bgr: np.ndarray) -> list[Detection]:
        """Return body-part detections. Boxes are not kept."""
        try:
            blob = _letterbox_blob(image_bgr, self.input_size)
            outputs = self.session.run(None, {self.input_name: blob})
        except Exception as exc:
            raise ModelError(f"Inference failed: {exc}") from exc
        return _postprocess(
            outputs[0],
            candidate_score=self.candidate_score,
            nms_score=self.nms_score,
            nms_iou=self.nms_iou,
        )

    def _warmup(self) -> None:
        blank = np.zeros((self.input_size, self.input_size, 3), dtype=np.uint8)
        self.classify(blank)

    @staticmethod
    def _warn_if_hash_differs(model_path: str) -> None:
        expected = str(MODEL_INFO["sha256"])
        digest = hashlib.sha256()
        with open(model_path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        actual = digest.hexdigest()
        if actual != expected:
            logger.warning(
                "Model checksum %s does not match pinned NudeNet 3.4.2 320n %s.",
                actual,
                expected,
            )


def _square_size(shape: list[object]) -> int:
    dims = [int(dim) for dim in shape if isinstance(dim, (int, np.integer)) and int(dim) > 0]
    # Static YOLOv8 input is [1, 3, 320, 320]. Fall back to 320 if dynamic.
    if len(dims) >= 2 and dims[-1] == dims[-2]:
        return int(dims[-1])
    return 320


def _letterbox_blob(image_bgr: np.ndarray, size: int) -> np.ndarray:
    """Pad to a square, then build an NCHW RGB blob in the 0–1 range."""
    image = image_bgr
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    elif image.shape[2] == 4:
        image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    height, width = image.shape[:2]
    side = max(height, width)
    padded = cv2.copyMakeBorder(
        image,
        0,
        side - height,
        0,
        side - width,
        cv2.BORDER_CONSTANT,
        value=(0, 0, 0),
    )
    return cv2.dnn.blobFromImage(
        padded,
        scalefactor=1.0 / 255.0,
        size=(size, size),
        mean=(0, 0, 0),
        swapRB=True,
        crop=False,
    )


def _postprocess(
    output: np.ndarray,
    candidate_score: float,
    nms_score: float,
    nms_iou: float,
) -> list[Detection]:
    predictions = np.squeeze(output)
    if predictions.ndim != 2:
        raise ModelError(f"Unexpected model output shape {output.shape}.")
    # YOLOv8 ONNX layout is [4 + classes, boxes]. NudeNet always transposes it.
    if predictions.shape[0] < predictions.shape[1]:
        predictions = predictions.T
    if predictions.shape[1] < 4 + len(LABELS):
        raise ModelError(
            f"Model output has {predictions.shape[1]} columns, "
            f"expected at least {4 + len(LABELS)}."
        )

    boxes: list[list[float]] = []
    scores: list[float] = []
    class_ids: list[int] = []
    for row in predictions:
        class_scores = row[4 : 4 + len(LABELS)]
        class_id = int(np.argmax(class_scores))
        score = float(class_scores[class_id])
        if score < candidate_score:
            continue
        x_center, y_center, width, height = (float(value) for value in row[:4])
        boxes.append(
            [x_center - width / 2.0, y_center - height / 2.0, width, height]
        )
        scores.append(score)
        class_ids.append(class_id)

    if not boxes:
        return []

    indices = cv2.dnn.NMSBoxes(boxes, scores, nms_score, nms_iou)
    if indices is None or len(indices) == 0:
        return []
    detections: list[Detection] = []
    for index in np.array(indices).reshape(-1):
        class_id = class_ids[int(index)]
        detections.append(Detection(label=LABELS[class_id], score=scores[int(index)]))
    detections.sort(key=lambda item: item.score, reverse=True)
    return detections
