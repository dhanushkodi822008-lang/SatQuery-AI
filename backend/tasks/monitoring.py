"""
Automated AOI monitoring scheduler.

Uses the exact stored AOI GeoJSON when present.
Retrieves real weather (observed vs forecast separated) and, when possible,
real satellite indicators for that AOI via Planetary Computer STAC.
Never invents measurements. Email/SMS only on genuine threshold crossings.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import sessionmaker

from backend.config import get_settings
from backend.db.models import get_engine, Alert, AlertHistory
from backend.ai.disaster_risk import assess_hazard
from backend.services.alert_service import send_email

logger = logging.getLogger(__name__)
settings = get_settings()

SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
scheduler = AsyncIOScheduler()

ALERT_COOLDOWN_HOURS = 6
SEVERITY_RANK = {"LOW": 1, "MODERATE": 2, "HIGH": 3, "SEVERE": 4, "CRITICAL": 4}


def _recent_notification_exists(db, alert_id: int, hours: int = ALERT_COOLDOWN_HOURS) -> bool:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    row = (
        db.query(AlertHistory)
        .filter(
            AlertHistory.alert_id == alert_id,
            AlertHistory.timestamp >= cutoff,
            AlertHistory.status == "success",
            AlertHistory.notification_type.in_(["email", "sms", "email+sms"]),
        )
        .first()
    )
    return row is not None


def _geometry_from_aoi(aoi: Any) -> Optional[Dict[str, Any]]:
    if not aoi or not isinstance(aoi, dict):
        return None
    t = (aoi.get("type") or "").lower()
    if t in ("polygon", "multipolygon"):
        return aoi
    if t == "feature":
        return aoi.get("geometry")
    if t == "featurecollection":
        feats = aoi.get("features") or []
        if feats and isinstance(feats[0], dict):
            return feats[0].get("geometry")
    return None


def _bbox_from_geometry(geom: Dict[str, Any]) -> Optional[List[float]]:
    """Return [min_lon, min_lat, max_lon, max_lat] from Polygon/MultiPolygon."""
    if not geom:
        return None
    coords = geom.get("coordinates")
    if not coords:
        return None
    lons, lats = [], []

    def walk(obj):
        if isinstance(obj, (list, tuple)) and obj and isinstance(obj[0], (int, float)):
            lons.append(float(obj[0]))
            lats.append(float(obj[1]))
        elif isinstance(obj, (list, tuple)):
            for x in obj:
                walk(x)

    walk(coords)
    if not lons or not lats:
        return None
    return [min(lons), min(lats), max(lons), max(lats)]


def _centroid(bbox: List[float]) -> Tuple[float, float]:
    return (bbox[1] + bbox[3]) / 2.0, (bbox[0] + bbox[2]) / 2.0


def _geocode_sync(name: str) -> Optional[Tuple[float, float]]:
    if not name or not name.strip():
        return None
    try:
        from geopy.geocoders import Nominatim

        geolocator = Nominatim(user_agent="SatQueryAI-Monitor/1.0")
        loc = geolocator.geocode(name, timeout=15)
        if loc:
            return float(loc.latitude), float(loc.longitude)
    except Exception as e:
        logger.warning(f"Geocode failed for '{name}': {e}")
    return None


def _fetch_weather_sync(lat: float, lon: float) -> Dict[str, Any]:
    """Observed rainfall vs forecast kept separate (same logic as weather_service)."""
    forecast_url = f"{settings.OPEN_METEO_URL}/forecast"
    forecast_params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
        "hourly": "precipitation,temperature_2m",
        "daily": "precipitation_sum,temperature_2m_max",
        "timezone": "auto",
        "forecast_days": 5,
        "past_days": 2,
    }
    archive_url = "https://archive-api.open-meteo.com/v1/archive"
    end_d = datetime.now(timezone.utc).date()
    start_d = end_d - timedelta(days=2)
    archive_params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_d.isoformat(),
        "end_date": end_d.isoformat(),
        "daily": "precipitation_sum",
        "timezone": "auto",
    }
    try:
        with httpx.Client(timeout=25.0) as client:
            resp = client.get(forecast_url, params=forecast_params)
            resp.raise_for_status()
            data = resp.json()
            archive_data = {}
            try:
                aresp = client.get(archive_url, params=archive_params)
                if aresp.status_code == 200:
                    archive_data = aresp.json()
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Open-Meteo error during monitoring: {e}")
        return {"success": False, "error": str(e)}

    current = data.get("current") or {}
    daily = data.get("daily") or {}
    hourly = data.get("hourly") or {}
    hourly_times = hourly.get("time") or []
    hourly_precip = hourly.get("precipitation") or []

    precip_24h = None
    precip_source = None
    ad = archive_data.get("daily") or {}
    ad_dates = ad.get("time") or []
    ad_precip = ad.get("precipitation_sum") or []
    today_str = end_d.isoformat()
    if ad_dates and ad_precip:
        vals = [float(p) for d, p in zip(ad_dates, ad_precip) if p is not None and d < today_str]
        if vals:
            precip_24h = round(vals[-1], 2)
            precip_source = "Open-Meteo Archive (previous complete day)"
        elif ad_precip[-1] is not None:
            precip_24h = round(float(ad_precip[-1]), 2)
            precip_source = "Open-Meteo Archive (latest daily)"

    if precip_24h is None and hourly_times and hourly_precip:
        now = datetime.now(timezone.utc)
        past = []
        for t_str, p in zip(hourly_times, hourly_precip):
            if p is None:
                continue
            try:
                t = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                if t <= now:
                    past.append(float(p))
            except Exception:
                continue
        if past:
            precip_24h = round(sum(past[-24:]), 2)
            precip_source = "Open-Meteo past hourly (observed slots only)"

    daily_precip = daily.get("precipitation_sum") or []
    daily_dates = daily.get("time") or []
    forecast_vals = [
        float(p) for d, p in zip(daily_dates, daily_precip)
        if p is not None and d >= today_str
    ]
    forecast_3d = round(sum(forecast_vals[:3]), 2) if forecast_vals else None

    temp_max = None
    if daily.get("temperature_2m_max"):
        temps = [t for t in daily["temperature_2m_max"][:1] if t is not None]
        temp_max = temps[0] if temps else current.get("temperature_2m")

    return {
        "success": True,
        "source": "Open-Meteo",
        "updated_at": current.get("time"),
        "rainfall": {
            "last_24h_mm": precip_24h,
            "last_24h_source": precip_source,
            "forecast_next_3d_mm": forecast_3d,
        },
        "temperature": {
            "max_c": temp_max,
            "current_c": current.get("temperature_2m"),
        },
        "wind": {"speed_kmh": current.get("wind_speed_10m")},
    }


def _stac_search_sync(bbox: List[float], lookback_days: int = 60, max_cloud: float = 40.0) -> Dict[str, Any]:
    """Synchronous Planetary Computer STAC search for the AOI bbox."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)
    body = {
        "collections": ["sentinel-2-l2a", "landsat-c2-l2"],
        "bbox": bbox,
        "datetime": f"{start.strftime('%Y-%m-%d')}T00:00:00Z/{end.strftime('%Y-%m-%d')}T23:59:59Z",
        "limit": 10,
        "query": {"eo:cloud_cover": {"lt": max_cloud}},
    }
    url = f"{settings.PLANETARY_COMPUTER_STAC}/search"
    try:
        with httpx.Client(timeout=45.0) as client:
            resp = client.post(url, json=body)
            if resp.status_code == 400:
                body.pop("query", None)
                resp = client.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"STAC search failed: {e}")
        return {"success": False, "error": str(e), "scenes": []}

    features = data.get("features") or []
    scenes = []
    for f in features:
        props = f.get("properties") or {}
        cloud = props.get("eo:cloud_cover")
        if cloud is not None and cloud > max_cloud:
            continue
        scenes.append({
            "id": f.get("id"),
            "collection": f.get("collection"),
            "acquisition_date": (props.get("datetime") or "")[:10],
            "cloud_cover_pct": cloud,
            "stac_item": f,
        })
    scenes.sort(key=lambda s: s.get("acquisition_date") or "", reverse=True)
    return {
        "success": True,
        "scenes": scenes,
        "source": "Microsoft Planetary Computer STAC",
    }


def _satellite_indicators_for_aoi(bbox: List[float], hazard: str) -> Dict[str, Any]:
    """
    Attempt real NDVI/NDWI for the AOI using existing raster pipeline.
    Returns structure suitable for assess_hazard; marks UNAVAILABLE when data missing.
    Never invents values.
    """
    out: Dict[str, Any] = {
        "satellite_available": False,
        "status": "UNAVAILABLE",
        "water_extent": None,
        "landcover": None,
        "scene_id": None,
        "acquisition_date": None,
        "error": None,
    }
    search = _stac_search_sync(bbox)
    if not search.get("success") or not search.get("scenes"):
        out["error"] = search.get("error") or "No suitable satellite scene for AOI/time range"
        return out

    scene = search["scenes"][0]
    out["scene_id"] = scene.get("id")
    out["acquisition_date"] = scene.get("acquisition_date")

    try:
        from backend.services.raster_fetch_service import fetch_optical_bands
        from backend.processing.ndvi import compute_ndvi
        from backend.processing.ndwi import compute_ndwi
    except Exception as e:
        out["error"] = f"Raster modules unavailable: {e}"
        return out

    bands_result = fetch_optical_bands(scene, bbox, needed=["green", "red", "nir"])
    if not bands_result.get("success"):
        out["error"] = bands_result.get("error") or "Could not read optical bands for AOI"
        out["status"] = "UNAVAILABLE"
        # Still record that a scene was found (metadata-only)
        out["water_extent"] = {"mode": "METADATA_ONLY", "scene_id": scene.get("id")}
        return out

    bands = bands_result.get("bands") or {}
    green, red, nir = bands.get("green"), bands.get("red"), bands.get("nir")

    landcover: Dict[str, Any] = {}
    water_extent: Dict[str, Any] = {}

    if red is not None and nir is not None:
        ndvi = compute_ndvi(nir, red)
        if ndvi.get("success"):
            landcover["ndvi_mean"] = ndvi.get("mean")
            landcover["ndvi_method"] = ndvi.get("method")
            landcover["valid_pixels"] = int(ndvi.get("valid_count") or 0) if ndvi.get("valid_count") else None

    if green is not None and nir is not None:
        ndwi = compute_ndwi(green, nir)
        if ndwi.get("success"):
            # Real water percentage from mask fraction (not invented)
            frac = ndwi.get("water_pixel_fraction")
            if frac is None:
                frac = ndwi.get("water_fraction")
            water_pct = float(frac) * 100.0 if frac is not None else None
            water_extent = {
                "quantitative_result": {
                    "water_pct": water_pct,
                    "ndwi_mean": ndwi.get("mean"),
                },
                "method": ndwi.get("method"),
                "scene_id": scene.get("id"),
                "acquisition_date": scene.get("acquisition_date"),
            }
            if water_pct is not None:
                water_extent["water_pct"] = water_pct

    if landcover or (water_extent and water_extent.get("quantitative_result")):
        out["satellite_available"] = True
        out["status"] = "AVAILABLE"
        out["landcover"] = landcover or None
        out["water_extent"] = water_extent or None
    else:
        out["status"] = "UNAVAILABLE"
        out["error"] = "Bands read but NDVI/NDWI could not be computed"
        out["water_extent"] = {"mode": "METADATA_ONLY", "scene_id": scene.get("id")}

    return out


def _hazard_from_condition(condition_type: str) -> str:
    c = (condition_type or "").lower().replace(" ", "_")
    mapping = [
        ("flood", "flood"),
        ("water_expansion", "flood"),
        ("drought", "drought"),
        ("vegetation_stress", "drought"),
        ("vegetation_decrease", "deforestation"),
        ("deforestation", "deforestation"),
        ("wildfire", "wildfire"),
        ("fire", "wildfire"),
        ("landslide", "landslide"),
        ("cyclone", "cyclone"),
        ("storm", "cyclone"),
        ("heatwave", "heatwave"),
        ("heat", "heatwave"),
        ("coastal_erosion", "coastal_erosion"),
        ("earthquake", "earthquake"),
    ]
    for key, hazard in mapping:
        if key in c:
            return hazard
    return "flood"


def _threshold_crossed(result: Dict[str, Any], threshold: float, condition_type: str) -> bool:
    score = float(result.get("score") or 0)
    severity = (result.get("severity") or "LOW").upper()
    confidence = float(result.get("confidence") or 0)
    if confidence < 0.15:
        return False
    ct = (condition_type or "").upper()
    for sev_name, rank in SEVERITY_RANK.items():
        if sev_name in ct and threshold <= rank:
            return SEVERITY_RANK.get(severity, 0) >= rank
    return score >= float(threshold)


def _evaluate_one_alert(db, alert: Alert) -> None:
    location = alert.location_name
    condition = alert.condition_type
    threshold = float(alert.threshold)
    aoi = getattr(alert, "aoi_geojson", None)

    if _recent_notification_exists(db, alert.id):
        db.add(AlertHistory(
            alert_id=alert.id,
            condition_detected=f"cooldown_skip:{condition}",
            notification_type="none",
            status="skipped",
            error_message=f"Duplicate protection: within last {ALERT_COOLDOWN_HOURS}h",
        ))
        db.commit()
        return

    geom = _geometry_from_aoi(aoi)
    bbox = _bbox_from_geometry(geom) if geom else None

    # Resolve coordinates: prefer AOI centroid, else geocode location_name
    if bbox:
        lat, lon = _centroid(bbox)
    else:
        coords = _geocode_sync(location)
        if not coords:
            db.add(AlertHistory(
                alert_id=alert.id,
                condition_detected="UNAVAILABLE",
                notification_type="none",
                status="unavailable",
                error_message=(
                    f"No AOI GeoJSON stored and could not geocode '{location}'. "
                    "No risk evaluation performed."
                ),
            ))
            db.commit()
            return
        lat, lon = coords

    weather = _fetch_weather_sync(lat, lon)
    hazard = _hazard_from_condition(condition)

    # Satellite indicators for AOI when polygon is available
    sat: Dict[str, Any] = {"status": "UNAVAILABLE", "satellite_available": False}
    if bbox:
        try:
            sat = _satellite_indicators_for_aoi(bbox, hazard)
        except Exception as e:
            logger.exception(f"Satellite retrieval failed for alert {alert.id}: {e}")
            sat = {
                "status": "UNAVAILABLE",
                "satellite_available": False,
                "error": str(e),
            }
    else:
        sat["error"] = "No AOI polygon stored on this alert; satellite AOI analysis skipped"

    result = assess_hazard(
        hazard=hazard,
        weather=weather if weather.get("success") else None,
        water_extent=sat.get("water_extent"),
        water_level=None,
        landcover=sat.get("landcover"),
        change=None,
        terrain=None,
        place_name=location,
    )

    confidence = float(result.get("confidence") or 0)
    score = float(result.get("score") or 0)
    severity = result.get("severity") or "LOW"
    sat_note = (
        f"satellite={sat.get('status')}"
        + (f" scene={sat.get('scene_id')} date={sat.get('acquisition_date')}" if sat.get("scene_id") else "")
        + (f" err={sat.get('error')}" if sat.get("error") else "")
    )

    if confidence < 0.15 and not weather.get("success") and not sat.get("satellite_available"):
        db.add(AlertHistory(
            alert_id=alert.id,
            condition_detected="UNAVAILABLE",
            notification_type="none",
            status="unavailable",
            error_message=(
                f"Insufficient real data for {hazard} at {location}. "
                f"confidence={confidence:.2f}. {sat_note}. No alert sent."
            ),
        ))
        db.commit()
        return

    if not _threshold_crossed(result, threshold, condition):
        db.add(AlertHistory(
            alert_id=alert.id,
            condition_detected=f"below_threshold:{hazard}:{severity}:{score}",
            notification_type="none",
            status="checked",
            error_message=(
                f"Evaluated {hazard} score={score} severity={severity} "
                f"(threshold={threshold}). {sat_note}. Threshold not crossed."
            ),
        ))
        db.commit()
        return

    # Threshold crossed — real notifications
    evidence = result.get("explanation") or ""
    factors = result.get("contributing_factors") or []
    factor_lines = "; ".join(
        f"{f.get('name')}: {f.get('detail')}" for f in factors[:5] if f.get("detail")
    )
    rain = (weather.get("rainfall") or {}) if weather.get("success") else {}
    body = (
        f"SatQuery AI — AOI risk threshold crossed\n\n"
        f"Location: {location}\n"
        f"AOI polygon used: {'yes' if bbox else 'no (location only)'}\n"
        f"Hazard: {result.get('label', hazard)}\n"
        f"Risk level: {severity} (score {score}/100)\n"
        f"Confidence: {confidence*100:.0f}%\n"
        f"Configured threshold: {threshold}\n"
        f"Observed rainfall (last_24h_mm): {rain.get('last_24h_mm')} "
        f"[{rain.get('last_24h_source') or 'n/a'}]\n"
        f"Forecast rainfall (next 3d): {rain.get('forecast_next_3d_mm')}\n"
        f"Satellite: {sat.get('status')} scene={sat.get('scene_id')} "
        f"date={sat.get('acquisition_date')}\n"
        f"Evidence: {evidence}\n"
        f"Factors: {factor_lines}\n\n"
        f"Disclaimer: Analytical satellite/environmental risk assessment — "
        f"not an official disaster warning. "
        f"Earthquake scores are exposure/susceptibility only — NOT prediction."
    )
    subject = f"[SatQuery AI] {severity} {result.get('label', hazard)} risk — {location}"

    successes, errors = [], []
    if alert.email:
        try:
            if send_email(alert.email, subject, body):
                successes.append("email")
            else:
                errors.append("Email not configured (SMTP credentials missing)")
        except Exception as e:
            errors.append(f"Email failed: {e}")

    ntype = "email" if successes else "none"
    db.add(AlertHistory(
        alert_id=alert.id,
        condition_detected=f"THRESHOLD_CROSSED:{hazard}:{severity}:{score}",
        notification_type=ntype,
        status="success" if successes else "failed",
        error_message="; ".join(errors) if errors else None,
    ))
    db.commit()
    logger.info(
        f"Alert {alert.id}: THRESHOLD CROSSED hazard={hazard} score={score} "
        f"aoi={'yes' if bbox else 'no'} sat={sat.get('status')} notifications={ntype}"
    )


def check_alerts_job():
    logger.info("Running automated AOI alert monitoring job...")
    db = SessionLocal()
    try:
        active = db.query(Alert).filter(Alert.active == 1).all()
        logger.info(f"Active monitoring configs: {len(active)}")
        for alert in active:
            try:
                _evaluate_one_alert(db, alert)
            except Exception as e:
                logger.exception(f"Error evaluating alert {alert.id}: {e}")
                try:
                    db.rollback()
                    db.add(AlertHistory(
                        alert_id=alert.id,
                        condition_detected="ERROR",
                        notification_type="none",
                        status="failed",
                        error_message=str(e)[:500],
                    ))
                    db.commit()
                except Exception:
                    db.rollback()
    except Exception as e:
        logger.error(f"Monitoring job failed: {e}")
    finally:
        db.close()


def start_monitoring():
    if scheduler.running:
        logger.info("Monitoring scheduler already running")
        return
    scheduler.add_job(check_alerts_job, "interval", hours=6, id="aoi_monitoring")
    scheduler.add_job(
        check_alerts_job,
        "date",
        run_date=datetime.now() + timedelta(seconds=20),
        id="aoi_monitoring_startup",
    )
    scheduler.start()
    logger.info(
        "AOI monitoring started (6h + startup). "
        "Uses stored AOI GeoJSON + Planetary Computer STAC + Open-Meteo. "
        "Never invents satellite or rainfall values."
    )
