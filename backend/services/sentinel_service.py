"""Sentinel-2 / Sentinel-1 helpers built on satellite_service."""
from typing import Any, Dict, List
from backend.services.satellite_service import search_scenes, get_best_optical_scene, get_best_sar_scene


async def search_sentinel2(bbox: List[float], start_date: str = None, end_date: str = None, max_cloud: float = 30.0):
    return await search_scenes(
        bbox=bbox,
        start_date=start_date,
        end_date=end_date,
        collections=["sentinel-2-l2a"],
        max_cloud=max_cloud,
    )


async def search_sentinel1(bbox: List[float], start_date: str = None, end_date: str = None):
    return await search_scenes(
        bbox=bbox,
        start_date=start_date,
        end_date=end_date,
        collections=["sentinel-1-rtc"],
        max_cloud=100.0,
    )


async def best_sentinel2(bbox: List[float]):
    return await get_best_optical_scene(bbox)
