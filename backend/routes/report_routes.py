from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO
from backend.config import get_settings

router = APIRouter(prefix="/api/report", tags=["report"])


class ReportRequest(BaseModel):
    location: str
    question: str
    analysis: Dict[str, Any]


def _number(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _category_lines(name: str, value: dict) -> list[str]:
    area_km2 = _number(value.get("area_km2"))
    if area_km2 is None:
        area_ha = _number(value.get("area_ha"))
        area_km2 = area_ha / 100 if area_ha is not None else None
    percentage = _number(value.get("percentage") or value.get("percentage_of_valid_pixels"))
    lines = [name]
    lines.append(f"Area: {area_km2:.3f} km²" if area_km2 is not None else "Area: Data unavailable")
    if area_km2 is not None:
        lines.append(f"Land covered: {area_km2 * 10763910.4167:,.0f} sq ft")
    lines.append(f"Percentage: {percentage:.2f}%" if percentage is not None else "Percentage: Data unavailable")
    return lines


def _report_lines(req: ReportRequest) -> list[str]:
    """Build a compact user-facing report from structured result fields only."""
    analysis = req.analysis or {}
    loc = analysis.get("location") if isinstance(analysis.get("location"), dict) else {}
    resolved = loc.get("display_name") or req.location or "Selected area"
    aoi_area = _number(loc.get("aoi_area_km2") or analysis.get("aoi_area_km2"))
    lines = [
        "SATQUERY AI",
        "REMOTE SENSING ANALYSIS REPORT",
        f"Generated: {datetime.now(timezone.utc).strftime('%d %B %Y, %H:%M UTC')}",
        "",
        f"Location: {resolved}",
        f"Selected area: {aoi_area:.3f} km²" if aoi_area is not None else "Selected area: Data unavailable",
        "",
        f"Analysis: {req.question}",
    ]

    categories = analysis.get("categories")
    if isinstance(categories, dict):
        lines.extend(["", "LAND-COVER ANALYSIS", "-" * 48])
        for name in ("Water", "Agriculture", "Built-up", "Forest / Vegetation"):
            value = categories.get(name)
            if isinstance(value, dict):
                lines.extend(_category_lines(name, value))
                lines.append("")
    elif analysis.get("selected_category") or analysis.get("class"):
        lines.extend(["", "LAND-COVER ANALYSIS", "-" * 48])
        lines.extend(_category_lines(
            str(analysis.get("selected_category") or analysis.get("class")),
            analysis,
        ))
    else:
        summary = analysis.get("answer_text") or analysis.get("summary") or analysis.get("message")
        if summary:
            lines.extend(["", "RESULT", "-" * 48, str(summary)])

        measurements = (
            ("Water-covered area", analysis.get("water_area_km2")),
            ("Vegetation area", analysis.get("vegetation_area_km2")),
            ("Built-up area", analysis.get("builtup_area_km2")),
            ("NDVI mean", analysis.get("ndvi_mean")),
            ("NDWI mean", analysis.get("ndwi_mean")),
            ("NDBI mean", analysis.get("ndbi_mean")),
        )
        available = [(label, value) for label, value in measurements if value is not None]
        if available:
            lines.extend(["", "MEASUREMENTS", "-" * 48])
            lines.extend(f"{label}: {value}" for label, value in available)

    status = analysis.get("data_status") or analysis.get("status")
    source = analysis.get("source") or analysis.get("analysis_method")
    acquisition_date = analysis.get("acquisition_date")
    if status or source or acquisition_date:
        lines.extend(["", "DATA QUALITY", "-" * 48])
        if status:
            lines.append(f"Status: {status}")
        if source:
            lines.append(f"Source: {source}")
        if acquisition_date:
            lines.append(f"Acquisition date: {acquisition_date}")

    lines.extend([
        "",
        "DISCLAIMER",
        "-" * 48,
        "Derived satellite indices are estimates, not official measurements.",
        "SatQuery AI does not provide an official emergency warning.",
    ])
    return [str(line) for line in lines]


@router.post("")
async def generate_report(req: ReportRequest):
    """Generate a text analysis report (JSON + plain text summary)."""
    settings = get_settings()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    text = "\n".join(_report_lines(req))
    out_path = settings.OUTPUTS_DIR / f"report_{ts}.txt"
    out_path.write_text(text, encoding="utf-8")
    return {
        "success": True,
        "report_text": text,
        "file": str(out_path.name),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/pdf")
async def generate_pdf(req: ReportRequest):
    """Render the selected, stored analysis as an inspectable PDF."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
        from xml.sax.saxutils import escape
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"PDF support is unavailable: {exc}") from exc

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.6 * inch,
        leftMargin=0.6 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title=f"SatQuery AI — {req.question}",
    )
    styles = getSampleStyleSheet()
    story = []
    for index, line in enumerate(_report_lines(req)):
        safe = escape(line).replace("\n", "<br/>")
        story.append(Paragraph(safe or " ", styles["Title" if index == 0 else "BodyText"]))
        story.append(Spacer(1, 0.06 * inch))
    doc.build(story)
    buffer.seek(0)
    filename = "satquery_analysis_report.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
