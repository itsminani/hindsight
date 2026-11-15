"""Price providers (demo and Tiingo) and the price history endpoint. No real network calls."""

from datetime import date
from decimal import Decimal

import httpx
import pytest

from hindsight.domain.models import PriceBar, PriceSource, hindsight_values
from hindsight.integrations.demo_prices import DemoPriceProvider
from hindsight.integrations.interfaces import ProviderUnavailable, UnknownTicker
from hindsight.integrations.tiingo import TiingoPriceProvider
from tests.conftest import sign_in

TODAY = date(2026, 11, 13)


def test_hindsight_values_count_splits_through_adjusted_prices():
    """50 shares sold at $100; adjusted price went from 25 to 75 (a 4:1 split then 3x): worth $15,000."""
    sold, today, diff = hindsight_values(
        50,
        PriceBar(date(2017, 6, 1), Decimal("100"), Decimal("25")),
        PriceBar(TODAY, Decimal("75"), Decimal("75")),
    )
    assert (sold, today, diff) == (Decimal("5000.00"), Decimal("15000.00"), Decimal("10000.00"))


def test_demo_prices_are_repeatable_and_labelled_demo():
    """Same ticker, same history; different tickers differ; source says demo."""
    a = DemoPriceProvider(today=TODAY)
    b = DemoPriceProvider(today=TODAY)
    start, end = date(2020, 1, 1), date(2020, 3, 1)
    assert a.daily_bars("AAPL", start, end) == b.daily_bars("AAPL", start, end)
    assert a.daily_bars("AAPL", start, end) != a.daily_bars("MSFT", start, end)
    assert all(bar.day.weekday() < 5 for bar in a.daily_bars("AAPL", start, end))
    assert a.source is PriceSource.DEMO


def test_demo_prices_know_no_zz_tickers():
    """Tickers starting with ZZ are unknown, to test that path without a real provider."""
    with pytest.raises(UnknownTicker):
        DemoPriceProvider(today=TODAY).daily_bars("ZZZZ", date(2020, 1, 1), TODAY)


def _tiingo(handler) -> TiingoPriceProvider:
    """A Tiingo provider whose HTTP calls go to `handler` instead of the internet."""
    client = httpx.Client(base_url="https://api.tiingo.com", transport=httpx.MockTransport(handler))
    return TiingoPriceProvider("test-key", client=client)


def test_tiingo_reads_close_and_adjusted_close():
    """A normal answer becomes PriceBars with the real and the adjusted close."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Answer like Tiingo does."""
        assert request.url.path == "/tiingo/daily/aapl/prices"
        assert request.url.params["startDate"] == "2017-05-25"
        return httpx.Response(
            200, json=[{"date": "2017-06-01T00:00:00.000Z", "close": 153.18, "adjClose": 36.53}]
        )

    bars = _tiingo(handler).daily_bars("AAPL", date(2017, 5, 25), date(2017, 6, 1))
    assert bars == [PriceBar(date(2017, 6, 1), Decimal("153.18"), Decimal("36.53"))]


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(404, json={"detail": "not found"}), UnknownTicker),
        (httpx.Response(429, json={"detail": "slow down"}), ProviderUnavailable),
        (httpx.Response(500, text="oops"), ProviderUnavailable),
        (httpx.Response(200, json=[{"date": "2020-01-01"}]), ProviderUnavailable),
    ],
    ids=["unknown-ticker", "rate-limited", "server-error", "unreadable-data"],
)
def test_tiingo_errors_are_classified(response, error):
    """404 is permanent (unknown ticker); everything else odd is temporary (retry later)."""
    with pytest.raises(error):
        _tiingo(lambda _: response).daily_bars("AAPL", date(2020, 1, 1), date(2020, 2, 1))


def test_tiingo_timeout_is_temporary():
    """A timeout is ProviderUnavailable, so the worker retries instead of failing the report."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Behave like a provider that never answers."""
        raise httpx.ReadTimeout("too slow", request=request)

    with pytest.raises(ProviderUnavailable):
        _tiingo(handler).daily_bars("AAPL", date(2020, 1, 1), date(2020, 2, 1))


def test_price_history_endpoint_returns_weekly_demo_prices(api):
    """Signed in: weekly points, oldest first, money as strings, and the source is shown."""
    alice = sign_in(api, "alice@example.com")
    r = api.get("/tickers/AAPL/prices", params={"from": "2024-01-01"}, headers=alice)
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "AAPL" and body["source"] == "demo"
    dates = [p["date"] for p in body["prices"]]
    assert dates == sorted(dates) and len(dates) > 50
    assert all(p["close"].count(".") == 1 and len(p["close"].split(".")[1]) == 2 for p in body["prices"])


def test_price_history_errors(api):
    """Unknown ticker 404, lower-case ticker 422, missing `from` 422, no token 401."""
    alice = sign_in(api, "alice@example.com")
    assert api.get("/tickers/ZZZZ/prices", params={"from": "2024-01-01"}, headers=alice).status_code == 404
    assert api.get("/tickers/aapl/prices", params={"from": "2024-01-01"}, headers=alice).status_code == 422
    assert api.get("/tickers/AAPL/prices", headers=alice).status_code == 422
    assert api.get("/tickers/AAPL/prices", params={"from": "2024-01-01"}).status_code == 401
