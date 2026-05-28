"""Tests for Analytics Service — ML energy & revenue prediction + data persistence"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Use a temporary database for tests (MUST be before importing main)
os.environ["VOLTEDGE_DB_PATH"] = os.path.join(tempfile.gettempdir(), "voltedge_test.db")
os.environ["VOLTEDGE_ML_DB_PATH"] = os.path.join(tempfile.gettempdir(), "ml_training_test.db")

# Clean up any old test DBs BEFORE importing the app
for _key in ["VOLTEDGE_DB_PATH", "VOLTEDGE_ML_DB_PATH"]:
    _p = os.environ[_key]
    if os.path.exists(_p):
        os.remove(_p)

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


# ══════════════════════════════════════════════════════════════
# Existing prediction tests (unchanged, should still pass)
# ══════════════════════════════════════════════════════════════

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
    assert "prediction_id" in data
    assert "model" in data
    assert data["model"]["type"] == "LinearRegression"


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
    assert "model" in data


# ══════════════════════════════════════════════════════════════
# New: Data persistence tests
# ══════════════════════════════════════════════════════════════

def test_4_get_training_data_empty_initially():
    """Initially, training data should be empty (bootstrap is in-memory, not DB)."""
    response = client.get("/analytics/training-data")
    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert data["count"] == 0  # Bootstrap data is in-memory, not in DB


def test_5_add_training_data():
    """POST /analytics/training-data should persist and retrain."""
    response = client.post("/analytics/training-data", json={
        "duration_minutes": 120,
        "temperature": 22,
        "hour_of_day": 15,
        "actual_energy_kwh": 30.0,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Training data added and model retrained"
    assert data["retrained_model"]["training_count"] > 0
    assert "v0.0." in data["retrained_model"]["model_version"]


def test_6_get_training_data_after_add():
    """After adding data, GET should return it."""
    response = client.get("/analytics/training-data")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 1
    # The first entry should match what we added
    assert data["data"][0]["duration_minutes"] == 120


def test_7_get_model_parameters():
    """GET /analytics/model-parameters should return regression coefficients."""
    response = client.get("/analytics/model-parameters")
    assert response.status_code == 200
    data = response.json()
    assert data["model_type"] == "LinearRegression"
    assert len(data["coefficients"]) == 3  # one per feature
    assert data["intercept"] is not None
    assert data["r2_score"] is not None


def test_8_predictions_are_stored():
    """Predictions made via POST should appear in GET /analytics/predictions."""
    # Make a prediction first
    client.post("/analytics/predict-energy", json={
        "duration_minutes": 45, "temperature": 18, "hour_of_day": 12,
    })

    response = client.get("/analytics/predictions")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 1
    # Verify structure
    entry = data["data"][0]
    assert "predicted_kwh" in entry
    assert "model_version" in entry
    assert "created_at" in entry


def test_9_record_actual_retrains():
    """POST /analytics/record-actual should update prediction and retrain."""
    # First make a prediction
    pred_resp = client.post("/analytics/predict-energy", json={
        "duration_minutes": 30, "temperature": 25, "hour_of_day": 10,
    })
    prediction_id = pred_resp.json()["prediction_id"]

    # Record actual
    response = client.post("/analytics/record-actual", json={
        "prediction_id": prediction_id,
        "actual_energy_kwh": 7.0,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Actual energy recorded and model retrained"
    assert data["retrained_model"]["training_count"] > 1

    # Verify prediction now has actual
    preds_resp = client.get("/analytics/predictions?only_with_actual=true")
    assert preds_resp.status_code == 200
    preds = preds_resp.json()
    assert preds["count"] >= 1


def test_10_get_metrics():
    """GET /analytics/metrics should return model performance KPIs."""
    response = client.get("/analytics/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["model_version"] is not None
    assert data["training_data_count"] > 0
    assert data["predictions_made"] > 0


def test_11_predict_energy_includes_model_info():
    """Response should now include model version and coefficients."""
    response = client.post("/analytics/predict-energy", json={
        "duration_minutes": 60,
        "temperature": 20,
        "hour_of_day": 14,
    })
    data = response.json()
    assert data["model"]["version"] is not None
    assert len(data["model"]["coefficients"]) == 3
    assert data["model"]["training_count"] > 0
