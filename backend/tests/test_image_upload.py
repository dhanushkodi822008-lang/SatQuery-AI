import io
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from fastapi.testclient import TestClient

from backend.app import app


client = TestClient(app)


def test_upload_valid_geotiff():
    data = io.BytesIO()
    with rasterio.open(
        data,
        "w",
        driver="GTiff",
        width=16,
        height=12,
        count=1,
        dtype="uint16",
        crs="EPSG:4326",
        transform=from_origin(78.0, 11.0, 0.1, 0.1),
    ) as dst:
        dst.write(np.full((12, 16), 1, dtype=np.uint16), 1)

    data.seek(0)
    response = client.post(
        "/api/images/upload",
        files={"file": ("sample_upload.tif", data.read(), "image/tiff")},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    assert payload["filename"] == "sample_upload.tif"
    assert payload["width"] == 16
    assert payload["height"] == 12
    assert payload["bands"] == 1
    assert payload["crs"] == "EPSG:4326"
    assert payload["file_size_bytes"] > 0


def test_upload_rejects_unsupported_extension():
    response = client.post(
        "/api/images/upload",
        files={"file": ("sample.txt", b"not an image", "text/plain")},
    )

    assert response.status_code == 400
    payload = response.json()
    assert "Unsupported image type" in payload["detail"]
