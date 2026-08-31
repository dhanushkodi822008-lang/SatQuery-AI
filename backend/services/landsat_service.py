"""Landsat helpers."""
from typing import Any, Dict, List
from backend.services.satellite_service import search_scenes


async def search_landsat(bbox: List[float], start_date: str = None, end_date: str = None, max_cloud: float = 30.0):
    return await search_scenes(
        bbox=bbox,
        start_date=start_date,
        end_date=end_date,
        collections=["landsat-c2-l2"],
        max_cloud=max_cloud,
    )
