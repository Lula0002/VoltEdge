"""Analytics Service — API endpoints for ML predictions and data access

ML model is isolated in ml_model.py, so the API layer only handles
request/response and calls to the model.

GET endpoints return data in a PowerBI-friendly JSON format so the
business can visualise the linear regression and track model accuracy.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from analytics_service.ml_model import (
    predict_energy_kwh,
    add_actual_and_retrain,
    get_model_info,
)
from analytics_service.ml_data_store import (
    get_all_training_data,
    get_all_predictions,
    get_predictions_with_actual,
    add_prediction,
    record_actual,
    get_model_state,
)

router = APIRouter(prefix="/analytics", tags=["Business Intelligence"])


# ── Request/Response Models ──────────────────────────────────

class PredictEnergyRequest(BaseModel):
    duration_minutes: int = Field(default=60, description="Expected charging time in minutes", examples=[60])
    temperature: float = Field(default=15, description="Expected temperature in °C", examples=[15])
    hour_of_day: int = Field(default=14, description="Time of day (0-23)", examples=[14])


class RevenueRequest(BaseModel):
    duration_minutes: int = Field(default=60, description="Average charging time per session")
    temperature: float = Field(default=15, description="Expected average temperature")
    hour_of_day: int = Field(default=14, description="Typical time of day")
    kwh_price: float = Field(default=2.45, description="Expected kWh price in DKK", examples=[2.45])
    num_sessions: int = Field(default=100, description="Expected number of charging sessions")
    num_chargers: int = Field(default=10, description="Number of chargers")


class RecordActualRequest(BaseModel):
    prediction_id: int = Field(description="ID of the prediction to associate with")
    actual_energy_kwh: float = Field(description="The actual energy consumed (kWh)")


class AddTrainingDataRequest(BaseModel):
    duration_minutes: int = Field(description="Duration in minutes", examples=[60])
    temperature: float = Field(description="Temperature in °C", examples=[20])
    hour_of_day: int = Field(description="Hour of day (0-23)", examples=[14])
    actual_energy_kwh: float = Field(description="Actual energy consumed", examples=[14.8])


# ── Prediction Endpoints ──────────────────────────────────────

@router.post("/predict-energy")
async def predict_energy(req: PredictEnergyRequest):
    """Predict future energy consumption (kWh) based on duration, weather and time of day.

    ML model: Linear regression trained on bootstrapped + accumulated real data.
    Features: duration (min), temperature (°C), hour of day.

    Every prediction is stored so PowerBI can track accuracy over time.
    """
    model_info = get_model_info()
    predicted_kwh = predict_energy_kwh(req.duration_minutes, req.temperature, req.hour_of_day)

    # Store the prediction for PowerBI analysis
    pred_id = add_prediction(
        duration_minutes=req.duration_minutes,
        temperature=req.temperature,
        hour_of_day=req.hour_of_day,
        predicted_kwh=round(predicted_kwh, 2),
        model_version=model_info["model_version"],
    )

    return {
        "prediction_id": pred_id,
        "input": {
            "duration_minutes": req.duration_minutes,
            "temperature_celsius": req.temperature,
            "hour_of_day": req.hour_of_day,
        },
        "predicted_energy_kwh": round(predicted_kwh, 2),
        "model": {
            "type": "LinearRegression",
            "version": model_info["model_version"],
            "coefficients": model_info["coefficients"],
            "intercept": model_info["intercept"],
            "training_count": model_info["training_count"],
        },
    }


@router.post("/predict-revenue")
async def predict_revenue(req: RevenueRequest):
    """Predict future revenue for a customer (e.g. Copenhagen Municipality).

    The ML model first predicts energy consumption based on duration, weather and time of day.
    Then calculates:
      - Expected costs (kWh x kWh price)
      - Expected revenue across all chargers and sessions
    """
    model_info = get_model_info()
    predicted_kwh_per_session = predict_energy_kwh(req.duration_minutes, req.temperature, req.hour_of_day)

    # Price calculation
    total_kwh = predicted_kwh_per_session * req.num_sessions
    total_cost_dkk = round(total_kwh * req.kwh_price, 2)

    # Revenue per charger
    revenue_per_charger = round(total_cost_dkk / req.num_chargers, 2)

    return {
        "input": {
            "duration_minutes": req.duration_minutes,
            "temperature_celsius": req.temperature,
            "kwh_price_dkk": req.kwh_price,
            "num_sessions": req.num_sessions,
            "num_chargers": req.num_chargers,
        },
        "prediction": {
            "predicted_kwh_per_session": round(predicted_kwh_per_session, 2),
            "total_predicted_kwh": round(total_kwh, 2),
            "total_predicted_cost_dkk": total_cost_dkk,
            "revenue_per_charger_dkk": revenue_per_charger,
            "avg_revenue_per_session_dkk": round(total_cost_dkk / req.num_sessions, 2),
        },
        "model": {
            "type": "LinearRegression",
            "version": model_info["model_version"],
            "training_count": model_info["training_count"],
        },
    }


# ── Record Actual (for model improvement) ─────────────────────

@router.post("/record-actual")
async def record_actual_endpoint(req: RecordActualRequest):
    """Record the actual energy consumed for a previous prediction.

    When you know the real result, call this so the model can:
      1. Track its accuracy over time
      2. Retrain with the new data point (improving future predictions)

    PowerBI can then visualise predicted vs actual to show the regression fit.
    """
    found = record_actual(req.prediction_id, req.actual_energy_kwh)
    if not found:
        raise HTTPException(status_code=404, detail=f"Prediction id {req.prediction_id} not found")

    # Trigger retrain with the new data
    # (We need the original prediction features to retrain)
    predictions = get_all_predictions()
    pred = next((p for p in predictions if p["id"] == req.prediction_id), None)
    if pred is None:
        raise HTTPException(status_code=404, detail="Prediction data not found")

    retrain_info = add_actual_and_retrain(
        duration_minutes=pred["duration_minutes"],
        temperature=pred["temperature"],
        hour_of_day=pred["hour_of_day"],
        actual_energy_kwh=req.actual_energy_kwh,
    )

    return {
        "message": "Actual energy recorded and model retrained",
        "prediction_id": req.prediction_id,
        "actual_energy_kwh": req.actual_energy_kwh,
        "retrained_model": retrain_info,
    }


# ── Add Raw Training Data ─────────────────────────────────────

@router.post("/training-data")
async def add_training_data_endpoint(req: AddTrainingDataRequest):
    """Manually add a training data point and retrain the model.

    Use this to feed historical data into the model for better predictions.
    The model retrains immediately with the new data point included.
    """
    retrain_info = add_actual_and_retrain(
        duration_minutes=req.duration_minutes,
        temperature=req.temperature,
        hour_of_day=req.hour_of_day,
        actual_energy_kwh=req.actual_energy_kwh,
    )

    return {
        "message": "Training data added and model retrained",
        "data_point": req.model_dump(),
        "retrained_model": retrain_info,
    }


# ── GET Endpoints (PowerBI-friendly) ──────────────────────────

@router.get("/training-data")
async def list_training_data():
    """Return ALL training data points.

    PowerBI can consume this endpoint directly via Power Query (Web connector)
    to show the scatter plot of actual energy consumption vs. duration/temperature.

    Returns an array of objects with:
      - duration_minutes, temperature, hour_of_day, actual_energy_kwh, created_at
    """
    data = get_all_training_data()
    return {
        "count": len(data),
        "data": data,
    }


@router.get("/predictions")
async def list_predictions(only_with_actual: bool = False):
    """Return ALL predictions made by the model.

    PowerBI can consume this to visualise:
      - Predicted vs actual energy (scatter plot + regression line)
      - Prediction error over time
      - Model accuracy metrics

    Parameters:
      - only_with_actual: if True, only return predictions where actual_kwh is recorded
    """
    if only_with_actual:
        data = get_predictions_with_actual()
    else:
        data = get_all_predictions()

    return {
        "count": len(data),
        "data": data,
    }


@router.get("/model-parameters")
async def model_parameters():
    """Return the current linear regression parameters.

    PowerBI can use this to draw the regression line:
      energy = intercept + slope[0]*duration + slope[1]*temperature + slope[2]*hour

    Returns:
      - coefficients: [duration_coef, temperature_coef, hour_coef]
      - intercept: the y-intercept
      - r2_score: how well the model fits (1.0 = perfect)
      - training_count: number of data points used
    """
    state = get_model_state()
    if state is None:
        return {
            "message": "Model not trained yet",
            "coefficients": None,
            "intercept": None,
        }

    return {
        "model_type": "LinearRegression",
        "coefficients": state["coefficients"],
        "intercept": state["intercept"],
        "r2_score": state["r2_score"],
        "training_count": state["training_count"],
        "trained_at": state["trained_at"],
    }


@router.get("/metrics")
async def model_metrics():
    """Return model accuracy and performance metrics.

    PowerBI can use this to show KPI cards:
      - R² score
      - Training data count
      - Model version
      - Predictions made
      - Average prediction error (%)
    """
    state = get_model_state()
    predictions = get_predictions_with_actual()

    if predictions:
        errors = [abs(p["error_pct"]) for p in predictions if p["error_pct"] is not None]
        avg_error_pct = round(sum(errors) / len(errors), 2) if errors else None
    else:
        avg_error_pct = None

    return {
        "model_version": get_model_info()["model_version"],
        "r2_score": state["r2_score"] if state else None,
        "training_data_count": state["training_count"] if state else 0,
        "predictions_made": len(get_all_predictions()),
        "predictions_with_actual": len(predictions),
        "average_absolute_error_pct": avg_error_pct,
    }
