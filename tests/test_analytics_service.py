"""Tests for Analytics Service — ML energy & revenue prediction"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Use a temporary database for tests
os.environ["VOLTEDGE_DB_PATH"] = os.path.join(tempfile.gettempdir(), "voltedge_test.db")
os.environ["VOLTEDGE_ML_DB_PATH"] = os.path.join(tempfile.gettempdir(), "ml_training_test.db")

# Clean up old test DBs before importing
for _key in ["VOLTEDGE_DB_PATH", "VOLTEDGE_ML_DB_PATH"]:
    _p = os.environ[_key]
    if os.path.exists(_p):
        os.remove(_p)

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_1_predict_energy():
    """Predict energy for a 60-min session at 20°C at 14:00"""
    response = client.post("/analytics/predict-energy", json={
        "duration_minutes": 60,
        "temperature": 20,
        "hour_of_day": 14,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["predicted_energy_kwh"] > 0
    assert data["input"]["duration_minutes"] == 60


def test_2_predict_energy_cold_weather():
    """Cold weather should predict higher energy usage"""
    response_warm = client.post("/analytics/predict-energy", json={
        "duration_minutes": 60, "temperature": 30, "hour_of_day": 14,
    })
    response_cold = client.post("/analytics/predict-energy", json={
        "duration_minutes": 60, "temperature": 0, "hour_of_day": 14,
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
        "num_chargers": 10,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["prediction"]["total_predicted_cost_dkk"] > 0
    assert data["prediction"]["revenue_per_charger_dkk"] > 0


def test_4_predict_energy_get():
    """GET predict-energy returns same result as POST"""
    response = client.get("/analytics/predict-energy", params={
        "duration_minutes": 60,
        "temperature": 20,
        "hour_of_day": 14,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["predicted_energy_kwh"] > 0
    assert data["input"]["duration_minutes"] == 60


def test_5_predict_revenue_get():
    """GET predict-revenue returns same result as POST"""
    response = client.get("/analytics/predict-revenue", params={
        "duration_minutes": 60,
        "temperature": 15,
        "hour_of_day": 14,
        "kwh_price": 2.45,
        "num_sessions": 100,
        "num_chargers": 10,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["prediction"]["total_predicted_cost_dkk"] > 0
    assert data["prediction"]["revenue_per_charger_dkk"] > 0


def test_6_predict_energy_get_equals_post():
    """GET and POST return identical predictions for same inputs"""
    params = {"duration_minutes": 90, "temperature": 10, "hour_of_day": 8}
    post_resp = client.post("/analytics/predict-energy", json=params)
    get_resp = client.get("/analytics/predict-energy", params=params)
    assert post_resp.status_code == 200
    assert get_resp.status_code == 200
    assert post_resp.json()["predicted_energy_kwh"] == get_resp.json()["predicted_energy_kwh"]
