import pytest

from backend.utils.validation import validate_polygon_geojson


def polygon(points):
    return {"type": "Polygon", "coordinates": [points]}


@pytest.mark.parametrize(
    "points",
    [
        [[78.0, 11.0], [78.1, 11.0], [78.0, 11.1], [78.0, 11.0]],
        [[78.0, 11.0], [78.1, 11.0], [78.1, 11.1], [78.0, 11.1], [78.0, 11.0]],
        [[78.0, 11.0], [78.2, 11.0], [78.15, 11.08], [78.05, 11.12], [78.0, 11.0]],
    ],
)
def test_simple_manual_polygons_are_accepted(points):
    assert validate_polygon_geojson(polygon(points))["type"] == "Polygon"


def test_self_intersecting_polygon_is_rejected():
    with pytest.raises(ValueError, match="self-intersecting"):
        validate_polygon_geojson(polygon([
            [78.0, 11.0], [78.2, 11.2], [78.0, 11.2], [78.2, 11.0], [78.0, 11.0],
        ]))


def test_out_of_range_polygon_is_rejected():
    with pytest.raises(ValueError, match="longitude/latitude"):
        validate_polygon_geojson(polygon([
            [78.0, 11.0], [181.0, 11.0], [78.0, 11.1], [78.0, 11.0],
        ]))
