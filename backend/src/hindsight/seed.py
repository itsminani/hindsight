"""Demo data for local development and the milestone demo. Never for production.

Run from backend/:   python -m uv run python -m hindsight.seed           (adds demo data if missing)
                     python -m uv run python -m hindsight.seed --reset   (empties every table first)
In Docker:           docker compose exec api python -m hindsight.seed

Everyone signs in with HINDSIGHT_SEED_PASSWORD (set in .env; a local-only demo value).

Who is who:
  alice@example.com  owns the shared "family" plan (10 credits), two portfolios with sold positions
  bob@example.com    member of Alice's plan, one portfolio
  carol@example.com  alone on her personal plan with 1 credit (to demo 402 insufficient_credits)
"""

import argparse
import sys
from datetime import date

from sqlalchemy import text

from hindsight.config import Settings, get_settings
from hindsight.domain.ids import new_id
from hindsight.domain.models import Membership, Plan, PlanKind, Portfolio, Position, Role, User
from hindsight.repositories.db import Database
from hindsight.repositories.orm import Base
from hindsight.repositories.postgres import PostgresUnitOfWork
from hindsight.service.passwords import hash_password

# (ticker, shares, buy_date, sell_date or None if still held)
ALICE_PORTFOLIOS = {
    "Tech I sold too early": [
        ("AAPL", 50, date(2015, 3, 2), date(2017, 6, 1)),
        ("NVDA", 20, date(2016, 1, 4), date(2018, 10, 1)),
        ("TSLA", 10, date(2019, 1, 2), date(2020, 2, 3)),
        ("MSFT", 15, date(2018, 5, 1), None),
    ],
    "Dividend picks": [
        ("KO", 40, date(2017, 4, 3), date(2021, 9, 1)),
        ("JNJ", 12, date(2016, 8, 1), None),
    ],
}
BOB_PORTFOLIOS = {
    "Bob's trades": [
        ("AMZN", 8, date(2016, 2, 1), date(2019, 5, 1)),
        ("NFLX", 6, date(2017, 3, 1), date(2018, 7, 2)),
    ],
}
CAROL_PORTFOLIOS = {
    "First steps": [("GOOGL", 3, date(2018, 1, 2), date(2019, 1, 2))],
}


def _require_safe_environment(settings: Settings) -> str:
    """Stop unless this is a non-production environment with a seed password; return the password."""
    if settings.env.lower() in {"prod", "production"}:
        sys.exit("refusing to seed: HINDSIGHT_ENV is production")
    if not settings.seed_password:
        sys.exit("HINDSIGHT_SEED_PASSWORD is not set (see .env.example)")
    return settings.seed_password


def _reset(database: Database) -> None:
    """Empty every table (keeps the schema and the migration history)."""
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with database.engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} CASCADE"))


def _add_user_with_personal_plan(
    uow: PostgresUnitOfWork, email: str, password_hash: str, credits: int
) -> User:
    """Create a user and their personal plan, and put them on it as owner."""
    user = User(id=new_id("user"), email=email, password_hash=password_hash)
    uow.users.add(user)
    personal = Plan(new_id("plan"), user.id, PlanKind.PERSONAL, credits_available=credits, credits_held=0)
    uow.plans.add(personal)
    uow.plans.set_membership(Membership(user.id, personal.id, Role.OWNER))
    return user


def _add_portfolios(uow: PostgresUnitOfWork, owner: User, portfolios: dict) -> None:
    """Create the owner's portfolios with their positions."""
    for name, rows in portfolios.items():
        positions = [Position(new_id("position"), t, n, bought, sold) for t, n, bought, sold in rows]
        uow.portfolios.add(
            Portfolio(id=new_id("portfolio"), owner_id=owner.id, name=name, positions=positions)
        )


def seed(database: Database, password: str) -> bool:
    """Add the demo users, plans and portfolios in one transaction. Returns False if already seeded."""
    with PostgresUnitOfWork(database) as uow:
        if uow.users.get_by_email("alice@example.com"):
            return False
        password_hash = hash_password(password)  # one hash for everyone: Argon2 is slow on purpose

        alice = _add_user_with_personal_plan(uow, "alice@example.com", password_hash, credits=3)
        bob = _add_user_with_personal_plan(uow, "bob@example.com", password_hash, credits=3)
        carol = _add_user_with_personal_plan(uow, "carol@example.com", password_hash, credits=1)

        family = Plan(new_id("plan"), alice.id, PlanKind.SHARED, credits_available=10, credits_held=0)
        uow.plans.add(family)
        uow.plans.set_membership(Membership(alice.id, family.id, Role.OWNER))
        uow.plans.set_membership(Membership(bob.id, family.id, Role.MEMBER))

        _add_portfolios(uow, alice, ALICE_PORTFOLIOS)
        _add_portfolios(uow, bob, BOB_PORTFOLIOS)
        _add_portfolios(uow, carol, CAROL_PORTFOLIOS)
        uow.commit()
    return True


def main() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description="Load Hindsight demo data (never in production).")
    parser.add_argument("--reset", action="store_true", help="empty every table before seeding")
    args = parser.parse_args()

    settings = get_settings()
    password = _require_safe_environment(settings)
    database = Database(settings.require_database_url())
    try:
        if args.reset:
            _reset(database)
            print("emptied every table")
        if seed(database, password):
            print("seeded: alice@example.com, bob@example.com, carol@example.com")
        else:
            print("already seeded (use --reset to start over)")
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
