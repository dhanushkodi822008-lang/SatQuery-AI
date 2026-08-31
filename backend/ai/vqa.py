"""
Remote-sensing VQA — real pipeline.
Renders a chip from uploaded GeoTIFF or STAC scene, injects numeric evidence,
and calls the pluggable VLM provider. Never invents values.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.ai.model_registry import get_registry
from backend.ai.vlm_provider import run_vlm
from backend.ai.raster_chip import render_chip_from_path, compute_index_stats_from_path
from backend.config import get_settings
from backend.utils.logging import logger


def _collect_evidence(context: Dict[str, Any]) -> Dict[str, Any]:
    evidence: Dict[str, Any] = {}
    evidence["display_name"] = context.get("display_name") or context.get("location")
    evidence["aoi_area_km2"] = context.get("aoi_area_km2")
    scene = context.get("scene") or {}
    if scene:
        evidence["scene_id"] = scene.get("id")
        evidence["acquisition_date"] = scene.get("acquisition_date")
        evidence["scene_date"] = scene.get("acquisition_date")
        evidence["cloud_cover_pct"] = scene.get("cloud_cover_pct")
        evidence["resolution_m"] = scene.get("resolution_m")
        evidence["satellite"] = scene.get("satellite")
        evidence["collection"] = scene.get("collection")

    metrics = context.get("metrics") or {}
    for k in (
        "ndvi_mean", "ndwi_mean", "ndbi_mean",
        "water_area_km2", "vegetation_area_km2", "builtup_area_km2",
        "water_pct", "vegetation_pct", "builtup_pct",
    ):
        if metrics.get(k) is not None:
            evidence[k] = metrics[k]
        elif context.get(k) is not None:
            evidence[k] = context[k]

    optical = context.get("optical_analysis") or context.get("indices") or {}
    for k, v in optical.items():
        if isinstance(v, (int, float, str)) and k not in evidence:
            evidence[k] = v
    return evidence


async def answer_vqa(
    query: str,
    context: Dict[str, Any],
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    model = get_registry()["vqa"]
    settings = get_settings()
    evidence = _collect_evidence(context)
    image_png: Optional[bytes] = None
    chip_meta: Dict[str, Any] = {}

    image_id = context.get("image_id")
    if image_id:
        upload_dir = settings.UPLOADS_DIR
        candidates = list(upload_dir.glob(f"{image_id}.*"))
        if candidates:
            path = candidates[0]
            image_png, chip_meta = render_chip_from_path(path, render="rgb", max_px=1024)
            stats = compute_index_stats_from_path(path)
            if stats.get("success"):
                if stats.get("ndvi_proxy"):
                    evidence["ndvi_mean"] = stats["ndvi_proxy"].get("mean")
                if stats.get("ndwi_proxy"):
                    evidence["ndwi_mean"] = stats["ndwi_proxy"].get("mean")
                evidence["upload_band_count"] = stats.get("band_count")
                evidence["upload_crs"] = stats.get("crs")

    if image_png is None and context.get("chip_path"):
        image_png, chip_meta = render_chip_from_path(Path(context["chip_path"]), render="rgb")

    try:
        vlm_out = await run_vlm(query, image_png, evidence, history=history)
    except Exception as exc:
        logger.exception("VLM failed")
        return {
            "success": False,
            "task": "vqa",
            "model": model.to_dict(),
            "query": query,
            "status": "ERROR",
            "answer": f"VQA pipeline error: {exc}",
            "confidence": None,
            "evidence": evidence,
        }

    status = "READY" if not vlm_out.get("degraded") else "DEGRADED"
    return {
        "success": True,
        "task": "vqa",
        "model": model.to_dict(),
        "query": query,
        "answer": vlm_out.get("answer"),
        "evidence": evidence,
        "confidence": vlm_out.get("confidence"),
        "provider": vlm_out.get("provider") or vlm_out.get("model"),
        "sources": vlm_out.get("sources") or [],
        "chip_meta": {k: v for k, v in chip_meta.items() if k != "error"} if chip_meta else {},
        "has_image": image_png is not None,
        "status": status,
        "degraded": bool(vlm_out.get("degraded")),
    }
