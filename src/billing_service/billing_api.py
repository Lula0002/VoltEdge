"""Billing Service — Tariff rating and invoice line generation (pure domain service)

DDD note: This service is a pure domain service. It calculates prices and generates
invoice lines but NEVER writes to session state. Session state transitions
(Rated, Invoiced) are owned by the session service (ChargingSession aggregate).
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field

from shared.events import SessionRated, InvoiceLineGenerated

router = APIRouter(prefix="/billing", tags=["billing"])


class RateRequest(BaseModel):
    session_id: str = Field(examples=["86c80cc7-47a9-48a0-901d-5dfc4f38c399"])
    energy_delivered: float = Field(examples=[25.5])
    duration_minutes: int = Field(examples=[60])
    charger_id: str = Field(examples=["charger-1"])
    contract_id: str = Field(examples=["contract-1"])


class InvoiceRequest(BaseModel):
    session_id: str = Field(examples=["86c80cc7-47a9-48a0-901d-5dfc4f38c399"])
    total_cost: float = Field(examples=[92.50])
    currency: str = "DKK"
    breakdown: dict = {}


# Simple tariff: 2.45 DKK/kWh + 0.50 DKK/min parking after 10 min free
ENERGY_RATE = 2.45  # DKK per kWh
PARKING_RATE = 0.50  # DKK per minute after 10 free minutes
PARKING_FREE_MINUTES = 10


def calculate_price(energy_delivered: float, duration_minutes: int) -> tuple[float, float, int, dict]:
    """Pure calculation — no side effects, no DB access."""
    energy_cost = round(energy_delivered * ENERGY_RATE, 2)
    billable_parking = max(0, duration_minutes - PARKING_FREE_MINUTES)
    parking_cost = round(billable_parking * PARKING_RATE, 2)
    total_cost = round(energy_cost + parking_cost, 2)
    breakdown = {
        "energy": energy_cost,
        "parking": parking_cost,
        "energy_rate": ENERGY_RATE,
        "parking_rate": PARKING_RATE,
        "billable_parking_minutes": billable_parking,
    }
    return total_cost, energy_cost, parking_cost, breakdown


@router.post("/rate", response_model=SessionRated)
async def rate_session(req: RateRequest):
    """Calculate price for a session (pure calculation, no side effects).
    
    Session state transition to 'Rated' must be handled by the session service.
    """
    total_cost, _, _, breakdown = calculate_price(req.energy_delivered, req.duration_minutes)

    return SessionRated(
        session_id=req.session_id,
        total_cost=total_cost,
        currency="DKK",
        breakdown=breakdown,
        timestamp=datetime.now(timezone.utc),
    )


@router.post("/invoice", response_model=InvoiceLineGenerated)
async def create_invoice(req: InvoiceRequest):
    """Generate an invoice line (pure generation, no side effects).
    
    Session state transition to 'Invoiced' must be handled by the session service.
    """
    invoice_id = str(uuid.uuid4())

    return InvoiceLineGenerated(
        session_id=req.session_id,
        invoice_id=invoice_id,
        amount=req.total_cost,
        currency=req.currency,
        timestamp=datetime.now(timezone.utc),
    )
