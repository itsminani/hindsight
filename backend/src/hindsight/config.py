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
    """

    model_config = SettingsConfigDict(env_prefix="HINDSIGHT_", env_file=".env", extra="ignore")

    env: str = "local"
    log_level: str = "INFO"
    contract_path: Path = _REPO_ROOT / "contract" / "openapi.yaml"


@lru_cache
def get_settings() -> Settings:
    """Return the settings, loaded once and then reused (cached)."""
    return Settings()
