"""Plan routes: my plan, and member management for shared-plan owners."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from hindsight.api.deps import CurrentUser, get_plan_service
from hindsight.api.schemas import MemberCreate, MemberOut, PlanOut
from hindsight.service.plans import PlanService

router = APIRouter(prefix="/plans/me", tags=["plans"])
Plans = Annotated[PlanService, Depends(get_plan_service)]


@router.get("", response_model=PlanOut)
def get_my_plan(user_id: CurrentUser, plans: Plans) -> PlanOut:
    """The plan the caller draws credits from, their role, and its balances."""
    mine = plans.my_plan(user_id)
    return PlanOut(
        id=mine.plan.id,
        kind=mine.plan.kind.value,
        role=mine.role.value,
        credits_available=mine.plan.credits_available,
        credits_held=mine.plan.credits_held,
        member_count=mine.member_count,
    )


@router.post("/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def add_member(body: MemberCreate, user_id: CurrentUser, plans: Plans) -> MemberOut:
    """Add a user (by email) to the caller's shared plan. Owner only."""
    user, role = plans.add_member(user_id, body.email)
    return MemberOut(user_id=user.id, email=user.email, role=role.value)


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(member_id: str, user_id: CurrentUser, plans: Plans) -> Response:
    """Remove a member; they go back to their personal plan immediately. Owner only."""
    plans.remove_member(user_id, member_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
