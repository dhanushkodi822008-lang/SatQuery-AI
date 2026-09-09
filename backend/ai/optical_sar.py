"""Optical + SAR joint analysis with real band processing when possible."""
from __future__ import annotations

from typing import Any, Dict, List
from backend.services.satellite_service import get_best_optical_scene, get_best_sar_scene
from backend.utils.logging import logger


async def run_optical_sar(bbox: List[float], aoi_km2: float = 0.0) -> Dict[str, Any]:
    optical = await get_best_optical_scene(bbox)
    sar = await get_best_sar_scene(bbox)

    if not optical.get("success") and not sar.get("success"):
        return {
            "success": False,
            "error": "Neither optical nor SAR scenes available for this AOI",
            "optical": optical,
            "sar": sar,
        }

    result: Dict[str, Any] = {
        "success": True,
        "task": "optical_sar",
        "optical": {
            "success": optical.get("success"),
            "scene": _thin(optical.get("scene")),
            "error": optical.get("error"),
        },
        "sar": {
            "success": sar.get("success"),
            "scene": _thin(sar.get("scene")),
            "error": sar.get("error"),
        },
        "mode": "METADATA",
        "metrics": {},
        "map_layers": {},
        "fusion_method": (
            "Joint analysis: optical NDWI/NDBI (spectral) + SAR backscatter statistics over same AOI. "
            "Full pixel co-registration fusion is optional when both rasters load."
        ),
        "interpretation": _interpret(optical, sar),
    }

    optical_water = None
    optical_built = None
    sar_stats = None

    if optical.get("success"):
        try:
            from backend.processing.raster_processing import analyze_optical_aoi
            rast = analyze_optical_aoi(optical["scene"], bbox, aoi_km2, ["ndwi", "ndbi"])
            if rast.get("mode") == "RASTER":
                result["mode"] = "RASTER"
                optical_water = (rast.get("quantitative_result") or {}).get("water")
                optical_built = (rast.get("quantitative_result") or {}).get("builtup_indicated")
                if rast.get("map_points", {}).get("water"):
                    result["map_layers"]["ndwi_water_points"] = rast["map_points"]["water"]
                if rast.get("map_points", {}).get("builtup"):
                    result["map_layers"]["ndbi_points"] = rast["map_points"]["builtup"]
            result["optical_raster_mode"] = rast.get("mode")
        except Exception as e:
            logger.warning(f"Optical joint raster failed: {e}")
            result["optical_raster_error"] = str(e)

    if sar.get("success"):
        try:
            from backend.services.raster_fetch_service import fetch_sar_band
            sar_data = fetch_sar_band(sar["scene"], bbox)
            if sar_data.get("success"):
                result["mode"] = "RASTER" if result["mode"] == "RASTER" else "SAR_RASTER"
                sar_stats = {
                    "polarization": sar_data.get("polarization"),
                    "mean_db": sar_data.get("mean_db"),
                    "std_db": sar_data.get("std_db"),
                    "acquisition_date": sar_data.get("acquisition_date"),
                    "note": (
                        "Low backscatter often associated with smooth water; "
                        "high/texture with built-up. Thresholding is context-dependent."
                    ),
                }
                result["sar_raster"] = sar_stats
            else:
                result["sar_raster_error"] = sar_data.get("error")
        except Exception as e:
            logger.warning(f"SAR raster failed: {e}")
            result["sar_raster_error"] = str(e)

    # Build summary
    lines = [f"Optical + SAR joint analysis."]
    lines.append(f"Interpretation: {result['interpretation']}")
    if optical_water:
        lines.append(
            f"OPTICAL water (NDWI): {optical_water.get('area_km2')} km² "
            f"on {optical_water.get('observation_date')} "
            f"({optical_water.get('satellite')})."
        )
        result["metrics"]["optical_water_km2"] = optical_water.get("area_km2")
    if optical_built:
        lines.append(
            f"OPTICAL built-up indication (NDBI): ~{optical_built.get('pct_approx')}% of valid pixels "
            f"on {optical_built.get('observation_date')}."
        )
        result["metrics"]["optical_builtup_pct"] = optical_built.get("pct_approx")
    if sar_stats:
        lines.append(
            f"SAR ({sar_stats.get('polarization')}): mean {sar_stats.get('mean_db'):.2f} dB "
            f"on {sar_stats.get('acquisition_date')}. {sar_stats.get('note')}"
        )
        result["metrics"]["sar_mean_db"] = sar_stats.get("mean_db")
    if not optical_water and not sar_stats:
        lines.append(
            "Raster-level fusion not completed; scene metadata only. "
            "No fabricated water/built-up percentages."
        )
    lines.append(f"Fusion method: {result['fusion_method']}")
    result["summary_text"] = "\n".join(lines)
    result["note"] = (
        "SAR is weather-independent (useful under clouds); optical provides spectral indices."
    )
    return result


def _thin(s):
    if not s:
        return None
    return {
        "id": s.get("id"),
        "satellite": s.get("satellite"),
        "sensor": s.get("sensor"),
        "acquisition_date": s.get("acquisition_date"),
        "cloud_cover_pct": s.get("cloud_cover_pct"),
        "resolution_m": s.get("resolution_m"),
        "collection": s.get("collection"),
    }


def _interpret(optical: Dict, sar: Dict) -> str:
    parts = []
    if optical.get("success"):
        s = optical["scene"]
        parts.append(
            f"Optical: {s.get('satellite')} {s.get('sensor')} on {s.get('acquisition_date')} "
            f"(cloud {s.get('cloud_cover_pct')}%)"
        )
    else:
        parts.append(f"Optical: unavailable — {optical.get('error')}")
    if sar.get("success"):
        s = sar["scene"]
        parts.append(
            f"SAR: {s.get('satellite')} {s.get('sensor')} on {s.get('acquisition_date')}"
        )
    else:
        parts.append(f"SAR: unavailable — {sar.get('error')}")
    return " | ".join(parts)
