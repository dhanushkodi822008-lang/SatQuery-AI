import numpy as np
import rasterio
from rasterio.transform import from_origin

from backend.processing.ndwi import compute_ndwi
from backend.services import raster_fetch_service as fetcher


SYNTHETIC_ITEM = {
    "id": "synthetic-s2",
    "assets": {
        "b03": {"href": "https://example.test/green.tif"},
        "B08": {"href": "https://example.test/nir.tif"},
    },
}


def _scene(item=SYNTHETIC_ITEM):
    return {
        "id": item["id"],
        "collection": "sentinel-2-l2a",
        "stac_item": item,
    }


def test_sentinel_assets_are_selected_case_insensitively(monkeypatch):
    monkeypatch.setattr(fetcher, "_sign_item", lambda item: None)
    monkeypatch.setattr(fetcher, "_read_band_window", lambda href, bbox, **kwargs: (
        np.ones((2, 2), dtype=np.float32), {"shape": [2, 2]}
    ))

    result = fetcher.fetch_optical_bands(_scene(), [78.0, 10.0, 78.1, 10.1], ["green", "nir"])

    assert result["success"] is True
    assert [detail["status"] for detail in result["asset_details"]] == ["read", "read"]


def test_signed_asset_href_is_used(monkeypatch):
    class SignedAsset:
        def to_dict(self):
            return {"href": "https://example.test/signed-green.tif?sig=redacted"}

    class SignedItem:
        assets = {"B03": SignedAsset()}

    monkeypatch.setattr(fetcher, "_sign_item", lambda item: SignedItem())
    opened = []
    monkeypatch.setattr(fetcher, "_read_band_window", lambda href, bbox, **kwargs: (
        opened.append(href) or (np.ones((2, 2), dtype=np.float32), {"shape": [2, 2]})
    ))

    result = fetcher.fetch_optical_bands(_scene(), [78.0, 10.0, 78.1, 10.1], ["green"])

    assert result["success"] is True
    assert opened == ["https://example.test/signed-green.tif?sig=redacted"]
    assert result["asset_details"][0]["status"] == "read"


def test_missing_green_asset_is_reported(monkeypatch):
    monkeypatch.setattr(fetcher, "_signed_assets", lambda item: ({}, None, True))

    result = fetcher.fetch_optical_bands(_scene({"id": "missing-green", "assets": {}}), [0, 0, 1, 1], ["green"])

    assert result["success"] is False
    assert result["mode"] == "ASSET_MISSING"
    assert result["missing"] == ["green"]


def test_missing_nir_asset_is_reported(monkeypatch):
    monkeypatch.setattr(fetcher, "_signed_assets", lambda item: (
        {"B03": {"href": "https://example.test/green.tif"}}, None, True
    ))

    result = fetcher.fetch_optical_bands(_scene(), [0, 0, 1, 1], ["nir"])

    assert result["success"] is False
    assert result["mode"] == "ASSET_MISSING"
    assert result["missing"] == ["nir"]


def test_failed_asset_access_is_distinguished(monkeypatch):
    monkeypatch.setattr(fetcher, "_signed_assets", lambda item: (
        {"B03": {"href": "https://example.test/green.tif"}}, None, True
    ))
    monkeypatch.setattr(fetcher, "_read_band_window", lambda href, bbox, **kwargs: None)

    result = fetcher.fetch_optical_bands(_scene(), [0, 0, 1, 1], ["green"])

    assert result["success"] is False
    assert result["mode"] == "ACCESS_FAILED"
    assert result["asset_details"][0]["status"] == "access_failed"


def test_synthetic_ndwi_detects_water():
    green = np.array([[0.8, 0.1], [0.7, 0.2]], dtype=np.float32)
    nir = np.array([[0.1, 0.3], [0.2, 0.4]], dtype=np.float32)

    result = compute_ndwi(green, nir, water_threshold=0.0)

    assert result["success"] is True
    assert result["water_pixel_fraction"] == 0.5
    assert result["water_mask"].tolist() == [[True, False], [True, False]]


def test_synthetic_ndwi_no_water_case():
    result = compute_ndwi(
        np.full((2, 2), 0.1, dtype=np.float32),
        np.full((2, 2), 0.5, dtype=np.float32),
        water_threshold=0.0,
    )

    assert result["success"] is True
    assert result["water_pixel_fraction"] == 0.0
    assert not result["water_mask"].any()


def test_synthetic_geotiff_is_read_before_ndwi(tmp_path):
    green_path = tmp_path / "green.tif"
    nir_path = tmp_path / "nir.tif"
    profile = {
        "driver": "GTiff",
        "width": 2,
        "height": 2,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": from_origin(78.0, 10.2, 0.1, 0.1),
    }
    with rasterio.open(green_path, "w", **profile) as dst:
        dst.write(np.array([[0.8, 0.1], [0.7, 0.2]], dtype=np.float32), 1)
    with rasterio.open(nir_path, "w", **profile) as dst:
        dst.write(np.array([[0.1, 0.3], [0.2, 0.4]], dtype=np.float32), 1)

    green = fetcher._read_band_window(str(green_path), [78.0, 10.0, 78.2, 10.2])[0]
    nir = fetcher._read_band_window(str(nir_path), [78.0, 10.0, 78.2, 10.2])[0]
    result = compute_ndwi(green, nir, water_threshold=0.0)

    assert result["success"] is True
    assert result["water_pixel_fraction"] == 0.5


def test_water_mask_geojson_generation():
    mask = np.array([[True, False], [True, False]], dtype=bool)

    result = fetcher.mask_to_geojson(mask, [78.0, 10.0, 78.2, 10.2])

    assert result["type"] == "FeatureCollection"
    assert len(result["features"]) == 1
    assert result["features"][0]["geometry"]["type"] in {"Polygon", "MultiPolygon"}
