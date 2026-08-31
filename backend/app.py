"""
SatQuery AI — FastAPI application
SIH 2026 Problem Statement SIH26167
Real data only — no fabricated satellite values.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from backend.config import get_settings
from backend.routes.location_routes import router as location_router
from backend.routes.satellite_routes import router as satellite_router
from backend.routes.analysis_routes import router as analysis_router
from backend.routes.weather_routes import router as weather_router
from backend.routes.water_routes import router as water_router
from backend.routes.report_routes import router as report_router
from backend.routes.image_routes import router as image_router
from backend.routes.landcover_routes import legacy_router as legacy_landcover_router
from backend.routes.landcover_routes import router as landcover_router
from backend.routes.chat_routes import router as chat_router
from backend.db.models import init_db
from backend.utils.logging import logger

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Interactive Vision-Language Assistant for Multimodal Remote Sensing "
        "Image Analysis through Text Queries (SIH26167). "
        "Uses real STAC catalogs, Open-Meteo, Nominatim, OSM."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if not settings.DEBUG else settings.CORS_ORIGINS + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(location_router)
app.include_router(satellite_router)
app.include_router(analysis_router)
app.include_router(weather_router)
app.include_router(water_router)
app.include_router(report_router)
app.include_router(image_router)
app.include_router(landcover_router)
app.include_router(legacy_landcover_router)
app.include_router(chat_router)

# Bootstrap SQLite chat DB
init_db()

FRONTEND = settings.BASE_DIR / "frontend"


@app.get("/api/status")
async def status():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "mode": "DEMO_MODE" if settings.DEMO_MODE else "REAL_DATA_MODE",
        "demo_mode": settings.DEMO_MODE,
        "providers": {
            "geocoding": "Nominatim (OpenStreetMap)",
            "satellite_catalog": "Microsoft Planetary Computer STAC",
            "weather": "Open-Meteo",
            "water_features": "OpenStreetMap Overpass",
            "water_level_gauges": "Not connected (honest unavailable responses)",
        },
        "sih_requirements": {
            "single_image_vqa": "IMPLEMENTED — VLM provider (API key or evidence-only fallback) + chip render",
            "additional_single_image_task": "IMPLEMENTED — captioning + real NDVI/NDWI/NDBI when COGs load",
            "multitemporal_change_analysis": "IMPLEMENTED — dual-date STAC + optional real NDWI change",
            "optical_sar_analysis": "IMPLEMENTED — paired search + NDWI/NDBI + SAR backscatter stats",
            "agentic_task_routing": "IMPLEMENTED — QueryRouter executes tools",
            "remote_sensing_model_adapter": "IMPLEMENTED — Model Registry (RSVQA/BigEarthNet/CDVQA hooks)",
            "natural_language_queries": "IMPLEMENTED",
            "visual_evidence": "IMPLEMENTED — Leaflet AOI, OSM water, spectral grounding GeoJSON, image previews",
            "confidence": "IMPLEMENTED — reported where applicable (not invented)",
            "execution_trace": "IMPLEMENTED",
            "real_satellite_data_integration": "IMPLEMENTED — Planetary Computer STAC + COG windowed reads",
        },
    }


@app.get("/")
async def root():
    index = FRONTEND / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"message": "SatQuery AI API. Open frontend/index.html or use /docs"}


# Serve frontend static assets
if FRONTEND.exists():
    app.mount("/css", StaticFiles(directory=FRONTEND / "css"), name="css")
    app.mount("/js", StaticFiles(directory=FRONTEND / "js"), name="js")


@app.on_event("startup")
async def startup():
    logger.info(f"{settings.APP_NAME} v{settings.APP_VERSION} starting — REAL_DATA_MODE={not settings.DEMO_MODE}")
