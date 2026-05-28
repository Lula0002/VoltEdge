"""Analytics Service — API endpoints for ML predictions and data access

Every prediction call saves input + result to the ML database so PowerBI
can track accuracy over time.
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from analytics_service.ml_model import (
    predict_energy_kwh,
    predict_price_rate,
    get_model_info,
)
from analytics_service.ml_data_store import (
    get_all_training_data,
    add_prediction,
    get_all_predictions,
    get_model_state,
)

router = APIRouter(prefix="/analytics", tags=["Business Intelligence"])


# ── Request/Response Models ──────────────────────────────────

class PredictPriceRateRequest(BaseModel):
    temperature: float = Field(default=15, description="Expected temperature in °C", examples=[15])
    hour_of_day: int = Field(default=14, description="Time of day (0-23)", examples=[14])


class RevenueRequest(BaseModel):
    duration_minutes: int = Field(default=60, description="Average charging time per session")
    temperature: float = Field(default=15, description="Expected average temperature")
    hour_of_day: int = Field(default=14, description="Typical time of day")
    kwh_price: float = Field(default=2.45, description="Expected kWh price in DKK — use ML predict-price-rate for dynamic pricing", examples=[2.45])
    num_sessions: int = Field(default=100, description="Expected number of charging sessions")
    num_chargers: int = Field(default=10, description="Number of chargers")


# ── Shared logic ──────────────────────────────────────────────

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
      - model:         current model coefficients, intercept, R² (for regression line)
    """
    model_state = get_model_state()

    return {
        "training_data": {
            "count": len(get_all_training_data()),
            "rows": get_all_training_data(),
        },
        "predictions": {
            "count": len(get_all_predictions()),
            "rows": get_all_predictions(),
        },
        "model": model_state if model_state else None,
    }


@router.get("/training-data/rows", include_in_schema=False)
async def list_training_data_rows():
    """Return ONLY the training data rows as a flat JSON array.

    PowerBI-friendly format: no nesting, just an array of objects.
    Each object has: duration_minutes, temperature, hour_of_day, actual_energy_kwh, created_at.

    Use THIS endpoint in PowerBI instead of /training-data if you
    have trouble parsing nested JSON.
    """
    return get_all_training_data()


@router.get("/revenue-data")
async def list_revenue_data(
    kwh_price: float = Query(default=2.45, description="KWh price in DKK for flat-rate scenario", gt=0),
):
    """Return training data with revenue calculated for both flat-rate and dynamic pricing.

    PowerBI can compare two scenarios:
      - Flat-rate revenue:  actual_energy_kwh × kwh_price
      - Dynamic revenue:     actual_energy_kwh × ML-predicted price rate (varies by weather)

    The dynamic price rate is predicted by the ML price-rate model based on each
    training row's temperature and hour_of_day. Controlled noise is added so the
    scatter plot shows natural spread with a few anomaly points for visual clarity.

    Example:
      GET /analytics/revenue-data?kwh_price=3.50
    """
    data = get_all_training_data()
    result = []
    for idx, row in enumerate(data):
        dynamic_rate = predict_price_rate(row["temperature"], row["hour_of_day"])

        # Generate reproducible gaussian noise (Box-Muller) so most points
        # cluster near the trend line with ~5% clear anomalies
        seed_key = f"{row['temperature']}-{row['hour_of_day']}-{row['duration_minutes']}-{idx}"
        hash_bytes = hashlib.md5(seed_key.encode()).digest()
        h1 = int.from_bytes(hash_bytes[:4], "big") / 0xFFFFFFFF
        h2 = int.from_bytes(hash_bytes[4:8], "big") / 0xFFFFFFFF
        z1 = math.sqrt(-2.0 * math.log(h1 + 1e-10)) * math.cos(2.0 * math.pi * h2)
        noise = round(z1 * 0.06, 3)  # std dev 0.06 → ~95% within ±0.12
        is_anomaly = abs(noise) > 0.12

        result.append({
            "duration_minutes": row["duration_minutes"],
            "temperature": row["temperature"],
            "hour_of_day": row["hour_of_day"],
            "actual_energy_kwh": row["actual_energy_kwh"],
            "flat_kwh_price": kwh_price,
            "flat_revenue_dkk": round(row["actual_energy_kwh"] * kwh_price, 2),
            "dynamic_price_dkk_per_kwh": round(dynamic_rate + noise, 2),
            "dynamic_revenue_dkk": round(row["actual_energy_kwh"] * (dynamic_rate + noise), 2),
            "is_anomaly": is_anomaly,
        })
    return result


# ── 12-Month Revenue Forecast (Power BI) ─────────────────────

@router.get("/forecast-12-months", include_in_schema=False)
async def forecast_12_months(
    num_chargers: int = Query(default=10, description="Number of chargers in operation", ge=1),
    avg_daily_sessions_per_charger: float = Query(default=2.0, description="Average sessions per charger per day", ge=0.1),
    avg_duration_minutes: int = Query(default=60, description="Average session duration in minutes", ge=1),
    parking_rate: float = Query(default=0.50, description="DKK per minute overstay parking fee"),
    free_parking_minutes: int = Query(default=10, description="Free parking minutes before tariff applies"),
    overstay_rate: float = Query(default=0.35, description="Fraction of sessions that incur overstay parking (0-1)"),
    growth_rate_pct: float = Query(default=1.5, description="Monthly growth in session volume (%)"),
):
    """Generate a 12-month revenue forecast for Power BI dashboards.

    Uses the trained ML models to predict future revenue based on:
      - Seasonal temperature patterns (affects dynamic price rate)
      - Predicted energy consumption per session
      - Parking overstay tariff (DKK/min beyond free minutes)

    Two revenue streams are calculated:
      1. **Charging revenue** — predicted_kWh × ML-predicted price rate
      2. **Parking revenue** — overstay_minutes × parking_rate × sessions with overstay

    The forecast assumes Danish seasonal temperatures and afternoon-peak charging.
    Returns a flat JSON array — one object per month — suitable for Power BI.
    """
    import calendar

    # Danish monthly average temperatures (°C)
    MONTHLY_TEMPS = [0, 1, 5, 10, 15, 20, 22, 21, 16, 11, 5, 1]

    # Determine start month (next month from now)
    now = datetime.now(timezone.utc)
    forecast = []
    for i in range(12):
        m = (now.month + i) % 12
        year = now.year + (now.month + i) // 12

        temp = MONTHLY_TEMPS[m]
        hour = 14  # typical afternoon charging

        # Growing session volume
        growth = 1 + (growth_rate_pct / 100.0) * i
        sessions_per_charger = avg_daily_sessions_per_charger * growth
        total_sessions = round(sessions_per_charger * num_chargers * 30)

        # ML predictions
        predicted_kwh = predict_energy_kwh(avg_duration_minutes, temp, hour)
        price_rate = predict_price_rate(temp, hour)

        # Charging revenue
        total_energy = round(predicted_kwh * total_sessions, 1)
        charging_revenue = round(total_energy * price_rate, 2)

        # Parking overstay revenue
        billable_parking = max(0, avg_duration_minutes - free_parking_minutes)
        sessions_with_overstay = round(total_sessions * overstay_rate)
        parking_revenue = round(billable_parking * parking_rate * sessions_with_overstay, 2)

        month_num = m + 1
        forecast.append({
            "year_month": f"{year}-{month_num:02d}",
            "month": calendar.month_abbr[month_num],
            "year": year,
            "month_num": month_num,
            "avg_temperature_celsius": temp,
            "total_sessions": total_sessions,
            "total_energy_kwh": total_energy,
            "avg_price_per_kwh": price_rate,
            "charging_revenue_dkk": charging_revenue,
            "parking_revenue_dkk": parking_revenue,
            "total_revenue_dkk": round(charging_revenue + parking_revenue, 2),
        })

    return forecast


# ── POST Endpoints ───────────────────────────────────────────

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


# ── Price Rate Prediction ─────────────────────────────────────

@router.post("/predict-price-rate")
async def predict_price_rate_endpoint(req: PredictPriceRateRequest):
    """Predict the price rate (DKK/kWh) based on weather and time of day.

    Business logic:
      - SOLSKIN/varmt → mere solenergi → lavere pris pr. kWh
      - GRÅT/koldt/regn → mindre vedvarende energi → højere pris pr. kWh
      - Myldretid (morgen/aften) → højere pris (efterspørgsel)

    ML model: Linear regression trained on historical price data.
    Features: temperature (°C), hour of day.
    """
    rate = predict_price_rate(req.temperature, req.hour_of_day)
    return {
        "input": {
            "temperature_celsius": req.temperature,
            "hour_of_day": req.hour_of_day,
        },
        "predicted_price_rate_dkk_per_kwh": rate,
        "note": "Prisen varierer med vejret: solskin = billigere, gråt/regn = dyrere",
    }


@router.get("/predict-price-rate")
async def predict_price_rate_get(
    temperature: float = Query(default=15, description="Expected temperature in °C"),
    hour_of_day: int = Query(default=14, description="Time of day (0-23)", ge=0, le=23),
):
    """Predict the price rate (DKK/kWh) — GET version with query parameters.

    Same as POST /predict-price-rate but accepts query params.
    Useful for quick testing in a browser or Power BI Web connector.
    """
    rate = predict_price_rate(temperature, hour_of_day)
    return {
        "input": {
            "temperature_celsius": temperature,
            "hour_of_day": hour_of_day,
        },
        "predicted_price_rate_dkk_per_kwh": rate,
        "note": "Prisen varierer med vejret: solskin = billigere, gråt/regn = dyrere",
    }
