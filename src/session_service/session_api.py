"""Session Service — Session aggregate (Aggregate 1 of the Charging Session Bounded Context, SessionID as root)"""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from shared.events import (
    SessionData,
    SessionStatus,
    SessionStarted,
    SessionRated,
    SessionValidated,
    InvoiceLineGenerated,
)
from shared.database import get_connection, execute, init_db
from billing_service.billing_api import calculate_price

# Initialize database tables on module load
init_db()

router = APIRouter(prefix="/sessions", tags=["Charging Session"])


class StartSessionRequest(BaseModel):
    charger_id: str = Field(examples=["charger-1"])
    contract_id: str = Field(examples=["contract-1"])


class CompleteSessionRequest(BaseModel):
    energy_delivered: float = Field(examples=[25.5])
    duration_minutes: int = Field(examples=[60], description="Total time at charger (charging + parking)")
    charging_duration_minutes: int = Field(examples=[45], description="Time the car was actually charging")
    temperature: Optional[float] = Field(default=None, description="Temperature in °C at charging time — used for ML dynamic pricing")
    hour_of_day: Optional[int] = Field(default=None, description="Hour of day (0-23) at charging time — used for ML dynamic pricing")


def _session_from_row(row) -> SessionData:
    return SessionData(
        session_id=row["session_id"],
        charger_id=row["charger_id"],
        contract_id=row["contract_id"],
        status=SessionStatus(row["status"]),
        start_time=datetime.fromisoformat(row["start_time"]) if row["start_time"] else None,
        end_time=datetime.fromisoformat(row["end_time"]) if row["end_time"] else None,
        energy_delivered=row["energy_delivered"],
        duration_minutes=row["duration_minutes"],
        charging_duration_minutes=row["charging_duration_minutes"],
        total_cost=row["total_cost"],
        invoice_line_id=row["invoice_line_id"],
        temperature=row["temperature"] if "temperature" in row.keys() else None,
        hour_of_day=row["hour_of_day"] if "hour_of_day" in row.keys() else None,
    )



@router.post("/start", response_model=SessionStarted)
async def start_session(req: StartSessionRequest):
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    now_str = now.isoformat()

    conn = get_connection()
    execute(
        conn,
        "INSERT INTO sessions (session_id, charger_id, contract_id, status, start_time) VALUES (?, ?, ?, ?, ?)",
        (session_id, req.charger_id, req.contract_id, SessionStatus.CREATED.value, now_str),
    )
    conn.commit()
    conn.close()

    return SessionStarted(
        session_id=session_id,
        charger_id=req.charger_id,
        contract_id=req.contract_id,
        timestamp=now,
    )


@router.post("/{session_id}/start-charging")
async def start_charging(session_id: str):
    conn = get_connection()
    cursor = execute(conn, "SELECT * FROM sessions WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    cursor.close()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found")

    session = _session_from_row(row)
    if session.status != SessionStatus.CREATED:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Cannot start charging in status {session.status.value}")

    execute(conn, "UPDATE sessions SET status = ? WHERE session_id = ?",
            (SessionStatus.CHARGING.value, session_id))
    conn.commit()
    conn.close()

    return {"session_id": session_id, "status": SessionStatus.CHARGING.value}


@router.post("/{session_id}/validate", response_model=SessionValidated)
async def validate_session(session_id: str, req: CompleteSessionRequest):
    """Validate and complete a session with energy and duration data."""
    return await _complete_session(session_id, req)


async def _complete_session(session_id: str, req: CompleteSessionRequest):
    conn = get_connection()
    cursor = execute(conn, "SELECT * FROM sessions WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    cursor.close()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found")

    session = _session_from_row(row)
    if session.status != SessionStatus.CHARGING:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Cannot validate in status {session.status.value}")

    now = datetime.now(timezone.utc)
    now_str = now.isoformat()

    execute(
        conn,
        "UPDATE sessions SET status = ?, end_time = ?, energy_delivered = ?, duration_minutes = ?, charging_duration_minutes = ?, temperature = ?, hour_of_day = ? WHERE session_id = ?",
        (SessionStatus.COMPLETED.value, now_str, req.energy_delivered, req.duration_minutes, req.charging_duration_minutes, req.temperature, req.hour_of_day, session_id),
    )
    conn.commit()
    conn.close()

    return SessionValidated(
        session_id=session_id,
        charger_id=session.charger_id,
        contract_id=session.contract_id,
        energy_delivered=req.energy_delivered,
        duration_minutes=req.duration_minutes,
        charging_duration_minutes=req.charging_duration_minutes,
        temperature=req.temperature,
        hour_of_day=req.hour_of_day,
        timestamp=now,
    )


@router.post("/{session_id}/rate", response_model=SessionRated)
async def rate_session(session_id: str):
    """Transition session from Completed to Rated — generate invoice_line_id (UUID) and save it on the session."""
    conn = get_connection()
    cursor = execute(conn, "SELECT * FROM sessions WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    cursor.close()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found")

    session = _session_from_row(row)
    if session.status != SessionStatus.COMPLETED:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Cannot rate session in status '{session.status.value}'")

    # Generate an invoice_line_id UUID and save it on the session.
    # No price calculation happens here — that happens at invoice time.
    invoice_line_id = str(uuid.uuid4())
    execute(
        conn,
        "UPDATE sessions SET status = ?, invoice_line_id = ? WHERE session_id = ?",
        (SessionStatus.RATED.value, invoice_line_id, session_id),
    )
    conn.commit()
    conn.close()

    return SessionRated(
        session_id=session_id,
        invoice_line_id=invoice_line_id,
        timestamp=datetime.now(timezone.utc),
    )

@router.post("/{session_id}/invoice", response_model=InvoiceLineGenerated)
async def create_invoice(session_id: str):
    """Transition session from Rated to Invoiced — calculate price via Tariff/RatingService and create invoice entry."""
    conn = get_connection()
    cursor = execute(conn, "SELECT * FROM sessions WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    cursor.close()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found")

    session = _session_from_row(row)
    if session.status != SessionStatus.RATED:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Cannot invoice session in status '{session.status.value}'")

    if not session.invoice_line_id:
        conn.close()
        raise HTTPException(status_code=400, detail="Session has no invoice_line_id — must be rated first")

    # Calculate price using Tariff/RatingService from Billing Context
    # ML dynamic pricing: if temperature + hour_of_day were recorded at validation,
    # the billing service uses the ML price-rate model to determine the kWh price
    total_cost, _, _, breakdown = calculate_price(
        session.energy_delivered,
        session.duration_minutes,
        session.charging_duration_minutes,
        temperature=session.temperature,
        hour_of_day=session.hour_of_day,
    )

    now = datetime.now(timezone.utc)
    now_str = now.isoformat()

    # Persist invoice using the pre-generated invoice_line_id
    execute(
        conn,
        "INSERT INTO invoices (invoice_line_id, session_id, amount, currency, status, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (session.invoice_line_id, session_id, total_cost, "DKK", "Generated", now_str),
    )

    # Update session status and store the calculated total_cost
    execute(
        conn,
        "UPDATE sessions SET status = ?, total_cost = ? WHERE session_id = ?",
        (SessionStatus.INVOICED.value, total_cost, session_id),
    )
    conn.commit()
    conn.close()

    return InvoiceLineGenerated(
        invoice_line_id=session.invoice_line_id,
        session_id=session_id,
        amount=total_cost,
        currency="DKK",
        breakdown=breakdown,
        timestamp=now,
    )


@router.get("/")
async def list_sessions():
    """Return all sessions ordered by creation time (newest first)."""
    conn = get_connection()
    cursor = execute(conn, "SELECT * FROM sessions ORDER BY start_time DESC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [_session_from_row(r) for r in rows]



