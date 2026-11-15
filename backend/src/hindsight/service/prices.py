"""Price history for charts: daily prices from the provider, thinned to one close per week."""

from datetime import date

from hindsight.domain.models import PriceBar, PriceSource
from hindsight.integrations.interfaces import PriceProvider, ProviderUnavailable, UnknownTicker
from hindsight.service.errors import NotFound, PriceProviderUnavailable


class PriceService:
    """Use case: weekly adjusted closes for one ticker, for the report charts."""

    def __init__(self, prices: PriceProvider, today: date | None = None) -> None:
        """prices: the market-data provider chosen in main.py."""
        self._prices = prices
        self._today = today

    @property
    def source(self) -> PriceSource:
        """Which provider answers (shown to users, so demo prices are never mistaken for real ones)."""
        return self._prices.source

    def weekly(self, ticker: str, start: date) -> list[PriceBar]:
        """The last trading day of each week from `start` to today, oldest first."""
        try:
            bars = self._prices.daily_bars(ticker, start, self._today or date.today())
        except UnknownTicker as error:
            raise NotFound(f"No prices for {ticker}") from error
        except ProviderUnavailable as error:
            raise PriceProviderUnavailable() from error
        weekly: dict[tuple[int, int], PriceBar] = {}
        for bar in bars:
            weekly[bar.day.isocalendar()[:2]] = bar  # later days of the same week overwrite earlier ones
        return list(weekly.values())
