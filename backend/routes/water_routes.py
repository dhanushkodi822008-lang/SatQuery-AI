from fastapi import APIRouter, Query
from backend.services.water_level_service import get_water_level
from backend.services.osm_service import get_water_features

router = APIRouter(prefix="/api/water", tags=["water"])


@router.get("/level")
async def water_level(lat: float, lon: float, place: str = ""):
    return await get_water_level(lat, lon, place)


@router.get("/features")
async def water_features(min_lon: float, min_lat: float, max_lon: float, max_lat: float):
    return await get_water_features([min_lon, min_lat, max_lon, max_lat])
