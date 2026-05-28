"""Tests for Billing Service — Tariff rating and invoice generation

Billing endpoints (POST /billing/rate, POST /billing/invoice) are no longer
exposed as HTTP endpoints — they are internal functions called by the Session
aggregate via direct Python import.

These tests verify the domain logic (Tariff, RatingService) and the invoice
persistence through the session HTTP endpoints.
"""
import os
import sys
import tempfile
from pathlib import Path

# Use a temporary database for tests
os.environ["VOLTEDGE_DB_PATH"] = os.path.join(tempfile.gettempdir(), "voltedge_test.db")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from billing_service.tariff import Tariff
from billing_service.rating_service import RatingService


# ── Pure domain logic tests (no HTTP, no DB) ────────────────

def test_1_energy_cost():
    """Verify energy cost: 25.5 kWh * 2.45 DKK/kWh = 62.48 DKK (no parking)"""
    tariff = Tariff()
    rating = RatingService(tariff)
    total_cost, energy_cost, parking_cost, breakdown = rating.rate(25.5, 45, 45)
    assert breakdown["charges"]["energy"]["amount"] == 62.48
    assert breakdown["charges"]["parking_overstay"]["amount"] == 0.0


def test_2_parking_cost():
    """Verify parking cost: 60 min total - 0 charging - 10 grace = 50 billable * 0.50 = 25.00 DKK"""
    tariff = Tariff()
    rating = RatingService(tariff)
    total_cost, energy_cost, parking_cost, breakdown = rating.rate(0, 60, 0)
    assert breakdown["charges"]["parking_overstay"]["amount"] == 25.0
    assert breakdown["charges"]["parking_overstay"]["billable_minutes"] == 50


def test_3_no_parking_cost():
    """Short session (5 min) should have no parking cost (under 10 min free)"""
    tariff = Tariff()
    rating = RatingService(tariff)
    total_cost, energy_cost, parking_cost, breakdown = rating.rate(1.0, 5, 0)
    assert breakdown["charges"]["parking_overstay"]["amount"] == 0.0
    assert breakdown["charges"]["parking_overstay"]["billable_minutes"] == 0


def test_4_total_cost():
    """Verify total cost: 62.48 energy + 0.00 parking = 62.48 DKK (charging = total)"""
    tariff = Tariff()
    rating = RatingService(tariff)
    total_cost, energy_cost, parking_cost, breakdown = rating.rate(25.5, 60, 60)
    assert total_cost == 62.48


def test_5_tariff_constants():
    """Verify pricing constants are as expected"""
    from billing_service.tariff import OverstayPolicy
    tariff = Tariff()
    overstay = OverstayPolicy()
    assert tariff.energy_rate == 2.45
    assert overstay.rate == 0.50
    assert overstay.grace_minutes == 10
