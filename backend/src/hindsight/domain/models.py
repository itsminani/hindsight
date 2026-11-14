"""Domain objects: plain Python data with the business rules, no database or HTTP code (Ch5).

Repositories load and save these; the service layer works only with these.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


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
