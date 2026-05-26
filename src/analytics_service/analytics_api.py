"""Analytics Service — ML anomaly detection using linear regression"""

import math
from datetime import datetime, timezone

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


class DetectRequest(BaseModel):
    session_id: str = Field(examples=["test-1"])
    energy_delivered: float = Field(examples=[2.0])
    duration_minutes: int = Field(examples=[60])


class DetectInvoiceRequest(BaseModel):
    session_id: str = Field(examples=["inv-001"])
    invoice_amount: float = Field(examples=[100.00])
    energy_kwh: float = Field(examples=[25.5])
    duration_minutes: int = Field(examples=[60])


class AnomalyResult(BaseModel):
    session_id: str
    energy_delivered: float
    expected_energy: float
    deviation_percent: float
    is_anomaly: bool
    message: str


class InvoiceAnomalyResult(BaseModel):
    session_id: str
    invoice_amount: float
    expected_amount: float
    deviation_percent: float
    is_anomaly: bool
    message: str


# Simulated training data: duration_minutes vs energy_delivered (kWh)
# Based on typical 7-22 kW charging
TRAIN_DURATIONS = np.array([10, 20, 30, 45, 60, 90, 120, 180, 240, 300]).reshape(-1, 1)
TRAIN_ENERGY = np.array([2.0, 4.5, 7.0, 11.0, 15.0, 22.0, 30.0, 45.0, 60.0, 75.0])

model = LinearRegression()
model.fit(TRAIN_DURATIONS, TRAIN_ENERGY)



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


# Tariff rates (same as billing service)
ENERGY_RATE = 2.45  # DKK per kWh
PARKING_RATE = 0.50  # DKK per minute after 10 free minutes
PARKING_FREE_MINUTES = 10


@router.post("/predict-price")
async def predict_price(req: PredictPriceRequest):
    """Predict total price based on energy consumption and duration.

    Uses the same tariff rates as the billing service:
    - 2.45 DKK/kWh for energy
    - 0.50 DKK/min for parking after 10 free minutes
    """
    energy_cost = round(req.energy_kwh * ENERGY_RATE, 2)
    billable_parking = max(0, req.duration_minutes - PARKING_FREE_MINUTES)
    parking_cost = round(billable_parking * PARKING_RATE, 2)
    total = round(energy_cost + parking_cost, 2)

    return {
        "energy_kwh": req.energy_kwh,
        "duration_minutes": req.duration_minutes,
        "predicted_energy_cost": energy_cost,
        "predicted_parking_cost": parking_cost,
        "predicted_total_dkk": total,
        "breakdown": {
            "energy_rate": ENERGY_RATE,
            "parking_rate": PARKING_RATE,
            "billable_parking_minutes": billable_parking,
        },
    }


@router.post("/detect-invoice", response_model=InvoiceAnomalyResult)
async def detect_invoice_anomaly(req: DetectInvoiceRequest):
    """Detect anomalies on invoice amounts.

    Compares the actual invoice amount against the expected amount
    calculated from the tariff rates. Flags if deviation > 30%.
    """
    energy_cost = req.energy_kwh * ENERGY_RATE
    billable_parking = max(0, req.duration_minutes - PARKING_FREE_MINUTES)
    parking_cost = billable_parking * PARKING_RATE
    expected_amount = round(energy_cost + parking_cost, 2)

    deviation = req.invoice_amount - expected_amount
    if expected_amount > 0:
        deviation_pct = round((deviation / expected_amount) * 100, 2)
    else:
        deviation_pct = 0.0

    # Flag as anomaly if deviation > 30%
    is_anomaly = abs(deviation_pct) > 30.0

    if is_anomaly:
        message = (
            f"Anomaly detected: invoice {req.invoice_amount} DKK vs "
            f"{expected_amount} DKK expected ({deviation_pct:+.2f}% deviation)"
        )
    else:
        message = f"Normal: {deviation_pct:+.2f}% deviation from expected"

    return InvoiceAnomalyResult(
        session_id=req.session_id,
        invoice_amount=req.invoice_amount,
        expected_amount=expected_amount,
        deviation_percent=deviation_pct,
        is_anomaly=is_anomaly,
        message=message,
    )
