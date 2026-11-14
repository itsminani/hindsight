"""The demo seed and password hashing."""

from hindsight.domain.models import PlanKind, Role
from hindsight.repositories.postgres import PostgresUnitOfWork
from hindsight.seed import seed
from hindsight.service.passwords import hash_password, verify_password


def test_password_hash_verifies_only_the_right_password():
    """A hash accepts its own password, refuses others, and never contains the password itself."""
    hashed = hash_password("correct horse")
    assert verify_password(hashed, "correct horse")
    assert not verify_password(hashed, "wrong horse")
    assert not verify_password("not-a-hash", "correct horse")
    assert "correct horse" not in hashed


def test_seed_creates_the_demo_world_once(clean_database):
    """Seeding creates Alice, Bob and Carol with the right plans, and a second run changes nothing."""
    assert seed(clean_database, "demo") is True
    assert seed(clean_database, "demo") is False

    with PostgresUnitOfWork(clean_database) as uow:
        alice = uow.users.get_by_email("alice@example.com")
        bob = uow.users.get_by_email("bob@example.com")
        carol = uow.users.get_by_email("carol@example.com")
        alice_plan = uow.plans.membership_of(alice.id)
        bob_plan = uow.plans.membership_of(bob.id)
        carol_plan = uow.plans.get(uow.plans.membership_of(carol.id).plan_id)
        family = uow.plans.get(alice_plan.plan_id)
        family_members = uow.plans.count_members(family.id)
        alice_portfolios = uow.portfolios.list_for_owner(alice.id)

    assert verify_password(alice.password_hash, "demo")
    assert family.kind is PlanKind.SHARED and family.credits_available == 10
    assert alice_plan.role is Role.OWNER
    assert bob_plan.plan_id == family.id and bob_plan.role is Role.MEMBER
    assert family_members == 2
    assert carol_plan.kind is PlanKind.PERSONAL and carol_plan.credits_available == 1
    assert len(alice_portfolios) == 2
    assert any(p.is_sold for p in alice_portfolios[0].positions)
