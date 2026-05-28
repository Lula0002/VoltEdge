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


def test_1_energy_same_regardless_of_weather():
    """Samme duration = samme kWh — vejr påvirker IKKE energimængden (kun prisen)"""
    # Brug predict-revenue som proxy: predicted_kwh_per_session skal være ens
    resp_sun = client.post("/analytics/predict-revenue", json={
        "duration_minutes": 60, "temperature": 30, "hour_of_day": 14,
        "kwh_price": 2.45, "num_sessions": 1, "num_chargers": 1,
    })
    resp_rain = client.post("/analytics/predict-revenue", json={
        "duration_minutes": 60, "temperature": 5, "hour_of_day": 14,
        "kwh_price": 2.45, "num_sessions": 1, "num_chargers": 1,
    })
    resp_cold = client.post("/analytics/predict-revenue", json={
        "duration_minutes": 60, "temperature": 0, "hour_of_day": 14,
        "kwh_price": 2.45, "num_sessions": 1, "num_chargers": 1,
    })

    assert resp_sun.status_code == 200
    assert resp_rain.status_code == 200
    assert resp_cold.status_code == 200

    kwh_sun = resp_sun.json()["prediction"]["predicted_kwh_per_session"]
    kwh_rain = resp_rain.json()["prediction"]["predicted_kwh_per_session"]
    kwh_cold = resp_cold.json()["prediction"]["predicted_kwh_per_session"]

    # Alle tre skal give SAMME kWh — kun varighed betyder noget
    assert kwh_sun == kwh_rain == kwh_cold, (
        f"Forventet samme kWh uanset vejr, fik: sol={kwh_sun}, regn={kwh_rain}, kold={kwh_cold}"
    )


def test_2_price_rate_varies_with_weather():
    """Prisen varierer: solskin/varmt = billigere, gråt/koldt = dyrere"""
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


def test_3_price_rate_peak_hours():
    """Myldretid = højere pris end nat"""
    resp_peak = client.post("/analytics/predict-price-rate", json={
        "temperature": 20, "hour_of_day": 8,
    })
    resp_night = client.post("/analytics/predict-price-rate", json={
        "temperature": 20, "hour_of_day": 22,
    })
    assert resp_peak.json()["predicted_price_rate_dkk_per_kwh"] > resp_night.json()["predicted_price_rate_dkk_per_kwh"]


def test_4_predict_price_rate_get():
    """GET predict-price-rate fungerer og returnerer samme som POST"""
    resp_post = client.post("/analytics/predict-price-rate", json={
        "temperature": 25, "hour_of_day": 12,
    })
    resp_get = client.get("/analytics/predict-price-rate", params={
        "temperature": 25, "hour_of_day": 12,
    })
    assert resp_post.status_code == 200
    assert resp_get.status_code == 200
    assert resp_post.json()["predicted_price_rate_dkk_per_kwh"] == resp_get.json()["predicted_price_rate_dkk_per_kwh"]


def test_5_predict_revenue():
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


def test_6_predict_revenue_get():
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


def test_7_predict_revenue_get_equals_post():
    """GET and POST predict-revenue return identical predictions for same inputs"""
    params = {
        "duration_minutes": 90,
        "temperature": 10,
        "hour_of_day": 8,
        "kwh_price": 3.00,
        "num_sessions": 50,
        "num_chargers": 5,
    }
    post_resp = client.post("/analytics/predict-revenue", json=params)
    get_resp = client.get("/analytics/predict-revenue", params=params)
    assert post_resp.status_code == 200
    assert get_resp.status_code == 200
    assert post_resp.json()["prediction"] == get_resp.json()["prediction"]


def test_8_revenue_data_dynamic_pricing():
    """Revenue-data endpoint inkluderer både flat-rate og dynamisk pris"""
    resp = client.get("/analytics/revenue-data", params={"kwh_price": 2.45})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0

    row = data[0]
    # Skal have flat-rate felter
    assert "flat_kwh_price" in row
    assert "flat_revenue_dkk" in row
    # Skal have dynamisk prisfastsættelse
    assert "dynamic_price_dkk_per_kwh" in row
    assert "dynamic_revenue_dkk" in row
    # Dynamisk pris skal være en fornuftig positiv værdi
    assert row["dynamic_price_dkk_per_kwh"] > 0
