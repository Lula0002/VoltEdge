"""RatingService — Domain service that calculates the total price (tariff + overstay).

Ubiquitous Language: Rating is the domain service that applies pricing rules
to a session — combining the Tariff (energy) and OverstayPolicy (parking penalty).
"""

from __future__ import annotations
from billing_service.tariff import Tariff, OverstayPolicy, calculate_total


class RatingService:
    """Domain service that calculates total price using Tariff + OverstayPolicy."""

    def __init__(self, tariff: Tariff | None = None, overstay: OverstayPolicy | None = None):
        self.tariff = tariff or Tariff()
        self.overstay = overstay or OverstayPolicy()

    def rate(self, energy_delivered: float, duration_minutes: int, charging_minutes: int = 0) -> tuple[float, float, float, dict]:
        """Calculate price using Tariff (energy) + OverstayPolicy (parking penalty).

        Args:
            energy_delivered: kWh delivered
            duration_minutes: total time at charger
            charging_minutes: time the car was actually charging (parking is free during charging)

        Returns (total_cost, energy_cost, parking_cost, breakdown).
        """
        return calculate_total(
            energy_delivered,
            duration_minutes,
            charging_minutes,
            tariff=self.tariff,
            overstay=self.overstay,
        )


# Default singleton for simple imports
default_rating_service = RatingService()
