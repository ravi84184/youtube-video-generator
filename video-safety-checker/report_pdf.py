"""One consolidated PDF report. Evidence images are the flagged frames."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image as RLImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from config import DISCLAIMER, MODEL_INFO, UNSUPPORTED_CATEGORIES


def write_pdf_report(payload: dict, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#1f2933"),
        alignment=TA_LEFT,
    )
    small = ParagraphStyle(
        "Small",
        parent=body,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#334155"),
    )
    heading = ParagraphStyle(
        "Heading",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#111827"),
        spaceAfter=4,
    )
    section = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#111827"),
        spaceBefore=8,
        spaceAfter=4,
    )
    video_title = ParagraphStyle(
        "VideoTitle",
        parent=section,
        fontSize=11,
        spaceBefore=10,
    )

    story: list = []
    story.append(Paragraph("Video Safety Report", heading))
    story.append(Paragraph(_esc(f"Generated {payload['generated_at']}"), small))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Scan", section))
    summary = payload["summary"]
    meta_rows = [
        ["Input folder", payload["input_folder"]],
        ["Recursive scan", "Yes" if payload["recursive"] else "No"],
        ["Videos scanned", str(summary["total"])],
        ["Low", str(summary.get("LOW", 0))],
        ["Medium", str(summary.get("MEDIUM", 0))],
        ["High", str(summary.get("HIGH", 0))],
        ["Critical", str(summary.get("CRITICAL", 0))],
        ["Restricted", str(summary.get("RESTRICTED", 0))],
        ["Incomplete", str(summary.get("INCOMPLETE", 0))],
        ["Failed", str(summary.get("FAILED", 0))],
        ["Sampling interval", f"{payload['settings']['frame_interval_seconds']:g} seconds"],
        ["Maximum frames", str(payload["settings"]["max_frames_per_video"])],
    ]
    story.append(_key_table(meta_rows, small))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Model", section))
    story.append(
        Paragraph(
            _esc(
                f"{MODEL_INFO['name']} version {MODEL_INFO['version']}. "
                f"{MODEL_INFO['architecture']}. Runtime: {MODEL_INFO['runtime']}. "
                f"Weights SHA-256 {MODEL_INFO['sha256']}."
            ),
            small,
        )
    )
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("Checks this model does not perform", section))
    for item in UNSUPPORTED_CATEGORIES:
        story.append(Paragraph(_esc(f"{item['id']}: {item['reason']}"), small))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Summary", section))
    story.append(_summary_table(payload["videos"], small))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Individual videos", section))

    output_dir = destination.parent
    if not payload["videos"]:
        story.append(Paragraph("No videos were scanned.", body))
    for video in payload["videos"]:
        story.extend(_video_block(video, output_dir, video_title, body, small))

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Disclaimer", section))
    story.append(Paragraph(_esc(DISCLAIMER), small))

    document = SimpleDocTemplate(
        str(destination),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Video Safety Report",
        author="Local video safety checker",
    )
    document.build(story, onFirstPage=_footer, onLaterPages=_footer)


def _video_block(video: dict, output_dir: Path, title, body, small) -> list:
    score = "n/a" if video["risk_score"] is None else str(video["risk_score"])
    confidence = video.get("max_model_confidence")
    confidence_text = "n/a" if confidence is None else f"{float(confidence):.2f}"
    categories = ", ".join(video.get("detected_categories") or []) or "None"
    timestamps = ", ".join(video.get("flagged_timestamps") or []) or "None"
    lines = [
        Paragraph(_esc(video["relative_path"]), title),
        Paragraph(
            _esc(
                f"Risk {video['risk_level']} ({score}). "
                f"Maximum scoring confidence {confidence_text}. "
                f"Flagged frames {video['flagged_frame_count']}. "
                f"Frames analysed {video['frames_analysed']}. "
                f"Completeness: {video['analysis_completeness']}."
            ),
            body,
        ),
        Paragraph(_esc(f"Categories: {categories}"), small),
        Paragraph(_esc(f"Flagged timestamps: {timestamps}"), small),
        Paragraph(_esc(f"Recommendation: {video['recommendation']}"), small),
    ]
    if video.get("error"):
        lines.append(Paragraph(_esc(f"Error: {video['error']}"), small))
    labels = video.get("scored_labels") or []
    if labels:
        shown = ", ".join(
            f"{item['label']} {item['score']:.2f} at {item['timestamp']}" for item in labels[:8]
        )
        lines.append(Paragraph(_esc(f"Scoring labels: {shown}"), small))
    context = video.get("context_summary") or []
    if context:
        shown = ", ".join(
            f"{item['label']} x{item['count']} (max {item['max_score']:.2f})"
            for item in context[:8]
        )
        lines.append(
            Paragraph(
                _esc(f"Not scored (does not raise risk): {shown}"),
                small,
            )
        )
    if video.get("sha256"):
        lines.append(Paragraph(_esc(f"SHA-256: {video['sha256']}"), small))
    evidence = video.get("evidence") or []
    image_blocks = []
    for item in evidence[:8]:
        path = output_dir / str(item["path"])
        if not path.is_file():
            continue
        try:
            image = RLImage(str(path))
            width = 70 * mm
            height = width * (image.imageHeight / float(image.imageWidth or 1))
            if height > 120 * mm:
                height = 120 * mm
                width = height * (image.imageWidth / float(image.imageHeight or 1))
            image.drawWidth = width
            image.drawHeight = height
            image_blocks.append(image)
            image_blocks.append(Paragraph(_esc(str(item.get("timestamp", ""))), small))
            image_blocks.append(Spacer(1, 2 * mm))
        except Exception:
            continue
    if image_blocks:
        lines.append(Spacer(1, 1.5 * mm))
        lines.append(Paragraph("Flagged frames at the listed timestamps.", small))
        lines.append(Spacer(1, 1 * mm))
        lines.extend(image_blocks)
    lines.append(Spacer(1, 2 * mm))
    return lines


def _summary_table(videos: list[dict], style) -> Table:
    header = [
        Paragraph("<b>Video</b>", style),
        Paragraph("<b>Risk</b>", style),
        Paragraph("<b>Score</b>", style),
        Paragraph("<b>Flagged</b>", style),
        Paragraph("<b>Recommendation</b>", style),
    ]
    rows = [header]
    for video in videos:
        score = "n/a" if video["risk_score"] is None else str(video["risk_score"])
        rows.append(
            [
                Paragraph(_esc(video["relative_path"]), style),
                Paragraph(_esc(str(video["risk_level"])), style),
                Paragraph(score, style),
                Paragraph(str(video["flagged_frame_count"]), style),
                Paragraph(_esc(str(video["recommendation"])), style),
            ]
        )
    if len(rows) == 1:
        rows.append([Paragraph("No videos.", style), "", "", "", ""])
    table = Table(rows, colWidths=[42 * mm, 24 * mm, 16 * mm, 18 * mm, 78 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111827")),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _key_table(pairs: list[list[str]], style) -> Table:
    rows = [[Paragraph(f"<b>{_esc(key)}</b>", style), Paragraph(_esc(value), style)] for key, value in pairs]
    table = Table(rows, colWidths=[40 * mm, 138 * mm])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def _footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawString(16 * mm, 8 * mm, "Local video safety checker. Sampling screen, not a platform decision.")
    canvas.drawRightString(A4[0] - 16 * mm, 8 * mm, f"Page {document.page}")
    canvas.restoreState()


def _esc(value: object) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
