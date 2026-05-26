"""Tests for Session Service — ChargingSession state machine"""

import os
import sys
import tempfile
from pathlib import Path

# Use a temporary database for tests
os.environ["VOLTEDGE_DB_PATH"] = os.path.join(tempfile.gettempdir(), "voltedge_test.db")

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

SESSION_ID = None


def test_1_health():
    """Health endpoint should return 200"""
    response = client.get("/sessions/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_2_start_session():
    """Start a new charging session"""
    global SESSION_ID
    response = client.post("/sessions/start", json={
        "charger_id": "charger-1",
        "contract_id": "contract-1"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["charger_id"] == "charger-1"
    assert data["contract_id"] == "contract-1"
    assert "session_id" in data
    SESSION_ID = data["session_id"]


def test_3_authorize_session():
    """Authorize the created session"""
    global SESSION_ID
    response = client.post(f"/sessions/{SESSION_ID}/authorize")
    assert response.status_code == 200
    assert response.json()["status"] == "Authorized"


def test_4_start_charging():
    """Start charging after authorization"""
    global SESSION_ID
    response = client.post(f"/sessions/{SESSION_ID}/start-charging")
    assert response.status_code == 200
    assert response.json()["status"] == "Charging"


def test_5_complete_session():
    """Complete session with energy data"""
    global SESSION_ID
    response = client.post(f"/sessions/{SESSION_ID}/complete", json={
        "energy_delivered": 25.5,
        "duration_minutes": 60
    })
    assert response.status_code == 200
    data = response.json()
    assert data["energy_delivered"] == 25.5
    assert data["duration_minutes"] == 60
    assert "SessionValidated" in str(type(data)) or data["session_id"] == SESSION_ID


def test_6_invalid_state_transition():
    """Should reject invalid state transitions"""
    global SESSION_ID
    # Try to authorize again on a completed session
    response = client.post(f"/sessions/{SESSION_ID}/authorize")
    assert response.status_code == 400
    assert "cannot" in response.json()["detail"].lower()
