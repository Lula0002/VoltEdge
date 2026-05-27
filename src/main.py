"""VoltEdge MVP — Combined FastAPI Application

All 3 services run in one Azure Web App on a single port.

Analytics/ML is presented as an **external capability** offered to customers
via its own API endpoints (/analytics/*). The ML model is isolated in
ml_model.py — separate from the core Session and Billing logic.
"""

import sys
from pathlib import Path

# Ensure src/ is on sys.path so all service packages are importable
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="VoltEdge Mobility MVP API",
    description=(
        "VoltEdge Mobility MVP API — DDD-based architecture with 3 Bounded Contexts.\n\n"
        "**Session Context** — Owns the ChargingSession aggregate and state machine.\n"
        "**Billing Context** — Owns the Invoice aggregate and handles pricing independently.\n"
        "**Analytics Context** — ML prediction capability (energy & revenue) offered as an\n"
        "external service via dedicated API endpoints. The ML model is isolated from the\n"
        "core microservice logic.\n\n"
        "All services run in one Azure Web App for deployment simplicity."
    ),
    version="1.0.3",
    docs_url="/docs",
    redoc_url="/redoc",
)


class AutoFlowRequest(BaseModel):
    charger_id: str = Field(default="charger-1")
    contract_id: str = Field(default="contract-1")
    energy_delivered: float = Field(default=25.5)
    duration_minutes: int = Field(default=60)


@app.post("/auto-flow", tags=["auto-flow"])
async def auto_flow(req: AutoFlowRequest):
    """Run the complete Happy Path automatically in a single call.

    Steps:
    1. Create session (Created)
    2. Start charging (Charging)
    3. Complete with meter data (Completed)
    4. Calculate price (Rated)
    5. Generate invoice (Invoiced)

    Returns the full trace from start to finish.
    """
    from session_service.session_api import (
        start_session,
        start_charging,
        complete_session,
        rate_session,
        create_invoice,
        StartSessionRequest,
        CompleteSessionRequest,
    )

    # Step 1: Start session
    started = await start_session(StartSessionRequest(
        charger_id=req.charger_id,
        contract_id=req.contract_id,
    ))
    session_id = started.session_id

    # Step 2: Start charging
    charging = await start_charging(session_id)

    # Step 3: Complete with meter data
    validated = await complete_session(
        session_id,
        CompleteSessionRequest(
            energy_delivered=req.energy_delivered,
            duration_minutes=req.duration_minutes,
        ),
    )

    # Step 4: Rate session (session service owns state transition)
    rated = await rate_session(session_id)

    # Step 5: Generate invoice (session service owns state transition)
    invoiced = await create_invoice(session_id)

    return {
        "session_started": started.model_dump(),
        "charging_started": charging,
        "session_validated": validated.model_dump(),
        "session_rated": rated.model_dump(),
        "invoice_generated": invoiced.model_dump(),
    }

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# Import and register all 3 service routers
from session_service.session_api import router as session_router
from billing_service.billing_api import router as billing_router
from analytics_service.analytics_api import router as analytics_router

app.include_router(session_router)
app.include_router(billing_router)
app.include_router(analytics_router)
