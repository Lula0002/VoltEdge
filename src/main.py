"""VoltEdge MVP — Combined FastAPI Application

All 3 services run in a single Azure Web App.
Each service has its own URL prefix.
"""

import sys
from pathlib import Path

# Ensure src/ is on sys.path so all service packages are importable
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="VoltEdge Mobility MVP API",
    description="Automated billing & settlement — Happy Path: SessionStarted → SessionValidated → PriceCalculated → InvoiceGenerated",
    version="1.0.0",
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


@app.get("/health")
async def root_health():
    return {"status": "healthy", "app": "voltige-mvp", "version": "1.0.0"}


# Import and register service routers
from session_service.session_api import router as session_router
from billing_service.billing_api import router as billing_router
from analytics_service.analytics_api import router as analytics_router

app.include_router(session_router)
app.include_router(billing_router)
app.include_router(analytics_router)
