"""
Explainable flood-risk indicator (not a calibrated probability model).
Uses rainfall + water extent availability + gauge status.
"""
from typing import Any, Dict, Optional


def assess_flood_risk(
    weather: Optional[Dict] = None,
    water_extent: Optional[Dict] = None,
    water_level: Optional[Dict] = None,
    place_name: str = "",
) -> Dict[str, Any]:
    score = 0
    evidence = []

    # Rainfall evidence
    rain_24h = None
    forecast_3d = None
    if weather and weather.get("success"):
        rain_24h = (weather.get("rainfall") or {}).get("last_24h_mm")
        forecast_3d = (weather.get("rainfall") or {}).get("forecast_next_3d_mm")
        if rain_24h is not None:
            if rain_24h >= 50:
                score += 35
                evidence.append(f"Recent 24h rainfall: {rain_24h} mm (heavy)")
            elif rain_24h >= 20:
                score += 20
                evidence.append(f"Recent 24h rainfall: {rain_24h} mm (moderate)")
            elif rain_24h >= 5:
                score += 8
                evidence.append(f"Recent 24h rainfall: {rain_24h} mm (light)")
            else:
                evidence.append(f"Recent 24h rainfall: {rain_24h} mm (low)")
        if forecast_3d is not None:
            if forecast_3d >= 80:
                score += 30
                evidence.append(f"3-day forecast rainfall: {forecast_3d} mm (high)")
            elif forecast_3d >= 30:
                score += 15
                evidence.append(f"3-day forecast rainfall: {forecast_3d} mm (moderate)")
            else:
                evidence.append(f"3-day forecast rainfall: {forecast_3d} mm")
        evidence.append(f"Weather source: {weather.get('source')} @ {weather.get('updated_at')}")
    else:
        evidence.append("Weather data: not available")

    # Water extent (if quantitative available)
    if water_extent and water_extent.get("quantitative_result"):
        evidence.append("Satellite water extent: available (see analysis)")
        score += 10
    elif water_extent and water_extent.get("mode") == "METADATA_ONLY":
        evidence.append("Satellite water extent: scene found, pixel mask not computed in this run")
    else:
        evidence.append("Satellite water extent: not computed")

    # Gauge
    if water_level and water_level.get("available"):
        evidence.append(f"River gauge: available ({water_level.get('source')})")
        score += 15
    else:
        evidence.append(
            water_level.get("message")
            if water_level
            else "River gauge water level: not available from connected sources"
        )

    score = min(100, score)
    if score >= 60:
        level = "HIGH"
    elif score >= 30:
        level = "MODERATE"
    else:
        level = "LOW"

    return {
        "success": True,
        "flood_risk": level,
        "risk_indicator_score": score,
        "score_scale": "0-100 analytical indicator (NOT calibrated flood probability)",
        "evidence": evidence,
        "disclaimer": (
            "Risk assessment is an analytical indicator and is not an official emergency warning. "
            "For official alerts consult local disaster management / IMD / CWC."
        ),
        "official_alert": None,
        "method": "Weighted evidence from rainfall (Open-Meteo) + water-extent availability + gauge status",
    }
