"""VoltEdge MVP — Combined FastAPI Application

All modules run in one Azure Web App on a single port.

Analytics/ML is presented as an **external capability** that can ONLY be
accessed via its own API endpoints (/analytics/*). The ML model is isolated in
ml_model.py — separate from the Charging Session Bounded Context.

Architecture:
  ┌─────────────────────────────────────────┐
  │  1 Bounded Context: Charging Session    │
  │  ├─ Aggregate 1: ChargingSession        │
  │  └─ Aggregate 2: Invoice                │
  └────────────┬────────────────────────────┘
               │ calls Analytics ONLY via HTTP
               ▼
  ┌─────────────────────────────────────┐
  │  Analytics/ML (External Capability) │
  │  - KUN tilgængelig via HTTP/API     │
  └─────────────────────────────────────┘
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
        "VoltEdge Mobility MVP API — DDD-based architecture with 1 Bounded Context.\n\n"
        "---\n"
        "### Charging Session (Bounded Context)\n"
        "- **Aggregate 1: ChargingSession** — State machine: Created → Charging → Completed → Rated → Invoiced.\n"
        "- **Aggregate 2: Invoice** — Tarifberegning og fakturagenerering.\n\n"
        "### External Capability (Analytics/ML) — `/analytics/*`\n"
        "- ML prediction (energy & revenue) offered as an **external API service**.\n"
        "- The ML model is ISOLATED in `ml_model.py` — no direct imports from Session/Billing.\n"
        "- The only way to use ML is via HTTP calls to `/analytics/` endpoints.\n\n"
        "**Try `POST /auto-flow-with-ml`** to see the core flow call Analytics via HTTP!"
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


@app.post("/auto-flow-with-ml", tags=["auto-flow"])
async def auto_flow_with_ml(req: AutoFlowRequest):
    """Run the Happy Path AND call Analytics/ML via HTTP — demonstrating separation.

    This endpoint shows that Analytics is an **external capability** consumed via API:
      1. Core flow runs (Session + Billing) — direct Python calls
      2. Analytics/ML is called via **HTTP** (httpx) — just like an external customer would

    The ML call uses httpx to make an actual HTTP request to the analytics endpoint,
    proving it is a separate service accessed through its API — not via direct import.
    """
    import httpx

    # ── Step 1-5: Core flow (Session + Billing) ──
    from session_service.session_api import (
        start_session,
        start_charging,
        complete_session,
        rate_session,
        create_invoice,
        StartSessionRequest,
        CompleteSessionRequest,
    )

    started = await start_session(StartSessionRequest(
        charger_id=req.charger_id,
        contract_id=req.contract_id,
    ))
    session_id = started.session_id
    charging = await start_charging(session_id)
    validated = await complete_session(
        session_id,
        CompleteSessionRequest(
            energy_delivered=req.energy_delivered,
            duration_minutes=req.duration_minutes,
        ),
    )
    rated = await rate_session(session_id)
    invoiced = await create_invoice(session_id)

    core_result = {
        "session_started": started.model_dump(),
        "charging_started": charging,
        "session_validated": validated.model_dump(),
        "session_rated": rated.model_dump(),
        "invoice_generated": invoiced.model_dump(),
    }

    # ── Step 6: Call Analytics/ML via HTTP (external API pattern) ──
    # This is the key demonstration: Analytics is consumed via HTTP,
    # NOT via a direct Python import.
    base_url = "http://localhost:8000"
    try:
        async with httpx.AsyncClient() as client:
            ml_response = await client.post(
                f"{base_url}/analytics/predict-energy",
                json={
                    "duration_minutes": req.duration_minutes,
                    "temperature": 15,
                    "hour_of_day": 14,
                },
                timeout=10,
            )
            ml_result = ml_response.json()
    except Exception as e:
        ml_result = {"error": f"Analytics service unavailable: {e}"}

    return {
        "core": core_result,
        "analytics_ml_external_api_call": {
            "endpoint": "POST /analytics/predict-energy (via HTTP)",
            "note": "Analytics/ML is an EXTERNAL capability — called via HTTP, not direct import",
            "result": ml_result,
        },
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
