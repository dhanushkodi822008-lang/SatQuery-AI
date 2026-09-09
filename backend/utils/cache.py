"""Simple file + memory cache for satellite search results and geocoding."""
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional
from cachetools import TTLCache
from backend.config import get_settings
from backend.utils.logging import logger

_memory_cache: TTLCache = TTLCache(maxsize=256, ttl=3600)


def _key_hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def cache_get(key: str, ttl: Optional[int] = None) -> Optional[Any]:
    settings = get_settings()
    # Memory first
    if key in _memory_cache:
        return _memory_cache[key]
    # File cache
    path = settings.CACHE_DIR / f"{_key_hash(key)}.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if ttl is None or (time.time() - data.get("_ts", 0)) < ttl:
                _memory_cache[key] = data["value"]
                return data["value"]
        except Exception as e:
            logger.warning(f"Cache read failed for {key}: {e}")
    return None


def cache_set(key: str, value: Any, ttl: int = 3600) -> None:
    settings = get_settings()
    _memory_cache[key] = value
    path = settings.CACHE_DIR / f"{_key_hash(key)}.json"
    try:
        path.write_text(
            json.dumps({"_ts": time.time(), "value": value}, default=str),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning(f"Cache write failed: {e}")


def make_cache_key(*parts: Any) -> str:
    return "|".join(str(p) for p in parts)
