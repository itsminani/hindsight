"""Sign-in (POST /auth/token) and access token checks."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from hindsight.api.deps import CurrentUser
from hindsight.service.auth import AUDIENCE, ISSUER, TokenService
from hindsight.service.errors import Unauthorized
from tests.conftest import DEMO_PASSWORD, TEST_JWT_SECRET, sign_in


@pytest.fixture
def whoami(app, api):
    """Add a throwaway protected route to the app that returns the caller's user ID."""

    @app.get("/whoami")
    def who(user_id: CurrentUser) -> dict:
        """Returns the signed-in user's ID."""
        return {"userId": user_id}

    return api


def test_sign_in_returns_a_bearer_token(api):
    """Right email and password: 200 with a token valid for 15 minutes."""
    r = api.post("/auth/token", json={"email": "alice@example.com", "password": DEMO_PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"accessToken", "tokenType", "expiresIn"}
    assert body["tokenType"] == "Bearer" and body["expiresIn"] == 900


def test_email_is_case_insensitive(api):
    """Signing in with the email in capitals still works."""
    r = api.post("/auth/token", json={"email": "ALICE@example.com", "password": DEMO_PASSWORD})
    assert r.status_code == 200


@pytest.mark.parametrize("email", ["alice@example.com", "nobody@example.com"])
def test_wrong_password_and_unknown_email_look_the_same(api, email):
    """Both give 401 invalid_credentials, so the API never reveals which emails exist."""
    r = api.post("/auth/token", json={"email": email, "password": "wrong"})
    assert r.status_code == 401
    assert r.headers["content-type"] == "application/problem+json"
    assert r.headers["WWW-Authenticate"] == "Bearer"
    assert r.json()["code"] == "invalid_credentials"


@pytest.mark.parametrize(
    "body",
    [
        {"email": "alice@example.com"},
        {"email": "not-an-email", "password": "x"},
        {"email": "alice@example.com", "password": "x", "admin": True},
    ],
)
def test_invalid_sign_in_bodies_are_422(api, body):
    """Missing fields, a malformed email or an unknown extra field are validation errors."""
    r = api.post("/auth/token", json=body)
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"


def test_protected_route_knows_the_caller(whoami):
    """A valid token identifies the user on protected routes."""
    alice = sign_in(whoami, "alice@example.com")
    bob = sign_in(whoami, "bob@example.com")
    alice_id = whoami.get("/whoami", headers=alice).json()["userId"]
    bob_id = whoami.get("/whoami", headers=bob).json()["userId"]
    assert alice_id.startswith("us_") and alice_id != bob_id


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer not-a-jwt"}, {"Authorization": "Basic YWxpY2U6cHc="}],
)
def test_protected_route_without_a_valid_token_is_401(whoami, headers):
    """No token, garbage, or another auth scheme: 401 unauthorized as a Problem."""
    r = whoami.get("/whoami", headers=headers)
    assert r.status_code == 401
    assert r.json()["code"] == "unauthorized"


def _forge(claims: dict, secret: str = TEST_JWT_SECRET, algorithm: str = "HS256") -> str:
    """Build a token by hand, to test what the API does with bad ones."""
    return jwt.encode(claims, secret, algorithm=algorithm)


def _claims(**overrides) -> dict:
    """Valid claims for user us_test, with some replaced."""
    now = datetime.now(UTC)
    return {
        "sub": "us_test",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    } | overrides


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(_forge(_claims(exp=datetime.now(UTC) - timedelta(seconds=1))), id="expired"),
        pytest.param(_forge(_claims(), secret="someone-elses-secret-" + "y" * 32), id="wrong-signature"),
        pytest.param(_forge(_claims(aud="another-api")), id="wrong-audience"),
        pytest.param(_forge(_claims(iss="someone-else")), id="wrong-issuer"),
        pytest.param(_forge(_claims(), secret="", algorithm="none"), id="alg-none"),
    ],
)
def test_token_service_rejects_bad_tokens(token):
    """Expired, forged, misdirected and unsigned ("alg: none") tokens are all refused."""
    with pytest.raises(Unauthorized):
        TokenService(TEST_JWT_SECRET).user_id_from(token)


def test_token_service_round_trip():
    """A token issued by the service is accepted and gives back the same user ID."""
    tokens = TokenService(TEST_JWT_SECRET, lifetime_seconds=60)
    issued = tokens.issue("us_abc")
    assert issued.expires_in == 60
    assert tokens.user_id_from(issued.value) == "us_abc"


def test_short_secret_is_refused():
    """A weak signing key is a configuration error, caught at startup."""
    with pytest.raises(ValueError):
        TokenService("too-short")
