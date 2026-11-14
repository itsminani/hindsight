"""Composition root: builds the app and wires the layers together."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI

from hindsight.api import health
from hindsight.api.errors import register_error_handlers
from hindsight.api.middleware import RequestIdMiddleware
from hindsight.config import Settings, get_settings
from hindsight.logging_setup import configure_logging
from hindsight.repositories.db import Database


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app: logging, middleware, error handlers, routes, and the /docs contract.

    settings: optional override (tests pass their own); defaults to the environment settings.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    database = Database(settings.database_url) if settings.database_url else None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Run on startup and shutdown: close the database pool cleanly when the app stops."""
        yield
        if database is not None:
            database.dispose()

    app = FastAPI(title="Hindsight API", version="1.0.0", lifespan=lifespan)
    # Without a database URL the app still starts (liveness works), but /health/ready says 503.
    app.state.database = database
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)
    app.include_router(health.router)

    # Swagger UI (/docs) shows the hand-written contract
    contract = yaml.safe_load(settings.contract_path.read_text(encoding="utf-8"))
    app.openapi = lambda: contract

    return app


app = create_app()
