"""Tariff — Pricing rules (time-of-use, subscription, fleet agreement)

Ubiquitous Language: Tariff defines the pricing rules applied during Rating.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Tariff:
    """Pricing rules for charging sessions.

    Default: 2.45 DKK/kWh energy + 0.50 DKK/min parking after 10 free minutes.
    """
    energy_rate: float = 2.45       # DKK per kWh
    parking_rate: float = 0.50      # DKK per minute
    parking_free_minutes: int = 10  # Free parking minutes per session

    def calculate_energy_cost(self, kwh: float) -> float:
        return round(kwh * self.energy_rate, 2)

    def calculate_parking_cost(self, minutes: int) -> float:
        billable = max(0, minutes - self.parking_free_minutes)
        return round(billable * self.parking_rate, 2)

    def calculate_total(self, kwh: float, minutes: int) -> tuple[float, float, float, dict]:
        """Full price calculation returning (total, energy_cost, parking_cost, breakdown)."""
        energy_cost = self.calculate_energy_cost(kwh)
        parking_cost = self.calculate_parking_cost(minutes)
        total = round(energy_cost + parking_cost, 2)
        billable = max(0, minutes - self.parking_free_minutes)
        breakdown = {
            "energy": energy_cost,
            "parking": parking_cost,
            "energy_rate": self.energy_rate,
            "parking_rate": self.parking_rate,
            "billable_parking_minutes": billable,
        }
        return total, energy_cost, parking_cost, breakdown
