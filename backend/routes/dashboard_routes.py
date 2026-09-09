"""
District / AOI Overview Dashboard + multi-hazard risk + export + alerts.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import io

from backend.ai.disaster_risk import assess_all_hazards, HAZARD_META
from backend.services.export_service import build_export_zip
from backend.utils.logging import logger

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# In-memory store for demo alerts (replace with DB in production)
_ALERT_RULES: Dict[str, Dict] = {}
_ALERTS: List[Dict] = []
_ANALYSIS_CACHE: Dict[str, Dict] = {}


class AoiRequest(BaseModel):
    district: str = Field(..., description="District or AOI name")
    lat: Optional[float] = None
    lon: Optional[float] = None
    aoi_geojson: Optional[Dict] = None
    aoi_area_km2: Optional[float] = None
    weather: Optional[Dict] = None
    water_extent: Optional[Dict] = None
    water_level: Optional[Dict] = None
    landcover: Optional[Dict] = None
    change: Optional[Dict] = None
    terrain: Optional[Dict] = None
    composition: Optional[Dict] = None
    water_bodies: Optional[List[Dict]] = None
    change_detection: Optional[List[Dict]] = None


class AlertRuleCreate(BaseModel):
    aoi_id: str
    aoi_name: str
    hazard: str
    threshold_severity: Optional[str] = None  # LOW/MODERATE/HIGH/SEVERE
    threshold_score: Optional[float] = None
    channel: str = "in_app"  # in_app | push | email


class ExportRequest(BaseModel):
    district: str
    analysis_date: Optional[str] = None
    aoi_geojson: Optional[Dict] = None
    composition: Optional[Dict] = None
    water_bodies: Optional[List[Dict]] = None
    change_detection: Optional[List[Dict]] = None
    risk_scores: Optional[Dict] = None
    indicators: Optional[Dict] = None
    metadata: Optional[Dict] = None
    summary_text: Optional[str] = None
    landcover_geojson: Optional[Dict] = None


def _build_composition_from_landcover(landcover: Optional[Dict], area_km2: Optional[float]) -> Dict:
    """Derive composition stats from landcover analysis if present."""
    if not landcover or not landcover.get("success"):
        return {"total_area_km2": area_km2, "classes": [], "unavailable": True}

    classes = []
    total = area_km2 or landcover.get("aoi_area_km2") or 0
    # Prefer explicit class percentages if provided
    if landcover.get("class_percentages"):
        for name, pct in landcover["class_percentages"].items():
            classes.append({
                "name": name,
                "percent": round(pct, 1),
                "area_km2": round(total * pct / 100, 2) if total else None,
            })
    elif landcover.get("summary"):
        # Fallback heuristic from category analysis
        cat = landcover.get("selected_category") or landcover.get("class") or "Other"
        pct = landcover.get("coverage_percent") or landcover.get("percent") or 0
        classes.append({
            "name": cat,
            "percent": round(pct, 1),
            "area_km2": round(total * pct / 100, 2) if total else None,
        })
        if pct < 100:
            classes.append({
                "name": "Other Land",
                "percent": round(100 - pct, 1),
                "area_km2": round(total * (100 - pct) / 100, 2) if total else None,
            })
    else:
        return {"total_area_km2": total, "classes": [], "unavailable": True}

    return {
        "total_area_km2": round(total, 2) if total else None,
        "classes": classes,
        "unavailable": False,
        "source": landcover.get("analysis_method") or "landcover pipeline",
    }


@router.post("/overview")
async def district_overview(req: AoiRequest):
    """
    Full district / AOI overview payload for the dashboard:
    composition, water bodies, change detection, multi-hazard risk.
    """
    analysis_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    composition = req.composition or _build_composition_from_landcover(req.landcover, req.aoi_area_km2)

    # Water bodies — pass through if provided, else mark unavailable
    water_bodies = req.water_bodies
    if water_bodies is None:
        water_bodies = []
        water_status = "unavailable"
    else:
        water_status = "ok"

    # Change detection list
    change_list = req.change_detection
    if change_list is None and req.change:
        change_list = []
        for key, label in [
            ("water_change_pct", "Water Bodies"),
            ("agriculture_change_pct", "Agricultural Land"),
            ("builtup_change_pct", "Built-up Area"),
            ("vegetation_change_pct", "Vegetation"),
        ]:
            pct = req.change.get(key)
            if pct is not None:
                change_list.append({
                    "class": label,
                    "percent_change": round(pct, 1),
                    "delta_km2": None,
                    "direction": "up" if pct > 0 else ("down" if pct < 0 else "stable"),
                    "thumbnail_before": None,
                    "thumbnail_after": None,
                })
        if not change_list:
            change_list = None

    # Multi-hazard risk
    risk = assess_all_hazards(
        weather=req.weather,
        water_extent=req.water_extent,
        water_level=req.water_level,
        landcover=req.landcover,
        change=req.change,
        terrain=req.terrain,
        place_name=req.district,
    )

    payload = {
        "success": True,
        "analysis_id": analysis_id,
        "district": req.district,
        "analysis_date": now[:10],
        "assessed_at": now,
        "aoi_area_km2": req.aoi_area_km2 or composition.get("total_area_km2"),
        "composition": composition,
        "water_bodies": {
            "status": water_status,
            "items": water_bodies,
        },
        "change_detection": {
            "status": "ok" if change_list else "unavailable",
            "items": change_list or [],
        },
        "risk": risk,
        "hazard_meta": HAZARD_META,
        "lat": req.lat,
        "lon": req.lon,
    }

    _ANALYSIS_CACHE[analysis_id] = payload
    return payload


@router.get("/risk/{hazard}")
async def single_hazard_detail(hazard: str, analysis_id: Optional[str] = None):
    """Detail view for one hazard (trend placeholder + indicators)."""
    if hazard not in HAZARD_META:
        raise HTTPException(404, f"Unknown hazard: {hazard}")

    cached = _ANALYSIS_CACHE.get(analysis_id or "") if analysis_id else None
    risk_block = None
    if cached and cached.get("risk"):
        risk_block = cached["risk"]["hazards"].get(hazard)

    if not risk_block:
        # Minimal empty response
        risk_block = {
            "hazard": hazard,
            "label": HAZARD_META[hazard]["label"],
            "score": 0,
            "severity": "LOW",
            "confidence": 0,
            "explanation": "No analysis run yet. Call /api/dashboard/overview first.",
            "contributing_factors": [],
            "dataSources": [],
            "lastUpdatedAt": datetime.now(timezone.utc).isoformat(),
        }

    # 30-day trend is a placeholder until historical storage is added
    trend = {
        "available": False,
        "message": "Historical risk trend requires persistent storage of past scores (not yet configured).",
        "points": [],
    }

    return {
        "success": True,
        "hazard": risk_block,
        "trend": trend,
        "recommended_actions": _recommended_actions(hazard, risk_block.get("severity", "LOW")),
    }


def _recommended_actions(hazard: str, severity: str) -> List[str]:
    base = {
        "flood": [
            "Monitor local flood bulletins and river gauges.",
            "Avoid low-lying areas if rainfall is intense.",
            "Prepare emergency kit and evacuation route.",
        ],
        "drought": [
            "Conserve water; prioritise essential uses.",
            "Monitor crop stress via NDVI if agricultural AOI.",
            "Check local drought advisories.",
        ],
        "wildfire": [
            "Avoid open burning; clear dry vegetation near structures.",
            "Monitor active-fire feeds (FIRMS) if available.",
            "Follow local fire restrictions.",
        ],
        "heatwave": [
            "Limit outdoor activity during peak hours.",
            "Stay hydrated; check on vulnerable people.",
            "Use cooling centres if available.",
        ],
    }
    actions = base.get(hazard, ["Review local emergency guidance for this hazard."])
    if severity in ("HIGH", "SEVERE"):
        actions = ["Elevated risk — act on official warnings first."] + actions
    return actions


# ---- Alerts ----

@router.post("/alerts/rules")
async def create_alert_rule(rule: AlertRuleCreate):
    if rule.hazard not in HAZARD_META:
        raise HTTPException(400, f"Unknown hazard: {rule.hazard}")
    rid = str(uuid.uuid4())
    entry = {
        "id": rid,
        **rule.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "active": True,
    }
    _ALERT_RULES[rid] = entry
    return {"success": True, "rule": entry}


@router.get("/alerts/rules")
async def list_alert_rules():
    return {"success": True, "rules": list(_ALERT_RULES.values())}


@router.delete("/alerts/rules/{rule_id}")
async def delete_alert_rule(rule_id: str):
    if rule_id not in _ALERT_RULES:
        raise HTTPException(404, "Rule not found")
    del _ALERT_RULES[rule_id]
    return {"success": True}


@router.get("/alerts")
async def list_alerts(
    hazard: Optional[str] = None,
    severity: Optional[str] = None,
    unread_only: bool = False,
):
    items = _ALERTS
    if hazard:
        items = [a for a in items if a.get("hazard") == hazard]
    if severity:
        items = [a for a in items if a.get("severity") == severity]
    if unread_only:
        items = [a for a in items if not a.get("read")]
    return {"success": True, "alerts": items, "unread_count": sum(1 for a in _ALERTS if not a.get("read"))}


@router.post("/alerts/{alert_id}/read")
async def mark_alert_read(alert_id: str):
    for a in _ALERTS:
        if a["id"] == alert_id:
            a["read"] = True
            return {"success": True}
    raise HTTPException(404, "Alert not found")


@router.post("/alerts/evaluate")
async def evaluate_alerts(analysis_id: str = Query(...)):
    """
    Re-score cached analysis against active rules and emit new alerts
    (de-duplicated by hazard + severity).
    """
    cached = _ANALYSIS_CACHE.get(analysis_id)
    if not cached:
        raise HTTPException(404, "Analysis not found — run overview first")

    risk = cached.get("risk") or {}
    hazards = risk.get("hazards") or {}
    new_alerts = []
    severity_rank = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "SEVERE": 3}

    for rule in _ALERT_RULES.values():
        if not rule.get("active"):
            continue
        h = rule["hazard"]
        result = hazards.get(h)
        if not result:
            continue
        score = result.get("score", 0)
        sev = result.get("severity", "LOW")
        triggered = False
        if rule.get("threshold_score") is not None and score >= rule["threshold_score"]:
            triggered = True
        if rule.get("threshold_severity"):
            if severity_rank.get(sev, 0) >= severity_rank.get(rule["threshold_severity"], 0):
                triggered = True
        if not triggered:
            continue

        # De-dupe: same hazard + severity within last hour
        recent = [
            a for a in _ALERTS
            if a.get("hazard") == h and a.get("severity") == sev and a.get("aoi_id") == rule["aoi_id"]
        ]
        if recent:
            continue

        alert = {
            "id": str(uuid.uuid4()),
            "rule_id": rule["id"],
            "hazard": h,
            "label": result.get("label"),
            "aoi_id": rule["aoi_id"],
            "aoi_name": rule["aoi_name"],
            "score": score,
            "severity": sev,
            "channel": rule["channel"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "read": False,
            "message": f"{result.get('label')} risk is {sev} (score {score}) for {rule['aoi_name']}",
        }
        _ALERTS.insert(0, alert)
        new_alerts.append(alert)

    return {"success": True, "new_alerts": new_alerts, "total_alerts": len(_ALERTS)}


# ---- Export (single folder ZIP) ----

@router.post("/export/zip")
async def export_zip(req: ExportRequest):
    """
    Build and stream a single ZIP archive for the current AOI / analysis run.
    """
    try:
        zip_bytes = build_export_zip(
            district=req.district,
            analysis_date=req.analysis_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            aoi_geojson=req.aoi_geojson,
            composition=req.composition,
            water_bodies=req.water_bodies,
            change_detection=req.change_detection,
            risk_scores=req.risk_scores,
            indicators=req.indicators,
            metadata=req.metadata,
            summary_text=req.summary_text,
            landcover_geojson=req.landcover_geojson,
        )
    except Exception as e:
        logger.exception("ZIP export failed")
        raise HTTPException(500, f"Export failed: {e}")

    fname = f"{req.district.replace(' ', '_')}_{req.analysis_date or 'export'}.zip"
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/hazards")
async def list_hazards():
    return {
        "success": True,
        "hazards": [
            {"id": k, "label": v["label"], "color": v["color"]}
            for k, v in HAZARD_META.items()
        ],
    }
