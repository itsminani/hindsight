"""Integration tests: the PostgreSQL repositories against a real (throwaway) database."""

import threading
import time
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from hindsight.domain.ids import new_id
from hindsight.domain.models import Membership, Plan, PlanKind, Portfolio, Position, Role, User
from hindsight.repositories.postgres import PostgresUnitOfWork


def _user(email: str = "alice@example.com") -> User:
    """A user with a fresh ID."""
    return User(id=new_id("user"), email=email, password_hash="not-a-real-hash")


def test_user_round_trip_and_case_insensitive_email(uow):
    """A saved user can be found by ID and by email in any letter case."""
    user = _user("Alice@Example.com")
    with uow:
        uow.users.add(user)
        uow.commit()
    with uow:
        assert uow.users.get(user.id).email == "alice@example.com"
        assert uow.users.get_by_email("ALICE@example.COM").id == user.id
        assert uow.users.get("us_missing") is None


def test_without_commit_nothing_is_saved(uow):
    """Leaving the unit of work without commit() rolls everything back."""
    user = _user()
    with uow:
        uow.users.add(user)
    with uow:
        assert uow.users.get(user.id) is None


def test_portfolio_with_positions_round_trip(uow):
    """Portfolios come back with their positions and the database's created_at."""
    owner = _user()
    portfolio = Portfolio(id=new_id("portfolio"), owner_id=owner.id, name="Retirement")
    sold = Position(new_id("position"), "AAPL", 10, date(2020, 1, 2), date(2021, 6, 1))
    held = Position(new_id("position"), "MSFT", 5, date(2022, 3, 4))
    with uow:
        uow.users.add(owner)
        saved = uow.portfolios.add(portfolio)
        uow.portfolios.add_position(portfolio.id, sold)
        uow.portfolios.add_position(portfolio.id, held)
        uow.commit()
    assert saved.created_at is not None
    with uow:
        loaded = uow.portfolios.get(portfolio.id)
        listed = uow.portfolios.list_for_owner(owner.id)
    assert [p.ticker for p in loaded.positions] == ["AAPL", "MSFT"]
    assert loaded.positions[0].sell_date == date(2021, 6, 1)
    assert [p.id for p in listed] == [portfolio.id]


def test_list_for_owner_never_returns_other_users_portfolios(uow):
    """Each owner only sees their own portfolios."""
    alice, bob = _user("alice@example.com"), _user("bob@example.com")
    with uow:
        uow.users.add(alice)
        uow.users.add(bob)
        uow.portfolios.add(Portfolio(id=new_id("portfolio"), owner_id=alice.id, name="A"))
        uow.portfolios.add(Portfolio(id=new_id("portfolio"), owner_id=bob.id, name="B"))
        uow.commit()
    with uow:
        assert [p.name for p in uow.portfolios.list_for_owner(alice.id)] == ["A"]


def _plan_with_owner(uow, credits: int) -> tuple[User, Plan]:
    """Create a user who owns a shared plan with some credits (helper for the plan tests)."""
    owner = _user()
    plan = Plan(new_id("plan"), owner.id, PlanKind.SHARED, credits_available=credits, credits_held=0)
    with uow:
        uow.users.add(owner)
        uow.plans.add(plan)
        uow.plans.set_membership(Membership(owner.id, plan.id, Role.OWNER))
        uow.commit()
    return owner, plan


def test_membership_is_one_plan_at_a_time(uow):
    """Moving a user to another plan replaces their old membership."""
    owner, plan = _plan_with_owner(uow, credits=5)
    bob = _user("bob@example.com")
    personal = Plan(new_id("plan"), bob.id, PlanKind.PERSONAL, credits_available=1, credits_held=0)
    with uow:
        uow.users.add(bob)
        uow.plans.add(personal)
        uow.plans.set_membership(Membership(bob.id, personal.id, Role.OWNER))
        uow.plans.set_membership(Membership(bob.id, plan.id, Role.MEMBER))
        uow.commit()
    with uow:
        assert uow.plans.membership_of(bob.id) == Membership(bob.id, plan.id, Role.MEMBER)
        assert uow.plans.count_members(plan.id) == 2
        assert uow.plans.count_members(personal.id) == 0


def test_database_refuses_negative_credits(uow):
    """Defense in depth (Book Ch6 p.90): even if code tries to oversell, the CHECK constraint refuses."""
    _, plan = _plan_with_owner(uow, credits=2)
    with uow:
        locked = uow.plans.get_for_update(plan.id)
        locked.credits_available -= 3
        with pytest.raises(IntegrityError, match="credits_available_not_negative"):
            uow.plans.save(locked)


def test_one_personal_plan_per_user(uow):
    """The partial unique index refuses a second personal plan for the same owner."""
    owner = _user()
    with uow:
        uow.users.add(owner)
        uow.plans.add(Plan(new_id("plan"), owner.id, PlanKind.PERSONAL, 1, 0))
        with pytest.raises(IntegrityError):
            uow.plans.add(Plan(new_id("plan"), owner.id, PlanKind.PERSONAL, 1, 0))


def test_get_for_update_makes_the_second_transaction_wait(clean_database, uow):
    """FOR UPDATE (Ch7): while one transaction holds the plan row, another one asking for it waits.

    Transaction A locks the plan and keeps it for 0.5 s. Transaction B, started meanwhile, can only
    read the plan after A commits, and then sees A's change.
    """
    _, plan = _plan_with_owner(uow, credits=3)
    a_has_lock = threading.Event()
    seen_by_b: dict[str, float | int] = {}

    def transaction_a() -> None:
        """Lock the plan, spend one credit, hold the lock a bit, then commit."""
        with PostgresUnitOfWork(clean_database) as a:
            locked = a.plans.get_for_update(plan.id)
            a_has_lock.set()
            time.sleep(0.5)
            locked.credits_available -= 1
            a.plans.save(locked)
            a.commit()

    thread = threading.Thread(target=transaction_a)
    thread.start()
    a_has_lock.wait(timeout=5)
    started = time.monotonic()
    with PostgresUnitOfWork(clean_database) as b:
        locked_by_b = b.plans.get_for_update(plan.id)
        seen_by_b["waited"] = time.monotonic() - started
        seen_by_b["credits"] = locked_by_b.credits_available
    thread.join()

    assert seen_by_b["waited"] >= 0.3, "B should have waited for A's lock"
    assert seen_by_b["credits"] == 2, "B should see A's committed change, not the old value"
