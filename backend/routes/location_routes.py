from fastapi import APIRouter, Query
from backend.services.geocoding_service import geocode, reverse_geocode

router = APIRouter(prefix="/api/location", tags=["location"])


@router.get("/search")
async def location_search(q: str = Query(..., min_length=1, max_length=300)):
    return await geocode(q)


@router.get("/reverse")
async def location_reverse(lat: float, lon: float):
    return await reverse_geocode(lat, lon)
