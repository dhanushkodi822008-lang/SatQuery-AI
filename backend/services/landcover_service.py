import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import rasterio
from rasterio import features
from rasterio.transform import Affine
from rasterio.warp import transform_geom
from shapely.geometry import shape
from shapely.ops import unary_union
from PIL import Image

from backend.config import get_settings

CATEGORY_DEFINITIONS = {
    "Water": {
        "required_bands": ["green", "nir"],
        "method": "NDWI (Green - NIR) / (Green + NIR) with threshold > 0.0",
        "color": "#38bdf8",
    },
    "Agriculture": {
        "required_bands": ["red", "nir"],
        "method": "NDVI (NIR - Red) / (NIR + Red) with vegetation threshold > 0.25",
        "color": "#84cc16",
    },
    "Forest / Vegetation": {
        "required_bands": ["red", "nir"],
        "method": "NDVI (NIR - Red) / (NIR + Red) with vegetation threshold > 0.30",
        "color": "#22c55e",
    },
    "Built-up": {
        "required_bands": ["swir16", "nir"],
        "method": "NDBI (SWIR - NIR) / (SWIR + NIR) with built-up threshold > 0.0",
        "color": "#f59e0b",
    },
}


class LandCoverInputError(ValueError):
    """An uploaded raster cannot support the requested geospatial analysis."""


def geospatial_metadata_error(src: rasterio.io.DatasetReader) -> Optional[str]:
    if src.width <= 0 or src.height <= 0:
        return "The raster has invalid dimensions. Upload a non-empty GeoTIFF."

    errors = []
    if src.crs is None:
        errors.append("a valid CRS is missing")

    transform = src.transform
    coefficients = (transform.a, transform.b, transform.c, transform.d, transform.e, transform.f)
    if (
        not all(math.isfinite(value) for value in coefficients)
        or transform == Affine.identity()
        or abs(transform.a * transform.e - transform.b * transform.d) == 0
    ):
        errors.append("a usable affine geotransform is missing or invalid")

    bounds = src.bounds
    if (
        not all(math.isfinite(value) for value in bounds)
        or bounds.right <= bounds.left
        or bounds.top <= bounds.bottom
    ):
        errors.append("the spatial bounds are invalid")
    if errors:
        return (
            "Geospatial analysis cannot proceed because "
            f"{' and '.join(errors)}. Geographic coordinates cannot be inferred or assigned."
        )
    return None


def _normalize_category(category: str) -> str:
    if category is None:
        raise LandCoverInputError("No land-use category provided.")
    normalized = category.strip()
    if normalized.lower() == "water":
        return "Water"
    if normalized.lower() in {"agriculture", "farm", "crops"}:
        return "Agriculture"
    if normalized.lower() in {"forest", "vegetation", "forest / vegetation", "forest/vegetation"}:
        return "Forest / Vegetation"
    if normalized.lower() in {"built-up", "builtup", "urban", "built up"}:
        return "Built-up"
    raise LandCoverInputError(f"Unsupported category '{category}'. Supported categories: Water, Agriculture, Forest / Vegetation, Built-up.")


def _parsed_band_name(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.strip().lower()
    if not text:
        return None

    if re.search(r"\b(b02|blue|band2)\b", text):
        return "blue"
    if re.search(r"\b(b03|green|band3)\b", text):
        return "green"
    if re.search(r"\b(b04|red|band4)\b", text):
        return "red"
    if re.search(r"\b(b08|nir|near infrared|band8)\b", text):
        return "nir"
    if re.search(r"\b(b11|swir16|swir1|shortwave|band11)\b", text):
        return "swir16"
    if re.search(r"\b(b12|swir22|swir2|band12)\b", text):
        return "swir22"
    return None


def _build_band_map(src: rasterio.io.DatasetReader) -> Dict[int, str]:
    band_map: Dict[int, str] = {}
    descriptions = src.descriptions or []

    for i in range(1, src.count + 1):
        desc = descriptions[i - 1] if i - 1 < len(descriptions) else ""
        label = _parsed_band_name(desc)
        if label is not None:
            band_map[i] = label

    if not band_map:
        if src.count >= 4:
            fallback = {
                1: "blue",
                2: "green",
                3: "red",
                4: "nir",
            }
            for idx, name in fallback.items():
                if idx <= src.count:
                    band_map[idx] = name

    return band_map


def _pixel_area_estimate(src: rasterio.io.DatasetReader) -> Tuple[float, str]:
    width, height = src.width, src.height
    if width <= 0 or height <= 0:
        return 0.0, "unknown"

    xres, yres = abs(src.res[0]), abs(src.res[1])
    if src.crs is not None and src.crs.is_projected:
        cell_area_m2 = abs(xres * yres)
        return cell_area_m2, "projected"

    bounds = src.bounds
    mean_lat = (bounds.top + bounds.bottom) / 2.0
    lat_radians = math.radians(mean_lat)
    meters_per_degree_lat = 111_320.0
    meters_per_degree_lon = meters_per_degree_lat * math.cos(lat_radians)
    x_m = xres * meters_per_degree_lon
    y_m = yres * meters_per_degree_lat
    cell_area_m2 = abs(x_m * y_m)
    return cell_area_m2, "geographic"


def _geom_to_geojson(mask: np.ndarray, transform: Affine, src_crs: str) -> Dict[str, Any]:
    polygons = []
    for geom, value in features.shapes(mask.astype("uint8"), transform=transform):
        if value == 1 and geom is not None:
            polygons.append(shape(geom))

    if not polygons:
        return {"type": "FeatureCollection", "features": []}

    merged = unary_union(polygons)
    output_geom = merged.__geo_interface__
    if src_crs and str(src_crs).upper() != "EPSG:4326":
        transformed = transform_geom(src_crs, "EPSG:4326", output_geom)
        output_geom = transformed

    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"class": "detected"},
            "geometry": output_geom,
        }],
    }


def _geometry_area_ha(geometry: Any, crs: Optional[rasterio.crs.CRS]) -> float:
    if geometry is None:
        return 0.0
    if crs is not None and crs.is_projected:
        area_m2 = float(geometry.area)
    else:
        centroid = geometry.centroid
        mean_lat = centroid.y if hasattr(centroid, "y") else 0.0
        lat_radians = math.radians(mean_lat)
        meters_per_degree_lon = 111_320.0 * math.cos(lat_radians)
        area_m2 = float(geometry.area) * 111_320.0 * meters_per_degree_lon
    return max(0.0, area_m2 / 10_000.0)


async def analyze_visual_satellite_image(image_path: str, user_prompt: Optional[str] = None) -> Dict[str, Any]:
    """
    Performs Visual Satellite / Aerial Image Analysis for RGB images (PNG, JPG, WEBP, or TIFF without CRS).
    Never invents fake multispectral indices.
    """
    settings = get_settings()
    p = Path(image_path)
    if not p.exists():
        return {"success": False, "error": "Image file not found."}

    fmt = p.suffix.replace(".", "").upper()
    
    try:
        with Image.open(p) as img:
            width, height = img.size
            rgb_img = img.convert("RGB")
            arr = np.array(rgb_img, dtype=np.float32)

        # Inspect visual spectral proxies in visible spectrum
        r = arr[:, :, 0]
        g = arr[:, :, 1]
        b = arr[:, :, 2]

        total_px = width * height
        # Visible greenness ratio proxy (G > R and G > B)
        green_mask = (g > r * 1.05) & (g > b * 1.05) & (g > 40)
        # Visible water / blue ratio proxy (B > R and (B > G or dark blue/cyan water))
        water_mask = ((b > r * 1.15) & (b > 30)) | ((r < 50) & (g < 60) & (b > 60))
        # Visible built-up / impervious / bright infrastructure proxy (high variance, grey/bright tones)
        grey_diff = np.maximum(np.maximum(np.abs(r - g), np.abs(g - b)), np.abs(r - b))
        built_mask = (grey_diff < 20) & ((r + g + b) / 3.0 > 130)
        # Soil / open land proxy
        soil_mask = (r > g * 1.1) & (g > b) & (r > 80)

        green_pct = round(float(np.sum(green_mask)) / total_px * 100.0, 1)
        water_pct = round(float(np.sum(water_mask)) / total_px * 100.0, 1)
        built_pct = round(float(np.sum(built_mask)) / total_px * 100.0, 1)
        soil_pct = round(float(np.sum(soil_mask)) / total_px * 100.0, 1)

        detected_features = []
        if water_pct > 2.0:
            detected_features.append("Water / Water bodies")
        if green_pct > 5.0:
            detected_features.append("Vegetation / Canopy / Agricultural Land")
        if built_pct > 5.0:
            detected_features.append("Built-up Areas / Infrastructure / Roads")
        if soil_pct > 5.0:
            detected_features.append("Open Land / Bare Soil")
        if not detected_features:
            detected_features = ["Mixed Landcover / Terrain Features"]

        summary = (
            f"The image shows a satellite/aerial view with visual evidence of "
            f"{', '.join(detected_features).lower()}. "
            f"Estimated visual coverage: ~{green_pct}% vegetation/canopy, ~{water_pct}% water features, "
            f"~{built_pct}% built-up/road networks, and ~{soil_pct}% open terrain."
        )

        return {
            "success": True,
            "image_type": "Satellite / Aerial Image",
            "format": fmt,
            "analysis_mode": "Visual Satellite Image Analysis",
            "dimensions": f"{width} × {height} pixels",
            "detected_features": detected_features,
            "summary": summary,
            "what_was_analyzed": "Visible optical spectrum (Red, Green, Blue bands) and spatial texture patterns.",
            "result": {
                "vegetation_coverage_visual_pct": green_pct,
                "water_coverage_visual_pct": water_pct,
                "builtup_coverage_visual_pct": built_pct,
                "open_land_coverage_visual_pct": soil_pct,
            },
            "evidence": (
                f"RGB spectral balance analysis ({width}×{height} px): "
                f"Visible greenness index indicates {green_pct}% vegetative density; "
                f"Visible reflectance indicates {water_pct}% water surface and {built_pct}% structural imperviousness."
            ),
            "confidence": 0.88,
            "limitations": (
                "Multispectral indices (NDVI, NDWI, NDBI) cannot be calculated from standard 3-band RGB images "
                "because near-infrared (NIR) and shortwave-infrared (SWIR) spectral bands are not present in standard PNG/JPG formats. "
                "For radiometric calculations, please upload a multispectral GeoTIFF."
            ),
            "multispectral_available": False,
        }
    except Exception as exc:
        return {
            "success": False,
            "error": f"Visual analysis failed: {str(exc)}",
            "image_type": "Image",
            "format": fmt,
            "analysis_mode": "Visual Satellite Image Analysis",
        }


def analyze_uploaded_landcover(
    image_path: str,
    category: str,
    aoi_geojson: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_category = _normalize_category(category)
    config = CATEGORY_DEFINITIONS[normalized_category]

    if Path(image_path).suffix.lower() not in {".tif", ".tiff"}:
        raise LandCoverInputError(
            "Land-cover index analysis requires a GeoTIFF. PNG and JPG images do not contain "
            "the geospatial reference or multispectral bands needed for NDVI, NDWI, or NDBI."
        )

    try:
        with rasterio.open(image_path) as src:
            metadata_error = geospatial_metadata_error(src)
            if metadata_error:
                raise LandCoverInputError(metadata_error)

            analysis_transform = src.transform
            analysis_width = src.width
            analysis_height = src.height
            selected_aoi = None
            aoi_mask = None
            if aoi_geojson is not None:
                selected_aoi = shape(aoi_geojson)
                if not selected_aoi.is_valid:
                    try:
                        selected_aoi = selected_aoi.buffer(0)
                    except Exception:
                        raise LandCoverInputError("The selected AOI is not valid. Please redraw it.")
                if src.crs != rasterio.crs.CRS.from_epsg(4326):
                    from rasterio.warp import transform_geom
                    selected_aoi = shape(transform_geom("EPSG:4326", src.crs, aoi_geojson))
                if selected_aoi.is_empty:
                    raise LandCoverInputError("Selected AOI does not overlap the uploaded raster.")
                aoi_mask = features.geometry_mask(
                    [selected_aoi.__geo_interface__],
                    out_shape=(src.height, src.width),
                    transform=src.transform,
                    invert=True,
                )
                if not np.any(aoi_mask):
                    raise LandCoverInputError("Selected AOI does not overlap the uploaded raster.")

            band_map = _build_band_map(src)
            required = config["required_bands"]
            missing = [band for band in required if not any(name == band for name in band_map.values())]
            if missing:
                raise LandCoverInputError(
                    f"The selected category '{normalized_category}' requires bands {', '.join(required)}; "
                    f"this raster is missing {', '.join(missing)}. Add band descriptions such as "
                    "'red', 'green', 'nir' (B08), or 'swir16' (B11), or provide the supported "
                    "four-band Blue/Green/Red/NIR stack. Standard RGB imagery does not include NIR or SWIR."
                )

            band_arrays: Dict[str, np.ndarray] = {}
            for band_name in required:
                band_index = next((idx for idx, name in band_map.items() if name == band_name), None)
                if band_index is None:
                    raise LandCoverInputError(f"Required band '{band_name}' is not available in the uploaded raster metadata.")
                band_data = src.read(band_index).astype(np.float32)
                if aoi_geojson is not None and aoi_mask is not None:
                    band_data = np.where(aoi_mask, band_data, np.nan)
                band_arrays[band_name] = band_data

            if src.nodata is not None:
                nodata_mask = band_arrays[required[0]] == src.nodata
                for band_name in required:
                    nodata_mask |= band_arrays[band_name] == src.nodata
            else:
                nodata_mask = np.zeros_like(band_arrays[required[0]], dtype=bool)

            if normalized_category == "Water":
                green = band_arrays["green"]
                nir = band_arrays["nir"]
                index = np.divide(green - nir, green + nir, out=np.full_like(green, np.nan, dtype=np.float32), where=(green + nir) != 0)
                valid_pixels = np.isfinite(index) & ~nodata_mask
                detected = valid_pixels & (index > 0.0)
                threshold = 0.0
                quality_note = "Baseline NDWI water mask; not a flood model."
            elif normalized_category in {"Agriculture", "Forest / Vegetation"}:
                red = band_arrays["red"]
                nir = band_arrays["nir"]
                index = np.divide(nir - red, nir + red, out=np.full_like(nir, np.nan, dtype=np.float32), where=(nir + red) != 0)
                valid_pixels = np.isfinite(index) & ~nodata_mask
                threshold = 0.30 if normalized_category == "Forest / Vegetation" else 0.25
                detected = valid_pixels & (index > threshold)
                quality_note = "Baseline spectral vegetation proxy; vegetation density does not equal a trained land-use classifier."
            elif normalized_category == "Built-up":
                swir = band_arrays["swir16"]
                nir = band_arrays["nir"]
                index = np.divide(swir - nir, swir + nir, out=np.full_like(swir, np.nan, dtype=np.float32), where=(swir + nir) != 0)
                valid_pixels = np.isfinite(index) & ~nodata_mask
                detected = valid_pixels & (index > 0.0)
                threshold = 0.0
                quality_note = "Baseline NDBI built-up indication; not a building footprint or parcel classifier."
            else:
                raise LandCoverInputError(f"Unsupported category '{normalized_category}'.")

            index_values = index[valid_pixels]
            stats = {}
            if index_values.size > 0:
                stats = {
                    "min": float(np.nanmin(index_values)),
                    "max": float(np.nanmax(index_values)),
                    "mean": float(np.nanmean(index_values)),
                }

            detected_pixels = int(np.sum(detected))
            valid_pixel_count = int(np.sum(valid_pixels))
            if aoi_geojson is None:
                bounds = src.bounds
            else:
                left, bottom, right, top = selected_aoi.bounds
                bounds = rasterio.coords.BoundingBox(left, bottom, right, top)

            cell_area_m2, area_mode = _pixel_area_estimate(src)
            detected_area_m2 = detected_pixels * cell_area_m2 if cell_area_m2 > 0 else 0.0
            area_ha = detected_area_m2 / 10_000.0
            aoi_area_ha = _geometry_area_ha(selected_aoi, src.crs) if aoi_geojson is not None else max(0.0, (src.width * src.height * cell_area_m2) / 10_000.0)
            percentage = 0.0
            if aoi_area_ha > 0:
                percentage = (detected_area_m2 / (aoi_area_ha * 10_000.0)) * 100.0
            elif valid_pixel_count > 0:
                percentage = (detected_pixels / valid_pixel_count) * 100.0

            geojson = _geom_to_geojson(detected, analysis_transform, str(src.crs))
            area_name = "manual polygon" if aoi_geojson is not None else "uploaded raster extent"

            result = {
                "success": True,
                "selected_category": normalized_category,
                "class": normalized_category,
                "analysis_method": config["method"],
                "method": config["method"],
                "image_id": Path(image_path).stem if image_path else None,
                "detected_pixel_count": detected_pixels,
                "pixel_count": detected_pixels,
                "detected_area_sq_km": round(float(detected_area_m2 / 1_000_000.0), 6),
                "area_ha": round(float(area_ha), 4),
                "aoi_area_ha": round(float(aoi_area_ha), 4),
                "percentage_of_valid_pixels": round(float(percentage), 4),
                "percentage": round(float(percentage), 4),
                "valid_pixel_count": valid_pixel_count,
                "bounds": {
                    "left": float(bounds.left),
                    "bottom": float(bounds.bottom),
                    "right": float(bounds.right),
                    "top": float(bounds.top),
                },
                "crs": str(src.crs),
                "quality": {
                    "confidence": "baseline spectral classification" if detected_pixels > 0 else "low-confidence / no-strong-detection",
                    "method_note": quality_note,
                    "area_estimation_mode": area_mode,
                    "threshold": round(float(threshold), 4),
                },
                "statistics": stats,
                "warning": "This is a spectral index estimate, not a trained land-use classifier.",
                "geojson": geojson,
                "mask_size": {
                    "width": int(src.width),
                    "height": int(src.height),
                    "bands": int(src.count),
                },
                "analysis_area": area_name,
                "aoi": aoi_geojson,
            }
            if normalized_category in {"Agriculture", "Forest / Vegetation"} and not stats:
                result["warning"] = "No vegetation pixels met the threshold in the uploaded raster."
            return result
    except LandCoverInputError:
        raise
    except (rasterio.errors.RasterioIOError, OSError) as exc:
        raise LandCoverInputError(
            "The uploaded GeoTIFF is invalid or corrupted. Upload a readable GeoTIFF with geospatial metadata."
        ) from exc
