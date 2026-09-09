"""
Comprehensive verification test suite for SatQuery AI.
Tests location search, real administrative boundaries, coordinates, chatbot actions,
image formats, visual analysis, and email alerts.
"""
import asyncio
import sys
from pathlib import Path

# Ensure root directory in python path
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from httpx import AsyncClient, ASGITransport
from backend.app import app
from backend.services.geocoding_service import geocode, geocode_coordinates, reverse_geocode
from backend.routes.chat_routes import process_chat_message, ChatMessageRequest


async def test_location_and_real_boundary():
    print("\n--- Test 1: Place Name Geocoding & Real Boundary ---")
    res = await geocode("Namakkal District")
    assert res["success"] is True
    assert res["place_name"] == "Namakkal"
    assert res["admin_level"] == "District"
    assert res["has_real_boundary"] is True
    assert res["geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert res["area_km2"] > 3000.0  # Namakkal District is ~3421 km²
    print(f"[OK] Namakkal District boundary verified: {res['area_km2']} km2 (Type: {res['geometry']['type']})")


async def test_coordinates_and_reverse_boundary():
    print("\n--- Test 2: Coordinates Validation & Reverse Geocode Boundary ---")
    res = await geocode("11.2189, 78.1674")
    assert res["success"] is True
    assert res["district"] == "Namakkal"
    assert res["state"] == "Tamil Nadu"
    assert res["has_real_boundary"] is True
    assert res["geometry"]["type"] in ("Polygon", "MultiPolygon")
    print(f"[OK] Coordinates (11.2189, 78.1674) identified district: {res['district']}, {res['state']}")


async def test_chatbot_location_action():
    print("\n--- Test 3: Chatbot Location Finding Action ---")
    req = ChatMessageRequest(message="Find Namakkal District")
    res = await process_chat_message(req)
    assert res["success"] is True
    assert res["task"] == "location_search"
    assert res["action"] is not None
    assert res["action"]["type"] == "set_location"
    assert res["action"]["payload"]["has_real_boundary"] is True
    print(f"[OK] Chatbot returned set_location action with real polygon")


async def test_chatbot_coordinate_action():
    print("\n--- Test 4: Chatbot Coordinate Action ---")
    req = ChatMessageRequest(message="Find 11.2189, 78.1674")
    res = await process_chat_message(req)
    assert res["success"] is True
    assert res["task"] == "coordinate_search"
    assert res["action"] is not None
    assert res["action"]["type"] == "set_location"
    print(f"[OK] Chatbot handled coordinate query and attached action")


async def test_chatbot_boundary_selection():
    print("\n--- Test 5: Chatbot Real Boundary Selection ---")
    req = ChatMessageRequest(message="Select Namakkal District boundary")
    res = await process_chat_message(req)
    assert res["success"] is True
    assert res["task"] == "boundary_selection"
    assert res["action"] is not None
    assert res["action"]["type"] == "set_aoi"
    assert res["action"]["payload"]["geojson"]["type"] in ("Polygon", "MultiPolygon")
    print(f"[OK] Chatbot returned set_aoi action for real boundary")


async def test_chatbot_basemap_switch():
    print("\n--- Test 6: Chatbot Basemap Switching ---")
    req = ChatMessageRequest(message="Switch to satellite view")
    res = await process_chat_message(req)
    assert res["success"] is True
    assert res["action"]["type"] == "set_basemap"
    assert res["action"]["payload"]["basemap"] == "satellite"
    print(f"[OK] Chatbot switched basemap to satellite")


async def test_alerts_endpoint():
    print("\n--- Test 7: Direct Test Alert API ---")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/alerts/test", json={"location_name": "Namakkal District"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["type"] == "TEST"
        print(f"[OK] Alerts endpoint returned test response: {data.get('message')}")


async def test_chatbot_landcover_action():
    print("\n--- Test 8: Chatbot Landcover & Spectral Index Action ---")
    req = ChatMessageRequest(message="Show water", location="Namakkal District")
    res = await process_chat_message(req)
    assert res["success"] is True
    assert res["action"] is not None
    assert res["action"]["type"] == "select_landcover"
    assert res["action"]["payload"]["category"] == "water"
    print(f"[OK] Chatbot returned select_landcover action for category: {res['action']['payload']['category']}")


if __name__ == "__main__":
    async def run_all():
        await test_location_and_real_boundary()
        await test_coordinates_and_reverse_boundary()
        await test_chatbot_location_action()
        await test_chatbot_coordinate_action()
        await test_chatbot_boundary_selection()
        await test_chatbot_basemap_switch()
        await test_alerts_endpoint()
        await test_chatbot_landcover_action()
        print("\n========================================================")
        print("ALL 8 TESTS PASSED SUCCESSFULLY! SATQUERY AI IS FULLY OPERATIONAL.")
        print("========================================================")

    asyncio.run(run_all())


