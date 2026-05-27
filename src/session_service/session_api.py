"""Session Service — Session aggregate (Aggregate 1 of the Charging Session Bounded Context, SessionID as root)"""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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

router = APIRouter(prefix="/sessions", tags=["sessions"])


class StartSessionRequest(BaseModel):
    charger_id: str = Field(examples=["charger-1"])
    contract_id: str = Field(examples=["contract-1"])


class CompleteSessionRequest(BaseModel):
    energy_delivered: float = Field(examples=[25.5])
    duration_minutes: int = Field(examples=[60])


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
        total_cost=row["total_cost"],
        invoice_line_id=row["invoice_line_id"],
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


@router.post("/{session_id}/complete", response_model=SessionValidated)
async def complete_session(session_id: str, req: CompleteSessionRequest):
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
        raise HTTPException(status_code=400, detail=f"Cannot complete in status {session.status.value}")

    now = datetime.now(timezone.utc)
    now_str = now.isoformat()

    execute(
        conn,
        "UPDATE sessions SET status = ?, end_time = ?, energy_delivered = ?, duration_minutes = ? WHERE session_id = ?",
        (SessionStatus.COMPLETED.value, now_str, req.energy_delivered, req.duration_minutes, session_id),
    )
    conn.commit()
    conn.close()

    return SessionValidated(
        session_id=session_id,
        charger_id=session.charger_id,
        contract_id=session.contract_id,
        energy_delivered=req.energy_delivered,
        duration_minutes=req.duration_minutes,
        timestamp=now,
    )


from billing_service.billing_api import rate_session as billing_rate, create_invoice as billing_create

@router.post("/{session_id}/rate", response_model=SessionRated)
async def rate_session(session_id: str):
    """Transition session from Completed to Rated by calling Billing Context."""
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

    # Call Billing Context (Retning B - Direct Domain Service Call).
    # Note: Billing Context is the authoritative source for invoicing data.
    # The session status is mirrored here for readability.
    from billing_service.billing_api import RateRequest
    rated_data = await billing_rate(RateRequest(
        session_id=session_id,
        energy_delivered=session.energy_delivered,
        duration_minutes=session.duration_minutes,
        charger_id=session.charger_id,
        contract_id=session.contract_id
    ))

    execute(
        conn,
        "UPDATE sessions SET status = ?, total_cost = ? WHERE session_id = ?",
        (SessionStatus.RATED.value, rated_data.total_cost, session_id),
    )
    conn.commit()
    conn.close()

    return rated_data

@router.post("/{session_id}/invoice", response_model=InvoiceLineGenerated)
async def create_invoice(session_id: str):
    """Transition session from Rated to Invoiced by calling Billing Context."""
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

    # Call Billing Context (Retning B - Direct Domain Service Call).
    # Note: Billing Context is the authoritative source for invoicing data.
    # The session status is mirrored here for readability.
    from billing_service.billing_api import InvoiceRequest
    invoice_data = await billing_create(InvoiceRequest(
        session_id=session_id,
        total_cost=session.total_cost
    ))

    execute(
        conn,
        "UPDATE sessions SET status = ?, invoice_line_id = ? WHERE session_id = ?",
        (SessionStatus.INVOICED.value, invoice_data.invoice_line_id, session_id),
    )
    conn.commit()
    conn.close()

    return invoice_data


@router.get("/")
async def list_sessions():
    """Return all sessions ordered by creation time (newest first)."""
    conn = get_connection()
    cursor = execute(conn, "SELECT * FROM sessions ORDER BY start_time DESC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [_session_from_row(r) for r in rows]


@router.get("/{session_id}")
async def get_session(session_id: str):
    conn = get_connection()
    cursor = execute(conn, "SELECT * FROM sessions WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    return _session_from_row(row)
