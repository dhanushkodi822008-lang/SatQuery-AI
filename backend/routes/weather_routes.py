from fastapi import APIRouter, Query
from backend.services.weather_service import get_weather

router = APIRouter(prefix="/api/weather", tags=["weather"])


@router.get("")
async def weather(lat: float = Query(...), lon: float = Query(...)):
    return await get_weather(lat, lon)
