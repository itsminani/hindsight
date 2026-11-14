"""Requesting hindsight reports over HTTP: credits, idempotency, ownership and validation."""

import uuid

import pytest
from sqlalchemy import text

from tests.conftest import sign_in


@pytest.fixture
def alice(api):
    """Authorization header for Alice (owner of the 10-credit family plan)."""
    return sign_in(api, "alice@example.com")


def _portfolio(api, headers, name: str) -> dict:
    """One of the caller's portfolios, by name."""
    return next(p for p in api.get("/portfolios", headers=headers).json()["items"] if p["name"] == name)


def _sold_ids(portfolio: dict, *tickers: str) -> list[str]:
    """IDs of the portfolio's sold positions with these tickers."""
    return [p["id"] for p in portfolio["positions"] if p["ticker"] in tickers and p["sellDate"]]


def _request(api, headers, portfolio_id, position_ids, key=None):
    """POST a report request with an Idempotency-Key (a fresh one unless given)."""
    return api.post(
        f"/portfolios/{portfolio_id}/hindsight-reports",
        json={"positionIds": position_ids},
        headers={**headers, "Idempotency-Key": key or str(uuid.uuid4())},
    )


def test_request_holds_one_credit_per_ticker_and_queues_a_job(api, alice, seeded_database):
    """3 sold tickers -> 202, 3 credits held, Location to poll, and exactly one queued job."""
    tech = _portfolio(api, alice, "Tech I sold too early")
    r = _request(api, alice, tech["id"], _sold_ids(tech, "AAPL", "NVDA", "TSLA"))
    assert r.status_code == 202
    body = r.json()
    assert body == {"id": body["id"], "status": "pending", "creditsHeld": 3, "creditsAvailable": 7}
    assert r.headers["Location"] == f"/hindsight-reports/{body['id']}"

    plan = api.get("/plans/me", headers=alice).json()
    assert (plan["creditsAvailable"], plan["creditsHeld"]) == (7, 3)
    with seeded_database.engine.connect() as conn:
        jobs = conn.execute(text("SELECT status FROM jobs WHERE report_id = :r"), {"r": body["id"]}).all()
    assert [j.status for j in jobs] == ["queued"]


def test_poll_the_report(api, alice):
    """The Location answers with the pending report and no results yet."""
    tech = _portfolio(api, alice, "Tech I sold too early")
    location = _request(api, alice, tech["id"], _sold_ids(tech, "AAPL")).headers["Location"]
    report = api.get(location, headers=alice).json()
    assert report["status"] == "pending" and report["portfolioId"] == tech["id"]
    assert report["creditsCharged"] == 0 and "results" not in report  # contract: an array, or absent


def test_same_key_same_body_replays_without_holding_twice(api, alice):
    """A retry (same key, same body) returns the original answer and holds nothing more."""
    tech = _portfolio(api, alice, "Tech I sold too early")
    ids = _sold_ids(tech, "AAPL", "NVDA")
    first = _request(api, alice, tech["id"], ids, key="retry-key-0001")
    second = _request(api, alice, tech["id"], list(reversed(ids)), key="retry-key-0001")
    assert first.status_code == second.status_code == 202
    assert second.json() == first.json()
    assert second.headers["Idempotent-Replayed"] == "true"
    assert api.get("/plans/me", headers=alice).json()["creditsHeld"] == 2


def test_same_key_different_body_is_409(api, alice):
    """Reusing a key for a different request is refused, and nothing extra is held."""
    tech = _portfolio(api, alice, "Tech I sold too early")
    _request(api, alice, tech["id"], _sold_ids(tech, "AAPL"), key="reused-key-0001")
    r = _request(api, alice, tech["id"], _sold_ids(tech, "NVDA"), key="reused-key-0001")
    assert r.status_code == 409 and r.json()["code"] == "idempotency_key_reuse"
    assert api.get("/plans/me", headers=alice).json()["creditsHeld"] == 1


def test_keys_are_private_to_each_user(api, alice):
    """Bob using Alice's key gets his own report, not a replay of hers."""
    bob = sign_in(api, "bob@example.com")
    tech = _portfolio(api, alice, "Tech I sold too early")
    trades = _portfolio(api, bob, "Bob's trades")
    a = _request(api, alice, tech["id"], _sold_ids(tech, "AAPL"), key="shared-key-0001")
    b = _request(api, bob, trades["id"], _sold_ids(trades, "AMZN"), key="shared-key-0001")
    assert a.status_code == b.status_code == 202
    assert a.json()["id"] != b.json()["id"]


def test_not_enough_credits_is_402_and_holds_nothing(api):
    """Carol has 1 credit; a 1-ticker report works, the next one is 402 insufficient_credits."""
    carol = sign_in(api, "carol@example.com")
    first = _portfolio(api, carol, "First steps")
    ids = _sold_ids(first, "GOOGL")
    assert _request(api, carol, first["id"], ids).status_code == 202
    r = _request(api, carol, first["id"], ids)
    assert r.status_code == 402 and r.json()["code"] == "insufficient_credits"
    plan = api.get("/plans/me", headers=carol).json()
    assert (plan["creditsAvailable"], plan["creditsHeld"]) == (0, 1)


def test_unsold_position_is_422_position_not_sold(api, alice):
    """MSFT is still held, so it cannot be in a hindsight report."""
    tech = _portfolio(api, alice, "Tech I sold too early")
    msft = [p["id"] for p in tech["positions"] if p["ticker"] == "MSFT"]
    r = _request(api, alice, tech["id"], msft)
    assert r.status_code == 422 and r.json()["code"] == "position_not_sold"


def test_someone_elses_portfolio_or_position_is_404(api, alice):
    """Bob cannot request a report on Alice's portfolio, nor include a position from another portfolio."""
    bob = sign_in(api, "bob@example.com")
    tech = _portfolio(api, alice, "Tech I sold too early")
    assert _request(api, bob, tech["id"], _sold_ids(tech, "AAPL")).status_code == 404
    dividends = _portfolio(api, alice, "Dividend picks")
    r = _request(api, alice, dividends["id"], _sold_ids(tech, "AAPL"))
    assert r.status_code == 404 and r.json()["code"] == "not_found"


def test_someone_elses_report_is_404(api, alice):
    """Only the requester can read a report."""
    tech = _portfolio(api, alice, "Tech I sold too early")
    location = _request(api, alice, tech["id"], _sold_ids(tech, "AAPL")).headers["Location"]
    carol = sign_in(api, "carol@example.com")
    assert api.get(location, headers=carol).status_code == 404


def test_missing_idempotency_key_is_422(api, alice):
    """No Idempotency-Key header: 422 idempotency_key_required."""
    tech = _portfolio(api, alice, "Tech I sold too early")
    r = api.post(
        f"/portfolios/{tech['id']}/hindsight-reports",
        json={"positionIds": _sold_ids(tech, "AAPL")},
        headers=alice,
    )
    assert r.status_code == 422 and r.json()["code"] == "idempotency_key_required"


@pytest.mark.parametrize("position_ids", [[], ["ps_a", "ps_a"], [f"ps_{i}" for i in range(51)]])
def test_bad_position_lists_are_422(api, alice, position_ids):
    """Empty, duplicated or more than 50 positions: validation_error."""
    tech = _portfolio(api, alice, "Tech I sold too early")
    r = _request(api, alice, tech["id"], position_ids)
    assert r.status_code == 422 and r.json()["code"] == "validation_error"
