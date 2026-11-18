"""Turn detector scores into a risk band.

A sampled or failed analysis is never reported as LOW. Score bands are
internal thresholds from config, not platform moderation rules.
"""

from __future__ import annotations

from config import RESTRICTED_CATEGORY_IDS, RESTRICTED_RECOMMENDATION
from moderation import INTIMATE_LABELS, NUDITY_LABELS, SCORING_LABELS


def format_timestamp(seconds: float) -> str:
    whole = max(0, int(round(seconds)))
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def band_for_score(score: int) -> tuple[str, str]:
    if score >= 75:
        return "CRITICAL", "Block and escalate"
    if score >= 50:
        return "HIGH", "Do not upload pending review"
    if score >= 25:
        return "MEDIUM", "Review"
    return "LOW", "Eligible for manual approval"


def empty_failure(filename: str, relative_path: str, message: str, sha256: str | None = None) -> dict:
    """A video that produced no usable analysis. This is never LOW."""
    return {
        "filename": filename,
        "relative_path": relative_path,
        "sha256": sha256,
        "metadata": {},
        "risk_score": None,
        "risk_level": "FAILED",
        "detected_categories": [],
        "scored_labels": [],
        "context_summary": [],
        "max_model_confidence": None,
        "flagged_frame_count": 0,
        "flagged_timestamps": [],
        "analysed_timestamps": [],
        "frames_analysed": 0,
        "analysis_completeness": "failed",
        "recommendation": "Scan failed. Do not treat this video as safe.",
        "error": message[:500],
        "warnings": [],
        "evidence": [],
        "frames": [],
    }


def assess_frames(
    frames: list[dict],
    coverage: str,
    thresholds: dict[str, float],
    interval_seconds: float,
    warnings: list[str] | None = None,
) -> dict:
    """Score frame dicts that already contain `detections` as label/score pairs.

    Each frame dict needs timestamp_seconds. Detections are {label, score}.
    """
    flag_score = float(thresholds.get("flag_score", 0.50))
    intimate_multiplier = float(thresholds.get("intimate_score_multiplier", 100.0))
    nudity_multiplier = float(thresholds.get("nudity_score_multiplier", 80.0))
    bonus_2 = float(thresholds.get("repeat_bonus_2", 4.0))
    bonus_3 = float(thresholds.get("repeat_bonus_3", 8.0))

    scored_frames: list[dict] = []
    categories: set[str] = set()
    scored_labels: list[dict] = []
    context_hits: list[dict] = []
    max_confidence = 0.0
    best_score = 0.0

    for frame in frames:
        timestamp = float(frame["timestamp_seconds"])
        label = format_timestamp(timestamp)
        frame_categories: list[str] = []
        frame_scored: list[dict] = []
        best_intimate = 0.0
        best_nudity = 0.0
        frame_confidence = 0.0

        for detection in frame.get("detections") or []:
            name = str(detection["label"])
            score = float(detection["score"])
            if name in SCORING_LABELS and score > max_confidence:
                max_confidence = score
            if score < flag_score:
                continue
            if name in INTIMATE_LABELS:
                best_intimate = max(best_intimate, score)
                frame_confidence = max(frame_confidence, score)
                frame_scored.append({"label": name, "score": round(score, 4)})
            elif name in NUDITY_LABELS:
                best_nudity = max(best_nudity, score)
                frame_confidence = max(frame_confidence, score)
                frame_scored.append({"label": name, "score": round(score, 4)})
            else:
                context_hits.append(
                    {"timestamp": label, "label": name, "score": round(score, 4)}
                )

        frame_score = 0.0
        if best_intimate > 0:
            frame_score = best_intimate * intimate_multiplier
            frame_categories.extend(["exposed_intimate_areas", "explicit_nudity"])
        if best_nudity > 0:
            frame_score = max(frame_score, best_nudity * nudity_multiplier)
            frame_categories.append("explicit_nudity")
        flagged = bool(frame_categories)
        if flagged:
            frame_score = max(frame_score, 25.0)
        frame_score = min(100.0, frame_score)
        best_score = max(best_score, frame_score)
        unique_categories = sorted(set(frame_categories))
        if flagged:
            categories.update(unique_categories)
        if flagged:
            for item in frame_scored:
                scored_labels.append({"timestamp": label, **item})
        scored_frames.append(
            {
                "timestamp": label,
                "timestamp_seconds": round(timestamp, 3),
                "source": frame.get("source", ""),
                "flagged": flagged,
                "score": int(round(frame_score)),
                "max_scoring_confidence": round(frame_confidence, 4),
                "categories": unique_categories,
                "scored_labels": frame_scored,
            }
        )

    flagged_frames = [frame for frame in scored_frames if frame["flagged"]]
    video_score = best_score
    if len(flagged_frames) >= 3:
        video_score += bonus_3
    elif len(flagged_frames) == 2:
        video_score += bonus_2
    video_score = int(round(min(100.0, video_score)))
    level, recommendation = band_for_score(video_score)

    completeness = coverage if frames else "incomplete"
    if completeness in {"incomplete", "limited_sample"} and level == "LOW":
        level = "INCOMPLETE"
        recommendation = (
            "Scan incomplete. Do not upload. Rescan before any approval."
            if completeness == "incomplete"
            else (
                "Frame cap was reached before the end of the video. "
                "Do not upload. Raise the frame cap or shorten the interval and rescan."
            )
        )
    elif completeness == "limited_sample":
        recommendation = (
            f"{recommendation}. Frame cap was reached before the end of the video."
        )
    elif completeness == "sampled":
        recommendation = (
            f"{recommendation}. Sampled about every {interval_seconds:g}s; "
            "brief scenes between samples can be missed."
        )
    elif completeness == "incomplete" and level != "INCOMPLETE":
        recommendation = (
            f"{recommendation}. The scan did not finish cleanly; do not treat it as complete."
        )

    flagged_timestamps = [frame["timestamp"] for frame in flagged_frames]
    result = {
        "risk_score": video_score,
        "risk_level": level,
        "detected_categories": sorted(categories),
        "scored_labels": scored_labels,
        "context_summary": _context_summary(context_hits),
        "max_model_confidence": round(max_confidence, 4),
        "flagged_frame_count": len(flagged_frames),
        "flagged_timestamps": flagged_timestamps,
        "analysed_timestamps": [frame["timestamp"] for frame in scored_frames],
        "frames_analysed": len(scored_frames),
        "analysis_completeness": completeness,
        "recommendation": recommendation,
        "error": None,
        "warnings": list(warnings or []),
        "evidence": [],
        "frames": scored_frames,
    }
    return enforce_restricted_policy(result)


def enforce_restricted_policy(result: dict) -> dict:
    """Strip previews and approval text from a restricted critical result.

    Nothing in the NudeNet adapter sets this state. The guard stays so a
    later change cannot attach thumbnails or an approval line to it.
    """
    categories = set(result.get("detected_categories") or [])
    restricted = result.get("risk_level") == "RESTRICTED" or bool(
        categories & RESTRICTED_CATEGORY_IDS
    )
    if not restricted:
        return result
    result["risk_level"] = "RESTRICTED"
    result["risk_score"] = 100
    result["detected_categories"] = ["restricted_critical"]
    result["evidence"] = []
    result["recommendation"] = RESTRICTED_RECOMMENDATION
    result["frames"] = []
    result["scored_labels"] = []
    result["context_summary"] = []
    return result


def evidence_allowed(result: dict) -> bool:
    if result.get("risk_level") in {"RESTRICTED", "FAILED"}:
        return False
    categories = set(result.get("detected_categories") or [])
    if categories & RESTRICTED_CATEGORY_IDS:
        return False
    return True


def _context_summary(hits: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for hit in hits:
        bucket = grouped.setdefault(
            hit["label"],
            {"label": hit["label"], "count": 0, "max_score": 0.0},
        )
        bucket["count"] += 1
        bucket["max_score"] = max(bucket["max_score"], float(hit["score"]))
    summary = list(grouped.values())
    summary.sort(key=lambda item: (-item["max_score"], item["label"]))
    for item in summary:
        item["max_score"] = round(float(item["max_score"]), 4)
    return summary[:12]
