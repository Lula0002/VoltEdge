"""VoltEdge MVP — Combined FastAPI Application

All modules run in one Azure Web App on a single port.

Analytics/ML is presented as an **external capability** that can ONLY be
accessed via its own API endpoints (/analytics/*). The ML model is isolated in
ml_model.py — separate from the Charging Session Bounded Context.

Architecture:
  ┌─────────────────────────────────────────┐
  │  1 Bounded Context: Charging Session    │
  │  ├─ Aggregate 1: Session (SessionID)    │
  │  └─ Aggregate 2: InvoiceLine (InvoiceLineID)│
  └────────────┬────────────────────────────┘
               │ calls Analytics ONLY via HTTP
               ▼
  ┌─────────────────────────────────────┐
  │  Analytics/ML (External Capability) │
  │  - ONLY accessible via HTTP/API     │
  └─────────────────────────────────────┘
"""

import json
import logging
import sys
import time
import uuid
from pathlib import Path

# Ensure src/ is on sys.path so all service packages are importable
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ── Structured JSON logging ──
logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[logging.StreamHandler()])
logger = logging.getLogger("voltedge")

app = FastAPI(
    title="VoltEdge Mobility MVP API",
    description=(
        "VoltEdge Mobility MVP"
    ),
    version="1.0.4",
    docs_url="/docs",
    redoc_url="/redoc",
)


class AutoFlowRequest(BaseModel):
    charger_id: str = Field(default="charger-1")
    contract_id: str = Field(default="contract-1")
    energy_delivered: float = Field(default=25.5)
    duration_minutes: int = Field(default=60, description="Total time at charger")
    charging_duration_minutes: int = Field(default=45, description="Time actually charging (parking is free while charging)")


@app.post("/auto-flow-with-ml", tags=["Proof of API"])
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
        validate_session,
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
    validated = await validate_session(
        session_id,
        CompleteSessionRequest(
            energy_delivered=req.energy_delivered,
            duration_minutes=req.duration_minutes,
            charging_duration_minutes=req.charging_duration_minutes,
            temperature=15,      # 15°C — en almindelig dag i København
            hour_of_day=14,      # Kl. 14 — eftermiddag, normal takst
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
                f"{base_url}/analytics/predict-price-rate",
                json={
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
            "endpoint": "POST /analytics/predict-price-rate (via HTTP)",
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


# ── Structured JSON logging middleware with correlation ID ──
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    correlation_id = str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    start = time.time()

    response = await call_next(request)

    duration_ms = round((time.time() - start) * 1000, 2)
    log_entry = json.dumps({
        "correlation_id": correlation_id,
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "duration_ms": duration_ms,
    })
    logger.info(log_entry)

    return response


# Import and register all 3 service routers
from session_service.session_api import router as session_router
from billing_service.billing_api import router as billing_router
from analytics_service.analytics_api import router as analytics_router

app.include_router(session_router)
app.include_router(billing_router)
app.include_router(analytics_router)
