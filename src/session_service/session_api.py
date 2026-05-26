"""Session Service — ChargingSession aggregate with state machine"""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from shared.events import (
    ChargingSessionData,
    SessionStatus,
    SessionStarted,
    SessionValidated,
)
from shared.database import get_connection, execute, init_db

# Initialize database tables on module load
init_db()

router = APIRouter(prefix="/sessions", tags=["sessions"])


class StartSessionRequest(BaseModel):
    charger_id: str = Field(examples=["charger-1"])
    contract_id: str = Field(examples=["contract-1"])


class CompleteSessionRequest(BaseModel):
    energy_delivered: float = Field(examples=[25.5])
    duration_minutes: int = Field(examples=[60])


def _session_from_row(row) -> ChargingSessionData:
    return ChargingSessionData(
        session_id=row["session_id"],
        charger_id=row["charger_id"],
        contract_id=row["contract_id"],
        status=SessionStatus(row["status"]),
        start_time=datetime.fromisoformat(row["start_time"]) if row["start_time"] else None,
        end_time=datetime.fromisoformat(row["end_time"]) if row["end_time"] else None,
        energy_delivered=row["energy_delivered"],
        duration_minutes=row["duration_minutes"],
    )


@router.get("/health")
async def health():
    return {"status": "healthy", "service": "session-service"}


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


@router.post("/{session_id}/authorize")
async def authorize_session(session_id: str):
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
        raise HTTPException(status_code=400, detail=f"Cannot authorize in status {session.status.value}")

    execute(conn, "UPDATE sessions SET status = ? WHERE session_id = ?",
            (SessionStatus.AUTHORIZED.value, session_id))
    conn.commit()
    conn.close()

    return {"session_id": session_id, "status": SessionStatus.AUTHORIZED.value}


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
    if session.status != SessionStatus.AUTHORIZED:
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
