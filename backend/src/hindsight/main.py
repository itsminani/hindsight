"""Composition root: builds the app and wires the layers together."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI

from hindsight.api import auth, health, plans, portfolios, prices, reports
from hindsight.api.errors import register_error_handlers
from hindsight.api.middleware import RequestIdMiddleware
from hindsight.config import Settings, get_settings
from hindsight.integrations.factory import price_provider_from
from hindsight.logging_setup import configure_logging
from hindsight.repositories.db import Database
from hindsight.repositories.postgres import PostgresUnitOfWork
from hindsight.service.auth import AuthService, TokenService
from hindsight.service.plans import PlanService
from hindsight.service.portfolios import PortfolioService
from hindsight.service.prices import PriceService
from hindsight.service.reports import ReportService


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
    _wire_services(app, settings, database)
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(portfolios.router)
    app.include_router(reports.router)
    app.include_router(plans.router)
    app.include_router(prices.router)

    # Swagger UI (/docs) shows the hand-written contract
    contract = yaml.safe_load(settings.contract_path.read_text(encoding="utf-8"))
    app.openapi = lambda: contract

    return app


def _wire_services(app: FastAPI, settings: Settings, database: Database | None) -> None:
    """Build the services once and keep them on app.state, where api/deps.py finds them.

    This is the only place that picks PostgreSQL behind the repository interfaces.
    Without a database (some tests), no services exist and routes that need one fail loudly.
    """
    for name in (
        "token_service",
        "auth_service",
        "portfolio_service",
        "report_service",
        "plan_service",
        "price_service",
    ):
        setattr(app.state, name, None)
    if database is None:
        return

    def uow_factory() -> PostgresUnitOfWork:
        """A new unit of work (one transaction) for each use case call."""
        return PostgresUnitOfWork(database)

    tokens = TokenService(settings.require_jwt_secret(), settings.token_lifetime_seconds)
    app.state.token_service = tokens
    app.state.auth_service = AuthService(uow_factory, tokens)
    app.state.portfolio_service = PortfolioService(uow_factory)
    app.state.report_service = ReportService(uow_factory)
    app.state.plan_service = PlanService(uow_factory)
    app.state.price_service = PriceService(price_provider_from(settings))


app = create_app()
