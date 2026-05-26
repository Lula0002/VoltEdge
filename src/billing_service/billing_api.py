"""Billing Service — Tariff rating and invoice line generation"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from shared.events import SessionRated, InvoiceLineCreated

router = APIRouter(prefix="/billing", tags=["billing"])


class RateRequest(BaseModel):
    session_id: str
    energy_delivered: float
    duration_minutes: int
    charger_id: str
    contract_id: str


class InvoiceRequest(BaseModel):
    session_id: str
    total_cost: float
    currency: str = "DKK"
    breakdown: dict = {}


# Simpel tariff: 2.45 DKK/kWh + 0.50 DKK/min parking after 10 min free
ENERGY_RATE = 2.45  # DKK per kWh
PARKING_RATE = 0.50  # DKK per minute after 10 free minutes
PARKING_FREE_MINUTES = 10


@router.get("/health")
async def health():
    return {"status": "healthy", "service": "billing-service"}


@router.post("/rate", response_model=SessionRated)
async def rate_session(req: RateRequest):
    energy_cost = round(req.energy_delivered * ENERGY_RATE, 2)
    billable_parking = max(0, req.duration_minutes - PARKING_FREE_MINUTES)
    parking_cost = round(billable_parking * PARKING_RATE, 2)
    total_cost = round(energy_cost + parking_cost, 2)

    breakdown = {
        "energy": energy_cost,
        "parking": parking_cost,
        "energy_rate": ENERGY_RATE,
        "parking_rate": PARKING_RATE,
        "billable_parking_minutes": billable_parking,
    }

    return SessionRated(
        session_id=req.session_id,
        total_cost=total_cost,
        currency="DKK",
        breakdown=breakdown,
        timestamp=datetime.now(timezone.utc),
    )


@router.post("/invoice", response_model=InvoiceLineCreated)
async def create_invoice(req: InvoiceRequest):
    invoice_id = str(uuid.uuid4())

    return InvoiceLineCreated(
        session_id=req.session_id,
        invoice_id=invoice_id,
        amount=req.total_cost,
        currency=req.currency,
        timestamp=datetime.now(timezone.utc),
    )
