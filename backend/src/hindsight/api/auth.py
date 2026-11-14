"""POST /auth/token: sign in with email and password, get a short-lived access token."""

from typing import Annotated

from fastapi import APIRouter, Depends

from hindsight.api.deps import get_auth_service
from hindsight.api.schemas import TokenRequest, TokenResponse
from hindsight.service.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
def create_token(body: TokenRequest, auth: Annotated[AuthService, Depends(get_auth_service)]) -> TokenResponse:
    """Check the credentials and return a Bearer token (401 invalid_credentials if wrong)."""
    token = auth.sign_in(body.email, body.password)
    return TokenResponse(access_token=token.value, expires_in=token.expires_in)
