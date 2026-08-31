"""Image-derived captioning with metadata enrichment. Falls back to metadata-only."""
from __future__ import annotations

from typing import Any, Dict, Optional

from backend.ai.model_registry import get_registry
from backend.ai.vlm_provider import run_vlm
from backend.ai.raster_chip import render_chip_from_path
from backend.config import get_settings


async def caption_scene(context: Dict[str, Any]) -> Dict[str, Any]:
    model = get_registry()["captioning"]
    settings = get_settings()
    scene = context.get("scene") or {}
    evidence = {
        "display_name": context.get("display_name"),
        "acquisition_date": scene.get("acquisition_date"),
        "cloud_cover_pct": scene.get("cloud_cover_pct"),
        "resolution_m": scene.get("resolution_m"),
        "satellite": scene.get("satellite"),
        "collection": scene.get("collection"),
    }
    metrics = context.get("metrics") or {}
    evidence.update({k: v for k, v in metrics.items() if v is not None})

    image_png = None
    image_id = context.get("image_id")
    if image_id:
        candidates = list(settings.UPLOADS_DIR.glob(f"{image_id}.*"))
        if candidates:
            image_png, _ = render_chip_from_path(candidates[0], render="rgb")

    if image_png is not None or any(evidence.get(k) for k in ("ndvi_mean", "ndwi_mean")):
        try:
            vlm = await run_vlm(
                "Write a concise remote-sensing caption (2-3 sentences) for this scene. "
                "Mention land cover cues, water, vegetation or built-up if supported by evidence. "
                "Do not invent numbers.",
                image_png,
                evidence,
            )
            return {
                "success": True,
                "task": "captioning",
                "model": model.to_dict(),
                "caption": vlm.get("answer"),
                "status": "READY" if not vlm.get("degraded") else "DEGRADED",
                "degraded": bool(vlm.get("degraded")),
                "provider": vlm.get("provider"),
                "evidence": evidence,
            }
        except Exception:
            pass

    # Metadata-only fallback
    if scene:
        text = (
            f"Satellite observation from {scene.get('satellite')} ({scene.get('sensor')}) "
            f"acquired on {scene.get('acquisition_date')}. "
            f"Cloud cover: {scene.get('cloud_cover_pct')}%. "
            f"Resolution: {scene.get('resolution_m')} m. "
            f"Collection: {scene.get('collection')}."
        )
    else:
        text = "No satellite scene available to caption for this location/time."
    return {
        "success": True,
        "task": "captioning",
        "model": model.to_dict(),
        "caption": text,
        "status": model.status,
        "degraded": True,
        "note": "Metadata-based caption. Full VLM captioning requires image chip or VLM_API_KEY.",
        "evidence": evidence,
    }
