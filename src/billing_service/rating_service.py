"""RatingService — Domain service, der beregner prisen for en session ud fra gældende tarif

Ubiquitous Language: Rating is the domain service that applies a Tariff to a session.
"""

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
