"""Domain objects: plain Python data with the business rules, no database or HTTP code (Ch5).

Repositories load and save these; the service layer works only with these.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class InsufficientCredits(Exception):
    """A plan does not have enough available credits for what was asked."""

    def __init__(self, needed: int, available: int) -> None:
        """needed: credits asked for. available: credits the plan has."""
        super().__init__(f"needs {needed} credits, plan has {available}")
        self.needed = needed
        self.available = available


class PlanKind(StrEnum):
    """Personal plans have one member; shared plans can have several."""

    PERSONAL = "personal"
    SHARED = "shared"


class Role(StrEnum):
    """A user's role on the plan they belong to."""

    OWNER = "owner"
    MEMBER = "member"


@dataclass
class User:
    """Someone who can sign in."""

    id: str
    email: str
    password_hash: str


@dataclass
class Plan:
    """A pool of credits shared by its members."""

    id: str
    owner_id: str
    kind: PlanKind
    credits_available: int
    credits_held: int

    def hold(self, credits: int) -> None:
        """Reserve credits for a pending report: available -> held. Refuses to go below zero."""
        if credits <= 0:
            raise ValueError("credits to hold must be positive")
        if credits > self.credits_available:
            raise InsufficientCredits(credits, self.credits_available)
        self.credits_available -= credits
        self.credits_held += credits

    def charge(self, credits: int) -> None:
        """A report finished: its held credits are spent for good."""
        if credits > self.credits_held:
            raise ValueError("cannot charge more than is held")
        self.credits_held -= credits

    def release(self, credits: int) -> None:
        """A report failed: give its held credits back (compensation)."""
        if credits > self.credits_held:
            raise ValueError("cannot release more than is held")
        self.credits_held -= credits
        self.credits_available += credits


@dataclass
class Membership:
    """Which plan a user draws credits from, and their role on it."""

    user_id: str
    plan_id: str
    role: Role


@dataclass
class Position:
    """Shares of one stock, bought on a date and maybe sold later."""

    id: str
    ticker: str
    shares: int
    buy_date: date
    sell_date: date | None = None

    def __post_init__(self) -> None:
        """Refuse positions that cannot exist (the database checks the same rules again)."""
        if self.shares <= 0:
            raise ValueError("shares must be positive")
        if self.sell_date is not None and self.sell_date < self.buy_date:
            raise ValueError("sell_date cannot be before buy_date")

    @property
    def is_sold(self) -> bool:
        """True once the position has a sell date (only sold positions can be in a report)."""
        return self.sell_date is not None


@dataclass
class Portfolio:
    """A named group of positions owned by one user."""

    id: str
    owner_id: str
    name: str
    created_at: datetime | None = None  # set by the database when the portfolio is saved
    positions: list[Position] = field(default_factory=list)


class ReportStatus(StrEnum):
    """Where a report is in its life."""

    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


@dataclass
class ReportItem:
    """One position in a report; the money fields stay empty until the worker fills them."""

    position_id: str
    ticker: str
    shares: int
    sold_for: Decimal | None = None
    worth_today: Decimal | None = None
    difference: Decimal | None = None


@dataclass
class Report:
    """A hindsight report: which positions, who asked, which plan pays, and how it went."""

    id: str
    portfolio_id: str
    requested_by: str
    plan_id: str
    credits_held: int
    status: ReportStatus = ReportStatus.PENDING
    credits_charged: int = 0
    failure_reason: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    items: list[ReportItem] = field(default_factory=list)


def report_cost(positions: list[Position]) -> int:
    """Price of a report: one credit per distinct ticker (two AAPL lots cost one credit)."""
    return len({p.ticker for p in positions})


@dataclass(frozen=True)
class StoredResponse:
    """The response saved for an Idempotency-Key, replayed when the same request is retried."""

    request_hash: str
    status: int
    body: dict
