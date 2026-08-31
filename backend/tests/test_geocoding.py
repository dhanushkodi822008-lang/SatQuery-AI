import asyncio
from types import SimpleNamespace

import pytest

from backend.services import geocoding_service


@pytest.fixture(autouse=True)
def disable_geocoding_cache(monkeypatch):
    monkeypatch.setattr(geocoding_service, "cache_get", lambda *args, **kwargs: None)
    monkeypatch.setattr(geocoding_service, "cache_set", lambda *args, **kwargs: None)


def _run(coroutine):
    return asyncio.run(coroutine)


def _location(address="Namakkal, Tamil Nadu, India"):
    return SimpleNamespace(latitude=11.2189, longitude=78.1674, address=address)


def test_namakkal_tamil_nadu_uses_nominatim_result(monkeypatch):
    calls = []

    async def fake_geocode(geolocator, query):
        calls.append(query)
        return _location()

    monkeypatch.setattr(geocoding_service, "_geocode_async", fake_geocode)

    result = _run(geocoding_service.geocode("Namakkal, Tamil Nadu"))

    assert result["success"] is True
    assert result["lat"] == 11.2189
    assert calls == ["Namakkal, Tamil Nadu"]


def test_nammakkal_typo_tries_corrected_query(monkeypatch):
    calls = []

    async def fake_geocode(geolocator, query):
        calls.append(query)
        return _location() if query == "Namakkal, Tamil Nadu" else None

    monkeypatch.setattr(geocoding_service, "_geocode_async", fake_geocode)

    result = _run(geocoding_service.geocode("Nammakkal,Tamil Nadu"))

    assert result["success"] is True
    assert result["display_name"] == "Namakkal, Tamil Nadu, India"
    assert calls[0] == "Nammakkal, Tamil Nadu"
    assert "Namakkal, Tamil Nadu" in calls[1:]


def test_namakkal_city_only_adds_state_fallback(monkeypatch):
    calls = []

    async def fake_geocode(geolocator, query):
        calls.append(query)
        return _location() if query == "Namakkal, Tamil Nadu" else None

    monkeypatch.setattr(geocoding_service, "_geocode_async", fake_geocode)

    result = _run(geocoding_service.geocode("  Namakkal  "))

    assert result["success"] is True
    assert calls[0] == "Namakkal"
    assert "Namakkal, Tamil Nadu" in calls[1:]


def test_invalid_location_returns_failure_without_coordinates(monkeypatch):
    calls = []

    async def fake_geocode(geolocator, query):
        calls.append(query)
        return None

    monkeypatch.setattr(geocoding_service, "_geocode_async", fake_geocode)

    result = _run(geocoding_service.geocode("not-a-real-place-12345"))

    assert result["success"] is False
    assert "No location found" in result["error"]
    assert "lat" not in result
    assert "lon" not in result
    assert calls
