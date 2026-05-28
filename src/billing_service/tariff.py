"""Tariff — Pricing rules for the core product (energy).

The Tariff defines what you ALWAYS pay for: the energy consumed.

Overstay parking is a SEPARATE penalty policy (not a tariff) — it only
applies when the car remains at the charger after charging completes.

Overstay policy:
  • Free to park while charging
  • 10 minute free grace period after charging completes
  • 15 DKK per 30 minutes (0.50 DKK/min) after the grace period
"""

from typing import Optional
from dataclasses import dataclass


@dataclass(frozen=True)
class Tariff:
    """Pricing rules for the energy service.

    Default: 2.45 DKK/kWh.
    """
    energy_rate: float = 2.45       # DKK per kWh — ALWAYS paid

    def calculate_energy_cost(self, kwh: float) -> float:
        return round(kwh * self.energy_rate, 2)


@dataclass(frozen=True)
class OverstayPolicy:
    """Penalty rules for occupying the charger after charging completes."""
    rate: float = 0.50              # DKK per minute (= 15 DKK/30min)
    grace_minutes: int = 10         # Free grace minutes AFTER charging ends

    def calculate_cost(self, total_minutes: int, charging_minutes: int) -> float:
        """Parking cost: free while charging, then grace_minutes free, then rate applies."""
        parking_minutes = max(0, total_minutes - charging_minutes)
        billable = max(0, parking_minutes - self.grace_minutes)
        return round(billable * self.rate, 2)


def calculate_total(
    kwh: float,
    total_minutes: int,
    charging_minutes: int,
    tariff: Optional[Tariff] = None,
    overstay: Optional[OverstayPolicy] = None,
) -> tuple[float, float, float, dict]:
    """Full price calculation.

    Returns (total, energy_cost, parking_cost, breakdown).
    """
    tariff = tariff or Tariff()
    overstay = overstay or OverstayPolicy()

    energy_cost = tariff.calculate_energy_cost(kwh)
    parking_cost = overstay.calculate_cost(total_minutes, charging_minutes)
    total = round(energy_cost + parking_cost, 2)

    parking_minutes = max(0, total_minutes - charging_minutes)
    billable = max(0, parking_minutes - overstay.grace_minutes)

    breakdown = {
        "charges": {
            "energy": {
                "amount": energy_cost,
                "rate": tariff.energy_rate,
                "unit": "DKK/kWh",
                "kwh": kwh,
            },
            "parking_overstay": {
                "amount": parking_cost,
                "rate": overstay.rate,
                "unit": "DKK/min",
                "grace_minutes": overstay.grace_minutes,
                "billable_minutes": billable,
                "label": "15 DKK / 30 min",
            },
        },
        "session": {
            "total_duration_minutes": total_minutes,
            "charging_duration_minutes": charging_minutes,
            "parking_duration_minutes": parking_minutes,
        },
    }
    return total, energy_cost, parking_cost, breakdown
