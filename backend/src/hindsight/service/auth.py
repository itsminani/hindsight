"""Sign-in use case and access tokens (JWT).

A token is a signed statement "this is user us_..., valid until <time>". The API checks the
signature on every request, so it never needs to look up a session.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from hindsight.repositories.interfaces import UnitOfWork
from hindsight.service.errors import InvalidCredentials, Unauthorized
from hindsight.service.passwords import hash_password, verify_password

ISSUER = "hindsight"
AUDIENCE = "hindsight-api"
ALGORITHM = "HS256"

# Checked when the email is unknown, so a wrong email takes as long as a wrong password
# (otherwise response times would reveal which emails have accounts).
_DUMMY_HASH = hash_password("timing-equalizer-not-a-real-password")


@dataclass(frozen=True)
class AccessToken:
    """A signed token and how many seconds it stays valid."""

    value: str
    expires_in: int


class TokenService:
    """Creates and checks access tokens with a shared secret (HS256)."""

    def __init__(self, secret: str, lifetime_seconds: int = 900) -> None:
        """secret: signing key from settings. lifetime_seconds: 15 minutes by default."""
        if len(secret) < 32:
            raise ValueError("the JWT secret must be at least 32 characters")
        self._secret = secret
        self._lifetime = lifetime_seconds

    def issue(self, user_id: str) -> AccessToken:
        """Return a new token for this user."""
        now = datetime.now(UTC)
        claims = {
            "sub": user_id,
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": now,
            "exp": now + timedelta(seconds=self._lifetime),
        }
        return AccessToken(jwt.encode(claims, self._secret, algorithm=ALGORITHM), self._lifetime)

    def user_id_from(self, token: str) -> str:
        """Return the user ID inside a valid token; raise Unauthorized if it is invalid or expired."""
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=[ALGORITHM],  # never trust the algorithm named in the token itself
                audience=AUDIENCE,
                issuer=ISSUER,
                options={"require": ["sub", "exp", "iat"]},
            )
        except jwt.ExpiredSignatureError as error:
            raise Unauthorized("The access token has expired") from error
        except jwt.InvalidTokenError as error:
            raise Unauthorized("The access token is invalid") from error
        return claims["sub"]


class AuthService:
    """Use case: exchange an email and password for an access token."""

    def __init__(self, uow_factory: Callable[[], UnitOfWork], tokens: TokenService) -> None:
        """uow_factory: makes a new unit of work per call. tokens: the token service."""
        self._uow_factory = uow_factory
        self._tokens = tokens

    def sign_in(self, email: str, password: str) -> AccessToken:
        """Return a token for valid credentials; raise InvalidCredentials otherwise."""
        with self._uow_factory() as uow:
            user = uow.users.get_by_email(email)
        if user is None:
            verify_password(_DUMMY_HASH, password)
            raise InvalidCredentials()
        if not verify_password(user.password_hash, password):
            raise InvalidCredentials()
        return self._tokens.issue(user.id)
