"""PostgreSQL implementations of the repository interfaces, using SQLAlchemy.

Each repository converts between table rows (orm.py) and domain objects (domain/models.py),
so nothing above this layer ever sees a SQLAlchemy object.
"""

from typing import Self

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from hindsight.domain.ids import new_id
from hindsight.domain.models import (
    Membership,
    Plan,
    PlanKind,
    Portfolio,
    Position,
    Report,
    ReportItem,
    ReportStatus,
    Role,
    StoredResponse,
    User,
)
from hindsight.repositories import orm
from hindsight.repositories.db import Database
from hindsight.repositories.interfaces import (
    IdempotencyStore,
    JobQueue,
    KeyAlreadyUsed,
    PlanRepository,
    PortfolioRepository,
    ReportRepository,
    UnitOfWork,
    UserRepository,
)


def _to_user(row: orm.User) -> User:
    """Table row -> domain User."""
    return User(id=row.id, email=row.email, password_hash=row.password_hash)


def _to_plan(row: orm.Plan) -> Plan:
    """Table row -> domain Plan."""
    return Plan(
        id=row.id,
        owner_id=row.owner_id,
        kind=PlanKind(row.kind),
        credits_available=row.credits_available,
        credits_held=row.credits_held,
    )


def _to_position(row: orm.Position) -> Position:
    """Table row -> domain Position."""
    return Position(
        id=row.id, ticker=row.ticker, shares=row.shares, buy_date=row.buy_date, sell_date=row.sell_date
    )


class PostgresUserRepository(UserRepository):
    """Users stored in the users table."""

    def __init__(self, session: Session) -> None:
        """session: the unit of work's session; this repository never commits by itself."""
        self._s = session

    def get(self, user_id: str) -> User | None:
        """Return the user with this ID, or None."""
        row = self._s.get(orm.User, user_id)
        return _to_user(row) if row else None

    def get_by_email(self, email: str) -> User | None:
        """Return the user with this email (emails are stored lower-case), or None."""
        row = self._s.scalar(select(orm.User).where(orm.User.email == email.lower()))
        return _to_user(row) if row else None

    def add(self, user: User) -> None:
        """Insert a new user, with the email lower-cased."""
        self._s.add(orm.User(id=user.id, email=user.email.lower(), password_hash=user.password_hash))
        self._s.flush()


class PostgresPlanRepository(PlanRepository):
    """Plans and memberships stored in the plans and plan_members tables."""

    def __init__(self, session: Session) -> None:
        """session: the unit of work's session; this repository never commits by itself."""
        self._s = session

    def get(self, plan_id: str) -> Plan | None:
        """Return the plan without locking it, or None."""
        row = self._s.get(orm.Plan, plan_id)
        return _to_plan(row) if row else None

    def get_for_update(self, plan_id: str) -> Plan | None:
        """Return the plan and lock its row (SELECT ... FOR UPDATE) until commit or rollback.

        populate_existing makes SQLAlchemy use the freshly locked values even if this session
        had already loaded the row earlier.
        """
        row = self._s.scalar(
            select(orm.Plan)
            .where(orm.Plan.id == plan_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return _to_plan(row) if row else None

    def add(self, plan: Plan) -> None:
        """Insert a new plan."""
        self._s.add(
            orm.Plan(
                id=plan.id,
                owner_id=plan.owner_id,
                kind=plan.kind.value,
                credits_available=plan.credits_available,
                credits_held=plan.credits_held,
            )
        )
        self._s.flush()

    def save(self, plan: Plan) -> None:
        """Write back the plan's credit balances. The CHECK constraints refuse negative values."""
        row = self._s.get(orm.Plan, plan.id)
        if row is None:
            raise LookupError(f"plan {plan.id} does not exist")
        row.credits_available = plan.credits_available
        row.credits_held = plan.credits_held
        self._s.flush()

    def membership_of(self, user_id: str) -> Membership | None:
        """Return the user's plan and role, or None if they belong to no plan."""
        row = self._s.get(orm.PlanMember, user_id)
        return Membership(user_id=row.user_id, plan_id=row.plan_id, role=Role(row.role)) if row else None

    def set_membership(self, membership: Membership) -> None:
        """Insert or replace the user's membership (user_id is the primary key: one plan at a time)."""
        row = self._s.get(orm.PlanMember, membership.user_id)
        if row is None:
            self._s.add(
                orm.PlanMember(
                    user_id=membership.user_id, plan_id=membership.plan_id, role=membership.role.value
                )
            )
        else:
            row.plan_id = membership.plan_id
            row.role = membership.role.value
            row.joined_at = func.now()
        self._s.flush()

    def count_members(self, plan_id: str) -> int:
        """Return how many users belong to the plan."""
        return self._s.scalar(
            select(func.count()).select_from(orm.PlanMember).where(orm.PlanMember.plan_id == plan_id)
        ) or 0

    def personal_plan_of(self, user_id: str) -> Plan | None:
        """Return the user's personal plan, or None."""
        row = self._s.scalar(
            select(orm.Plan).where(orm.Plan.owner_id == user_id, orm.Plan.kind == PlanKind.PERSONAL.value)
        )
        return _to_plan(row) if row else None


class PostgresPortfolioRepository(PortfolioRepository):
    """Portfolios and positions stored in the portfolios and positions tables."""

    def __init__(self, session: Session) -> None:
        """session: the unit of work's session; this repository never commits by itself."""
        self._s = session

    def _positions_by_portfolio(self, portfolio_ids: list[str]) -> dict[str, list[Position]]:
        """Load the positions of many portfolios in ONE query (avoids the N+1 problem, Ch6 p.87)."""
        result: dict[str, list[Position]] = {pid: [] for pid in portfolio_ids}
        if not portfolio_ids:
            return result
        rows = self._s.scalars(
            select(orm.Position)
            .where(orm.Position.portfolio_id.in_(portfolio_ids))
            .order_by(orm.Position.buy_date, orm.Position.id)
        )
        for row in rows:
            result[row.portfolio_id].append(_to_position(row))
        return result

    def _to_portfolio(self, row: orm.Portfolio, positions: list[Position]) -> Portfolio:
        """Table row + its positions -> domain Portfolio."""
        return Portfolio(
            id=row.id, owner_id=row.owner_id, name=row.name, created_at=row.created_at, positions=positions
        )

    def get(self, portfolio_id: str) -> Portfolio | None:
        """Return the portfolio with its positions, or None."""
        row = self._s.get(orm.Portfolio, portfolio_id)
        if row is None:
            return None
        return self._to_portfolio(row, self._positions_by_portfolio([row.id])[row.id])

    def list_for_owner(self, owner_id: str) -> list[Portfolio]:
        """Return the owner's portfolios (oldest first), each with its positions: 2 queries in total."""
        rows = list(
            self._s.scalars(
                select(orm.Portfolio)
                .where(orm.Portfolio.owner_id == owner_id)
                .order_by(orm.Portfolio.created_at, orm.Portfolio.id)
            )
        )
        positions = self._positions_by_portfolio([r.id for r in rows])
        return [self._to_portfolio(r, positions[r.id]) for r in rows]

    def add(self, portfolio: Portfolio) -> Portfolio:
        """Insert a new portfolio (and any positions it already has); returns it with created_at."""
        row = orm.Portfolio(id=portfolio.id, owner_id=portfolio.owner_id, name=portfolio.name)
        self._s.add(row)
        self._s.flush()
        self._s.refresh(row)  # read back created_at, which PostgreSQL filled in
        for position in portfolio.positions:
            self.add_position(portfolio.id, position)
        return self._to_portfolio(row, list(portfolio.positions))

    def add_position(self, portfolio_id: str, position: Position) -> None:
        """Insert a new position into the portfolio."""
        self._s.add(
            orm.Position(
                id=position.id,
                portfolio_id=portfolio_id,
                ticker=position.ticker,
                shares=position.shares,
                buy_date=position.buy_date,
                sell_date=position.sell_date,
            )
        )
        self._s.flush()


class PostgresReportRepository(ReportRepository):
    """Reports stored in the reports and report_items tables."""

    def __init__(self, session: Session) -> None:
        """session: the unit of work's session; this repository never commits by itself."""
        self._s = session

    def add(self, report: Report) -> Report:
        """Insert the report and one report_items row per position; returns it with created_at."""
        row = orm.Report(
            id=report.id,
            portfolio_id=report.portfolio_id,
            requested_by=report.requested_by,
            plan_id=report.plan_id,
            status=report.status.value,
            credits_held=report.credits_held,
            credits_charged=report.credits_charged,
        )
        self._s.add(row)
        self._s.flush()
        self._s.add_all(orm.ReportItem(report_id=report.id, position_id=i.position_id) for i in report.items)
        self._s.flush()
        self._s.refresh(row)
        report.created_at = row.created_at
        return report

    def get(self, report_id: str) -> Report | None:
        """Return the report with its items (ticker and shares come from the positions table)."""
        row = self._s.get(orm.Report, report_id)
        if row is None:
            return None
        items = self._s.execute(
            select(orm.ReportItem, orm.Position.ticker, orm.Position.shares)
            .join(orm.Position, orm.Position.id == orm.ReportItem.position_id)
            .where(orm.ReportItem.report_id == report_id)
            .order_by(orm.Position.ticker, orm.Position.id)
        )
        return Report(
            id=row.id,
            portfolio_id=row.portfolio_id,
            requested_by=row.requested_by,
            plan_id=row.plan_id,
            credits_held=row.credits_held,
            status=ReportStatus(row.status),
            credits_charged=row.credits_charged,
            failure_reason=row.failure_reason,
            created_at=row.created_at,
            completed_at=row.completed_at,
            items=[
                ReportItem(item.position_id, ticker, shares, item.sold_for, item.worth_today, item.difference)
                for item, ticker, shares in items
            ],
        )


class PostgresJobQueue(JobQueue):
    """Jobs stored in the jobs table, picked up later by the worker."""

    def __init__(self, session: Session) -> None:
        """session: the unit of work's session, so the job commits with the business change or not at all."""
        self._s = session

    def enqueue_report(self, report_id: str) -> str:
        """Insert a queued job for the report; returns its ID."""
        job_id = new_id("job")
        self._s.add(orm.Job(id=job_id, report_id=report_id))
        self._s.flush()
        return job_id


class PostgresIdempotencyStore(IdempotencyStore):
    """Saved responses in the idempotency_keys table, keyed by (user, key)."""

    def __init__(self, session: Session) -> None:
        """session: the unit of work's session; this repository never commits by itself."""
        self._s = session

    def get(self, user_id: str, key: str) -> StoredResponse | None:
        """Return the saved response for this user's key, or None."""
        row = self._s.get(orm.IdempotencyKey, (user_id, key))
        if row is None:
            return None
        return StoredResponse(row.request_hash, row.response_status, row.response_body)

    def put(self, user_id: str, key: str, response: StoredResponse) -> None:
        """Insert the response. If a concurrent request inserted the same key first, the primary key
        refuses this one and we raise KeyAlreadyUsed (the caller rolls back and replays theirs)."""
        self._s.add(
            orm.IdempotencyKey(
                user_id=user_id,
                key=key,
                request_hash=response.request_hash,
                response_status=response.status,
                response_body=response.body,
            )
        )
        try:
            self._s.flush()
        except IntegrityError as error:
            if getattr(error.orig.diag, "constraint_name", None) == "pk_idempotency_keys":
                raise KeyAlreadyUsed(key) from error
            raise


class PostgresUnitOfWork(UnitOfWork):
    """A unit of work over one SQLAlchemy session = one PostgreSQL transaction.

    .NET equivalent: a scoped DbContext, where SaveChanges() is commit().
    """

    def __init__(self, database: Database) -> None:
        """database: the shared connection pool."""
        self._database = database
        self._session: Session | None = None

    def __enter__(self) -> Self:
        """Open a session and attach the repositories to it."""
        self._session = self._database.new_session()
        self.users = PostgresUserRepository(self._session)
        self.plans = PostgresPlanRepository(self._session)
        self.portfolios = PostgresPortfolioRepository(self._session)
        self.reports = PostgresReportRepository(self._session)
        self.jobs = PostgresJobQueue(self._session)
        self.idempotency = PostgresIdempotencyStore(self._session)
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Roll back whatever was not committed, then return the connection to the pool."""
        assert self._session is not None
        self._session.rollback()
        self._session.close()
        self._session = None

    def commit(self) -> None:
        """Commit the transaction."""
        assert self._session is not None
        self._session.commit()
