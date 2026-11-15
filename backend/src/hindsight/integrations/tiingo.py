"""Real market data from Tiingo (https://www.tiingo.com), used when HINDSIGHT_TIINGO_API_KEY is set.

Endpoint: GET /tiingo/daily/{ticker}/prices?startDate=...&endDate=...
Each row has `close` (the real price that day) and `adjClose` (adjusted for later splits and
dividends), which is exactly what the hindsight calculation needs.
"""

import logging
from datetime import date
from decimal import Decimal

import httpx

from hindsight.domain.models import PriceBar, PriceSource
from hindsight.integrations.interfaces import PriceProvider, ProviderUnavailable, UnknownTicker

log = logging.getLogger(__name__)
BASE_URL = "https://api.tiingo.com"


class TiingoPriceProvider(PriceProvider):
    """Daily prices from Tiingo. Short timeouts: a slow provider must not block a worker for long."""

    source = PriceSource.TIINGO

    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        """api_key: the Tiingo token (a secret, from settings). client: injectable for tests."""
        self._client = client or httpx.Client(
            base_url=BASE_URL,
            timeout=httpx.Timeout(5.0, connect=3.0),
            headers={"Authorization": f"Token {api_key}", "Accept": "application/json"},
        )

    def daily_bars(self, ticker: str, start: date, end: date) -> list[PriceBar]:
        """Every trading day between start and end.

        404 -> UnknownTicker; timeouts, errors and unreadable data -> ProviderUnavailable.
        """
        try:
            response = self._client.get(
                f"/tiingo/daily/{ticker.lower()}/prices",
                params={"startDate": start.isoformat(), "endDate": end.isoformat()},
            )
        except httpx.HTTPError as error:
            raise ProviderUnavailable(f"Tiingo request failed: {error.__class__.__name__}") from error

        if response.status_code == 404:
            raise UnknownTicker(ticker)
        if response.status_code != 200:
            log.warning("tiingo error", extra={"status": response.status_code, "ticker": ticker})
            raise ProviderUnavailable(f"Tiingo answered {response.status_code}")

        try:
            return [
                PriceBar(
                    date.fromisoformat(row["date"][:10]),
                    Decimal(str(row["close"])),
                    Decimal(str(row["adjClose"])),
                )
                for row in response.json()
            ]
        except (ValueError, KeyError, TypeError) as error:
            raise ProviderUnavailable("Tiingo sent data we could not read") from error
