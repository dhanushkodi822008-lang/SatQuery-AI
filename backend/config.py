"""
SatQuery AI Configuration
All secrets via environment variables. Never hardcode API keys.
"""
from functools import lru_cache
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    APP_NAME: str = "SatQuery AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    DEMO_MODE: bool = False  # Must remain False for real-data mode

    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    CACHE_DIR: Path = DATA_DIR / "cache"
    DOWNLOADS_DIR: Path = DATA_DIR / "downloads"
    OUTPUTS_DIR: Path = DATA_DIR / "outputs"
    UPLOADS_DIR: Path = DATA_DIR / "uploads"
    MAX_UPLOAD_SIZE_BYTES: int = 50 * 1024 * 1024

    # API Keys (optional – many providers work without keys for search)
    OPENWEATHER_API_KEY: Optional[str] = None
    SENTINEL_HUB_CLIENT_ID: Optional[str] = None
    SENTINEL_HUB_CLIENT_SECRET: Optional[str] = None
    NASA_EARTHDATA_TOKEN: Optional[str] = None
    PLANETARY_COMPUTER_SUBSCRIPTION_KEY: Optional[str] = None

    # Vision-Language Model (optional hosted API)
    VLM_API_KEY: Optional[str] = None
    VLM_BASE_URL: str = "https://api.openai.com/v1"
    VLM_MODEL: str = "gpt-4o-mini"

    # External endpoints
    NOMINATIM_URL: str = "https://nominatim.openstreetmap.org"
    OVERPASS_URL: str = "https://overpass-api.de/api/interpreter"
    OPEN_METEO_URL: str = "https://api.open-meteo.com/v1"
    PLANETARY_COMPUTER_STAC: str = "https://planetarycomputer.microsoft.com/api/stac/v1"
    COPERNICUS_STAC: str = "https://catalogue.dataspace.copernicus.eu/stac"

    # Cache TTL (seconds)
    CACHE_TTL_GEOCODING: int = 86400
    CACHE_TTL_SATELLITE_SEARCH: int = 3600
    CACHE_TTL_WEATHER: int = 600
    CACHE_TTL_WATER_LEVEL: int = 1800

    # Processing limits
    MAX_AOI_AREA_KM2: float = 500.0
    DEFAULT_AOI_BUFFER_KM: float = 5.0
    MAX_CLOUD_COVER: float = 40.0
    DEFAULT_LOOKBACK_DAYS: int = 90

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000",
                                 "http://localhost:8000", "http://127.0.0.1:8000",
                                 "http://localhost:5500", "http://127.0.0.1:5500",
                                 "null"]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    settings.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    settings.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    settings.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return settings
