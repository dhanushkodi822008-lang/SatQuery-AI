from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional

from backend.db.models import get_db, Alert, AlertHistory
from backend.services.alert_service import send_email

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class AlertCreate(BaseModel):
    location_name: str
    condition_type: str
    threshold: float
    email: Optional[str] = None
    # Exact user-selected AOI (GeoJSON Geometry, Feature, or FeatureCollection)
    aoi_geojson: Optional[Dict[str, Any]] = None


class AlertResponse(BaseModel):
    id: int
    location_name: str
    condition_type: str
    threshold: float
    email: Optional[str] = None
    active: int
    aoi_geojson: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class DirectTestAlertRequest(BaseModel):
    email: Optional[str] = None
    location_name: Optional[str] = "Namakkal District, Tamil Nadu"
    condition_type: Optional[str] = "In-App Notification Verification"
    threshold: Optional[float] = 0.30


def _validate_aoi(aoi: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Require Polygon/MultiPolygon geometry."""
    if not aoi:
        return None
    geom = aoi
    if aoi.get("type") == "Feature":
        geom = aoi.get("geometry") or {}
    elif aoi.get("type") == "FeatureCollection":
        feats = aoi.get("features") or []
        if not feats:
            raise HTTPException(400, "aoi_geojson FeatureCollection has no features")
        geom = (feats[0].get("geometry") if isinstance(feats[0], dict) else None) or {}
    gtype = (geom.get("type") or "").lower()
    if gtype not in ("polygon", "multipolygon"):
        raise HTTPException(
            400,
            "aoi_geojson must be a GeoJSON Polygon or MultiPolygon",
        )
    return aoi


@router.post("/", response_model=AlertResponse)
async def create_alert(alert_in: AlertCreate, db: Session = Depends(get_db)):
    aoi = _validate_aoi(alert_in.aoi_geojson)
    data = alert_in.model_dump() if hasattr(alert_in, "model_dump") else alert_in.dict()
    data["aoi_geojson"] = aoi
    if "phone" in data:
        data.pop("phone", None)
    db_alert = Alert(**data)
    db.add(db_alert)
    db.commit()
    db.refresh(db_alert)
    return db_alert


@router.get("/", response_model=List[AlertResponse])
async def list_alerts(db: Session = Depends(get_db)):
    return db.query(Alert).all()


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    return alert


@router.post("/test")
async def send_direct_test_alert(req: DirectTestAlertRequest, db: Session = Depends(get_db)):
    """
    Direct in-app test alert endpoint for verifying notification delivery.
    """
    location = req.location_name or "Namakkal District, Tamil Nadu"
    condition = req.condition_type or "In-App Notification Verification"

    # Log to AlertHistory as TEST
    try:
        history = AlertHistory(
            alert_id=0,
            condition_detected="TEST_ALERT",
            notification_type="in-app",
            status="success",
            error_message=f"Test notification verified for {location}",
        )
        db.add(history)
        db.commit()
    except Exception:
        db.rollback()

    return {
        "success": True,
        "type": "TEST",
        "title": "🔔 Test Alert",
        "message": "SatQuery AI notification system is working successfully.",
        "location": location,
        "condition": condition,
    }


@router.get("/history/list")
async def list_alert_history(limit: int = 50, db: Session = Depends(get_db)):
    """Retrieve historical alert log records (both TEST and REAL)."""
    rows = (
        db.query(AlertHistory)
        .order_by(AlertHistory.timestamp.desc())
        .limit(limit)
        .all()
    )
    return {
        "success": True,
        "history": [
            {
                "id": r.id,
                "alert_id": r.alert_id,
                "condition_detected": r.condition_detected,
                "notification_type": r.notification_type,
                "status": r.status,
                "error_message": r.error_message,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            }
            for r in rows
        ],
    }


@router.post("/{alert_id}/test")
async def test_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert rule not found")

    has_aoi = bool(alert.aoi_geojson)
    try:
        history = AlertHistory(
            alert_id=alert.id,
            condition_detected="TEST_ALERT",
            notification_type="in-app",
            status="success",
            error_message="Test alert rule verification",
        )
        db.add(history)
        db.commit()
        return {
            "success": True,
            "type": "TEST",
            "title": f"🔔 Test Alert: Rule #{alert.id}",
            "message": f"Monitoring rule for {alert.location_name} is active.",
            "aoi_stored": has_aoi,
        }
    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "error": str(e),
            "aoi_stored": has_aoi,
        }
