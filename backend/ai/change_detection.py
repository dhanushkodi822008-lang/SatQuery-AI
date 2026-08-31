"""Multitemporal change detection with optional real NDWI comparison."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from backend.services.satellite_service import search_scenes
from backend.processing.change_maps import compute_change_stats
from backend.utils.logging import logger


async def run_change_detection(
    bbox: List[float],
    year_before: int = 2024,
    year_after: int = 2025,
    aoi_km2: float = 0.0,
) -> Dict[str, Any]:
    before = await search_scenes(
        bbox=bbox,
        start_date=f"{year_before}-01-01",
        end_date=f"{year_before}-12-31",
        collections=["sentinel-2-l2a", "landsat-c2-l2"],
        max_cloud=30.0,
        limit=10,
    )
    after = await search_scenes(
        bbox=bbox,
        start_date=f"{year_after}-01-01",
        end_date=f"{year_after}-12-31",
        collections=["sentinel-2-l2a", "landsat-c2-l2"],
        max_cloud=30.0,
        limit=10,
    )

    scene_b = before.get("scenes", [None])[0] if before.get("scenes") else None
    scene_a = after.get("scenes", [None])[0] if after.get("scenes") else None

    if not scene_b and not scene_a:
        return {
            "success": False,
            "error": f"No suitable optical scenes found for {year_before} or {year_after}",
            "before_search": {"scene_count": before.get("scene_count"), "error": before.get("error")},
            "after_search": {"scene_count": after.get("scene_count"), "error": after.get("error")},
        }

    result: Dict[str, Any] = {
        "success": True,
        "task": "change_detection",
        "year_before": year_before,
        "year_after": year_after,
        "before_scene": _thin_scene(scene_b),
        "after_scene": _thin_scene(scene_a),
        "before_source": before.get("source"),
        "after_source": after.get("source"),
        "quantitative_change": None,
        "metrics": {},
        "mode": "METADATA",
        "method": "STAC multitemporal search + optional NDWI differencing when rasters available",
        "message": (
            "Scenes located for both periods where available. "
            "Pixel-level change requires downloading and comparing both rasters."
        ),
    }

    if scene_b and scene_a:
        result["acquisition_dates"] = {
            "before": scene_b.get("acquisition_date"),
            "after": scene_a.get("acquisition_date"),
        }
        result["sensors"] = {
            "before": f"{scene_b.get('satellite')} / {scene_b.get('sensor')}",
            "after": f"{scene_a.get('satellite')} / {scene_a.get('sensor')}",
        }

        # Attempt real NDWI on both dates
        try:
            from backend.processing.raster_processing import analyze_optical_aoi

            rb = analyze_optical_aoi(scene_b, bbox, aoi_km2, ["ndwi"])
            ra = analyze_optical_aoi(scene_a, bbox, aoi_km2, ["ndwi"])
            qb = (rb.get("quantitative_result") or {}).get("water")
            qa = (ra.get("quantitative_result") or {}).get("water")

            if rb.get("mode") == "RASTER" and ra.get("mode") == "RASTER" and qb and qa:
                ch = compute_change_stats(
                    {"value": qb.get("area_km2"), "acquisition_date": scene_b.get("acquisition_date"), "unit": "km²"},
                    {"value": qa.get("area_km2"), "acquisition_date": scene_a.get("acquisition_date"), "unit": "km²"},
                )
                result["quantitative_change"] = ch
                result["mode"] = "RASTER"
                result["metrics"] = {
                    "water_before_km2": qb.get("area_km2"),
                    "water_after_km2": qa.get("area_km2"),
                    "water_change_km2": ch.get("absolute_change"),
                    "water_change_pct": ch.get("percent_change"),
                    "before_date": scene_b.get("acquisition_date"),
                    "after_date": scene_a.get("acquisition_date"),
                }
                direction = "increased" if (ch.get("absolute_change") or 0) > 0 else (
                    "decreased" if (ch.get("absolute_change") or 0) < 0 else "unchanged"
                )
                result["summary_text"] = (
                    f"Water extent change {year_before}→{year_after}: {direction}.\n"
                    f"BEFORE {scene_b.get('acquisition_date')}: {qb.get('area_km2')} km² "
                    f"({scene_b.get('satellite')}).\n"
                    f"AFTER {scene_a.get('acquisition_date')}: {qa.get('area_km2')} km² "
                    f"({scene_a.get('satellite')}).\n"
                    f"Change: {ch.get('absolute_change')} km² "
                    f"({ch.get('percent_change')}%).\n"
                    f"Method: NDWI on real Planetary Computer COG bands. "
                    f"No values fabricated."
                )
                result["message"] = "Quantitative water-extent change from real NDWI masks."
            else:
                result["summary_text"] = (
                    f"Change analysis {year_before}→{year_after}.\n"
                    f"BEFORE scene: {scene_b.get('acquisition_date')} "
                    f"({scene_b.get('satellite')}, cloud {scene_b.get('cloud_cover_pct')}%).\n"
                    f"AFTER scene: {scene_a.get('acquisition_date')} "
                    f"({scene_a.get('satellite')}, cloud {scene_a.get('cloud_cover_pct')}%).\n"
                    f"Pixel NDWI comparison not completed "
                    f"(before mode={rb.get('mode')}, after mode={ra.get('mode')}). "
                    f"No change percentage fabricated."
                )
                result["before_raster_mode"] = rb.get("mode")
                result["after_raster_mode"] = ra.get("mode")
        except Exception as e:
            logger.warning(f"Change raster step failed: {e}")
            result["summary_text"] = (
                f"Scenes found for {year_before} and {year_after}. "
                f"Raster comparison failed: {e}. No fabricated change %."
            )
            result["raster_error"] = str(e)
    elif scene_a or scene_b:
        only = scene_a or scene_b
        result["summary_text"] = (
            f"Only one period has a suitable scene "
            f"({only.get('acquisition_date')}). Cannot compute change without both dates."
        )

    return result


def _thin_scene(s: Optional[Dict]) -> Optional[Dict]:
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
