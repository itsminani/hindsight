"""Fixtures for the conformance suite: an HTTP client that checks every response against the contract.

Run against a LOCAL server with the demo seed loaded (these tests create data):
    docker compose up -d --build && docker compose exec api python -m hindsight.seed
    cd conformance && python -m uv run pytest
"""

import os
from urllib.parse import urlparse

import httpx
import pytest

from contract import Contract

BASE_URL = os.environ.get("HINDSIGHT_BASE_URL", "http://127.0.0.1:8000")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "api"}  # "api" = the Compose service name in CI


@pytest.fixture(scope="session")
def contract() -> Contract:
    """The parsed contract/openapi.yaml."""
    return Contract()


@pytest.fixture(scope="session")
def client(contract: Contract):
    """An HTTP client whose every response is checked against the contract automatically."""
    if urlparse(BASE_URL).hostname not in LOCAL_HOSTS:
        pytest.exit(f"refusing to run write tests against {BASE_URL}: local servers only")

    def check(response: httpx.Response) -> None:
        """Response hook: read the body, then validate status, content type and body."""
        response.read()
        contract.check(response)

    with httpx.Client(base_url=BASE_URL, timeout=10, event_hooks={"response": [check]}) as c:
        try:
            c.get("/health/live")
        except httpx.ConnectError:
            pytest.exit(f"no server at {BASE_URL}; start it with: docker compose up -d --build")
        yield c


@pytest.fixture(scope="session")
def password() -> str:
    """The demo users' password (same variable the seed script uses)."""
    value = os.environ.get("HINDSIGHT_SEED_PASSWORD")
    if not value:
        pytest.exit("set HINDSIGHT_SEED_PASSWORD (the value from your .env)")
    return value


def bearer(client: httpx.Client, email: str, password: str) -> dict[str, str]:
    """Sign in and return the Authorization header."""
    token = client.post("/auth/token", json={"email": email, "password": password}).json()["accessToken"]
    return {"Authorization": f"Bearer {token}"}
