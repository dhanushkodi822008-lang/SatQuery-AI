"""
Chart data builder for SatQuery AI.
Never fabricates index values. Uses STAC scene presence / metadata only unless
real COG-derived metrics are supplied by the caller.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.services.geocoding_service import geocode
from backend.services.satellite_service import search_scenes, get_best_scene_for_year
from backend.utils.logging import logger


async def build_year_presence_chart(
    location: str,
    start_year: int,
    end_year: int,
    index: Optional[str] = None,
) -> Dict[str, Any]:
    """
    For each year in [start_year, end_year], record whether a scene exists and
    cloud cover of the best scene. Does NOT invent NDVI/NDWI values.
    """
    if start_year > end_year:
        start_year, end_year = end_year, start_year
    if end_year - start_year > 20:
        return {
            "success": False,
            "message": "Year range too large (max 20 years). Narrow the range.",
        }

    geo = await geocode(location)
    if not geo.get("success"):
        return {"success": False, "message": geo.get("error") or "Could not geocode location."}
    bbox = geo.get("bbox")
    if not bbox:
        lat, lon = float(geo["lat"]), float(geo["lon"])
        d = 0.05
        bbox = [lon - d, lat - d, lon + d, lat + d]

    years: List[int] = []
    cloud: List[Optional[float]] = []
    scene_ids: List[Optional[str]] = []
    dates: List[Optional[str]] = []

    for y in range(start_year, end_year + 1):
        try:
            r = await get_best_scene_for_year(bbox, y, max_cloud=80.0)
            if r.get("success") and r.get("scene"):
                s = r["scene"]
                years.append(y)
                cloud.append(s.get("cloud_cover_pct"))
                scene_ids.append(s.get("id"))
                dates.append(s.get("acquisition_date") or s.get("datetime"))
            else:
                years.append(y)
                cloud.append(None)
                scene_ids.append(None)
                dates.append(None)
        except Exception as e:
            logger.warning(f"chart year {y}: {e}")
            years.append(y)
            cloud.append(None)
            scene_ids.append(None)
            dates.append(None)

    available = sum(1 for c in cloud if c is not None)
    msg = (
        f"Scene availability for {location} from {start_year} to {end_year}: "
        f"{available}/{len(years)} years have at least one optical scene in STAC. "
        "Cloud cover of the best scene per year is plotted when available. "
        "Index means (NDVI/NDWI/…) require COG band reads and are not invented here."
    )
    if index:
        msg += f" Requested index '{index}' cannot be fabricated without raster processing."

    series = [
        {
            "name": "cloud_cover_pct (best scene)",
            "data": [{"x": y, "y": c} for y, c in zip(years, cloud)],
        }
    ]
    return {
        "success": available > 0,
        "chart_type": "line",
        "x": "year",
        "series": series,
        "years": years,
        "cloud_cover": cloud,
        "scene_ids": scene_ids,
        "acquisition_dates": dates,
        "location": geo.get("display_name") or location,
        "bbox": bbox,
        "index_requested": index,
        "message": msg,
        "source": "Microsoft Planetary Computer STAC",
        "note": "Values are real catalog metadata only — not fabricated index numbers.",
    }


async def chart_data_request(
    location: Optional[str] = None,
    bbox: Optional[List[float]] = None,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    index: Optional[str] = None,
    metric: str = "mean",
    satellite: str = "auto",
) -> Dict[str, Any]:
    if not location and not bbox:
        return {
            "success": False,
            "message": "No chart can be generated because location/AOI is missing.",
        }
    if start_year is None and start_date:
        start_year = int(start_date[:4])
    if end_year is None and end_date:
        end_year = int(end_date[:4])
    if start_year is None or end_year is None:
        return {
            "success": False,
            "message": "Provide start_year/end_year or start_date/end_date for the chart range.",
        }
    loc = location or "AOI"
    return await build_year_presence_chart(loc, int(start_year), int(end_year), index=index)
