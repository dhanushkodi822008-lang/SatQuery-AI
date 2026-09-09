"""
Natural Disaster Risk Assessment Engine for SatQuery AI.
Multi-hazard risk scoring with documented weights and honest unavailable handling.
Never invents values — missing feeds lower confidence and are excluded from score.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Tunable configuration — adjust weights / thresholds here
# ---------------------------------------------------------------------------
HAZARD_WEIGHTS: Dict[str, Dict[str, float]] = {
    "flood": {
        "rainfall_24h": 0.30,
        "rainfall_forecast_3d": 0.25,
        "water_extent": 0.20,
        "gauge_level": 0.15,
        "terrain_lowland": 0.10,
    },
    "drought": {
        "ndvi_anomaly": 0.35,
        "rainfall_deficit": 0.30,
        "soil_moisture": 0.20,
        "temp_anomaly": 0.15,
    },
    "wildfire": {
        "nbr_anomaly": 0.30,
        "active_fires": 0.25,
        "temp_high": 0.20,
        "rainfall_deficit": 0.15,
        "vegetation_dryness": 0.10,
    },
    "landslide": {
        "slope_steep": 0.35,
        "rainfall_24h": 0.30,
        "soil_moisture": 0.20,
        "landcover_unstable": 0.15,
    },
    "cyclone": {
        "wind_speed": 0.35,
        "pressure_drop": 0.25,
        "rainfall_forecast": 0.20,
        "coastal_proximity": 0.20,
    },
    "earthquake": {
        "seismic_zone": 0.50,
        "soil_type": 0.25,
        "building_density": 0.25,
    },
    "heatwave": {
        "temp_max": 0.40,
        "temp_anomaly": 0.30,
        "humidity_low": 0.15,
        "duration_days": 0.15,
    },
    "coastal_erosion": {
        "sea_level_trend": 0.35,
        "coastal_proximity": 0.30,
        "wave_energy": 0.20,
        "landcover_change": 0.15,
    },
    "deforestation": {
        "ndvi_decline": 0.40,
        "forest_loss_pct": 0.35,
        "landcover_change": 0.25,
    },
}

SEVERITY_THRESHOLDS = {
    "LOW": (0, 25),
    "MODERATE": (25, 50),
    "HIGH": (50, 75),
    "SEVERE": (75, 101),
}

HAZARD_META = {
    "flood": {"label": "Flood", "color": "#3b82f6"},
    "drought": {"label": "Drought", "color": "#f59e0b"},
    "wildfire": {"label": "Wildfire", "color": "#ef4444"},
    "landslide": {"label": "Landslide", "color": "#a855f7"},
    "cyclone": {"label": "Cyclone / Storm", "color": "#06b6d4"},
    "earthquake": {
        "label": "Earthquake Exposure / Susceptibility — NOT earthquake prediction",
        "color": "#78716c",
    },
    "heatwave": {"label": "Heatwave", "color": "#f97316"},
    "coastal_erosion": {"label": "Coastal Erosion", "color": "#0ea5e9"},
    "deforestation": {"label": "Deforestation / Degradation", "color": "#22c55e"},
}


def _score_to_severity(score: float) -> str:
    for band, (lo, hi) in SEVERITY_THRESHOLDS.items():
        if lo <= score < hi:
            return band
    return "SEVERE"


def _normalize(value: Optional[float], low: float, high: float, invert: bool = False) -> Optional[float]:
    """Map a raw indicator into 0-100. Returns None if value is missing."""
    if value is None:
        return None
    if high == low:
        return 50.0
    t = (value - low) / (high - low)
    t = max(0.0, min(1.0, t))
    if invert:
        t = 1.0 - t
    return t * 100.0


def _weighted_score(indicators: Dict[str, Optional[float]], weights: Dict[str, float]) -> tuple[float, float, List[str]]:
    """
    Compute weighted score from available indicators only.
    Returns (score 0-100, confidence 0-1, list of missing keys).
    """
    total_w = 0.0
    accum = 0.0
    missing = []
    for key, w in weights.items():
        val = indicators.get(key)
        if val is None:
            missing.append(key)
            continue
        accum += val * w
        total_w += w
    if total_w <= 0:
        return 0.0, 0.0, missing
    score = accum / total_w
    confidence = total_w / sum(weights.values())
    return min(100.0, max(0.0, score)), confidence, missing


def assess_hazard(
    hazard: str,
    weather: Optional[Dict] = None,
    water_extent: Optional[Dict] = None,
    water_level: Optional[Dict] = None,
    landcover: Optional[Dict] = None,
    change: Optional[Dict] = None,
    terrain: Optional[Dict] = None,
    place_name: str = "",
) -> Dict[str, Any]:
    """Assess a single hazard. All inputs optional; missing data lowers confidence."""
    now = datetime.now(timezone.utc).isoformat()
    weights = HAZARD_WEIGHTS.get(hazard, {})
    indicators: Dict[str, Optional[float]] = {k: None for k in weights}
    factors: List[Dict[str, Any]] = []
    data_sources: List[Dict[str, str]] = []
    explanation_parts: List[str] = []

    # ---- Extract common weather indicators ----
    rain_24h = None
    rain_3d = None
    temp_max = None
    if weather and weather.get("success"):
        rainfall = weather.get("rainfall") or {}
        rain_24h = rainfall.get("last_24h_mm")
        rain_3d = rainfall.get("forecast_next_3d_mm")
        temp = weather.get("temperature") or {}
        temp_max = temp.get("max_c") or temp.get("current_c")
        data_sources.append({
            "name": "Open-Meteo",
            "type": "weather",
            "updated_at": weather.get("updated_at") or now,
        })

    # ---- Flood ----
    if hazard == "flood":
        indicators["rainfall_24h"] = _normalize(rain_24h, 0, 80)
        indicators["rainfall_forecast_3d"] = _normalize(rain_3d, 0, 120)
        # Use only actual numeric water-extent measurements when present
        we_val = None
        if water_extent:
            qr = water_extent.get("quantitative_result") or {}
            # Prefer explicit percentage / area-derived indicators if the pipeline provided them
            for key in ("water_pct", "water_percent", "ndwi_water_pct", "extent_score"):
                if isinstance(qr.get(key), (int, float)):
                    we_val = float(qr[key])
                    break
            if we_val is None and isinstance(water_extent.get("water_pct"), (int, float)):
                we_val = float(water_extent["water_pct"])
            if we_val is not None:
                indicators["water_extent"] = _normalize(we_val, 0, 40)
                factors.append({
                    "name": "Satellite water extent",
                    "rating": "High" if we_val >= 25 else ("Moderate" if we_val >= 10 else "Low"),
                    "detail": f"Observed water indicator {we_val:.1f}",
                })
            elif water_extent.get("quantitative_result"):
                # Mask exists but no numeric percentage — do NOT invent a score
                factors.append({
                    "name": "Satellite water extent",
                    "rating": "Available (non-numeric)",
                    "detail": "Quantitative mask present; numeric extent % not supplied — excluded from score",
                })
            elif water_extent.get("mode") == "METADATA_ONLY":
                factors.append({
                    "name": "Satellite water extent",
                    "rating": "Unavailable",
                    "detail": "Scene found, mask not computed",
                })
        # Gauge: only use real numeric level if provided
        if water_level and water_level.get("available"):
            gauge_val = None
            for key in ("level_m", "level", "value", "pct_of_bankfull"):
                if isinstance(water_level.get(key), (int, float)):
                    gauge_val = float(water_level[key])
                    break
            if gauge_val is not None:
                # Heuristic normalize: treat higher levels as higher risk (domain-specific calibration required)
                indicators["gauge_level"] = _normalize(gauge_val, 0, 10)
                factors.append({
                    "name": "River gauge",
                    "rating": "Moderate",
                    "detail": f"{gauge_val} ({water_level.get('source', 'gauge')})",
                })
                data_sources.append({
                    "name": water_level.get("source", "Gauge"),
                    "type": "water_level",
                    "updated_at": now,
                })
            else:
                factors.append({
                    "name": "River gauge",
                    "rating": "Unavailable",
                    "detail": "Gauge feed marked available but no numeric level provided — excluded from score",
                })
        if terrain and terrain.get("lowland_pct") is not None:
            indicators["terrain_lowland"] = _normalize(terrain.get("lowland_pct"), 0, 100)
        if rain_24h is not None:
            rating = "High" if rain_24h >= 50 else ("Moderate" if rain_24h >= 20 else "Low")
            factors.append({"name": "24h rainfall", "rating": rating, "detail": f"{rain_24h} mm"})
        if rain_3d is not None:
            rating = "High" if rain_3d >= 80 else ("Moderate" if rain_3d >= 30 else "Low")
            factors.append({"name": "3-day forecast rain", "rating": rating, "detail": f"{rain_3d} mm"})

    # ---- Drought ----
    elif hazard == "drought":
        if landcover and landcover.get("ndvi_mean") is not None:
            # Low NDVI => higher drought risk
            indicators["ndvi_anomaly"] = _normalize(landcover.get("ndvi_mean"), 0.6, 0.15, invert=True)
            factors.append({"name": "Vegetation (NDVI)", "rating": "Moderate", "detail": f"mean NDVI {landcover.get('ndvi_mean'):.2f}"})
        indicators["rainfall_deficit"] = _normalize(rain_24h, 30, 0, invert=True) if rain_24h is not None else None
        if temp_max is not None:
            indicators["temp_anomaly"] = _normalize(temp_max, 25, 42)
            rating = "High" if temp_max >= 38 else ("Moderate" if temp_max >= 33 else "Low")
            factors.append({"name": "Temperature", "rating": rating, "detail": f"{temp_max} °C"})

    # ---- Wildfire ----
    elif hazard == "wildfire":
        if temp_max is not None:
            indicators["temp_high"] = _normalize(temp_max, 28, 42)
            rating = "High" if temp_max >= 38 else ("Moderate" if temp_max >= 33 else "Low")
            factors.append({"name": "High temperature", "rating": rating, "detail": f"{temp_max} °C"})
        indicators["rainfall_deficit"] = _normalize(rain_24h, 20, 0, invert=True) if rain_24h is not None else None
        if landcover and landcover.get("ndvi_mean") is not None:
            indicators["vegetation_dryness"] = _normalize(landcover.get("ndvi_mean"), 0.55, 0.2, invert=True)

    # ---- Landslide ----
    elif hazard == "landslide":
        indicators["rainfall_24h"] = _normalize(rain_24h, 0, 100)
        if terrain and terrain.get("mean_slope_deg") is not None:
            indicators["slope_steep"] = _normalize(terrain.get("mean_slope_deg"), 5, 35)
            factors.append({"name": "Terrain slope", "rating": "Moderate", "detail": f"{terrain.get('mean_slope_deg'):.1f}°"})
        if rain_24h is not None:
            rating = "High" if rain_24h >= 60 else ("Moderate" if rain_24h >= 25 else "Low")
            factors.append({"name": "Recent rainfall", "rating": rating, "detail": f"{rain_24h} mm"})

    # ---- Cyclone / Storm ----
    elif hazard == "cyclone":
        indicators["rainfall_forecast"] = _normalize(rain_3d, 0, 150)
        if weather and weather.get("success"):
            wind = (weather.get("wind") or {}).get("speed_kmh")
            if wind is not None:
                indicators["wind_speed"] = _normalize(wind, 20, 120)
                rating = "High" if wind >= 80 else ("Moderate" if wind >= 40 else "Low")
                factors.append({"name": "Wind speed", "rating": rating, "detail": f"{wind} km/h"})
        if terrain and terrain.get("coastal_distance_km") is not None:
            indicators["coastal_proximity"] = _normalize(terrain.get("coastal_distance_km"), 100, 0, invert=True)

    # ---- Earthquake exposure / susceptibility (NOT prediction) ----
    elif hazard == "earthquake":
        # Satellite imagery cannot predict earthquakes. This is static exposure/susceptibility only.
        if landcover and landcover.get("builtup_pct") is not None:
            indicators["building_density"] = _normalize(landcover.get("builtup_pct"), 0, 60)
            factors.append({
                "name": "Built-up density (exposure proxy)",
                "rating": "Moderate",
                "detail": f"{landcover.get('builtup_pct'):.1f}% — exposure factor only",
            })
        factors.append({
            "name": "Seismic zone / live seismicity",
            "rating": "Unavailable",
            "detail": "No live seismic feed connected. Satellite data does NOT predict earthquakes.",
        })
        explanation_parts.append(
            "This is an exposure/susceptibility indicator only. "
            "It is NOT an earthquake prediction and must not be treated as a warning."
        )

    # ---- Heatwave ----
    elif hazard == "heatwave":
        if temp_max is not None:
            indicators["temp_max"] = _normalize(temp_max, 30, 45)
            indicators["temp_anomaly"] = _normalize(temp_max, 28, 42)
            rating = "High" if temp_max >= 40 else ("Moderate" if temp_max >= 35 else "Low")
            factors.append({"name": "Max temperature", "rating": rating, "detail": f"{temp_max} °C"})
            explanation_parts.append(f"Current max temperature {temp_max} °C")

    # ---- Coastal erosion ----
    elif hazard == "coastal_erosion":
        if terrain and terrain.get("coastal_distance_km") is not None:
            indicators["coastal_proximity"] = _normalize(terrain.get("coastal_distance_km"), 50, 0, invert=True)
            factors.append({"name": "Distance to coast", "rating": "Moderate", "detail": f"{terrain.get('coastal_distance_km'):.1f} km"})
        if change and change.get("water_change_pct") is not None:
            indicators["landcover_change"] = _normalize(abs(change.get("water_change_pct")), 0, 20)

    # ---- Deforestation / land degradation ----
    elif hazard == "deforestation":
        if change and change.get("vegetation_change_pct") is not None:
            # Negative change = loss => higher risk
            vc = change.get("vegetation_change_pct")
            indicators["ndvi_decline"] = _normalize(-vc if vc < 0 else 0, 0, 25)
            indicators["forest_loss_pct"] = indicators["ndvi_decline"]
            rating = "High" if vc < -10 else ("Moderate" if vc < -3 else "Low")
            factors.append({"name": "Vegetation change", "rating": rating, "detail": f"{vc:+.1f}%"})
        if landcover and landcover.get("ndvi_mean") is not None:
            indicators["ndvi_decline"] = indicators.get("ndvi_decline") or _normalize(landcover.get("ndvi_mean"), 0.55, 0.2, invert=True)

    score, confidence, missing = _weighted_score(indicators, weights)
    severity = _score_to_severity(score)

    # Build plain-language explanation
    if confidence < 0.2:
        explanation = f"Insufficient live data to score {HAZARD_META[hazard]['label']} for this AOI. Connect additional feeds to improve confidence."
    elif not explanation_parts:
        explanation = (
            f"{HAZARD_META[hazard]['label']} risk is assessed as {severity} "
            f"(score {score:.0f}/100) based on available indicators. "
            f"Confidence {confidence*100:.0f}%."
        )
    else:
        explanation = (
            f"{HAZARD_META[hazard]['label']} risk is {severity}. "
            + " ".join(explanation_parts)
            + f" Overall score {score:.0f}/100 (confidence {confidence*100:.0f}%)."
        )

    # Ensure at least some factors listed
    if not factors:
        for m in missing[:4]:
            factors.append({"name": m.replace("_", " ").title(), "rating": "Unavailable", "detail": "Feed not available"})

    return {
        "hazard": hazard,
        "label": HAZARD_META[hazard]["label"],
        "color": HAZARD_META[hazard]["color"],
        "score": round(score, 1),
        "severity": severity,
        "confidence": round(confidence, 3),
        "explanation": explanation,
        "contributing_factors": factors,
        "missing_indicators": missing,
        "dataSources": data_sources,
        "lastUpdatedAt": now,
        "weights_used": {k: v for k, v in weights.items() if k not in missing},
    }


def assess_all_hazards(
    weather: Optional[Dict] = None,
    water_extent: Optional[Dict] = None,
    water_level: Optional[Dict] = None,
    landcover: Optional[Dict] = None,
    change: Optional[Dict] = None,
    terrain: Optional[Dict] = None,
    place_name: str = "",
) -> Dict[str, Any]:
    """Run full multi-hazard assessment and produce composite summary."""
    results = {}
    for h in HAZARD_WEIGHTS:
        results[h] = assess_hazard(
            h,
            weather=weather,
            water_extent=water_extent,
            water_level=water_level,
            landcover=landcover,
            change=change,
            terrain=terrain,
            place_name=place_name,
        )

    # Composite: highest severity / score among hazards with confidence >= 0.25
    ranked = sorted(
        [r for r in results.values() if r["confidence"] >= 0.15],
        key=lambda x: x["score"],
        reverse=True,
    )
    top = ranked[:3] if ranked else []
    composite_score = top[0]["score"] if top else 0.0
    composite_severity = _score_to_severity(composite_score)

    return {
        "success": True,
        "hazards": results,
        "composite": {
            "score": round(composite_score, 1),
            "severity": composite_severity,
            "top_hazards": [
                {"hazard": t["hazard"], "label": t["label"], "score": t["score"], "severity": t["severity"]}
                for t in top
            ],
            "explanation": (
                f"Highest assessed risk is {top[0]['label']} ({top[0]['severity']}) "
                f"if data is available; otherwise all hazards remain low-confidence."
                if top else "No hazard could be scored with sufficient confidence."
            ),
        },
        "assessed_at": datetime.now(timezone.utc).isoformat(),
        "note": (
            "Scores are analytical indicators for decision support, not official emergency warnings, "
            "calibrated probabilities, or predictions. "
            "Earthquake entries are exposure/susceptibility only — satellite data does not predict earthquakes."
        ),
    }
