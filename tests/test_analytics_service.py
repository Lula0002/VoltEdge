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


def test_2_energy_same_regardless_of_weather():
    """Same duration = same energy prediction — weather does NOT affect energy amount"""
    response_sun = client.post("/analytics/predict-energy", json={
        "duration_minutes": 60, "temperature": 30, "hour_of_day": 14,
    })
    response_rain = client.post("/analytics/predict-energy", json={
        "duration_minutes": 60, "temperature": 5, "hour_of_day": 14,
    })
    response_cold = client.post("/analytics/predict-energy", json={
        "duration_minutes": 60, "temperature": 0, "hour_of_day": 14,
    })
    # All three should give the SAME energy — duration is what matters
    assert response_sun.json()["predicted_energy_kwh"] == response_rain.json()["predicted_energy_kwh"]
    assert response_rain.json()["predicted_energy_kwh"] == response_cold.json()["predicted_energy_kwh"]


def test_3_price_rate_varies_with_weather():
    """Price rate varies: sunny/warm = cheaper, cold/rain = more expensive"""
    resp_sun = client.post("/analytics/predict-price-rate", json={
        "temperature": 30, "hour_of_day": 14,
    })
    resp_rain = client.post("/analytics/predict-price-rate", json={
        "temperature": 5, "hour_of_day": 14,
    })
    assert resp_sun.status_code == 200
    assert resp_rain.status_code == 200
    # Solskin = billigere end gråt/regn
    assert resp_sun.json()["predicted_price_rate_dkk_per_kwh"] < resp_rain.json()["predicted_price_rate_dkk_per_kwh"]


def test_4_price_rate_peak_hours():
    """Myldretid = højere pris end nat"""
    resp_peak = client.post("/analytics/predict-price-rate", json={
        "temperature": 20, "hour_of_day": 8,
    })
    resp_night = client.post("/analytics/predict-price-rate", json={
        "temperature": 20, "hour_of_day": 22,
    })
    assert resp_peak.json()["predicted_price_rate_dkk_per_kwh"] > resp_night.json()["predicted_price_rate_dkk_per_kwh"]


def test_6_predict_energy_get():
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


def test_7_predict_price_rate_get():
    """GET predict-price-rate returns same result as POST"""
    resp_post = client.post("/analytics/predict-price-rate", json={
        "temperature": 25, "hour_of_day": 12,
    })
    resp_get = client.get("/analytics/predict-price-rate", params={
        "temperature": 25, "hour_of_day": 12,
    })
    assert resp_post.status_code == 200
    assert resp_get.status_code == 200
    assert resp_post.json()["predicted_price_rate_dkk_per_kwh"] == resp_get.json()["predicted_price_rate_dkk_per_kwh"]


def test_8_predict_revenue():
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


def test_9_predict_revenue_get():
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


def test_10_predict_energy_get_equals_post():
    """GET and POST return identical predictions for same inputs"""
    params = {"duration_minutes": 90, "temperature": 10, "hour_of_day": 8}
    post_resp = client.post("/analytics/predict-energy", json=params)
    get_resp = client.get("/analytics/predict-energy", params=params)
    assert post_resp.status_code == 200
    assert get_resp.status_code == 200
    assert post_resp.json()["predicted_energy_kwh"] == get_resp.json()["predicted_energy_kwh"]


def test_11_predict_price_rate_get_equals_post():
    """GET and POST predict-price-rate return identical results for same inputs"""
    params = {"temperature": 10, "hour_of_day": 8}
    post_resp = client.post("/analytics/predict-price-rate", json=params)
    get_resp = client.get("/analytics/predict-price-rate", params=params)
    assert post_resp.status_code == 200
    assert get_resp.status_code == 200
    assert post_resp.json()["predicted_price_rate_dkk_per_kwh"] == get_resp.json()["predicted_price_rate_dkk_per_kwh"]
