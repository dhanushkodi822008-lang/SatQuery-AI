"""
Fetch and clip real Sentinel-2 / Landsat band data from Microsoft Planetary Computer.
Uses signed COG URLs + rasterio windowed reads over the AOI.
Never invents pixel values.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from backend.config import get_settings
from backend.utils.logging import logger
from backend.utils.cache import cache_get, cache_set, make_cache_key

# Band asset names on Planetary Computer
S2_BANDS = {
    "B02": "blue",
    "B03": "green",
    "B04": "red",
    "B08": "nir",
    "B11": "swir16",
    "B12": "swir22",
    "SCL": "scl",  # scene classification (cloud mask)
}

LANDSAT_BANDS = {
    "red": "red",
    "green": "green",
    "nir08": "nir",
    "swir16": "swir16",
}


def _sign_item(item_dict: Dict) -> Any:
    """Sign STAC item assets with Planetary Computer."""
    try:
        import planetary_computer as pc
        from pystac import Item

        item = Item.from_dict(item_dict)
        return pc.sign(item)
    except Exception as e:
        logger.warning(f"planetary_computer.sign failed: {e}")
        return None


def _asset_href(asset: Any) -> Optional[str]:
    return asset.get("href") if isinstance(asset, dict) else getattr(asset, "href", None)


def _find_asset(assets: Dict[str, Any], asset_key: str) -> Tuple[Optional[str], Any]:
    """Find an asset without changing the key or URL returned by STAC."""
    if asset_key in assets:
        return asset_key, assets[asset_key]
    wanted = asset_key.lower()
    for key, asset in assets.items():
        if str(key).lower() == wanted:
            return str(key), asset
    return None, None


def _signed_assets(item_dict: Dict) -> Tuple[Dict[str, Any], Optional[str], bool]:
    """Return signed assets, with a per-URL fallback for cached STAC items."""
    unsigned = item_dict.get("assets") or {}
    signed = _sign_item(item_dict)
    if signed is not None:
        assets = {
            key: value.to_dict() if hasattr(value, "to_dict") else value
            for key, value in signed.assets.items()
        }
        return assets, None, True

    try:
        import planetary_computer as pc
    except ImportError as exc:
        return unsigned, f"planetary-computer is not installed: {exc}", False

    assets: Dict[str, Any] = {}
    errors = []
    for key, asset in unsigned.items():
        href = _asset_href(asset)
        if not href:
            continue
        try:
            assets[key] = {"href": pc.sign_url(href)}
        except Exception as exc:
            errors.append(f"{key}: {type(exc).__name__}: {exc}")

    return assets, "; ".join(errors) if errors else None, bool(assets)


def _read_band_window(
    href: str,
    bbox: List[float],
    max_size: int = 512,
    error_out: Optional[List[str]] = None,
) -> Optional[Tuple[np.ndarray, Dict[str, Any]]]:
    """
    Read a COG band clipped to bbox using rasterio windowed read.
    Returns (array, meta) or None on failure.
    """
    try:
        import rasterio
        from rasterio.windows import from_bounds
        from rasterio.enums import Resampling
        from rasterio.warp import transform_bounds
    except ImportError as e:
        logger.error(f"rasterio not available: {e}")
        if error_out is not None:
            error_out.append(f"rasterio unavailable: {type(e).__name__}: {e}")
        return None

    min_lon, min_lat, max_lon, max_lat = bbox
    try:
        with rasterio.open(href) as src:
            # Transform AOI to raster CRS if needed
            try:
                left, bottom, right, top = transform_bounds(
                    "EPSG:4326", src.crs, min_lon, min_lat, max_lon, max_lat
                )
            except Exception:
                left, bottom, right, top = min_lon, min_lat, max_lon, max_lat

            window = from_bounds(left, bottom, right, top, src.transform)
            window = window.intersection(
                rasterio.windows.Window(0, 0, src.width, src.height)
            )
            if window.width <= 0 or window.height <= 0:
                logger.warning("AOI window empty for band")
                if error_out is not None:
                    error_out.append("AOI does not intersect the asset extent")
                return None

            # Downsample large windows for performance
            out_h = int(window.height)
            out_w = int(window.width)
            if max(out_h, out_w) > max_size:
                scale = max_size / max(out_h, out_w)
                out_h = max(1, int(out_h * scale))
                out_w = max(1, int(out_w * scale))

            data = src.read(
                1,
                window=window,
                out_shape=(out_h, out_w),
                resampling=Resampling.bilinear,
                boundless=True,
                fill_value=0,
            )
            data = np.asarray(data, dtype=np.float32)

            # Sentinel-2 L2A often scaled reflectance * 10000
            if data.max() > 1.5:
                data = data / 10000.0
                data = np.clip(data, 0, 1)

            meta = {
                "crs": str(src.crs),
                "dtype": str(data.dtype),
                "shape": list(data.shape),
                "nodata": src.nodata,
                "resolution_approx_m": None,
            }
            return data, meta
    except Exception as e:
        logger.warning(f"Band read failed ({href[:80]}...): {e}")
        if error_out is not None:
            error_out.append(f"{type(e).__name__}: {e}")
        return None


def fetch_optical_bands(
    scene: Dict[str, Any],
    bbox: List[float],
    needed: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Download/read required optical bands for a STAC scene over bbox.
    needed: list of logical names e.g. ['green','red','nir','swir16']
    """
    if needed is None:
        needed = ["green", "red", "nir", "swir16"]

    stac_item = scene.get("stac_item")
    if not stac_item:
        return {
            "success": False,
            "error": "No STAC item attached to scene; cannot fetch bands",
            "mode": "NO_ITEM",
        }

    collection = scene.get("collection") or ""
    assets, signing_error, signed_assets = _signed_assets(stac_item)

    # Map logical band names to asset keys
    if "sentinel-2" in collection:
        key_map = {v: k for k, v in S2_BANDS.items()}
    else:
        key_map = {v: k for k, v in LANDSAT_BANDS.items()}
        # also try common aliases
        key_map.update({"red": "red", "green": "green", "nir": "nir08", "swir16": "swir16"})

    bands: Dict[str, np.ndarray] = {}
    band_meta: Dict[str, Any] = {}
    missing = []
    read_errors = []
    asset_details = []

    for logical in needed:
        asset_key = key_map.get(logical)
        if not asset_key:
            # try direct
            asset_key = logical
        selected_key, asset = _find_asset(assets, asset_key)
        if not asset:
            missing.append(logical)
            asset_details.append({"band": logical, "asset_key": asset_key, "status": "missing"})
            logger.warning(
                "Optical asset missing: scene_id=%s requested_band=%s asset_key=%s signed=%s",
                scene.get("id"), logical, asset_key, signed_assets,
            )
            continue
        href = _asset_href(asset)
        if not href:
            missing.append(logical)
            read_errors.append(f"{logical} ({selected_key}) has no href")
            asset_details.append({"band": logical, "asset_key": selected_key, "status": "missing_href"})
            continue
        logger.info(
            "Opening optical asset: scene_id=%s band=%s asset_key=%s signed=%s",
            scene.get("id"), logical, selected_key, signed_assets,
        )
        read_reason: List[str] = []
        result = _read_band_window(href, bbox, error_out=read_reason)
        if result is None:
            missing.append(logical)
            reason = read_reason[0] if read_reason else "unknown raster access error"
            read_errors.append(f"{logical} ({selected_key}): {reason}")
            asset_details.append({"band": logical, "asset_key": selected_key, "status": "access_failed"})
            continue
        arr, meta = result
        bands[logical] = arr
        band_meta[logical] = meta
        asset_details.append({"band": logical, "asset_key": selected_key, "status": "read"})

    if not bands:
        if missing and all(detail["status"] in {"missing", "missing_href"} for detail in asset_details):
            mode = "ASSET_MISSING"
            error = "Required optical band assets are missing from the STAC item"
        elif signing_error and not assets:
            mode = "SIGNING_FAILED"
            error = "Planetary Computer asset signing failed"
        else:
            mode = "ACCESS_FAILED"
            error = "Could not open any optical band assets for this scene/AOI"
        return {
            "success": False,
            "error": error,
            "missing": missing,
            "mode": mode,
            "signing_error": signing_error,
            "read_errors": read_errors,
            "asset_details": asset_details,
            "hint": (
                "Install planetary-computer and rasterio in the same environment as run.py, "
                "then verify that signed Planetary Computer COG URLs are reachable."
            ),
        }

    # Align shapes (crop to min common)
    shapes = [b.shape for b in bands.values()]
    min_h = min(s[0] for s in shapes)
    min_w = min(s[1] for s in shapes)
    for k in list(bands.keys()):
        bands[k] = bands[k][:min_h, :min_w]

    return {
        "success": True,
        "mode": "RASTER",
        "bands": bands,
        "band_meta": band_meta,
        "missing": missing,
        "asset_details": asset_details,
        "signing_error": signing_error,
        "shape": [min_h, min_w],
        "scene_id": scene.get("id"),
        "acquisition_date": scene.get("acquisition_date"),
        "collection": collection,
        "resolution_m": scene.get("resolution_m") or 10,
    }


def fetch_sar_band(
    scene: Dict[str, Any],
    bbox: List[float],
) -> Dict[str, Any]:
    """Fetch Sentinel-1 RTC VV or VH backscatter over AOI."""
    stac_item = scene.get("stac_item")
    if not stac_item:
        return {"success": False, "error": "No STAC item for SAR scene", "mode": "NO_ITEM"}

    assets, signing_error, signed_assets = _signed_assets(stac_item)

    # Prefer vv, then vh
    href = None
    pol = None
    for key in ("vv", "VH", "vh", "VV"):
        asset = assets.get(key) or assets.get(key.lower())
        if asset:
            href = asset.get("href") if isinstance(asset, dict) else getattr(asset, "href", None)
            pol = key.lower()
            if href:
                break

    if not href:
        return {
            "success": False,
            "error": "No VV/VH asset found on SAR item",
            "available_assets": list(assets.keys()),
            "signing_error": signing_error,
            "signed_assets": signed_assets,
            "mode": "NO_ASSET",
        }

    result = _read_band_window(href, bbox, max_size=512)
    if result is None:
        return {"success": False, "error": "SAR band read failed", "mode": "FETCH_FAILED"}

    arr, meta = result
    # RTC is often linear power; convert to dB for display stats
    with np.errstate(divide="ignore", invalid="ignore"):
        db = 10.0 * np.log10(np.maximum(arr, 1e-10))

    return {
        "success": True,
        "mode": "RASTER",
        "polarization": pol,
        "array_linear": arr,
        "array_db": db,
        "meta": meta,
        "shape": list(arr.shape),
        "scene_id": scene.get("id"),
        "acquisition_date": scene.get("acquisition_date"),
        "mean_db": float(np.nanmean(db)),
        "std_db": float(np.nanstd(db)),
        "resolution_m": scene.get("resolution_m") or 10,
    }


def mask_to_geojson_points(
    mask: np.ndarray,
    bbox: List[float],
    max_points: int = 200,
) -> List[Dict[str, Any]]:
    """
    Sample True pixels from a mask into lat/lon points for Leaflet overlay.
    Approximate mapping from array indices to bbox.
    """
    if mask is None or mask.size == 0:
        return []
    h, w = mask.shape
    min_lon, min_lat, max_lon, max_lat = bbox
    ys, xs = np.where(mask)
    if len(ys) == 0:
        return []
    # subsample
    step = max(1, len(ys) // max_points)
    points = []
    for i in range(0, len(ys), step):
        row, col = int(ys[i]), int(xs[i])
        lon = min_lon + (col + 0.5) / w * (max_lon - min_lon)
        lat = max_lat - (row + 0.5) / h * (max_lat - min_lat)
        points.append({"lat": lat, "lon": lon})
    return points


def mask_to_geojson(
    mask: np.ndarray,
    bbox: List[float],
    min_pixels: int = 1,
) -> Dict[str, Any]:
    """Convert a sampled AOI mask to GeoJSON polygons in EPSG:4326."""
    if mask is None or mask.size == 0:
        return {"type": "FeatureCollection", "features": []}

    try:
        import rasterio.features
        from rasterio.transform import from_bounds
        from shapely.geometry import shape, mapping
        from shapely.ops import unary_union
    except ImportError:
        return {"type": "FeatureCollection", "features": []}

    height, width = mask.shape
    min_lon, min_lat, max_lon, max_lat = bbox
    transform = from_bounds(min_lon, min_lat, max_lon, max_lat, width, height)
    geometries = []
    for geometry, value in rasterio.features.shapes(mask.astype("uint8"), transform=transform):
        if value == 1:
            polygon = shape(geometry)
            if polygon.area >= min_pixels * abs(transform.a * transform.e):
                geometries.append(polygon)

    if not geometries:
        return {"type": "FeatureCollection", "features": []}

    merged = unary_union(geometries)
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"class": "detected"},
            "geometry": mapping(merged),
        }],
    }
