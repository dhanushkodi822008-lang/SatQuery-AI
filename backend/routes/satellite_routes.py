from fastapi import APIRouter, Query
from typing import Optional, List
from backend.services.satellite_service import search_scenes, get_best_optical_scene, get_best_sar_scene

router = APIRouter(prefix="/api/satellite", tags=["satellite"])


@router.get("/search")
async def satellite_search(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    collection: Optional[str] = "sentinel-2-l2a",
    max_cloud: float = 40.0,
    limit: int = 15,
):
    bbox = [min_lon, min_lat, max_lon, max_lat]
    collections = [c.strip() for c in collection.split(",") if c.strip()]
    return await search_scenes(bbox, start_date, end_date, collections, max_cloud, limit)


@router.get("/best-optical")
async def best_optical(min_lon: float, min_lat: float, max_lon: float, max_lat: float):
    return await get_best_optical_scene([min_lon, min_lat, max_lon, max_lat])


@router.get("/best-sar")
async def best_sar(min_lon: float, min_lat: float, max_lon: float, max_lat: float):
    return await get_best_sar_scene([min_lon, min_lat, max_lon, max_lat])
