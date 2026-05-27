"""Standalone Analytics Service — external ML capability

Runs independently on port 8001.
Offered as an external capability to customers (e.g. Copenhagen Municipality).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from analytics_service.analytics_api import router

app = FastAPI(
    title="VoltEdge Analytics ML Service",
    description=(
        "Standalone ML service offering energy and revenue predictions.\n"
        "This is an **external capability** — not part of the core Session/Billing microservice.\n"
        "Customers can use it to forecast charging demand and expected revenue."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(router)
