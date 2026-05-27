"""Analytics Service — Linear regression for price prediction"""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sklearn.linear_model import LinearRegression
import numpy as np

router = APIRouter(prefix="/analytics", tags=["analytics"])


class PredictRequest(BaseModel):
    duration_minutes: int = Field(examples=[60])


class PredictPriceRequest(BaseModel):
    energy_kwh: float = Field(examples=[25.5])
    duration_minutes: int = Field(examples=[60])


# Simulated training data: duration_minutes vs energy_delivered (kWh)
TRAIN_DURATIONS = np.array([10, 20, 30, 45, 60, 90, 120, 180, 240, 300]).reshape(-1, 1)
TRAIN_ENERGY = np.array([2.0, 4.5, 7.0, 11.0, 15.0, 22.0, 30.0, 45.0, 60.0, 75.0])

model = LinearRegression()
model.fit(TRAIN_DURATIONS, TRAIN_ENERGY)


@router.get("/health")
async def health():
    """Health check for Analytics Service."""
    return {"status": "healthy", "service": "analytics-service"}


@router.post("/predict")
async def predict_energy(req: PredictRequest):
    """Predict expected energy (kWh) based on charging duration (minutes)."""
    duration = np.array([[req.duration_minutes]])
    predicted = float(model.predict(duration)[0])
    return {
        "duration_minutes": req.duration_minutes,
        "predicted_energy_kwh": round(predicted, 2),
    }


@router.post("/predict-price")
async def predict_price(req: PredictPriceRequest):
    """Predict total price based on energy consumption and duration.

    Uses tariff rates: 2.45 DKK/kWh + 0.50 DKK/min after 10 free minutes.
    """
    energy_cost = round(req.energy_kwh * 2.45, 2)
    billable_parking = max(0, req.duration_minutes - 10)
    parking_cost = round(billable_parking * 0.50, 2)
    total = round(energy_cost + parking_cost, 2)

    return {
        "energy_kwh": req.energy_kwh,
        "duration_minutes": req.duration_minutes,
        "predicted_energy_cost": energy_cost,
        "predicted_parking_cost": parking_cost,
        "predicted_total_dkk": total,
    }
