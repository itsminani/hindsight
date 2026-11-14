"""Portfolio and position endpoints, including "you only ever see your own" (404, never 403)."""

import pytest

from tests.conftest import sign_in


@pytest.fixture
def alice(api):
    """Authorization header for Alice (two seeded portfolios)."""
    return sign_in(api, "alice@example.com")


@pytest.fixture
def bob(api):
    """Authorization header for Bob (one seeded portfolio)."""
    return sign_in(api, "bob@example.com")


def _first_portfolio(api, headers) -> dict:
    """The caller's first portfolio, as returned by GET /portfolios."""
    return api.get("/portfolios", headers=headers).json()["items"][0]


def test_list_shows_only_my_portfolios(api, alice, bob):
    """Alice sees her 2 portfolios with positions; Bob sees only his 1."""
    mine = api.get("/portfolios", headers=alice)
    assert mine.status_code == 200
    names = [p["name"] for p in mine.json()["items"]]
    assert sorted(names) == ["Dividend picks", "Tech I sold too early"]
    assert [p["name"] for p in api.get("/portfolios", headers=bob).json()["items"]] == ["Bob's trades"]


def test_portfolio_body_matches_the_contract_shape(api, alice):
    """camelCase fields, ISO dates, null for a position still held, nothing extra."""
    portfolio = next(p for p in api.get("/portfolios", headers=alice).json()["items"] if p["name"] == "Tech I sold too early")
    assert set(portfolio) == {"id", "name", "createdAt", "positions"}
    assert portfolio["id"].startswith("pf_")
    aapl = next(p for p in portfolio["positions"] if p["ticker"] == "AAPL")
    assert aapl == {"id": aapl["id"], "ticker": "AAPL", "shares": 50, "buyDate": "2015-03-02", "sellDate": "2017-06-01"}
    msft = next(p for p in portfolio["positions"] if p["ticker"] == "MSFT")
    assert msft["sellDate"] is None


def test_create_portfolio_then_find_it(api, alice):
    """POST creates it (201 + Location), and it can then be read and listed."""
    r = api.post("/portfolios", json={"name": "Crypto regrets"}, headers=alice)
    assert r.status_code == 201
    created = r.json()
    assert created["positions"] == []
    assert r.headers["Location"] == f"/portfolios/{created['id']}"
    assert api.get(r.headers["Location"], headers=alice).json()["name"] == "Crypto regrets"
    assert len(api.get("/portfolios", headers=alice).json()["items"]) == 3


def test_someone_elses_portfolio_is_404_like_a_missing_one(api, alice, bob):
    """Bob asking for Alice's portfolio gets exactly the same answer as for an ID that doesn't exist."""
    alices_id = _first_portfolio(api, alice)["id"]
    theirs = api.get(f"/portfolios/{alices_id}", headers=bob)
    missing = api.get("/portfolios/pf_doesNotExist", headers=bob)
    assert theirs.status_code == missing.status_code == 404
    assert theirs.json()["code"] == missing.json()["code"] == "not_found"
    assert theirs.json()["detail"] == missing.json()["detail"]


def test_add_position(api, alice):
    """A new position appears in the portfolio."""
    portfolio_id = _first_portfolio(api, alice)["id"]
    body = {"ticker": "BRK.B", "shares": 3, "buyDate": "2019-01-02", "sellDate": "2020-03-02"}
    r = api.post(f"/portfolios/{portfolio_id}/positions", json=body, headers=alice)
    assert r.status_code == 201
    assert r.json()["id"].startswith("ps_") and r.json()["ticker"] == "BRK.B"
    tickers = [p["ticker"] for p in api.get(f"/portfolios/{portfolio_id}", headers=alice).json()["positions"]]
    assert "BRK.B" in tickers


def test_cannot_add_a_position_to_someone_elses_portfolio(api, alice, bob):
    """Writing into another user's portfolio is 404, and nothing is written."""
    portfolio_id = _first_portfolio(api, alice)["id"]
    before = len(api.get(f"/portfolios/{portfolio_id}", headers=alice).json()["positions"])
    body = {"ticker": "GME", "shares": 1, "buyDate": "2021-01-04"}
    assert api.post(f"/portfolios/{portfolio_id}/positions", json=body, headers=bob).status_code == 404
    assert len(api.get(f"/portfolios/{portfolio_id}", headers=alice).json()["positions"]) == before


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"ticker": "AAPL", "shares": 1, "buyDate": "2020-05-01", "sellDate": "2020-01-01"}, "sellDate"),
        ({"ticker": "aapl", "shares": 1, "buyDate": "2020-05-01"}, "ticker"),
        ({"ticker": "AAPL", "shares": 0, "buyDate": "2020-05-01"}, "shares"),
        ({"ticker": "AAPL", "shares": 1, "buyDate": "not-a-date"}, "buyDate"),
        ({"ticker": "AAPL", "shares": 1, "buyDate": "2020-05-01", "price": 10}, "price"),
    ],
)
def test_invalid_positions_are_422_naming_the_field(api, alice, body, field):
    """Each invalid body is a validation_error that points at the offending field."""
    portfolio_id = _first_portfolio(api, alice)["id"]
    r = api.post(f"/portfolios/{portfolio_id}/positions", json=body, headers=alice)
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"
    assert [e["field"] for e in r.json()["errors"]] == [field]


@pytest.mark.parametrize("name", ["", "x" * 101])
def test_portfolio_name_length_is_validated(api, alice, name):
    """Names must be 1 to 100 characters."""
    assert api.post("/portfolios", json={"name": name}, headers=alice).status_code == 422


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "/portfolios"), ("post", "/portfolios"), ("get", "/portfolios/pf_x"), ("post", "/portfolios/pf_x/positions")],
)
def test_every_portfolio_route_requires_a_token(api, method, path):
    """No token: 401 on every route, before anything else is checked."""
    r = api.request(method.upper(), path, json={})
    assert r.status_code == 401
    assert r.json()["code"] == "unauthorized"
