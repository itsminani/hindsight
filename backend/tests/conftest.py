"""Shared test fixtures, including a real, throwaway PostgreSQL database for integration tests.

Integration tests never touch your dev data: they use a separate database whose name must end
in "_test" (by default "hindsight_test" on the same server), created and migrated automatically.
Without a reachable PostgreSQL they are skipped locally, but they FAIL in CI (CI=true), so a
broken pipeline can never pass by silently skipping them.
"""

import os
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url

from hindsight.config import get_settings
from hindsight.repositories.db import Database
from hindsight.repositories.orm import Base
from hindsight.repositories.postgres import PostgresUnitOfWork

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _test_database_url() -> str | None:
    """HINDSIGHT_TEST_DATABASE_URL if set, else the app's URL with the database renamed to *_test."""
    explicit = os.environ.get("HINDSIGHT_TEST_DATABASE_URL")
    if explicit:
        return explicit
    app_url = get_settings().database_url
    if not app_url:
        return None
    url = make_url(app_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


def _create_database_if_missing(url: str) -> None:
    """Create the test database through the server's default "postgres" database."""
    parsed = make_url(url)
    admin = parsed.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
    with psycopg.connect(admin, autocommit=True, connect_timeout=3) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (parsed.database,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{parsed.database}"')


@pytest.fixture(scope="session")
def database() -> Database:
    """A migrated, empty test database, shared by the whole test run."""
    url = _test_database_url()
    reason = None
    if url is None:
        reason = "HINDSIGHT_DATABASE_URL is not set"
    elif not make_url(url).database.endswith("_test"):
        pytest.fail(f"refusing to run tests on database {make_url(url).database!r}: name must end in _test")
    else:
        try:
            _create_database_if_missing(url)
        except psycopg.OperationalError as error:
            reason = f"PostgreSQL is not reachable ({error.__class__.__name__}); run: docker compose up -d db"
    if reason:
        if os.environ.get("CI"):
            pytest.fail(reason)
        pytest.skip(reason)

    config = Config(toml_file=str(BACKEND_DIR / "pyproject.toml"))
    config.attributes["database_url"] = url
    command.upgrade(config, "head")

    db = Database(url)
    yield db
    db.dispose()


@pytest.fixture
def clean_database(database: Database) -> Database:
    """The test database with every table emptied, so each test starts from nothing."""
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with database.engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    return database


@pytest.fixture
def uow(clean_database: Database) -> PostgresUnitOfWork:
    """A fresh unit of work on the clean test database."""
    return PostgresUnitOfWork(clean_database)


TEST_JWT_SECRET = "test-secret-" + "x" * 32
DEMO_PASSWORD = "demo-password"


@pytest.fixture
def seeded_database(clean_database: Database) -> Database:
    """The clean test database with the demo data (Alice, Bob, Carol) loaded."""
    from hindsight.seed import seed

    seed(clean_database, DEMO_PASSWORD)
    return clean_database


@pytest.fixture
def app(seeded_database: Database):
    """The real app wired to the seeded test database (never your dev database)."""
    from hindsight.config import Settings
    from hindsight.main import create_app

    url = seeded_database.engine.url.render_as_string(hide_password=False)
    return create_app(Settings(database_url=url, jwt_secret=TEST_JWT_SECRET, _env_file=None))


@pytest.fixture
def api(app):
    """An HTTP test client for the app (500s come back as responses, not exceptions)."""
    from fastapi.testclient import TestClient

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def sign_in(api, email: str) -> dict[str, str]:
    """Sign in as a demo user and return the Authorization header to send with requests."""
    response = api.post("/auth/token", json={"email": email, "password": DEMO_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}
