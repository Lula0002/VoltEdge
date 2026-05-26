"""Billing Service — Tariff rating and invoice line generation"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from shared.events import SessionStatus, SessionRated, InvoiceLineGenerated
from shared.database import get_connection, execute, init_db

init_db()

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


@router.post("/rate", response_model=SessionRated)
async def rate_session(req: RateRequest):
    # Check session exists and is completed
    conn = get_connection()
    cursor = execute(conn, "SELECT * FROM sessions WHERE session_id = ?", (req.session_id,))
    row = cursor.fetchone()
    cursor.close()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found")

    session_status = row["status"]
    if session_status != SessionStatus.COMPLETED.value:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail=f"Cannot rate session in status '{session_status}'. Must be 'Completed'.",
        )

    # Calculate price
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

    # Update session status to Rated and store total_cost
    execute(
        conn,
        "UPDATE sessions SET status = ?, total_cost = ? WHERE session_id = ?",
        (SessionStatus.RATED.value, total_cost, req.session_id),
    )
    conn.commit()
    conn.close()

    return SessionRated(
        session_id=req.session_id,
        total_cost=total_cost,
        currency="DKK",
        breakdown=breakdown,
        timestamp=datetime.now(timezone.utc),
    )


@router.post("/invoice", response_model=InvoiceLineGenerated)
async def create_invoice(req: InvoiceRequest):
    # Check session exists and is rated
    conn = get_connection()
    cursor = execute(conn, "SELECT * FROM sessions WHERE session_id = ?", (req.session_id,))
    row = cursor.fetchone()
    cursor.close()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found")

    session_status = row["status"]
    if session_status != SessionStatus.RATED.value:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail=f"Cannot invoice session in status '{session_status}'. Must be 'Rated'.",
        )

    invoice_id = str(uuid.uuid4())

    # Update session status to Invoiced and store invoice_id
    execute(
        conn,
        "UPDATE sessions SET status = ?, invoice_id = ? WHERE session_id = ?",
        (SessionStatus.INVOICED.value, invoice_id, req.session_id),
    )
    conn.commit()
    conn.close()

    return InvoiceLineGenerated(
        session_id=req.session_id,
        invoice_id=invoice_id,
        amount=req.total_cost,
        currency=req.currency,
        timestamp=datetime.now(timezone.utc),
    )
