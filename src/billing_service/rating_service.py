"""RatingService — Domain service that calculates the price for a session based on the applicable tariff.

Ubiquitous Language: Rating is the domain service that applies a Tariff to a session.
"""

from __future__ import annotations
from billing_service.tariff import Tariff


class RatingService:
    """Domain service that calculates price for a charging session based on tariff rules."""

    def __init__(self, tariff: Tariff | None = None):
        self.tariff = tariff or Tariff()

    def rate(self, energy_delivered: float, duration_minutes: int) -> tuple[float, float, float, dict]:
        """Calculate price using the configured tariff.

        Returns (total_cost, energy_cost, parking_cost, breakdown).
        """
        return self.tariff.calculate_total(energy_delivered, duration_minutes)


# Default singleton for simple imports
default_rating_service = RatingService()
