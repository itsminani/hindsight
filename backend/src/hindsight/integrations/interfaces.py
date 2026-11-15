"""What the service layer may ask of a market-data provider, and how a provider can fail.

The service layer depends on this interface only; main.py picks Tiingo or the demo provider.
"""

from abc import ABC, abstractmethod
from datetime import date

from hindsight.domain.models import PriceBar, PriceSource


class UnknownTicker(Exception):
    """The provider has no such stock. Permanent: retrying will not help."""


class ProviderUnavailable(Exception):
    """The provider timed out, rate-limited us or broke. Temporary: retry later with backoff."""


class PriceProvider(ABC):
    """Daily prices for a stock."""

    source: PriceSource

    @abstractmethod
    def daily_bars(self, ticker: str, start: date, end: date) -> list[PriceBar]:
        """Every trading day from start to end (inclusive), oldest first.

        Raises UnknownTicker or ProviderUnavailable.
        """
