"""Analytics Service — API endpoints for ML predictions and data access

Every prediction call saves input + result to the ML database so PowerBI
can track accuracy over time.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from analytics_service.ml_model import (
    predict_energy_kwh,
    get_model_info,
)
from analytics_service.ml_data_store import (
    get_all_training_data,
    add_prediction,
    get_all_predictions,
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


# ── Shared logic ──────────────────────────────────────────────

def _build_energy_response(duration_minutes: int, temperature: float, hour_of_day: int):
    """Run prediction, persist it, and build the response dict."""
    model_info = get_model_info()
    predicted_kwh = round(predict_energy_kwh(duration_minutes, temperature, hour_of_day), 2)

    # Save every prediction to the database
    add_prediction(
        duration_minutes=duration_minutes,
        temperature=temperature,
        hour_of_day=hour_of_day,
        predicted_kwh=predicted_kwh,
        model_version=model_info["model_version"],
    )

    return {
        "input": {
            "duration_minutes": duration_minutes,
            "temperature_celsius": temperature,
            "hour_of_day": hour_of_day,
        },
        "predicted_energy_kwh": predicted_kwh,
        "model": {
            "type": "LinearRegression",
            "version": model_info["model_version"],
            "training_count": model_info["training_count"],
        },
    }


def _build_revenue_response(duration_minutes: int, temperature: float, hour_of_day: int,
                            kwh_price: float, num_sessions: int, num_chargers: int):
    """Run revenue prediction, persist the energy prediction, and build response."""
    model_info = get_model_info()
    predicted_kwh_per_session = round(predict_energy_kwh(duration_minutes, temperature, hour_of_day), 2)

    # Save the underlying energy prediction to the database
    add_prediction(
        duration_minutes=duration_minutes,
        temperature=temperature,
        hour_of_day=hour_of_day,
        predicted_kwh=predicted_kwh_per_session,
        model_version=model_info["model_version"],
    )

    total_kwh = predicted_kwh_per_session * num_sessions
    total_cost_dkk = round(total_kwh * kwh_price, 2)
    revenue_per_charger = round(total_cost_dkk / num_chargers, 2)

    return {
        "input": {
            "duration_minutes": duration_minutes,
            "temperature_celsius": temperature,
            "kwh_price_dkk": kwh_price,
            "num_sessions": num_sessions,
            "num_chargers": num_chargers,
        },
        "prediction": {
            "predicted_kwh_per_session": predicted_kwh_per_session,
            "total_predicted_kwh": round(total_kwh, 2),
            "total_predicted_cost_dkk": total_cost_dkk,
            "revenue_per_charger_dkk": revenue_per_charger,
            "avg_revenue_per_session_dkk": round(total_cost_dkk / num_sessions, 2),
        },
        "model": {
            "type": "LinearRegression",
            "version": model_info["model_version"],
            "training_count": model_info["training_count"],
        },
    }


# ── Training Data (read-only, for PowerBI) ───────────────────

@router.get("/training-data")
async def list_training_data():
    """Return ALL data from the ML database — both training data and predictions.

    PowerBI can consume this endpoint via Power Query (Web connector).

    Returns:
      - training_data: rows used to train the model (actual consumption)
      - predictions:   every prediction made (for accuracy tracking)
    """
    return {
        "training_data": {
            "count": len(get_all_training_data()),
            "rows": get_all_training_data(),
        },
        "predictions": {
            "count": len(get_all_predictions()),
            "rows": get_all_predictions(),
        },
    }


# ── POST Endpoints ───────────────────────────────────────────

@router.post("/predict-energy")
async def predict_energy(req: PredictEnergyRequest):
    """Predict future energy consumption (kWh) based on duration, weather and time of day.

    ML model: Linear regression trained on bootstrapped + accumulated real data.
    Features: duration (min), temperature (°C), hour of day.

    Every prediction is saved to the database so PowerBI can track accuracy over time.
    """
    return _build_energy_response(req.duration_minutes, req.temperature, req.hour_of_day)


@router.post("/predict-revenue")
async def predict_revenue(req: RevenueRequest):
    """Predict future revenue for a customer (e.g. Copenhagen Municipality).

    The ML model first predicts energy consumption based on duration, weather and time of day.
    Then calculates:
      - Expected costs (kWh x kWh price)
      - Expected revenue across all chargers and sessions

    Every prediction is saved to the database so PowerBI can track accuracy over time.
    """
    return _build_revenue_response(
        req.duration_minutes, req.temperature, req.hour_of_day,
        req.kwh_price, req.num_sessions, req.num_chargers,
    )


# ── GET Endpoints (query params for easy browser/PowerBI use) ─

@router.get("/predict-energy")
async def predict_energy_get(
    duration_minutes: int = Query(default=60, description="Expected charging time in minutes", ge=1),
    temperature: float = Query(default=15, description="Expected temperature in °C"),
    hour_of_day: int = Query(default=14, description="Time of day (0-23)", ge=0, le=23),
):
    """Predict future energy consumption (kWh) — GET version with query parameters.

    Same as POST /predict-energy but accepts query params instead of a request body.
    Useful for quick testing in a browser or Power BI Web connector.

    Every prediction is saved to the database so PowerBI can track accuracy over time.
    """
    return _build_energy_response(duration_minutes, temperature, hour_of_day)


@router.get("/predict-revenue")
async def predict_revenue_get(
    duration_minutes: int = Query(default=60, description="Average charging time per session", ge=1),
    temperature: float = Query(default=15, description="Expected average temperature"),
    hour_of_day: int = Query(default=14, description="Typical time of day", ge=0, le=23),
    kwh_price: float = Query(default=2.45, description="Expected kWh price in DKK", gt=0),
    num_sessions: int = Query(default=100, description="Expected number of charging sessions", ge=1),
    num_chargers: int = Query(default=10, description="Number of chargers", ge=1),
):
    """Predict future revenue — GET version with query parameters.

    Same as POST /predict-revenue but accepts query params instead of a request body.
    Useful for quick testing in a browser or Power BI Web connector.

    Every prediction is saved to the database so PowerBI can track accuracy over time.
    """
    return _build_revenue_response(
        duration_minutes, temperature, hour_of_day,
        kwh_price, num_sessions, num_chargers,
    )
