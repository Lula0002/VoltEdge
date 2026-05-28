"""Billing — InvoiceLine entity (Aggregate 2 of the Charging Session Bounded Context, InvoiceLineID as root).

Handles tariff rating, price calculation, and invoice persistence.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field

from shared.events import InvoiceLineGenerated
from shared.database import get_connection, execute, init_db
from billing_service.tariff import Tariff
from billing_service.rating_service import RatingService, default_rating_service


# Ensure database tables exist
init_db()

router = APIRouter(prefix="/billing", tags=["Charging Session"])


class RateRequest(BaseModel):
    session_id: str = Field(examples=["86c80cc7-47a9-48a0-901d-5dfc4f38c399"])
    energy_delivered: float = Field(examples=[25.5])
    duration_minutes: int = Field(examples=[60])
    charging_minutes: int = Field(default=0, examples=[45], description="Time the car was actually charging")
    charger_id: str = Field(examples=["charger-1"])
    contract_id: str = Field(examples=["contract-1"])


class InvoiceRequest(BaseModel):
    session_id: str = Field(examples=["86c80cc7-47a9-48a0-901d-5dfc4f38c399"])
    total_cost: float = Field(examples=[92.50])
    currency: str = "DKK"
    breakdown: dict = {}


# Re-export for backward compatibility with session_service
def calculate_price(energy_delivered: float, duration_minutes: int, charging_minutes: int = 0) -> tuple[float, float, float, dict]:
    """Pure calculation — delegates to RatingService (UL domain service).

    Args:
        energy_delivered: kWh delivered
        duration_minutes: total time at charger
        charging_minutes: time the car was actually charging (parking is free while charging)

    Returns (total_cost, energy_cost, parking_cost, breakdown).
    """
    return default_rating_service.rate(energy_delivered, duration_minutes, charging_minutes)


class Invoice(BaseModel):
    invoice_line_id: str
    session_id: str
    amount: float
    currency: str = "DKK"
    status: str = "Generated"
    timestamp: datetime

async def rate_session(req: RateRequest):
    """Calculate price for a session (kept for backward compatibility, no longer called from session_api)."""
    tariff = Tariff()
    rating_service = RatingService(tariff)
    total_cost, _, _, breakdown = rating_service.rate(req.energy_delivered, req.duration_minutes, req.charging_minutes)
    
    return {
        "session_id": req.session_id,
        "total_cost": total_cost,
        "currency": "DKK",
        "breakdown": breakdown,
        "timestamp": datetime.now(timezone.utc),
    }

async def create_invoice(req: InvoiceRequest):
    """Generate and persist an invoice in SQLite database."""
    invoice_line_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    now_str = now.isoformat()
    
    conn = get_connection()
    execute(
        conn,
        "INSERT INTO invoices (invoice_line_id, session_id, amount, currency, status, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (invoice_line_id, req.session_id, req.total_cost, req.currency, "Generated", now_str),
    )
    conn.commit()
    conn.close()
    
    return InvoiceLineGenerated(
        session_id=req.session_id,
        invoice_line_id=invoice_line_id,
        amount=req.total_cost,
        currency=req.currency,
        timestamp=now,
    )


@router.get("/invoices")
async def list_invoices():
    """Return all invoices from the database."""
    conn = get_connection()
    cursor = execute(conn, "SELECT * FROM invoices ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    result = []
    for row in rows:
        result.append({
            "invoice_line_id": row["invoice_line_id"],
            "session_id": row["session_id"],
            "amount": row["amount"],
            "currency": row["currency"],
            "status": row["status"],
            "timestamp": row["timestamp"],
        })
    return result
