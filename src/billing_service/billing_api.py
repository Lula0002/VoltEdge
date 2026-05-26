"""Billing Service — Tariff rating and Invoice aggregate.

DDD note: This service is now a Bounded Context that owns the Invoice aggregate.
It handles its own state (Generated) and persists invoice data independently 
of the session service.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field

from shared.events import SessionRated, InvoiceLineGenerated
from billing_service.tariff import Tariff
from billing_service.rating_service import RatingService, default_rating_service


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


# Re-export for backward compatibility with session_service
def calculate_price(energy_delivered: float, duration_minutes: int) -> tuple[float, float, int, dict]:
    """Pure calculation — delegates to RatingService (UL domain service).

    Kept as module-level function for backward compatibility.
    """
    return default_rating_service.rate(energy_delivered, duration_minutes)


# In-memory storage for Billing Context
invoices = {}

class Invoice(BaseModel):
    invoice_id: str
    session_id: str
    amount: float
    currency: str = "DKK"
    status: str = "Generated"
    timestamp: datetime

@router.post("/rate", response_model=SessionRated)
async def rate_session(req: RateRequest):
    """Calculate price for a session and store the result in Billing Context."""
    tariff = Tariff()
    rating_service = RatingService(tariff)
    total_cost, _, _, breakdown = rating_service.rate(req.energy_delivered, req.duration_minutes)
    
    rated_event = SessionRated(
        session_id=req.session_id,
        total_cost=total_cost,
        currency="DKK",
        breakdown=breakdown,
        timestamp=datetime.now(timezone.utc),
    )
    return rated_event

@router.post("/invoice", response_model=InvoiceLineGenerated)
async def create_invoice(req: InvoiceRequest):
    """Generate and persist an invoice in Billing Context."""
    invoice_id = str(uuid.uuid4())
    
    invoice = Invoice(
        invoice_id=invoice_id,
        session_id=req.session_id,
        amount=req.total_cost,
        timestamp=datetime.now(timezone.utc)
    )
    invoices[invoice_id] = invoice
    
    return InvoiceLineGenerated(
        session_id=req.session_id,
        invoice_id=invoice_id,
        amount=req.total_cost,
        currency=req.currency,
        timestamp=invoice.timestamp,
    )
