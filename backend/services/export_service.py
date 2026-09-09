"""
Single-folder ZIP export for a district / AOI analysis run.
Builds the package described in the SatQuery dashboard prompt.
"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.config import get_settings


def _safe_name(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in (s or "aoi"))[:80]


def _write_csv(rows: List[Dict[str, Any]], fieldnames: List[str]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue().encode("utf-8")


def build_export_zip(
    *,
    district: str,
    analysis_date: str,
    aoi_geojson: Optional[Dict] = None,
    composition: Optional[Dict] = None,
    water_bodies: Optional[List[Dict]] = None,
    change_detection: Optional[List[Dict]] = None,
    risk_scores: Optional[Dict] = None,
    indicators: Optional[Dict] = None,
    metadata: Optional[Dict] = None,
    summary_text: Optional[str] = None,
    map_png: Optional[bytes] = None,
    composition_chart_png: Optional[bytes] = None,
    risk_trend_png: Optional[bytes] = None,
    change_images: Optional[Dict[str, bytes]] = None,
    landcover_geojson: Optional[Dict] = None,
    report_pdf: Optional[bytes] = None,
) -> bytes:
    """
    Assemble the ZIP archive in memory and return the bytes.
    Missing artifacts are recorded in metadata.json under failures[].
    """
    settings = get_settings()
    ts = analysis_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    folder = f"{_safe_name(district)}_{ts}"
    failures: List[str] = []

    meta = dict(metadata or {})
    meta.setdefault("district", district)
    meta.setdefault("analysis_date", ts)
    meta.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
    meta.setdefault("app", settings.APP_NAME)
    meta.setdefault("version", settings.APP_VERSION)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # summary.md
        summary = summary_text or _default_summary(district, ts, composition, risk_scores)
        zf.writestr(f"{folder}/summary.md", summary)

        # data/composition.csv
        if composition and composition.get("classes"):
            rows = []
            for c in composition["classes"]:
                rows.append({
                    "class": c.get("name"),
                    "percent": c.get("percent"),
                    "area_km2": c.get("area_km2"),
                })
            zf.writestr(
                f"{folder}/data/composition.csv",
                _write_csv(rows, ["class", "percent", "area_km2"]),
            )
        else:
            failures.append("composition.csv")

        # data/water_bodies.csv
        if water_bodies:
            zf.writestr(
                f"{folder}/data/water_bodies.csv",
                _write_csv(
                    water_bodies,
                    ["name", "type", "current_level_m", "change_vs_last_year", "source"],
                ),
            )
        else:
            failures.append("water_bodies.csv")

        # data/change_detection.csv
        if change_detection:
            zf.writestr(
                f"{folder}/data/change_detection.csv",
                _write_csv(
                    change_detection,
                    ["class", "percent_change", "delta_km2", "direction"],
                ),
            )
        else:
            failures.append("change_detection.csv")

        # data/risk_scores.csv
        if risk_scores and risk_scores.get("hazards"):
            rows = []
            for h, r in risk_scores["hazards"].items():
                rows.append({
                    "hazard": h,
                    "label": r.get("label"),
                    "score": r.get("score"),
                    "severity": r.get("severity"),
                    "confidence": r.get("confidence"),
                })
            zf.writestr(
                f"{folder}/data/risk_scores.csv",
                _write_csv(rows, ["hazard", "label", "score", "severity", "confidence"]),
            )
        else:
            failures.append("risk_scores.csv")

        # data/indicators.json
        if indicators:
            zf.writestr(
                f"{folder}/data/indicators.json",
                json.dumps(indicators, indent=2, default=str),
            )
        else:
            failures.append("indicators.json")

        # geo/
        if aoi_geojson:
            zf.writestr(
                f"{folder}/geo/aoi.geojson",
                json.dumps(aoi_geojson, indent=2),
            )
        else:
            failures.append("aoi.geojson")

        if landcover_geojson:
            zf.writestr(
                f"{folder}/geo/landcover_mask.geojson",
                json.dumps(landcover_geojson, indent=2),
            )
        else:
            failures.append("landcover_mask.geojson")

        # images/
        if map_png:
            zf.writestr(f"{folder}/images/map_overview.png", map_png)
        else:
            failures.append("map_overview.png")

        if composition_chart_png:
            zf.writestr(f"{folder}/images/composition_chart.png", composition_chart_png)
        else:
            failures.append("composition_chart.png")

        if risk_trend_png:
            zf.writestr(f"{folder}/images/risk_trend.png", risk_trend_png)
        else:
            failures.append("risk_trend.png")

        if change_images:
            for name, data in change_images.items():
                zf.writestr(f"{folder}/images/{name}", data)

        # report.pdf (optional, may be generated upstream)
        if report_pdf:
            zf.writestr(f"{folder}/report.pdf", report_pdf)
        else:
            # Minimal placeholder text report so the folder is never empty of a report
            placeholder = (
                f"SatQuery AI — District Report\n"
                f"District: {district}\nDate: {ts}\n\n"
                f"Full PDF generation requires reportlab rendering of charts.\n"
                f"See summary.md and data/ for structured outputs.\n"
            )
            zf.writestr(f"{folder}/report.txt", placeholder)
            failures.append("report.pdf (placeholder report.txt written instead)")

        meta["failures"] = failures
        meta["artifact_count"] = len(zf.namelist())
        zf.writestr(f"{folder}/metadata.json", json.dumps(meta, indent=2, default=str))

    return buf.getvalue()


def _default_summary(
    district: str,
    ts: str,
    composition: Optional[Dict],
    risk_scores: Optional[Dict],
) -> str:
    lines = [
        f"# {district} — SatQuery AI Summary",
        f"",
        f"**Analysis date:** {ts}",
        f"",
        "## Area Composition",
    ]
    if composition and composition.get("classes"):
        total = composition.get("total_area_km2", "—")
        lines.append(f"Total area: **{total} km²**")
        lines.append("")
        for c in composition["classes"]:
            lines.append(f"- {c.get('name')}: {c.get('percent')}% ({c.get('area_km2')} km²)")
    else:
        lines.append("_Composition data unavailable for this run._")

    lines.extend(["", "## Natural Disaster Risk"])
    if risk_scores and risk_scores.get("composite"):
        comp = risk_scores["composite"]
        lines.append(f"Composite severity: **{comp.get('severity')}** (score {comp.get('score')}/100)")
        for t in comp.get("top_hazards") or []:
            lines.append(f"- {t.get('label')}: {t.get('severity')} ({t.get('score')}/100)")
    else:
        lines.append("_Risk scores unavailable._")

    lines.extend([
        "",
        "---",
        "Generated by SatQuery AI. Scores are analytical indicators, not official warnings.",
    ])
    return "\n".join(lines)
