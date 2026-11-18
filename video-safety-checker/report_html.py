"""Standalone offline HTML report. No remote assets and no server."""

from __future__ import annotations

import html
from pathlib import Path

from config import DISCLAIMER, MODEL_INFO, UNSUPPORTED_CATEGORIES


def write_html_report(payload: dict, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    summary = payload["summary"]
    cards = [
        ("Scanned", summary.get("total", 0), "all"),
        ("Low", summary.get("LOW", 0), "LOW"),
        ("Medium", summary.get("MEDIUM", 0), "MEDIUM"),
        ("High", summary.get("HIGH", 0), "HIGH"),
        ("Critical", summary.get("CRITICAL", 0), "CRITICAL"),
        ("Incomplete", summary.get("INCOMPLETE", 0), "INCOMPLETE"),
        ("Failed", summary.get("FAILED", 0), "FAILED"),
    ]
    if summary.get("RESTRICTED"):
        cards.append(("Restricted", summary["RESTRICTED"], "RESTRICTED"))

    card_html = "\n".join(
        (
            f'<button type="button" class="card" data-filter="{html.escape(key)}">'
            f'<span class="card-value">{count}</span>'
            f'<span class="card-label">{html.escape(label)}</span></button>'
        )
        for label, count, key in cards
    )
    unsupported = "\n".join(
        f"<li><strong>{html.escape(item['id'])}.</strong> {html.escape(item['reason'])}</li>"
        for item in UNSUPPORTED_CATEGORIES
    )
    videos = "\n".join(_video_article(video) for video in payload["videos"])
    if not videos:
        videos = '<p class="empty">No videos were scanned.</p>'

    document = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Video Safety Report</title>
<style>
:root {{
  color-scheme: light;
  --bg: #f4f6f8;
  --paper: #ffffff;
  --ink: #1f2933;
  --muted: #52606d;
  --line: #e4e7eb;
  --low: #0f7b4c;
  --medium: #8a5a00;
  --high: #c2410c;
  --critical: #b42318;
  --restricted: #7f1d1d;
  --incomplete: #334e68;
  --failed: #3e4c59;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  font-family: "Segoe UI", system-ui, sans-serif;
  background: var(--bg);
  color: var(--ink);
  line-height: 1.45;
}}
header.page, main {{
  width: min(1100px, calc(100% - 32px));
  margin: 0 auto;
}}
header.page {{ padding: 28px 0 8px; }}
h1 {{ margin: 0 0 6px; font-size: 1.8rem; }}
h2 {{ margin: 28px 0 8px; font-size: 1.15rem; }}
.meta, .note, .disclaimer {{ color: var(--muted); }}
.cards {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 10px;
  margin: 16px 0;
}}
.card {{
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px;
  text-align: left;
  cursor: pointer;
}}
.card.active {{ outline: 2px solid #243b53; }}
.card-value {{ display: block; font-size: 1.5rem; font-weight: 700; }}
.card-label {{ color: var(--muted); font-size: 0.85rem; }}
.toolbar {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin: 8px 0 14px;
}}
input[type="search"], select {{
  font: inherit;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: white;
}}
input[type="search"] {{ flex: 1 1 220px; }}
.video {{
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 14px 16px;
  margin: 0 0 10px;
}}
.video-top {{
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}}
.filename {{ font-weight: 650; word-break: break-word; }}
.pill {{
  display: inline-block;
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: white;
  background: var(--failed);
}}
.pill.LOW {{ background: var(--low); }}
.pill.MEDIUM {{ background: var(--medium); }}
.pill.HIGH {{ background: var(--high); }}
.pill.CRITICAL {{ background: var(--critical); }}
.pill.RESTRICTED {{ background: var(--restricted); }}
.pill.INCOMPLETE {{ background: var(--incomplete); }}
.pill.FAILED {{ background: var(--failed); }}
.stats {{ color: var(--muted); font-size: 0.92rem; margin: 6px 0; }}
details {{ margin-top: 6px; }}
.thumbs {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }}
figure {{ margin: 0; width: min(320px, 100%); }}
img {{ width: 100%; border-radius: 8px; background: #d9e2ec; }}
figcaption {{ font-size: 0.75rem; color: var(--muted); }}
ul {{ margin: 6px 0 0 18px; padding: 0; }}
.hidden {{ display: none; }}
@media (max-width: 640px) {{
  .video-top {{ flex-direction: column; }}
}}
@media print {{
  body {{ background: white; }}
  .toolbar, .cards {{ display: none; }}
  .video {{ break-inside: avoid; border-color: #ccc; }}
  details {{ display: block; }}
  details > *:not(summary) {{ display: block; }}
}}
</style>
</head>
<body>
<header class="page">
  <h1>Video Safety Report</h1>
  <p class="meta">Generated {_esc(payload["generated_at"])}<br>
  Input folder: {_esc(payload["input_folder"])}<br>
  Recursive: {"yes" if payload["recursive"] else "no"}</p>
</header>
<main>
  <section class="cards" aria-label="Summary">{card_html}</section>
  <section class="toolbar">
    <input id="search" type="search" placeholder="Search filename or category" aria-label="Search videos">
    <label>Sort
      <select id="sort">
        <option value="scan">Scan order</option>
        <option value="risk">Risk</option>
        <option value="score">Score</option>
        <option value="name">Filename</option>
        <option value="flagged">Flagged frames</option>
      </select>
    </label>
    <button type="button" id="expand">Expand all</button>
  </section>
  <section id="list">{videos}</section>
  <h2>Model</h2>
  <p>{_esc(MODEL_INFO["name"])} version {_esc(MODEL_INFO["version"])}. {_esc(MODEL_INFO["architecture"])}. Runtime: {_esc(MODEL_INFO["runtime"])}.</p>
  <p class="note">Weights file {_esc(MODEL_INFO["file"])}. SHA-256 {_esc(MODEL_INFO["sha256"])}.</p>
  <h2>Checks this model does not perform</h2>
  <ul>{unsupported}</ul>
  <h2>Disclaimer</h2>
  <p class="disclaimer">{_esc(DISCLAIMER)}</p>
</main>
<script>
const list = document.getElementById("list");
const search = document.getElementById("search");
const sort = document.getElementById("sort");
let filter = "all";
const rank = {{RESTRICTED:6, CRITICAL:5, HIGH:4, MEDIUM:3, INCOMPLETE:2, FAILED:1, LOW:0}};

function apply() {{
  const query = search.value.trim().toLowerCase();
  const items = Array.from(list.querySelectorAll(".video"));
  const mode = sort.value;
  const indexed = items.map((node, index) => ({{node, index}}));
  indexed.sort((a, b) => {{
    if (mode === "name") return a.node.dataset.name.localeCompare(b.node.dataset.name);
    if (mode === "score") return Number(b.node.dataset.score) - Number(a.node.dataset.score);
    if (mode === "flagged") return Number(b.node.dataset.flagged) - Number(a.node.dataset.flagged);
    if (mode === "risk") return (rank[b.node.dataset.level] || 0) - (rank[a.node.dataset.level] || 0);
    return a.index - b.index;
  }});
  indexed.forEach((item) => list.appendChild(item.node));
  items.forEach((node) => {{
    const matchesFilter = filter === "all" || node.dataset.level === filter;
    const haystack = (node.dataset.name + " " + node.dataset.categories).toLowerCase();
    const matchesQuery = !query || haystack.includes(query);
    node.classList.toggle("hidden", !(matchesFilter && matchesQuery));
  }});
}}

document.querySelectorAll(".card").forEach((card) => {{
  card.addEventListener("click", () => {{
    filter = card.dataset.filter;
    document.querySelectorAll(".card").forEach((other) => other.classList.toggle("active", other === card));
    apply();
  }});
}});
search.addEventListener("input", apply);
sort.addEventListener("change", apply);
document.getElementById("expand").addEventListener("click", () => {{
  const details = list.querySelectorAll("details");
  const open = Array.from(details).some((node) => !node.open);
  details.forEach((node) => {{ node.open = open; }});
}});
window.addEventListener("beforeprint", () => {{
  document.querySelectorAll("details").forEach((node) => {{ node.open = true; }});
}});
</script>
</body>
</html>
"""
    destination.write_text(document, encoding="utf-8")


def _video_article(video: dict) -> str:
    score = video.get("risk_score")
    score_text = "n/a" if score is None else str(score)
    score_sort = -1 if score is None else score
    level = str(video.get("risk_level") or "FAILED")
    categories = video.get("detected_categories") or []
    category_text = ", ".join(categories) if categories else "None"
    timestamps = video.get("flagged_timestamps") or []
    timestamp_text = ", ".join(timestamps) if timestamps else "None"
    confidence = video.get("max_model_confidence")
    confidence_text = "n/a" if confidence is None else f"{float(confidence):.2f}"
    evidence = []
    for item in video.get("evidence") or []:
        evidence.append(
            "<figure>"
            f'<img src="{_esc(item["path"])}" alt="Flagged frame at {_esc(item["timestamp"])}">'
            f"<figcaption>{_esc(item['timestamp'])}</figcaption>"
            "</figure>"
        )
    evidence_html = ""
    if evidence:
        evidence_html = (
            f'<div class="thumbs">{"".join(evidence)}</div>'
        )
    scored = video.get("scored_labels") or []
    scored_html = ""
    if scored:
        items = "".join(
            "<li>{label} {score:.2f} at {timestamp}</li>".format(
                label=_esc(item["label"]),
                score=float(item["score"]),
                timestamp=_esc(item["timestamp"]),
            )
            for item in scored[:12]
        )
        scored_html = f"<p>Scoring labels</p><ul>{items}</ul>"
    context = video.get("context_summary") or []
    context_html = ""
    if context:
        items = "".join(
            "<li>{label}: {count} detection(s), max {score:.2f}. Not scored.</li>".format(
                label=_esc(item["label"]),
                count=_esc(item["count"]),
                score=float(item["max_score"]),
            )
            for item in context
        )
        context_html = (
            "<p>Detections that did not raise the score "
            "(covered parts, faces, belly, feet, armpits, male chest)</p>"
            f"<ul>{items}</ul>"
        )
    error_html = ""
    if video.get("error"):
        error_html = f"<p>Error: {_esc(video['error'])}</p>"
    warning_html = ""
    warnings = video.get("warnings") or []
    if warnings:
        warning_html = "<ul>" + "".join(f"<li>{_esc(item)}</li>" for item in warnings) + "</ul>"
    metadata = video.get("metadata") or {}
    duration = metadata.get("duration_seconds")
    duration_text = "unknown" if duration is None else f"{float(duration):.1f}s"
    return (
        f'<article class="video" data-level="{_esc(level)}" '
        f'data-name="{_esc(video["relative_path"])}" '
        f'data-score="{score_sort}" data-flagged="{int(video.get("flagged_frame_count") or 0)}" '
        f'data-categories="{_esc(category_text)}">'
        '<div class="video-top">'
        f'<div class="filename">{_esc(video["relative_path"])}</div>'
        f'<span class="pill { _esc(level) }">{_esc(level)} { _esc(score_text) }</span>'
        "</div>"
        '<p class="stats">'
        f"Frames analysed {_esc(video.get('frames_analysed'))}. "
        f"Flagged {_esc(video.get('flagged_frame_count'))}. "
        f"Max confidence {_esc(confidence_text)}. "
        f"Completeness {_esc(video.get('analysis_completeness'))}."
        "</p>"
        f"<p>Flagged timestamps: {_esc(timestamp_text)}</p>"
        f"<p>{_esc(video.get('recommendation'))}</p>"
        "<details><summary>Details</summary>"
        f"<p>Categories: {_esc(category_text)}</p>"
        f"<p>SHA-256: {_esc(video.get('sha256') or 'n/a')}</p>"
        f"<p>Duration { _esc(duration_text) }, "
        f"{_esc(metadata.get('width') or '?')}x{_esc(metadata.get('height') or '?')}, "
        f"codec {_esc(metadata.get('codec') or 'unknown')}.</p>"
        f"<p>Analysed timestamps: {_esc(', '.join(video.get('analysed_timestamps') or []) or 'None')}</p>"
        f"{error_html}{warning_html}{scored_html}{context_html}{evidence_html}"
        "</details></article>"
    )


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)
