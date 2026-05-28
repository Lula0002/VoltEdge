"""Shared event models for VoltEdge MVP"""

from enum import Enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class SessionStatus(str, Enum):
    CREATED = "Created"
    CHARGING = "Charging"
    COMPLETED = "Completed"
    RATED = "Rated"
    INVOICED = "Invoiced"


class SessionData(BaseModel):
    session_id: str
    charger_id: str
    contract_id: str
    status: SessionStatus
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    energy_delivered: Optional[float] = None
    duration_minutes: Optional[int] = None
    charging_duration_minutes: Optional[int] = None
    total_cost: Optional[float] = None
    invoice_line_id: Optional[str] = None
    temperature: Optional[float] = None
    hour_of_day: Optional[int] = None


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
    charging_duration_minutes: int
    temperature: Optional[float] = None
    hour_of_day: Optional[int] = None
    timestamp: datetime


class SessionRated(BaseModel):
    session_id: str
    invoice_line_id: str
    timestamp: datetime


class InvoiceLineGenerated(BaseModel):
    invoice_line_id: str
    session_id: str
    amount: float
    currency: str = "DKK"
    breakdown: dict = {}
    timestamp: datetime
