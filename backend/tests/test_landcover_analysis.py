import io

import numpy as np
import rasterio
from rasterio.transform import from_origin
from fastapi.testclient import TestClient

from backend.app import app
from backend.config import get_settings
from backend.routes import landcover_routes

client = TestClient(app)
settings = get_settings()


def _create_upload(file_name: str, *, red=None, green=None, nir=None, swir16=None):
    if red is None:
        red = np.full((20, 20), 50, dtype=np.uint16)
    if green is None:
        green = np.full((20, 20), 60, dtype=np.uint16)
    if nir is None:
        nir = np.full((20, 20), 90, dtype=np.uint16)
    if swir16 is None:
        swir16 = np.full((20, 20), 80, dtype=np.uint16)

    data = io.BytesIO()
    with rasterio.open(
        data,
        "w",
        driver="GTiff",
        width=20,
        height=20,
        count=4,
        dtype="uint16",
        crs="EPSG:4326",
        transform=from_origin(78.0, 11.0, 0.1, 0.1),
    ) as dst:
        dst.set_band_description(1, "red")
        dst.set_band_description(2, "green")
        dst.set_band_description(3, "nir")
        dst.set_band_description(4, "swir16")
        dst.write(np.asarray(red, dtype=np.uint16), 1)
        dst.write(np.asarray(green, dtype=np.uint16), 2)
        dst.write(np.asarray(nir, dtype=np.uint16), 3)
        dst.write(np.asarray(swir16, dtype=np.uint16), 4)

    data.seek(0)
    response = client.post(
        "/api/images/upload",
        files={"file": (file_name, data.read(), "image/tiff")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_metadata_incomplete_upload(*, crs="EPSG:4326", transform=None):
    data = io.BytesIO()
    profile = {
        "driver": "GTiff",
        "width": 10,
        "height": 10,
        "count": 4,
        "dtype": "uint16",
        "crs": crs,
    }
    if transform is not None:
        profile["transform"] = transform
    with rasterio.open(data, "w", **profile) as dst:
        for band in range(1, 5):
            dst.set_band_description(band, ("blue", "green", "red", "nir")[band - 1])
            dst.write(np.full((10, 10), band, dtype=np.uint16), band)

    data.seek(0)
    response = client.post(
        "/api/images/upload",
        files={"file": ("metadata_incomplete.tif", data.read(), "image/tiff")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_valid_landcover_analysis_request():
    uploaded = _create_upload("landcover_valid.tif")
    result = client.post(
        "/api/landcover/analyze",
        json={"image_id": uploaded["image_id"], "category": "Water"},
    )

    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["success"] is True
    assert payload["selected_category"] == "Water"
    assert payload["class"] == "Water"
    assert payload["analysis_method"]
    assert payload["detected_pixel_count"] >= 0
    assert payload["area_ha"] >= 0
    assert payload["percentage"] >= 0
    assert payload["crs"] == "EPSG:4326"
    assert payload["bounds"]["left"] == 78.0


def test_invalid_category():
    uploaded = _create_upload("landcover_invalid_category.tif")
    result = client.post(
        "/api/landcover/analyze",
        json={"image_id": uploaded["image_id"], "category": "Unknown"},
    )

    assert result.status_code == 400
    payload = result.json()
    assert "Unsupported category" in payload["detail"]


def test_missing_uploaded_image():
    result = client.post(
        "/api/landcover/analyze",
        json={"image_id": "no_such_image_id", "category": "Water"},
    )

    assert result.status_code == 404
    assert "Uploaded image not found" in result.json()["detail"]


def test_missing_required_bands():
    data = io.BytesIO()
    with rasterio.open(
        data,
        "w",
        driver="GTiff",
        width=10,
        height=10,
        count=2,
        dtype="uint16",
        crs="EPSG:4326",
        transform=from_origin(78.0, 11.0, 0.1, 0.1),
    ) as dst:
        dst.write(np.full((10, 10), 1, dtype=np.uint16), 1)
        dst.write(np.full((10, 10), 2, dtype=np.uint16), 2)

    data.seek(0)
    upload = client.post(
        "/api/images/upload",
        files={"file": ("no_red_nir.tif", data.read(), "image/tiff")},
    )
    image_id = upload.json()["image_id"]

    result = client.post(
        "/api/landcover/analyze",
        json={"image_id": image_id, "category": "Water"},
    )

    assert result.status_code == 400
    assert "requires bands green, nir" in result.json()["detail"]
    assert "missing green, nir" in result.json()["detail"]


def test_raster_processing_error():
    data = io.BytesIO(b"not really a tif")
    response = client.post(
        "/api/images/upload",
        files={"file": ("broken.tif", data.read(), "image/tiff")},
    )
    assert response.status_code == 400
    assert "Invalid raster or corrupted TIFF file" in response.json()["detail"]
    assert "uploads" not in response.json()["detail"]


def test_missing_crs_is_rejected_with_clear_message():
    uploaded = _create_metadata_incomplete_upload(crs=None, transform=from_origin(78, 11, 0.1, 0.1))
    result = client.post(
        "/api/landcover/analyze",
        json={"image_id": uploaded["image_id"], "category": "Water"},
    )

    assert result.status_code == 400
    assert "valid CRS is missing" in result.json()["detail"]


def test_missing_geotransform_is_rejected_with_clear_message():
    uploaded = _create_metadata_incomplete_upload()
    assert uploaded["has_geospatial"] is False
    result = client.post(
        "/api/landcover/analyze",
        json={"image_id": uploaded["image_id"], "category": "Water"},
    )

    assert result.status_code == 400
    assert "affine geotransform is missing or invalid" in result.json()["detail"]


def test_rgb_image_is_not_accepted_for_geospatial_index_analysis():
    image = io.BytesIO()
    from PIL import Image

    Image.new("RGB", (10, 10), color=(20, 50, 80)).save(image, format="PNG")
    upload = client.post(
        "/api/images/upload",
        files={"file": ("rgb.png", image.getvalue(), "image/png")},
    )
    assert upload.status_code == 200
    result = client.post(
        "/api/landcover/analyze",
        json={"image_id": upload.json()["image_id"], "category": "Water"},
    )

    assert result.status_code == 400
    assert "requires a GeoTIFF" in result.json()["detail"]
    assert "do not contain" in result.json()["detail"]


def test_invalid_analysis_request_is_rejected():
    result = client.post("/api/landcover/analyze", json={})
    assert result.status_code == 422
    assert "category" in result.text


def test_overall_measurement_returns_category_metrics_and_acquisition(monkeypatch):
    scene = {
        "id": "test-scene",
        "satellite": "Sentinel-2",
        "sensor": "MSI",
        "acquisition_date": "2026-09-01",
        "cloud_cover_pct": 5.0,
    }
    async def fake_get_best_scene(_bbox):
        return {"success": True, "scene": scene, "candidates": [scene]}

    monkeypatch.setattr(landcover_routes, "get_best_optical_scene", fake_get_best_scene)

    def fake_analysis(*args, **kwargs):
        return {
            "success": True,
            "mode": "RASTER",
            "scene": scene,
            "source": "Microsoft Planetary Computer (signed COG windowed read)",
            "quantitative_result": {
                "water": {"area_km2": 1.2, "area_ha": 120, "pct_of_aoi": 12, "pixel_count": 12, "valid_coverage_pct": 98},
                "agriculture": {"area_km2": 2.3, "area_ha": 230, "pct_of_aoi": 23, "pixel_count": 23},
                "builtup": {"area_km2": 0.4, "area_ha": 40, "pct_of_aoi": 4, "pixel_count": 4},
                "forest": {"area_km2": 1.1, "area_ha": 110, "pct_of_aoi": 11, "pixel_count": 11},
            },
        }

    monkeypatch.setattr(landcover_routes, "analyze_optical_aoi", fake_analysis)
    aoi = {
        "type": "Polygon",
        "coordinates": [[[78.0, 10.0], [78.2, 10.0], [78.2, 10.2], [78.0, 10.2], [78.0, 10.0]]],
    }
    result = client.post(
        "/api/landcover/analyze",
        json={"category": "Overall Measurement", "aoi": aoi},
    )

    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["source"].startswith("Microsoft Planetary Computer")
    assert payload["acquisition_date"] == "2026-09-01"
    assert payload["categories"]["Water"]["area_km2"] == 1.2
    assert payload["categories"]["Water"]["area_ha"] == 120
    assert payload["categories"]["Water"]["percentage"] == 12
    assert payload["categories"]["Built-up"]["index"] == "NDBI"


def test_correct_spatial_bounds_in_response():
    uploaded = _create_upload("spatial_bounds.tif")
    result = client.post(
        "/api/landcover/analyze",
        json={"image_id": uploaded["image_id"], "category": "Agriculture"},
    )

    payload = result.json()
    expected_left, expected_bottom, expected_right, expected_top = rasterio.transform.array_bounds(
        20,
        20,
        from_origin(78.0, 11.0, 0.1, 0.1),
    )
    assert payload["bounds"] == {
        "left": expected_left,
        "bottom": expected_bottom,
        "right": expected_right,
        "top": expected_top,
    }
    assert payload["crs"] == "EPSG:4326"


def test_manual_aoi_is_validated_and_used():
    uploaded = _create_upload("manual_aoi.tif")
    aoi = {
        "type": "Polygon",
        "coordinates": [[[78.2, 10.2], [78.8, 10.2], [78.8, 10.8], [78.2, 10.8], [78.2, 10.2]]],
    }
    result = client.post(
        "/api/landcover/analyze",
        json={"image_id": uploaded["image_id"], "category": "Water", "aoi": aoi},
    )

    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["analysis_area"] == "manual polygon"
    assert payload["aoi"] == aoi
    assert payload["bounds"]["left"] >= 78.2
    assert payload["bounds"]["right"] <= 78.8


def test_empty_manual_aoi_is_rejected():
    uploaded = _create_upload("empty_aoi.tif")
    result = client.post(
        "/api/landcover/analyze",
        json={
            "image_id": uploaded["image_id"],
            "category": "Water",
            "aoi": {"type": "Polygon", "coordinates": []},
        },
    )

    assert result.status_code == 400
    assert "coordinates are empty" in result.json()["detail"]


def test_agriculture_generates_detected_geojson():
    uploaded = _create_upload(
        "agriculture_mask.tif",
        red=np.full((20, 20), 10, dtype=np.uint16),
        nir=np.full((20, 20), 100, dtype=np.uint16),
    )
    result = client.post(
        "/api/landcover/analyze",
        json={"image_id": uploaded["image_id"], "category": "Agriculture"},
    )

    payload = result.json()
    assert result.status_code == 200
    assert payload["detected_pixel_count"] == 400
    assert payload["geojson"]["features"]


def test_forest_vegetation_generates_detected_geojson():
    uploaded = _create_upload(
        "forest_mask.tif",
        red=np.full((20, 20), 10, dtype=np.uint16),
        nir=np.full((20, 20), 100, dtype=np.uint16),
    )
    result = client.post(
        "/api/landcover/analyze",
        json={"image_id": uploaded["image_id"], "category": "Forest / Vegetation"},
    )

    payload = result.json()
    assert result.status_code == 200
    assert payload["detected_pixel_count"] == 400
    assert payload["geojson"]["features"]


def test_builtup_generates_detected_geojson():
    uploaded = _create_upload(
        "builtup_mask.tif",
        nir=np.full((20, 20), 10, dtype=np.uint16),
        swir16=np.full((20, 20), 100, dtype=np.uint16),
    )
    result = client.post(
        "/api/landcover/analyze",
        json={"image_id": uploaded["image_id"], "category": "Built-up"},
    )

    payload = result.json()
    assert result.status_code == 200
    assert payload["detected_pixel_count"] == 400
    assert payload["geojson"]["features"]
