"""Analytics Service — ML anomaly detection using linear regression"""

import math
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel
from sklearn.linear_model import LinearRegression
import numpy as np

router = APIRouter(prefix="/analytics", tags=["analytics"])


class PredictRequest(BaseModel):
    duration_minutes: int


class DetectRequest(BaseModel):
    session_id: str
    energy_delivered: float
    duration_minutes: int


class AnomalyResult(BaseModel):
    session_id: str
    energy_delivered: float
    expected_energy: float
    deviation_percent: float
    is_anomaly: bool
    message: str


# Simulated training data: duration_minutes vs energy_delivered (kWh)
# Based on typical 7-22 kW charging
TRAIN_DURATIONS = np.array([10, 20, 30, 45, 60, 90, 120, 180, 240, 300]).reshape(-1, 1)
TRAIN_ENERGY = np.array([2.0, 4.5, 7.0, 11.0, 15.0, 22.0, 30.0, 45.0, 60.0, 75.0])

model = LinearRegression()
model.fit(TRAIN_DURATIONS, TRAIN_ENERGY)


@router.get("/health")
async def health():
    return {"status": "healthy", "service": "analytics-service"}


@router.post("/predict")
async def predict_energy(req: PredictRequest):
    duration = np.array([[req.duration_minutes]])
    predicted = float(model.predict(duration)[0])
    return {
        "duration_minutes": req.duration_minutes,
        "predicted_energy_kwh": round(predicted, 2),
    }


@router.post("/detect", response_model=AnomalyResult)
async def detect_anomaly(req: DetectRequest):
    duration = np.array([[req.duration_minutes]])
    expected = float(model.predict(duration)[0])
    deviation = req.energy_delivered - expected
    deviation_pct = round((deviation / expected) * 100, 2)

    # Flag as anomaly if deviation > 40%
    is_anomaly = abs(deviation_pct) > 40.0

    if is_anomaly:
        message = (
            f"Anomaly detected: {req.energy_delivered} kWh vs {round(expected, 2)} kWh expected "
            f"({deviation_pct:+.2f}% deviation)"
        )
    else:
        message = f"Normal: {deviation_pct:+.2f}% deviation from expected"

    return AnomalyResult(
        session_id=req.session_id,
        energy_delivered=req.energy_delivered,
        expected_energy=round(expected, 2),
        deviation_percent=deviation_pct,
        is_anomaly=is_anomaly,
        message=message,
    )
