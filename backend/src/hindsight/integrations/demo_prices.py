"""Demo prices: generated, repeatable, and labelled "demo" everywhere they are shown.

Used when no market-data API key is configured (local runs, CI, demos), so the app works offline
and tests are stable. Each ticker gets its own random walk, seeded by the ticker, so the same
ticker always has the same history.
"""

import hashlib
import math
import random
from datetime import date, timedelta
from decimal import Decimal

from hindsight.domain.models import PriceBar, PriceSource
from hindsight.integrations.interfaces import PriceProvider, UnknownTicker

HISTORY_START = date(2000, 1, 3)
_CENT = Decimal("0.01")


class DemoPriceProvider(PriceProvider):
    """Deterministic, plausible-looking prices. Tickers starting with "ZZ" are unknown (for tests)."""

    source = PriceSource.DEMO

    def __init__(self, today: date | None = None) -> None:
        """today: the last day with a price (defaults to the real today)."""
        self._today = today or date.today()
        self._cache: dict[str, list[PriceBar]] = {}

    def daily_bars(self, ticker: str, start: date, end: date) -> list[PriceBar]:
        """The generated trading days between start and end."""
        if ticker.startswith("ZZ"):
            raise UnknownTicker(ticker)
        history = self._cache.get(ticker) or self._generate(ticker)
        self._cache[ticker] = history
        return [bar for bar in history if start <= bar.day <= end]

    def _generate(self, ticker: str) -> list[PriceBar]:
        """A random walk with this ticker's own drift and volatility, from 2000 to today."""
        seed = int.from_bytes(hashlib.sha256(ticker.encode()).digest()[:8], "big")
        rng = random.Random(seed)  # noqa: S311 - repeatable demo data, not security
        yearly_drift = rng.uniform(0.04, 0.22)
        yearly_vol = rng.uniform(0.18, 0.40)
        price = rng.uniform(15, 120)
        daily_drift = yearly_drift / 252
        daily_vol = yearly_vol / math.sqrt(252)

        bars: list[PriceBar] = []
        day = HISTORY_START
        while day <= self._today:
            if day.weekday() < 5:  # trading days only
                price *= math.exp(daily_drift - daily_vol**2 / 2 + daily_vol * rng.gauss(0, 1))
                close = Decimal(price).quantize(_CENT)
                bars.append(PriceBar(day, close, close))  # no splits or dividends in demo data
            day += timedelta(days=1)
        return bars
