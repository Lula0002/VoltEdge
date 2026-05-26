"""Tests for Billing Service — Tariff rating and invoice generation"""

import os
import sys
import tempfile
from pathlib import Path

# Use a temporary database for tests
os.environ["VOLTEDGE_DB_PATH"] = os.path.join(tempfile.gettempdir(), "voltedge_test.db")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_1_health():
    """Health endpoint should return 200"""
    response = client.get("/billing/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_2_rate_session():
    """Rate a completed session"""
    response = client.post("/billing/rate", json={
        "session_id": "test-session-1",
        "energy_delivered": 25.5,
        "duration_minutes": 60,
        "charger_id": "charger-1",
        "contract_id": "contract-1"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "test-session-1"
    assert data["currency"] == "DKK"
    assert data["total_cost"] > 0
    assert "energy" in data["breakdown"]
    assert "parking" in data["breakdown"]


def test_3_rate_energy_cost():
    """Verify energy cost calculation:
       25.5 kWh * 2.45 DKK/kWh = 62.48 DKK
    """
    response = client.post("/billing/rate", json={
        "session_id": "test-session-2",
        "energy_delivered": 25.5,
        "duration_minutes": 60,
        "charger_id": "charger-1",
        "contract_id": "contract-1"
    })
    data = response.json()
    assert data["breakdown"]["energy"] == 62.48  # 25.5 * 2.45


def test_4_rate_parking_cost():
    """Verify parking cost calculation:
       60 min - 10 free = 50 billable min * 0.50 = 25.00 DKK
    """
    response = client.post("/billing/rate", json={
        "session_id": "test-session-3",
        "energy_delivered": 0,
        "duration_minutes": 60,
        "charger_id": "charger-1",
        "contract_id": "contract-1"
    })
    data = response.json()
    assert data["breakdown"]["parking"] == 25.0
    assert data["breakdown"]["billable_parking_minutes"] == 50


def test_5_create_invoice():
    """Create an invoice line"""
    response = client.post("/billing/invoice", json={
        "session_id": "test-session-1",
        "total_cost": 92.50,
        "currency": "DKK",
        "breakdown": {"energy": 62.50, "parking": 30.0}
    })
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "test-session-1"
    assert data["amount"] == 92.50
    assert "invoice_id" in data


def test_6_rate_no_parking_cost():
    """Short session should have no parking cost (under 10 min free)"""
    response = client.post("/billing/rate", json={
        "session_id": "test-session-4",
        "energy_delivered": 1.0,
        "duration_minutes": 5,
        "charger_id": "charger-1",
        "contract_id": "contract-1"
    })
    data = response.json()
    assert data["breakdown"]["parking"] == 0.0
    assert data["breakdown"]["billable_parking_minutes"] == 0
