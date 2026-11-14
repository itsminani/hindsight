"""SQLAlchemy table mappings (data-source layer, Ch6).

These classes describe the database tables, nothing more. Business rules live in `domain/`,
and the rest of the app reaches these rows only through repositories.
The diagram for these tables is in docs/data-model.md.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Predictable constraint names, so later migrations can find and change them by name.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Money = Numeric(14, 2)


class Base(DeclarativeBase):
    """Parent of every table class; holds the shared metadata Alembic compares against."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _created_at() -> Mapped[datetime]:
    """A 'created at' column that PostgreSQL fills in with the current time."""
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    """Someone who can sign in. Users are seeded; there is no sign-up endpoint for now."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class Plan(Base):
    """A credit plan. Its row is the contended resource that reports lock with FOR UPDATE."""

    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint("kind IN ('personal', 'shared')", name="kind"),
        CheckConstraint("credits_available >= 0", name="credits_available_not_negative"),
        CheckConstraint("credits_held >= 0", name="credits_held_not_negative"),
        # Each user has exactly one personal plan.
        Index(
            "uq_plans_one_personal_per_owner",
            "owner_id",
            unique=True,
            postgresql_where=text("kind = 'personal'"),
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(Text)
    credits_available: Mapped[int] = mapped_column(Integer, server_default="0")
    credits_held: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = _created_at()


class PlanMember(Base):
    """Which plan a user currently draws credits from. One row per user, so one plan at a time."""

    __tablename__ = "plan_members"
    __table_args__ = (CheckConstraint("role IN ('owner', 'member')", name="role"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"), index=True)
    role: Mapped[str] = mapped_column(Text)
    joined_at: Mapped[datetime] = _created_at()


class Portfolio(Base):
    """A named group of positions owned by one user."""

    __tablename__ = "portfolios"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class Position(Base):
    """Shares of one stock bought on a date and maybe sold later. Deleted with its portfolio."""

    __tablename__ = "positions"
    __table_args__ = (
        CheckConstraint("shares > 0", name="shares_positive"),
        CheckConstraint("sell_date IS NULL OR sell_date >= buy_date", name="sell_after_buy"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    portfolio_id: Mapped[str] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), index=True
    )
    ticker: Mapped[str] = mapped_column(Text)
    shares: Mapped[int] = mapped_column(Integer)
    buy_date: Mapped[date] = mapped_column(Date)
    sell_date: Mapped[date | None] = mapped_column(Date)


class Report(Base):
    """A hindsight report request and its outcome, including the credits it held or charged."""

    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'done', 'failed')", name="status"),
        CheckConstraint("credits_held >= 0", name="credits_held_not_negative"),
        CheckConstraint("credits_charged >= 0", name="credits_charged_not_negative"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id"), index=True)
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"))
    status: Mapped[str] = mapped_column(Text, server_default="pending")
    credits_held: Mapped[int] = mapped_column(Integer)
    credits_charged: Mapped[int] = mapped_column(Integer, server_default="0")
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReportItem(Base):
    """One line of a report: what one position was sold for and what it would be worth today."""

    __tablename__ = "report_items"

    report_id: Mapped[str] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), primary_key=True
    )
    position_id: Mapped[str] = mapped_column(ForeignKey("positions.id"), primary_key=True)
    sold_for: Mapped[Decimal | None] = mapped_column(Money)
    worth_today: Mapped[Decimal | None] = mapped_column(Money)
    difference: Mapped[Decimal | None] = mapped_column(Money)


class IdempotencyKey(Base):
    """The saved response for an Idempotency-Key, so a retried request gets the same answer."""

    __tablename__ = "idempotency_keys"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    request_hash: Mapped[str] = mapped_column(Text)
    response_status: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


class Job(Base):
    """Background work for one report. Inserted in the same transaction that holds the credits."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="status"),
        # The worker looks for queued jobs that are due.
        Index("ix_jobs_status_run_after", "status", "run_after"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    report_id: Mapped[str] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[str] = mapped_column(Text, server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
