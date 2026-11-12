import re
import uuid
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from rasterio.errors import RasterioIOError
import rasterio
from PIL import Image

from backend.config import get_settings
from backend.services.landcover_service import (
    analyze_visual_satellite_image,
    geospatial_metadata_error,
)

router = APIRouter(prefix="/api/images", tags=["images"])
settings = get_settings()
ALLOWED_EXTENSIONS = {".tif", ".tiff", ".jpg", ".jpeg", ".png", ".webp"}
logger = logging.getLogger(__name__)


def sanitize_filename(filename: str) -> str:
    if not filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    candidate = Path(filename).name.strip()
    candidate = re.sub(r"[^A-Za-z0-9._-]+", "_", candidate)
    candidate = candidate.strip("._ ")
    if not candidate or candidate in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    return candidate


def _safe_upload_path(filename: str) -> tuple[str, Path]:
    upload_dir = settings.UPLOADS_DIR.resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = sanitize_filename(filename)
    suffix = Path(safe_name).suffix.lower()
    image_id = uuid.uuid4().hex
    unique_name = f"{image_id}{suffix}"
    dest = (upload_dir / unique_name).resolve()

    if upload_dir not in dest.parents and dest != upload_dir:
        raise HTTPException(status_code=400, detail="Invalid upload directory.")
    return image_id, dest


@router.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected.")

    extension = Path(file.filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported image type. Please upload a GeoTIFF (.tif/.tiff), PNG, JPG, JPEG, or WEBP.",
        )

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if len(contents) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File too large. Maximum allowed size is "
                f"{settings.MAX_UPLOAD_SIZE_BYTES / (1024 * 1024):.1f} MB."
            ),
        )

    image_id, destination = _safe_upload_path(file.filename)
    try:
        destination.write_bytes(contents)
    except Exception as exc:
        logger.exception("Failed to persist uploaded image")
        raise HTTPException(status_code=500, detail="Image upload failed because of an internal error.") from exc

    try:
        if extension in {".tif", ".tiff"}:
            try:
                with rasterio.open(destination) as src:
                    if src.width <= 0 or src.height <= 0:
                        raise ValueError("Invalid raster dimensions.")

                    geospatial_error = geospatial_metadata_error(src)
                    has_geospatial = geospatial_error is None
                    crs_value = str(src.crs) if src.crs is not None else "MISSING CRS"
                    bounds = src.bounds
                    resolution_x, resolution_y = src.res
                    response = {
                        "success": True,
                        "filename": sanitize_filename(file.filename),
                        "image_id": image_id,
                        "stored_filename": destination.name,
                        "format": "GeoTIFF" if has_geospatial else "TIFF (Missing geospatial metadata)",
                        "image_type": "Satellite / Aerial Imagery",
                        "analysis_mode": "Advanced Geospatial Analysis" if has_geospatial else "Visual Satellite Image Analysis",
                        "width": int(src.width),
                        "height": int(src.height),
                        "bands": int(src.count),
                        "band_descriptions": [description or "" for description in (src.descriptions or ())],
                        "crs": crs_value,
                        "bounds": {
                            "left": float(bounds.left),
                            "bottom": float(bounds.bottom),
                            "right": float(bounds.right),
                            "top": float(bounds.top),
                        } if has_geospatial else None,
                        "resolution": {
                            "x": float(abs(resolution_x)),
                            "y": float(abs(resolution_y)),
                        } if has_geospatial else None,
                        "dtype": str(src.dtypes[0]) if src.dtypes else "UNKNOWN",
                        "file_size_bytes": int(destination.stat().st_size),
                        "has_geospatial": has_geospatial,
                    }

                    if geospatial_error:
                        response["notice"] = geospatial_error

                    return response
            except (RasterioIOError, ValueError):
                # Fallback to Pillow for TIFF without rasterio geospatial header
                with Image.open(destination) as img:
                    width, height = img.size
                    return {
                        "success": True,
                        "filename": sanitize_filename(file.filename),
                        "image_id": image_id,
                        "stored_filename": destination.name,
                        "format": "TIFF",
                        "image_type": "Satellite / Aerial Imagery",
                        "analysis_mode": "Visual Satellite Image Analysis",
                        "width": width,
                        "height": height,
                        "bands": len(img.getbands()),
                        "crs": "MISSING CRS",
                        "file_size_bytes": int(destination.stat().st_size),
                        "has_geospatial": False,
                        "notice": (
                            "This image appears to be a GeoTIFF, but it does not contain geographic reference information. "
                            "We can analyze its visible satellite content, but map-based spatial calculations require geographic reference information."
                        ),
                    }
        else:
            # Handle JPG/JPEG/PNG/WEBP via Pillow
            with Image.open(destination) as img:
                width, height = img.size
                mode = img.mode
                bands_count = len(img.getbands())
                
                # Check visual characteristics
                response = {
                    "success": True,
                    "filename": sanitize_filename(file.filename),
                    "image_id": image_id,
                    "stored_filename": destination.name,
                    "format": extension.replace(".", "").upper(),
                    "image_type": "Satellite / Aerial Image",
                    "analysis_mode": "Visual Satellite Image Analysis",
                    "width": width,
                    "height": height,
                    "bands": bands_count,
                    "crs": "MISSING CRS",
                    "dtype": mode,
                    "file_size_bytes": int(destination.stat().st_size),
                    "has_geospatial": False,
                    "notice": (
                        "Standard RGB image uploaded. Visual satellite/aerial image analysis mode enabled. "
                        "Multispectral indices (NDVI/NDWI/NDBI) require multispectral NIR/SWIR bands available in GeoTIFF."
                    ),
                }
                return response

    except (RasterioIOError, ValueError, OSError) as exc:
        destination.unlink(missing_ok=True)
        logger.exception("Rejected invalid or unreadable uploaded image")
        raise HTTPException(
            status_code=400,
            detail="Invalid raster or corrupted TIFF file. Upload a readable GeoTIFF or supported image.",
        ) from exc
    except Exception as exc:
        destination.unlink(missing_ok=True)
        logger.exception("Unexpected uploaded image processing failure")
        raise HTTPException(status_code=500, detail="Image processing failed because of an internal error.") from exc


@router.post("/{image_id}/visual-analysis")
async def run_visual_analysis(image_id: str, prompt: Optional[str] = None):
    """
    Run Visual Satellite/Aerial Image Analysis on standard RGB or TIFF images without CRS.
    """
    upload_dir = settings.UPLOADS_DIR
    candidates = list(upload_dir.glob(f"{image_id}.*"))
    if not candidates:
        raise HTTPException(status_code=404, detail="Image not found")

    result = await analyze_visual_satellite_image(str(candidates[0]), user_prompt=prompt)
    return result


@router.get("/{image_id}/preview.png")
async def image_preview(image_id: str, render: str = "rgb"):
    """RGB / false-colour / NDVI / NDWI / NDBI preview of an uploaded GeoTIFF or RGB image."""
    from fastapi.responses import Response
    from backend.ai.raster_chip import render_chip_from_path

    if render not in ("rgb", "false", "ndvi", "ndwi", "ndbi"):
        raise HTTPException(status_code=400, detail="render must be rgb|false|ndvi|ndwi|ndbi")

    upload_dir = settings.UPLOADS_DIR
    candidates = list(upload_dir.glob(f"{image_id}.*"))
    if not candidates:
        raise HTTPException(status_code=404, detail="Image not found")

    # If it's standard PNG/JPG/WEBP, return direct image/png
    suffix = candidates[0].suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        try:
            with Image.open(candidates[0]) as img:
                import io
                buf = io.BytesIO()
                img.convert("RGB").save(buf, format="PNG")
                return Response(content=buf.getvalue(), media_type="image/png")
        except Exception:
            pass

    png, meta = render_chip_from_path(candidates[0], render=render, max_px=1024)
    if png is None:
        raise HTTPException(status_code=500, detail=meta.get("error", "Render failed"))
    return Response(
        content=png,
        media_type="image/png",
        headers={"X-Chip-Meta": str({k: v for k, v in meta.items() if k != "error"})[:500]},
    )


@router.get("/{image_id}/meta")
async def image_meta(image_id: str):
    from backend.ai.raster_chip import compute_index_stats_from_path
    upload_dir = settings.UPLOADS_DIR
    candidates = list(upload_dir.glob(f"{image_id}.*"))
    if not candidates:
        raise HTTPException(status_code=404, detail="Image not found")
    stats = compute_index_stats_from_path(candidates[0])
    return {"image_id": image_id, "path": candidates[0].name, **stats}
