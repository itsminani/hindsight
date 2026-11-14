"""Repository interfaces (Ch6, Listing 6.1 style): what the service layer may ask of storage.

The service layer depends only on these abstract classes. Which storage stands behind them
(PostgreSQL in the app, in-memory fakes in some tests) is decided once, in main.py.
"""

from abc import ABC, abstractmethod
from typing import Self

from hindsight.domain.models import Membership, Plan, Portfolio, Position, User


class UserRepository(ABC):
    """Home of users (seeded; there is no sign-up)."""

    @abstractmethod
    def get(self, user_id: str) -> User | None:
        """Return the user with this ID, or None."""

    @abstractmethod
    def get_by_email(self, email: str) -> User | None:
        """Return the user with this email (case-insensitive), or None."""

    @abstractmethod
    def add(self, user: User) -> None:
        """Store a new user."""


class PlanRepository(ABC):
    """Home of plans, their credits, and who belongs to which plan."""

    @abstractmethod
    def get(self, plan_id: str) -> Plan | None:
        """Return the plan, or None. Plain read, no lock."""

    @abstractmethod
    def get_for_update(self, plan_id: str) -> Plan | None:
        """Return the plan and lock its row until the transaction ends (SELECT ... FOR UPDATE).

        Any other transaction asking for the same plan waits here, so two requests can never
        both spend the same credits (Ch7).
        """

    @abstractmethod
    def add(self, plan: Plan) -> None:
        """Store a new plan."""

    @abstractmethod
    def save(self, plan: Plan) -> None:
        """Write back a plan's credit balances."""

    @abstractmethod
    def membership_of(self, user_id: str) -> Membership | None:
        """Return which plan the user belongs to and their role, or None."""

    @abstractmethod
    def set_membership(self, membership: Membership) -> None:
        """Put a user on a plan, replacing their previous membership (one plan at a time)."""

    @abstractmethod
    def count_members(self, plan_id: str) -> int:
        """Return how many users belong to the plan."""


class PortfolioRepository(ABC):
    """Home of portfolios and their positions, loaded and saved together."""

    @abstractmethod
    def get(self, portfolio_id: str) -> Portfolio | None:
        """Return the portfolio with its positions, or None."""

    @abstractmethod
    def list_for_owner(self, owner_id: str) -> list[Portfolio]:
        """Return the owner's portfolios with their positions, oldest first."""

    @abstractmethod
    def add(self, portfolio: Portfolio) -> Portfolio:
        """Store a new portfolio; returns it with database-filled fields (created_at)."""

    @abstractmethod
    def add_position(self, portfolio_id: str, position: Position) -> None:
        """Store a new position in an existing portfolio."""


class UnitOfWork(ABC):
    """One business transaction: every repository inside it commits or rolls back together.

    Usage in the service layer:
        with uow:
            plan = uow.plans.get_for_update(plan_id)
            ...
            uow.commit()
    Leaving the block without commit() rolls everything back.
    """

    users: UserRepository
    plans: PlanRepository
    portfolios: PortfolioRepository

    @abstractmethod
    def __enter__(self) -> Self:
        """Start the transaction."""

    @abstractmethod
    def __exit__(self, *exc_info: object) -> None:
        """End the transaction, rolling back anything not committed."""

    @abstractmethod
    def commit(self) -> None:
        """Make every change in this transaction permanent."""
