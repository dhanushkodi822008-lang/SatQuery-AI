from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from pathlib import Path
from backend.config import get_settings

router = APIRouter(prefix="/api/report", tags=["report"])


class ReportRequest(BaseModel):
    location: str
    question: str
    analysis: Dict[str, Any]


@router.post("")
async def generate_report(req: ReportRequest):
    """Generate a text analysis report (JSON + plain text summary)."""
    settings = get_settings()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    analysis = req.analysis
    loc = analysis.get("location") or {}
    lines = [
        "=" * 60,
        "SatQuery AI — Analysis Report",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "=" * 60,
        f"Location query: {req.location}",
        f"Resolved: {loc.get('display_name')}",
        f"Coordinates: {loc.get('lat')}, {loc.get('lon')}",
        f"AOI area (approx): {loc.get('aoi_area_km2')} km²",
        f"Geocoding source: {loc.get('source')}",
        "",
        f"Question: {req.question}",
        f"Detected task: {analysis.get('detected_task')}",
        "",
        "ANSWER",
        "-" * 40,
        analysis.get("answer_text") or "(no answer)",
        "",
        "DATA STATUS",
        "-" * 40,
        f"Status: {analysis.get('data_status')}",
        f"Freshness: {analysis.get('freshness')}",
        "",
        "SOURCES",
        "-" * 40,
    ]
    for s in analysis.get("sources") or []:
        lines.append(f"  - {s}")
    lines.extend([
        "",
        "LIMITATIONS",
        "-" * 40,
    ])
    for lim in analysis.get("limitations") or []:
        lines.append(f"  - {lim}")
    lines.extend([
        "",
        "EXECUTION TRACE",
        "-" * 40,
    ])
    for step in analysis.get("execution_trace") or []:
        lines.append(f"  [{step.get('status')}] {step.get('step')}: {step.get('detail')}")
    lines.extend([
        "",
        "DISCLAIMER",
        "-" * 40,
        "Satellite water extent ≠ gauge water level.",
        "Derived indices are estimates, not official measurements.",
        "Flood risk indicator is not an official emergency warning.",
        "SatQuery AI — SIH 2026 prototype (SIH26167).",
    ])
    text = "\n".join(str(x) for x in lines)
    out_path = settings.OUTPUTS_DIR / f"report_{ts}.txt"
    out_path.write_text(text, encoding="utf-8")
    return {
        "success": True,
        "report_text": text,
        "file": str(out_path.name),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
