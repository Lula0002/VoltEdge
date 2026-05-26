"""Session Service — ChargingSession aggregate with state machine"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from shared.events import (
    ChargingSessionData,
    SessionStatus,
    SessionStarted,
    SessionValidated,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])

# In-memory storage (PostgreSQL er valgfri — miljøvariabel styrer)
sessions: dict[str, ChargingSessionData] = {}


class StartSessionRequest(BaseModel):
    charger_id: str
    contract_id: str


class CompleteSessionRequest(BaseModel):
    energy_delivered: float
    duration_minutes: int


@router.get("/health")
async def health():
    return {"status": "healthy", "service": "session-service"}


@router.post("/start", response_model=SessionStarted)
async def start_session(req: StartSessionRequest):
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    session = ChargingSessionData(
        session_id=session_id,
        charger_id=req.charger_id,
        contract_id=req.contract_id,
        status=SessionStatus.CREATED,
        start_time=now,
    )
    sessions[session_id] = session

    return SessionStarted(
        session_id=session_id,
        charger_id=req.charger_id,
        contract_id=req.contract_id,
        timestamp=now,
    )


@router.post("/{session_id}/authorize")
async def authorize_session(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != SessionStatus.CREATED:
        raise HTTPException(status_code=400, detail=f"Cannot authorize in status {session.status}")

    session.status = SessionStatus.AUTHORIZED
    return {"session_id": session_id, "status": SessionStatus.AUTHORIZED}


@router.post("/{session_id}/start-charging")
async def start_charging(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != SessionStatus.AUTHORIZED:
        raise HTTPException(status_code=400, detail=f"Cannot start charging in status {session.status}")

    session.status = SessionStatus.CHARGING
    return {"session_id": session_id, "status": SessionStatus.CHARGING}


@router.post("/{session_id}/complete", response_model=SessionValidated)
async def complete_session(session_id: str, req: CompleteSessionRequest):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != SessionStatus.CHARGING:
        raise HTTPException(status_code=400, detail=f"Cannot complete in status {session.status}")

    now = datetime.now(timezone.utc)
    session.status = SessionStatus.COMPLETED
    session.end_time = now
    session.energy_delivered = req.energy_delivered
    session.duration_minutes = req.duration_minutes

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
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session
