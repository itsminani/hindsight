"""The app shell: health checks, request IDs, and errors that never leak a stack trace."""

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from hindsight.main import create_app


class Body(BaseModel):
    """A tiny request body with one required field, used to trigger a validation error."""

    name: str


@pytest.fixture
def client() -> TestClient:
    """A test client for a fresh app, plus two throwaway routes that exercise the error handlers."""
    app = create_app()

    @app.get("/boom")
    def boom():
        """Always crashes, to check that a 500 hides the internal details."""
        raise RuntimeError("secret internal detail")

    @app.post("/echo")
    def echo(body: Body):
        """Returns the body it receives; used to send an invalid body."""
        return body

    return TestClient(app, raise_server_exceptions=False)


def test_liveness(client):
    """/health/live answers 200 {"status": "ok"}."""
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readiness(client):
    """/health/ready answers ok while nothing is down."""
    assert client.get("/health/ready").json() == {"status": "ok"}


def test_request_id_is_generated(client):
    """Without an X-Request-ID header, the service makes one up and returns it."""
    r = client.get("/health/live")
    assert r.headers["X-Request-ID"].startswith("req_")


def test_request_id_from_caller_is_kept(client):
    """A caller's X-Request-ID is reused, so one ID can follow a call across services."""
    r = client.get("/health/live", headers={"X-Request-ID": "abc-123"})
    assert r.headers["X-Request-ID"] == "abc-123"


def test_unknown_route_is_a_problem(client):
    """An unknown URL returns a 404 Problem with code not_found and the request ID."""
    r = client.get("/nope", headers={"X-Request-ID": "abc-123"})
    assert r.status_code == 404
    assert r.headers["content-type"] == "application/problem+json"
    body = r.json()
    assert body["code"] == "not_found"
    assert body["status"] == 404
    assert body["requestId"] == "abc-123"


def test_validation_error_lists_fields(client):
    """A body missing a required field returns 422 validation_error naming that field."""
    r = client.post("/echo", json={})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "validation_error"
    assert body["errors"][0]["field"] == "name"


def test_crash_returns_500_without_stack_trace(client):
    """A crash returns a clean 500 with a request ID, and never the exception text or traceback."""
    r = client.get("/boom")
    assert r.status_code == 500
    assert r.json()["code"] == "internal_error"
    assert "secret internal detail" not in r.text
    assert "Traceback" not in r.text
    assert r.headers["X-Request-ID"].startswith("req_")


def test_docs_serve_the_hand_written_contract(client):
    """/openapi.json (and so /docs) serves contract/openapi.yaml, not a generated spec."""
    spec = client.get("/openapi.json").json()
    assert spec["openapi"] == "3.1.0"
    assert "/portfolios/{portfolioId}/hindsight-reports" in spec["paths"]
