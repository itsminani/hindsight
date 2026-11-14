"""Alembic entry point: connects to the database from our settings and runs migrations.

Run from backend/:  python -m uv run alembic upgrade head
"""

from alembic import context
from sqlalchemy import create_engine, pool

from hindsight.config import get_settings
from hindsight.logging_setup import configure_logging
from hindsight.repositories.orm import Base

settings = get_settings()
configure_logging(settings.log_level)

# The models' metadata: "alembic check" compares it with the real database.
target_metadata = Base.metadata


def _database_url() -> str:
    """The URL to migrate: one passed in by code (the tests' own database), else the settings'."""
    return context.config.attributes.get("database_url") or settings.require_database_url()


def run_migrations_offline() -> None:
    """Print the SQL instead of running it (alembic upgrade head --sql), e.g. for a DBA review."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database and apply the pending migrations in one transaction."""
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
