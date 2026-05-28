"""Tests for Analytics Service — ML energy & revenue prediction"""

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


def test_1_predict_energy():
    """Predict energy for a 60-min session at 20°C at 14:00"""
    response = client.post("/analytics/predict-energy", json={
        "duration_minutes": 60,
        "temperature": 20,
        "hour_of_day": 14
    })
    assert response.status_code == 200
    data = response.json()
    assert data["predicted_energy_kwh"] > 0
    assert data["input"]["duration_minutes"] == 60


def test_2_predict_energy_cold_weather():
    """Cold weather should predict higher energy usage"""
    response_warm = client.post("/analytics/predict-energy", json={
        "duration_minutes": 60, "temperature": 30, "hour_of_day": 14
    })
    response_cold = client.post("/analytics/predict-energy", json={
        "duration_minutes": 60, "temperature": 0, "hour_of_day": 14
    })
    assert response_cold.json()["predicted_energy_kwh"] > response_warm.json()["predicted_energy_kwh"]


def test_3_predict_revenue():
    """Predict revenue for a customer with 10 chargers and 100 sessions"""
    response = client.post("/analytics/predict-revenue", json={
        "duration_minutes": 60,
        "temperature": 15,
        "hour_of_day": 14,
        "kwh_price": 2.45,
        "num_sessions": 100,
        "num_chargers": 10
    })
    assert response.status_code == 200
    data = response.json()
    assert data["prediction"]["total_predicted_cost_dkk"] > 0
    assert data["prediction"]["revenue_per_charger_dkk"] > 0
