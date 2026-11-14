"""Database connection: one engine (connection pool) per process, one session per transaction."""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


class Database:
    """Owns the connection pool. Create one at startup and share it (it is thread-safe)."""

    def __init__(self, url: str) -> None:
        """Build the pool. No connection is opened until something needs one."""
        self.engine: Engine = create_engine(
            url,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,  # drop dead connections (e.g. after a database restart) before using them
            connect_args={"connect_timeout": 3},  # fail fast instead of hanging when the DB is down
        )
        self._session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def new_session(self) -> Session:
        """Open a new session (a transaction starts on first use)."""
        return self._session_factory()

    def ping(self) -> None:
        """Run SELECT 1; raises if the database cannot be reached. Used by /health/ready."""
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def dispose(self) -> None:
        """Close every pooled connection (on shutdown)."""
        self.engine.dispose()
