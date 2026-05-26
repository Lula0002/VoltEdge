"""Tests for Analytics Service — ML anomaly detection"""

import os
import sys
import tempfile
from pathlib import Path

# Use a temporary database for tests
os.environ["VOLTEDGE_DB_PATH"] = os.path.join(tempfile.gettempdir(), "voltedge_test.db")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_1_health():
    """Health endpoint should return 200"""
    response = client.get("/analytics/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_2_predict_energy():
    """Predict energy for a 60-minute session"""
    response = client.post("/analytics/predict", json={
        "duration_minutes": 60
    })
    assert response.status_code == 200
    data = response.json()
    assert data["duration_minutes"] == 60
    assert data["predicted_energy_kwh"] > 0


def test_3_predict_long_session():
    """Predict energy for a 120-minute session"""
    response = client.post("/analytics/predict", json={
        "duration_minutes": 120
    })
    data = response.json()
    assert data["predicted_energy_kwh"] > 20  # Should be ~30 kWh


def test_4_detect_normal_session():
    """Normal session should NOT be flagged as anomaly"""
    response = client.post("/analytics/detect", json={
        "session_id": "normal-1",
        "energy_delivered": 15.0,
        "duration_minutes": 60
    })
    assert response.status_code == 200
    data = response.json()
    assert data["is_anomaly"] == False
    assert "Normal" in data["message"]


def test_5_detect_anomaly_low_energy():
    """Very low energy for duration should be flagged as anomaly"""
    response = client.post("/analytics/detect", json={
        "session_id": "anomaly-low-1",
        "energy_delivered": 1.0,
        "duration_minutes": 60
    })
    data = response.json()
    assert data["is_anomaly"] == True
    assert "Anomaly" in data["message"]


def test_6_detect_anomaly_high_energy():
    """Very high energy for duration should be flagged as anomaly"""
    response = client.post("/analytics/detect", json={
        "session_id": "anomaly-high-1",
        "energy_delivered": 50.0,
        "duration_minutes": 30
    })
    data = response.json()
    assert data["is_anomaly"] == True
    assert "Anomaly" in data["message"]


def test_7_predict_boundary():
    """Predict at boundary values (10 min)"""
    response = client.post("/analytics/predict", json={
        "duration_minutes": 10
    })
    assert response.status_code == 200
    data = response.json()
    assert data["predicted_energy_kwh"] > 0
