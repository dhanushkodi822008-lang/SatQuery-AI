"""
Render raster chips (RGB / false-colour / index heatmaps) from COGs or uploaded GeoTIFFs.
Used by VQA, captioning, grounding previews and image overlay endpoints.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import io
import numpy as np

from backend.utils.logging import logger

try:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import transform_bounds
    from PIL import Image
except ImportError:
    rasterio = None  # type: ignore
    Image = None  # type: ignore


def _percentile_stretch(arr: np.ndarray, lo: float = 2.0, hi: float = 98.0) -> np.ndarray:
    valid = arr[np.isfinite(arr)]
    if valid.size == 0:
        return np.zeros_like(arr, dtype=np.uint8)
    p_lo, p_hi = np.percentile(valid, [lo, hi])
    if p_hi <= p_lo:
        p_hi = p_lo + 1e-6
    stretched = (arr - p_lo) / (p_hi - p_lo)
    stretched = np.clip(stretched, 0, 1)
    return (stretched * 255).astype(np.uint8)


def _downsample(data: np.ndarray, max_px: int = 1024) -> np.ndarray:
    """data shape: (C, H, W) or (H, W)."""
    if data.ndim == 2:
        h, w = data.shape
        scale = min(1.0, max_px / max(h, w))
        if scale >= 0.999:
            return data
        new_h, new_w = max(1, int(h * scale)), max(1, int(w * scale))
        from skimage.transform import resize
        return resize(data, (new_h, new_w), order=1, preserve_range=True, anti_aliasing=True).astype(data.dtype)
    c, h, w = data.shape
    scale = min(1.0, max_px / max(h, w))
    if scale >= 0.999:
        return data
    new_h, new_w = max(1, int(h * scale)), max(1, int(w * scale))
    from skimage.transform import resize
    out = np.zeros((c, new_h, new_w), dtype=data.dtype)
    for i in range(c):
        out[i] = resize(data[i], (new_h, new_w), order=1, preserve_range=True, anti_aliasing=True).astype(data.dtype)
    return out


def _colour_ramp_ndvi(arr: np.ndarray) -> np.ndarray:
    """Simple brown→green ramp for NDVI-like values [-1,1]."""
    t = np.clip((arr + 1) / 2, 0, 1)  # 0..1
    r = (np.clip(1.2 - t * 1.4, 0, 1) * 255).astype(np.uint8)
    g = (np.clip(t * 1.1, 0, 1) * 255).astype(np.uint8)
    b = (np.clip(0.3 - t * 0.3, 0, 1) * 255).astype(np.uint8)
    return np.stack([r, g, b], axis=-1)


def _colour_ramp_ndwi(arr: np.ndarray) -> np.ndarray:
    t = np.clip((arr + 1) / 2, 0, 1)
    r = (np.clip(0.2 * (1 - t), 0, 1) * 255).astype(np.uint8)
    g = (np.clip(0.4 + 0.4 * t, 0, 1) * 255).astype(np.uint8)
    b = (np.clip(0.6 + 0.4 * t, 0, 1) * 255).astype(np.uint8)
    return np.stack([r, g, b], axis=-1)


def _colour_ramp_ndbi(arr: np.ndarray) -> np.ndarray:
    t = np.clip((arr + 1) / 2, 0, 1)
    r = (np.clip(0.5 + 0.5 * t, 0, 1) * 255).astype(np.uint8)
    g = (np.clip(0.4 * (1 - t), 0, 1) * 255).astype(np.uint8)
    b = (np.clip(0.3 * (1 - t), 0, 1) * 255).astype(np.uint8)
    return np.stack([r, g, b], axis=-1)


def render_chip_from_path(
    path: Path,
    render: str = "rgb",
    max_px: int = 1024,
) -> Tuple[Optional[bytes], Dict[str, Any]]:
    """
    Render a GeoTIFF to PNG bytes.
    render: rgb | false | ndvi | ndwi | ndbi
    Returns (png_bytes or None, meta).
    """
    meta: Dict[str, Any] = {"path": str(path), "render": render}
    if rasterio is None or Image is None:
        meta["error"] = "rasterio/Pillow not available"
        return None, meta

    path = Path(path)
    if not path.exists():
        meta["error"] = f"File not found: {path}"
        return None, meta

    try:
        with rasterio.open(path) as src:
            meta["crs"] = str(src.crs) if src.crs else None
            meta["bounds"] = list(src.bounds)
            meta["width"] = src.width
            meta["height"] = src.height
            meta["count"] = src.count
            if src.crs and src.crs.to_epsg() != 4326:
                try:
                    meta["bounds_wgs84"] = list(transform_bounds(src.crs, "EPSG:4326", *src.bounds))
                except Exception:
                    meta["bounds_wgs84"] = None
            else:
                meta["bounds_wgs84"] = list(src.bounds)

            # Read up to 4 bands, downsample via overview if possible
            scale = min(1.0, max_px / max(src.height, src.width))
            out_h = max(1, int(src.height * scale))
            out_w = max(1, int(src.width * scale))

            bands_needed = min(src.count, 4)
            data = src.read(
                list(range(1, bands_needed + 1)),
                out_shape=(bands_needed, out_h, out_w),
                resampling=Resampling.bilinear,
            ).astype(np.float32)

            # mask nodata
            if src.nodata is not None:
                data = np.where(data == src.nodata, np.nan, data)

            rgb = None
            if render == "rgb":
                if data.shape[0] >= 3:
                    r = _percentile_stretch(data[0])
                    g = _percentile_stretch(data[1])
                    b = _percentile_stretch(data[2])
                elif data.shape[0] == 1:
                    g = _percentile_stretch(data[0])
                    r = b = g
                else:
                    r = _percentile_stretch(data[0])
                    g = _percentile_stretch(data[1] if data.shape[0] > 1 else data[0])
                    b = g
                rgb = np.stack([r, g, b], axis=-1)
            elif render == "false":
                # NIR-R-G style if we have ≥3 bands, else fall back
                if data.shape[0] >= 3:
                    r = _percentile_stretch(data[2] if data.shape[0] > 2 else data[0])
                    g = _percentile_stretch(data[0])
                    b = _percentile_stretch(data[1] if data.shape[0] > 1 else data[0])
                else:
                    g = _percentile_stretch(data[0])
                    r = b = g
                rgb = np.stack([r, g, b], axis=-1)
            elif render in ("ndvi", "ndwi", "ndbi"):
                # Expect bands ordered approximately R,G,B,NIR or similar; compute simple index
                if data.shape[0] >= 2:
                    a, b_ = data[0], data[-1]
                    denom = a + b_
                    denom = np.where(np.abs(denom) < 1e-6, np.nan, denom)
                    idx = (b_ - a) / denom
                else:
                    idx = data[0]
                if render == "ndvi":
                    rgb = _colour_ramp_ndvi(idx)
                elif render == "ndwi":
                    rgb = _colour_ramp_ndwi(idx)
                else:
                    rgb = _colour_ramp_ndbi(idx)
            else:
                meta["error"] = f"Unknown render mode: {render}"
                return None, meta

            # NaN → black
            rgb = np.nan_to_num(rgb, nan=0).astype(np.uint8)
            img = Image.fromarray(rgb, mode="RGB")
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            png = buf.getvalue()
            meta["png_bytes"] = len(png)
            meta["success"] = True
            return png, meta
    except Exception as exc:
        logger.exception("render_chip_from_path failed")
        meta["error"] = str(exc)
        return None, meta


def compute_index_stats_from_path(path: Path) -> Dict[str, Any]:
    """Quick NDVI/NDWI/NDBI-ish stats from an uploaded multi-band GeoTIFF."""
    out: Dict[str, Any] = {"success": False}
    if rasterio is None:
        out["error"] = "rasterio unavailable"
        return out
    path = Path(path)
    if not path.exists():
        out["error"] = "file not found"
        return out
    try:
        with rasterio.open(path) as src:
            # sample a modest window
            h = min(src.height, 512)
            w = min(src.width, 512)
            data = src.read(
                list(range(1, min(src.count, 4) + 1)),
                out_shape=(min(src.count, 4), h, w),
                resampling=Resampling.bilinear,
            ).astype(np.float32)
            if src.nodata is not None:
                data = np.where(data == src.nodata, np.nan, data)

            def idx_stats(a: np.ndarray, b: np.ndarray) -> Dict[str, float]:
                denom = a + b
                denom = np.where(np.abs(denom) < 1e-6, np.nan, denom)
                idx = (b - a) / denom
                valid = idx[np.isfinite(idx)]
                if valid.size == 0:
                    return {}
                return {
                    "mean": round(float(np.nanmean(valid)), 4),
                    "std": round(float(np.nanstd(valid)), 4),
                    "p10": round(float(np.nanpercentile(valid, 10)), 4),
                    "p90": round(float(np.nanpercentile(valid, 90)), 4),
                }

            if data.shape[0] >= 2:
                out["ndvi_proxy"] = idx_stats(data[0], data[-1])
                out["ndwi_proxy"] = idx_stats(data[-1], data[0])  # flipped heuristic
            out["band_count"] = src.count
            out["crs"] = str(src.crs) if src.crs else None
            out["bounds"] = list(src.bounds)
            out["success"] = True
            return out
    except Exception as exc:
        out["error"] = str(exc)
        return out
