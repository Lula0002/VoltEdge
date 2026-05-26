"""Shared event models for VoltEdge MVP"""

from enum import Enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class SessionStatus(str, Enum):
    CREATED = "Created"
    AUTHORIZED = "Authorized"
    CHARGING = "Charging"
    COMPLETED = "Completed"


class ChargingSessionData(BaseModel):
    session_id: str
    charger_id: str
    contract_id: str
    status: SessionStatus
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    energy_delivered: Optional[float] = None
    duration_minutes: Optional[int] = None


class SessionStarted(BaseModel):
    session_id: str
    charger_id: str
    contract_id: str
    timestamp: datetime


class SessionValidated(BaseModel):
    session_id: str
    charger_id: str
    contract_id: str
    energy_delivered: float
    duration_minutes: int
    timestamp: datetime


class SessionRated(BaseModel):
    session_id: str
    total_cost: float
    currency: str = "DKK"
    breakdown: dict = {}
    timestamp: datetime


class InvoiceLineCreated(BaseModel):
    session_id: str
    invoice_id: str
    amount: float
    currency: str = "DKK"
    timestamp: datetime
