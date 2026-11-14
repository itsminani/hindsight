"""Requesting a hindsight report: the concurrency-critical use case (Ch7, Ch3, Ch9).

In ONE transaction:
  1. lock the caller's plan row (SELECT ... FOR UPDATE), so concurrent requests queue up
  2. hold one credit per distinct ticker (refused if the plan does not have enough)
  3. insert the report and its job (outbox: the job exists if and only if the credits are held)
  4. save the response under the Idempotency-Key, so a retry replays it instead of paying twice
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

from hindsight.domain.ids import new_id
from hindsight.domain.models import (
    InsufficientCredits,
    Report,
    ReportItem,
    StoredResponse,
    report_cost,
)
from hindsight.repositories.interfaces import KeyAlreadyUsed, UnitOfWork
from hindsight.service.errors import (
    IdempotencyKeyReuse,
    InvalidInput,
    NotEnoughCredits,
    NotFound,
    PositionNotSold,
)
from hindsight.service.portfolios import owned_portfolio


@dataclass(frozen=True)
class ReportAccepted:
    """What the caller gets back: the HTTP status and body to send (also what is replayed)."""

    status: int
    body: dict
    replayed: bool = False


def request_hash(portfolio_id: str, position_ids: list[str]) -> str:
    """Fingerprint of the request, to tell "same retry" from "same key, different request".

    Position order does not matter: [a, b] and [b, a] are the same request.
    """
    canonical = json.dumps({"portfolioId": portfolio_id, "positionIds": sorted(position_ids)})
    return hashlib.sha256(canonical.encode()).hexdigest()


class ReportService:
    """Use cases on hindsight reports."""

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        """uow_factory: makes a new unit of work (one transaction) per call."""
        self._uow_factory = uow_factory

    def request(
        self, user_id: str, portfolio_id: str, position_ids: list[str], idempotency_key: str
    ) -> ReportAccepted:
        """Hold credits and queue a report, exactly once per Idempotency-Key."""
        fingerprint = request_hash(portfolio_id, position_ids)
        try:
            return self._request_once(user_id, portfolio_id, position_ids, idempotency_key, fingerprint)
        except KeyAlreadyUsed:
            # A concurrent retry with the same key committed first. Our transaction was rolled
            # back (nothing held twice); answer with what the first one saved.
            with self._uow_factory() as uow:
                return _replay(uow.idempotency.get(user_id, idempotency_key), fingerprint)

    def _request_once(
        self, user_id: str, portfolio_id: str, position_ids: list[str], key: str, fingerprint: str
    ) -> ReportAccepted:
        """One attempt at the whole transaction (steps 1-4 in the module docstring)."""
        with self._uow_factory() as uow:
            saved = uow.idempotency.get(user_id, key)
            if saved is not None:
                return _replay(saved, fingerprint)

            portfolio = owned_portfolio(uow, user_id, portfolio_id)
            by_id = {p.id: p for p in portfolio.positions}
            missing = [pid for pid in position_ids if pid not in by_id]
            if missing:
                raise NotFound(f"No position {missing[0]} in this portfolio")
            positions = [by_id[pid] for pid in position_ids]
            not_sold = [p.id for p in positions if not p.is_sold]
            if not_sold:
                raise PositionNotSold(f"Position {not_sold[0]} has no sell date")
            cost = report_cost(positions)

            plan = _lock_callers_plan(uow, user_id)
            try:
                plan.hold(cost)
            except InsufficientCredits as error:
                raise NotEnoughCredits(
                    f"This report needs {error.needed} credits; your plan has {error.available}"
                ) from error
            uow.plans.save(plan)

            report = uow.reports.add(
                Report(
                    id=new_id("report"),
                    portfolio_id=portfolio.id,
                    requested_by=user_id,
                    plan_id=plan.id,
                    credits_held=cost,
                    items=[ReportItem(p.id, p.ticker, p.shares) for p in positions],
                )
            )
            uow.jobs.enqueue_report(report.id)

            body = {
                "id": report.id,
                "status": report.status.value,
                "creditsHeld": cost,
                "creditsAvailable": plan.credits_available,
            }
            uow.idempotency.put(user_id, key, StoredResponse(fingerprint, 202, body))
            uow.commit()
            return ReportAccepted(202, body)

    def get(self, user_id: str, report_id: str) -> Report:
        """A report the caller requested; anyone else's (or a missing one) is NotFound."""
        with self._uow_factory() as uow:
            report = uow.reports.get(report_id)
        if report is None or report.requested_by != user_id:
            raise NotFound("No report with this ID")
        return report


def _lock_callers_plan(uow: UnitOfWork, user_id: str):
    """Lock the plan the caller belongs to, re-checking membership AFTER the lock.

    Removing a member also locks the plan, so once we hold the lock nobody can move the caller
    out of it until we commit. If they were moved while we waited, we lock their new plan instead.
    """
    for _ in range(3):
        membership = uow.plans.membership_of(user_id)
        if membership is None:
            raise InvalidInput("You do not belong to any plan")
        plan = uow.plans.get_for_update(membership.plan_id)
        still = uow.plans.membership_of(user_id)
        if still is not None and still.plan_id == membership.plan_id:
            return plan
    raise RuntimeError("membership kept changing while locking the plan")


def _replay(saved: StoredResponse | None, fingerprint: str) -> ReportAccepted:
    """Return the saved response for a retry, or refuse a different request under the same key."""
    if saved is None:
        raise RuntimeError("idempotency key reported as used but no response is stored")
    if saved.request_hash != fingerprint:
        raise IdempotencyKeyReuse("This Idempotency-Key was already used for a different request")
    return ReportAccepted(saved.status, saved.body, replayed=True)
