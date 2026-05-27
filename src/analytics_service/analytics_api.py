"""Analytics Service — API endpoints for ML predictions

ML model is isolated in ml_model.py, so the API layer only handles
request/response and calls to the model.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from analytics_service.ml_model import predict_energy_kwh

router = APIRouter(prefix="/analytics", tags=["analytics (ml) - external capability"])


# ── Request/Response modeller ────────────────────────────────

class PredictEnergyRequest(BaseModel):
    duration_minutes: int = Field(default=60, description="Expected charging time in minutes", examples=[60])
    temperature: float = Field(default=15, description="Forventet temperatur i °C", examples=[15])
    hour_of_day: int = Field(default=14, description="Time of day (0-23)", examples=[14])


class RevenueRequest(BaseModel):
    duration_minutes: int = Field(default=60, description="Average charging time per session")
    temperature: float = Field(default=15, description="Forventet gennemsnitstemperatur")
    hour_of_day: int = Field(default=14, description="Typical time of day")
    kwh_price: float = Field(default=2.45, description="Forventet kWh-pris i DKK", examples=[2.45])
    num_sessions: int = Field(default=100, description="Antal forventede ladesessioner")
    num_chargers: int = Field(default=10, description="Number of chargers")


# ── Endpoints ────────────────────────────────────────────────

@router.get("/health")
async def health():
    """Sundhedstjek for Analytics Service."""
    return {"status": "healthy", "service": "analytics-service"}


@router.post("/predict-energy")
async def predict_energy(req: PredictEnergyRequest):
    """Predict future energy consumption (kWh) based on duration, weather and time of day.

    ML model: Linear regression trained on simulated historical data.
    Features: duration (min), temperature (°C), hour of day.
    """
    predicted_kwh = predict_energy_kwh(req.duration_minutes, req.temperature, req.hour_of_day)

    return {
        "input": {
            "duration_minutes": req.duration_minutes,
            "temperature_celsius": req.temperature,
            "hour_of_day": req.hour_of_day,
        },
        "predicted_energy_kwh": round(predicted_kwh, 2),
        "model": "LinearRegression",
        "note": "Prediction based on simulated training data"
    }


@router.post("/predict-revenue")
async def predict_revenue(req: RevenueRequest):
    """Predict future revenue for a customer (e.g. Copenhagen Municipality).

    The ML model first predicts energy consumption based on duration, weather and time of day.
    Then calculates:
      - Expected costs (kWh x kWh price)
      - Expected revenue across all chargers and sessions
    """
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
        "model": "LinearRegression",
        "note": "Prediction based on simulated data. With real historical data the model can be improved."
    }
