import re
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from rasterio.errors import RasterioIOError
import rasterio

from backend.config import get_settings

router = APIRouter(prefix="/api/images", tags=["images"])
settings = get_settings()
ALLOWED_EXTENSIONS = {".tif", ".tiff"}


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
            detail="Unsupported image type. Please upload a GeoTIFF (.tif or .tiff).",
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
    except Exception as exc:  # pragma: no cover - defensive filesystem guard
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc

    try:
        with rasterio.open(destination) as src:
            if src.width is None or src.height is None:
                raise ValueError("Invalid raster dimensions.")

            crs_value = str(src.crs) if src.crs is not None else "MISSING CRS"
            bounds = src.bounds
            resolution_x, resolution_y = src.res
            response = {
                "success": True,
                "filename": sanitize_filename(file.filename),
                "image_id": image_id,
                "stored_filename": destination.name,
                "width": int(src.width),
                "height": int(src.height),
                "bands": int(src.count),
                "crs": crs_value,
                "bounds": {
                    "left": float(bounds.left),
                    "bottom": float(bounds.bottom),
                    "right": float(bounds.right),
                    "top": float(bounds.top),
                },
                "resolution": {
                    "x": float(abs(resolution_x)),
                    "y": float(abs(resolution_y)),
                },
                "dtype": str(src.dtypes[0]) if src.dtypes else "UNKNOWN",
                "file_size_bytes": int(destination.stat().st_size),
                "geographic_extent": {
                    "min_x": float(bounds.left),
                    "min_y": float(bounds.bottom),
                    "max_x": float(bounds.right),
                    "max_y": float(bounds.top),
                },
            }

            if src.crs is None:
                response["warning"] = "CRS is missing for this GeoTIFF; the file was accepted but cannot be mapped without a coordinate reference system."

            return response
    except (RasterioIOError, ValueError, OSError) as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid raster or corrupted TIFF file: {exc}",
        ) from exc
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Upload failed: {exc}") from exc


@router.get("/{image_id}/preview.png")
async def image_preview(image_id: str, render: str = "rgb"):
    """RGB / false-colour / NDVI / NDWI / NDBI colour-ramp preview of an uploaded GeoTIFF."""
    from fastapi.responses import Response
    from backend.ai.raster_chip import render_chip_from_path

    if render not in ("rgb", "false", "ndvi", "ndwi", "ndbi"):
        raise HTTPException(status_code=400, detail="render must be rgb|false|ndvi|ndwi|ndbi")

    upload_dir = settings.UPLOADS_DIR
    candidates = list(upload_dir.glob(f"{image_id}.*"))
    if not candidates:
        raise HTTPException(status_code=404, detail="Image not found")

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
