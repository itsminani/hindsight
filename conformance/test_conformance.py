"""Walk through every operation in the contract, happy paths and error paths.

Each test only drives the API; the client fixture validates every single response against
contract/openapi.yaml (status allowed? content type? body matches the schema?).
"""

import uuid

import pytest

from conftest import bearer


@pytest.fixture(scope="module")
def alice(client, password):
    """Alice's Authorization header."""
    return bearer(client, "alice@example.com", password)


@pytest.fixture(scope="module")
def bob(client, password):
    """Bob's Authorization header."""
    return bearer(client, "bob@example.com", password)


def test_health(client):
    """Liveness and readiness."""
    client.get("/health/live")
    assert client.get("/health/ready").status_code == 200


def test_auth_errors(client):
    """Wrong password (401) and an invalid body (422) are Problems with the right shape."""
    assert client.post("/auth/token", json={"email": "alice@example.com", "password": "nope"}).status_code == 401
    assert client.post("/auth/token", json={"email": "alice@example.com"}).status_code == 422


def test_unauthorized_everywhere(client):
    """Every protected operation without a token is a contract-shaped 401."""
    calls = [
        ("GET", "/portfolios"), ("POST", "/portfolios"), ("GET", "/portfolios/pf_x"),
        ("POST", "/portfolios/pf_x/positions"), ("POST", "/portfolios/pf_x/hindsight-reports"),
        ("GET", "/hindsight-reports/rp_x"), ("GET", "/plans/me"), ("POST", "/plans/me/members"),
        ("DELETE", "/plans/me/members/us_x"),
    ]
    for method, path in calls:
        assert client.request(method, path, json={}).status_code == 401, (method, path)


def test_portfolio_flow(client, alice, bob):
    """List, create, read, add a position, and the 404/422 paths around them."""
    assert client.get("/portfolios", headers=alice).status_code == 200
    created = client.post("/portfolios", json={"name": f"Conformance {uuid.uuid4().hex[:6]}"}, headers=alice)
    assert created.status_code == 201
    pid = created.json()["id"]
    assert client.get(f"/portfolios/{pid}", headers=alice).status_code == 200
    assert client.get(f"/portfolios/{pid}", headers=bob).status_code == 404
    position = {"ticker": "AAPL", "shares": 2, "buyDate": "2019-01-02", "sellDate": "2020-01-02"}
    assert client.post(f"/portfolios/{pid}/positions", json=position, headers=alice).status_code == 201
    bad = {**position, "sellDate": "2018-01-01"}
    assert client.post(f"/portfolios/{pid}/positions", json=bad, headers=alice).status_code == 422
    assert client.post("/portfolios", json={"name": ""}, headers=alice).status_code == 422


def test_report_flow(client, alice, bob):
    """Request (202), replay (202), key reuse (409), not sold (422), poll (200), not yours (404)."""
    portfolio = client.post("/portfolios", json={"name": "Conformance reports"}, headers=alice).json()
    pid = portfolio["id"]
    sold = client.post(
        f"/portfolios/{pid}/positions",
        json={"ticker": "MSFT", "shares": 1, "buyDate": "2019-01-02", "sellDate": "2020-01-02"},
        headers=alice,
    ).json()["id"]
    held = client.post(
        f"/portfolios/{pid}/positions", json={"ticker": "KO", "shares": 1, "buyDate": "2019-01-02"}, headers=alice
    ).json()["id"]
    key = str(uuid.uuid4())
    url = f"/portfolios/{pid}/hindsight-reports"

    first = client.post(url, json={"positionIds": [sold]}, headers={**alice, "Idempotency-Key": key})
    assert first.status_code == 202
    replay = client.post(url, json={"positionIds": [sold]}, headers={**alice, "Idempotency-Key": key})
    assert replay.json() == first.json()
    reuse = client.post(url, json={"positionIds": [held]}, headers={**alice, "Idempotency-Key": key})
    assert reuse.status_code == 409
    not_sold = client.post(url, json={"positionIds": [held]}, headers={**alice, "Idempotency-Key": str(uuid.uuid4())})
    assert not_sold.status_code == 422
    no_key = client.post(url, json={"positionIds": [sold]}, headers=alice)
    assert no_key.status_code == 422 and no_key.json()["code"] == "idempotency_key_required"

    location = first.headers["Location"]
    assert client.get(location, headers=alice).status_code == 200
    assert client.get(location, headers=bob).status_code == 404


def test_plan_flow(client, alice, bob, password):
    """My plan (200), add member (201/403/404/409), remove member (204/404)."""
    assert client.get("/plans/me", headers=alice).status_code == 200
    assert client.post("/plans/me/members", json={"email": "carol@example.com"}, headers=bob).status_code == 403
    assert client.post("/plans/me/members", json={"email": "nobody@example.com"}, headers=alice).status_code == 404
    assert client.post("/plans/me/members", json={"email": "bob@example.com"}, headers=alice).status_code == 409
    added = client.post("/plans/me/members", json={"email": "carol@example.com"}, headers=alice)
    assert added.status_code == 201
    member_id = added.json()["userId"]
    assert client.delete(f"/plans/me/members/{member_id}", headers=alice).status_code == 204
    assert client.delete(f"/plans/me/members/{member_id}", headers=alice).status_code == 404


def test_insufficient_credits(client, password):
    """A fresh portfolio with more tickers than Carol's 1 credit: 402 with a Problem body."""
    carol = bearer(client, "carol@example.com", password)
    pid = client.post("/portfolios", json={"name": "Too many tickers"}, headers=carol).json()["id"]
    ids = [
        client.post(
            f"/portfolios/{pid}/positions",
            json={"ticker": t, "shares": 1, "buyDate": "2019-01-02", "sellDate": "2020-01-02"},
            headers=carol,
        ).json()["id"]
        for t in ("AAPL", "MSFT")
    ]
    r = client.post(
        f"/portfolios/{pid}/hindsight-reports",
        json={"positionIds": ids},
        headers={**carol, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 402 and r.json()["code"] == "insufficient_credits"
