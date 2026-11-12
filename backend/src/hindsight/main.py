"""Composition root: builds the app and wires the layers together."""

import yaml
from fastapi import FastAPI

from hindsight.api import health
from hindsight.api.errors import register_error_handlers
from hindsight.api.middleware import RequestIdMiddleware
from hindsight.config import Settings, get_settings
from hindsight.logging_setup import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app: logging, middleware, error handlers, routes, and the /docs contract.

    settings: optional override (tests pass their own); defaults to the environment settings.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="Hindsight API", version="1.0.0")
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)
    app.include_router(health.router)

    # Swagger UI (/docs) shows the hand-written contract
    contract = yaml.safe_load(settings.contract_path.read_text(encoding="utf-8"))
    app.openapi = lambda: contract

    return app


app = create_app()
