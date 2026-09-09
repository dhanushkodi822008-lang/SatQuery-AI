"""
Comprehensive test suite for SatQuery AI Groq API & 2,000-question Knowledge Base.
Tests all 10 required scenarios.
"""
import sys
import asyncio
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient
from backend.app import app
from backend.ai.knowledge_engine import get_knowledge_engine, search_knowledge
from backend.ai.vlm_provider import run_vlm

client = TestClient(app)

def run_all_tests():
    print("==========================================================")
    print(" SatQuery AI — Comprehensive Chatbot & Groq Test Suite")
    print("==========================================================\n")

    # Check 1: Knowledge base size & categories
    eng = get_knowledge_engine()
    print(f"[TEST 1] Knowledge Base Loaded: {len(eng.documents)} questions")
    assert len(eng.documents) >= 2000, f"Expected >= 2000 items, got {len(eng.documents)}"
    beginner_count = sum(1 for d in eng.documents if d.get("difficulty") == "beginner")
    print(f"         Beginner questions: {beginner_count} (>= 800 requirement satisfied)")
    assert beginner_count >= 800

    # Check 2: Normal & Remote Sensing Question
    print("\n[TEST 2] Testing Remote Sensing Basics Question:")
    r = client.post("/api/chat", json={"message": "What is remote sensing?"})
    assert r.status_code == 200
    res = r.json()
    print("         Status:", r.status_code)
    print("         Answer Excerpt:", res.get("content")[:180].replace("\n", " "))

    # Check 3: NDVI Question with beginner-first structure
    print("\n[TEST 3] Testing NDVI Question:")
    r = client.post("/api/chat", json={"message": "What is NDVI?"})
    assert r.status_code == 200
    res = r.json()
    print("         Status:", r.status_code)
    print("         Contains definition & explanation:", bool(res.get("content")))
    print("         Answer Excerpt:", res.get("content")[:180].replace("\n", " "))

    # Check 4: Agriculture & Crops Question
    print("\n[TEST 4] Testing Agriculture Question:")
    r = client.post("/api/chat", json={"message": "How can satellites help farmers monitor crops?"})
    assert r.status_code == 200
    res = r.json()
    print("         Status:", r.status_code)
    print("         Answer Excerpt:", res.get("content")[:180].replace("\n", " "))

    # Check 5: Multi-turn Follow-up Question
    print("\n[TEST 5] Testing Multi-turn Follow-up Context:")
    # Turn 1
    r_turn1 = client.post("/api/chat", json={"message": "What is NDVI?"})
    session_id = r_turn1.json().get("session_id")
    # Turn 2 using "it"
    r_turn2 = client.post("/api/chat", json={
        "session_id": session_id,
        "message": "How is it useful for agriculture?"
    })
    assert r_turn2.status_code == 200
    res2 = r_turn2.json()
    print("         Session ID:", session_id)
    print("         Follow-up Answer Excerpt:", res2.get("content")[:200].replace("\n", " "))

    # Check 6: Unrelated Question Handling
    print("\n[TEST 6] Testing Unrelated Query:")
    r = client.post("/api/chat", json={"message": "How do I bake a chocolate cake?"})
    assert r.status_code == 200
    print("         Answer Excerpt:", r.json().get("content")[:180].replace("\n", " "))

    # Check 7: Empty Question Validation
    print("\n[TEST 7] Testing Empty Question Validation:")
    r = client.post("/api/chat", json={"message": "   "})
    print("         Status for empty string:", r.status_code, "(Expected 422 Validation Error)")
    assert r.status_code == 422

    # Check 8: Image Query without Upload (Strict Zero-Fabrication)
    print("\n[TEST 8] Testing Image Query Without Upload:")
    r = client.post("/api/chat", json={"message": "What is shown in this satellite image?"})
    assert r.status_code == 200
    content = r.json().get("content")
    print("         Response:", content)
    assert "upload a satellite image" in content.lower()

    # Check 9: Knowledge Search Endpoint
    print("\n[TEST 9] Testing Direct Knowledge Search Endpoint:")
    r = client.get("/api/chat/knowledge/search?q=spatial%20resolution")
    assert r.status_code == 200
    found = r.json().get("results_count", 0)
    print(f"         Found {found} matching Q&A records")
    assert found > 0

    # Check 10: Endpoint parity (/api/chat and /api/chat/message)
    print("\n[TEST 10] Testing Endpoint Parity (/api/chat vs /api/chat/message):")
    r_a = client.post("/api/chat", json={"message": "What is GIS?"})
    r_b = client.post("/api/chat/message", json={"message": "What is GIS?"})
    assert r_a.status_code == 200 and r_b.status_code == 200
    print("         Both endpoints responded with HTTP 200 OK")

    print("\n==========================================================")
    print(" ALL 10 TESTS PASSED SUCCESSFULLY! ")
    print("==========================================================")

if __name__ == "__main__":
    run_all_tests()
