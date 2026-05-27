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

import sys
from pathlib import Path

# Ensure src/ is on sys.path so all service packages are importable
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="VoltEdge Mobility MVP API",
    description=(
        "VoltEdge Mobility MVP API — DDD-based architecture with 1 Bounded Context.\n\n"
        "---\n"
        "### Charging Session (Bounded Context)\n"
        "- **Aggregate 1: Session** (SessionID as root) — State machine: Created → Charging → Completed → Rated → Invoiced.\n"
        "- **Aggregate 2: InvoiceLine** (InvoiceLineID as root) — Tariff calculation and invoice generation.\n\n"
        "### External Capability (Analytics/ML) — `/analytics/*`\n"
        "- ML prediction (energy & revenue) offered as an **external API service**.\n"
        "- The ML model is ISOLATED in `ml_model.py` — no direct imports from Session/Billing.\n"
        "- The only way to use ML is via HTTP calls to `/analytics/` endpoints.\n\n"
        "Analytics/ML endpoints return HTTP request details in their response — proving they are called via HTTP, not direct import."
    ),
    version="1.0.4",
    docs_url="/docs",
    redoc_url="/redoc",
)


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
