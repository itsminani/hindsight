"""FastAPI dependencies: how a route gets its services and the signed-in user.

.NET equivalent: constructor injection from the DI container, and [Authorize] + User.Identity.
"""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from hindsight.service.auth import AuthService, TokenService
from hindsight.service.errors import Unauthorized
from hindsight.service.portfolios import PortfolioService

# auto_error=False: we send our own Problem response instead of FastAPI's default 403.
_bearer = HTTPBearer(auto_error=False)


def _service(request: Request, name: str):
    """Fetch a service built in main.py; a missing one is a configuration bug, so fail loudly (500)."""
    service = getattr(request.app.state, name, None)
    if service is None:
        raise RuntimeError(f"{name} is not configured (is HINDSIGHT_DATABASE_URL set?)")
    return service


def get_auth_service(request: Request) -> AuthService:
    """The AuthService built once in main.py."""
    return _service(request, "auth_service")


def get_token_service(request: Request) -> TokenService:
    """The TokenService built once in main.py."""
    return _service(request, "token_service")


def get_portfolio_service(request: Request) -> PortfolioService:
    """The PortfolioService built once in main.py."""
    return _service(request, "portfolio_service")


def current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> str:
    """The ID of the user whose valid token came with the request; otherwise 401 unauthorized."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise Unauthorized("Send an access token: Authorization: Bearer <token>")
    return tokens.user_id_from(credentials.credentials)


CurrentUser = Annotated[str, Depends(current_user_id)]
