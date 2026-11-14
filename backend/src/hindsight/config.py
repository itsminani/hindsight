from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/hindsight/config.py -> repository root is 4 levels up
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """App settings, read from HINDSIGHT_* environment variables (or a local .env file).

    env: where the app runs ("local", "ci", "prod").
    log_level: minimum log level (DEBUG, INFO, WARNING...).
    contract_path: the OpenAPI file shown at /docs.
    database_url: PostgreSQL connection string. No default on purpose (it holds a password);
        anything that touches the database fails loudly if it is missing.
    seed_password: password given to the demo users by the seed script (local/demo only).
    jwt_secret: key that signs access tokens (32+ characters). No default, like database_url.
    token_lifetime_seconds: how long an access token stays valid (15 minutes).
    """

    model_config = SettingsConfigDict(env_prefix="HINDSIGHT_", env_file=_REPO_ROOT / ".env", extra="ignore")

    env: str = "local"
    log_level: str = "INFO"
    contract_path: Path = _REPO_ROOT / "contract" / "openapi.yaml"
    database_url: str | None = None
    seed_password: str | None = None
    jwt_secret: str | None = None
    token_lifetime_seconds: int = 900

    def require_database_url(self) -> str:
        """Return the database URL, or stop with a clear message if it was never set."""
        if not self.database_url:
            raise RuntimeError("HINDSIGHT_DATABASE_URL is not set (see .env.example)")
        return self.database_url

    def require_jwt_secret(self) -> str:
        """Return the token signing key, or stop with a clear message if it was never set."""
        if not self.jwt_secret:
            raise RuntimeError("HINDSIGHT_JWT_SECRET is not set (see .env.example)")
        return self.jwt_secret


@lru_cache
def get_settings() -> Settings:
    """Return the settings, loaded once and then reused (cached)."""
    return Settings()
