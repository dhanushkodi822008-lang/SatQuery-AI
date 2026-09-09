"""SAR (Sentinel-1) service."""
from typing import Any, Dict, List
from backend.services.satellite_service import get_best_sar_scene, search_scenes


async def search_sar(bbox: List[float], start_date: str = None, end_date: str = None):
    return await search_scenes(
        bbox=bbox,
        start_date=start_date,
        end_date=end_date,
        collections=["sentinel-1-rtc"],
        max_cloud=100.0,
    )


async def best_sar(bbox: List[float]):
    return await get_best_sar_scene(bbox)
