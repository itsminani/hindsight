"""Plan use cases: see my plan, and (owner only) add or remove members.

Membership changes lock the plan row, like credit spends do. So a member removed by the owner
can never spend in the same instant: whichever transaction gets the lock first wins, and the
other one sees the result (contract: removal "takes effect immediately").
"""

from collections.abc import Callable
from dataclasses import dataclass

from hindsight.domain.models import Membership, Plan, PlanKind, Role, User
from hindsight.repositories.interfaces import UnitOfWork
from hindsight.service.errors import AlreadyMember, InvalidInput, NotFound, NotPlanOwner


@dataclass(frozen=True)
class MyPlan:
    """The caller's plan as they see it: the plan, their role, and how many members it has."""

    plan: Plan
    role: Role
    member_count: int


class PlanService:
    """Use cases on plans and memberships."""

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        """uow_factory: makes a new unit of work (one transaction) per call."""
        self._uow_factory = uow_factory

    def my_plan(self, user_id: str) -> MyPlan:
        """The plan the caller belongs to."""
        with self._uow_factory() as uow:
            membership = _membership(uow, user_id)
            plan = uow.plans.get(membership.plan_id)
            return MyPlan(plan, membership.role, uow.plans.count_members(plan.id))

    def add_member(self, owner_id: str, email: str) -> tuple[User, Role]:
        """Move the user with this email onto the caller's shared plan, as a member."""
        with self._uow_factory() as uow:
            plan = _lock_owned_shared_plan(uow, owner_id)
            user = uow.users.get_by_email(email)
            if user is None:
                raise NotFound("No user with this email")
            current = uow.plans.membership_of(user.id)
            if current is not None:
                current_plan = uow.plans.get(current.plan_id)
                if current_plan.kind is PlanKind.SHARED:
                    raise AlreadyMember("This user already belongs to a shared plan")
            uow.plans.set_membership(Membership(user.id, plan.id, Role.MEMBER))
            uow.commit()
            return user, Role.MEMBER

    def remove_member(self, owner_id: str, member_id: str) -> None:
        """Move a member of the caller's plan back to their personal plan."""
        with self._uow_factory() as uow:
            plan = _lock_owned_shared_plan(uow, owner_id)
            membership = uow.plans.membership_of(member_id)
            if membership is None or membership.plan_id != plan.id or membership.role is not Role.MEMBER:
                raise NotFound("No member with this ID on your plan")
            personal = uow.plans.personal_plan_of(member_id)
            if personal is None:
                raise RuntimeError(f"user {member_id} has no personal plan")
            uow.plans.set_membership(Membership(member_id, personal.id, Role.OWNER))
            uow.commit()


def _membership(uow: UnitOfWork, user_id: str) -> Membership:
    """The caller's membership; every seeded user has one, so a missing one is invalid state."""
    membership = uow.plans.membership_of(user_id)
    if membership is None:
        raise InvalidInput("You do not belong to any plan")
    return membership


def _lock_owned_shared_plan(uow: UnitOfWork, user_id: str) -> Plan:
    """Lock the caller's plan if they own it and it is shared; otherwise 403 not_plan_owner."""
    membership = _membership(uow, user_id)
    if membership.role is not Role.OWNER:
        raise NotPlanOwner()
    plan = uow.plans.get_for_update(membership.plan_id)
    if plan.kind is not PlanKind.SHARED:
        raise NotPlanOwner("Only the owner of a shared plan can manage members")
    return plan
