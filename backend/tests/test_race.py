"""The race tests (Ch7): many requests at the same instant must never oversell credits.

These call the service layer from real threads, each with its own database connection, all
released at once by a barrier. Without SELECT ... FOR UPDATE, several threads would read
"3 credits available" at the same time and all succeed.
"""

import threading

from sqlalchemy import text

from hindsight.repositories.postgres import PostgresUnitOfWork
from hindsight.service.errors import NotEnoughCredits
from hindsight.service.reports import ReportService

REQUESTS = 20


def _alice_setup(database, credits: int) -> tuple[str, str, str]:
    """Give Alice's family plan exactly `credits`; return (alice_id, portfolio_id, AAPL position id)."""
    with PostgresUnitOfWork(database) as uow:
        alice = uow.users.get_by_email("alice@example.com")
        plan_id = uow.plans.membership_of(alice.id).plan_id
        tech = next(p for p in uow.portfolios.list_for_owner(alice.id) if p.name == "Tech I sold too early")
        aapl = next(p for p in tech.positions if p.ticker == "AAPL")
    with database.engine.begin() as conn:
        conn.execute(
            text("UPDATE plans SET credits_available = :c, credits_held = 0 WHERE id = :p"),
            {"c": credits, "p": plan_id},
        )
    return alice.id, tech.id, aapl.id


def _run_at_once(n: int, work) -> list:
    """Run work(i) in n threads released at the same moment; return each result or exception."""
    barrier = threading.Barrier(n)
    results: list = [None] * n

    def worker(i: int) -> None:
        """Wait for everyone, then do the work and record what happened."""
        barrier.wait()
        try:
            results[i] = work(i)
        except Exception as error:  # recorded and asserted on by the test
            results[i] = error

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results


def _plan_and_counts(database) -> tuple[int, int, int, int]:
    """(credits_available, credits_held, number of reports, number of jobs) for Alice's family plan."""
    with database.engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT p.credits_available, p.credits_held,"
                " (SELECT count(*) FROM reports r WHERE r.plan_id = p.id),"
                " (SELECT count(*) FROM jobs j JOIN reports r ON r.id = j.report_id WHERE r.plan_id = p.id)"
                " FROM plans p JOIN users u ON u.id = p.owner_id"
                " WHERE u.email = 'alice@example.com' AND p.kind = 'shared'"
            )
        ).one()
    return tuple(row)


def test_twenty_simultaneous_requests_on_three_credits(seeded_database):
    """20 requests at once, 1 credit each, 3 credits available: exactly 3 succeed, 17 get 402.

    And the books balance: 0 available, 3 held, 3 reports, 3 jobs. No oversell, no lost update.
    """
    alice_id, portfolio_id, aapl_id = _alice_setup(seeded_database, credits=3)
    service = ReportService(lambda: PostgresUnitOfWork(seeded_database))

    results = _run_at_once(
        REQUESTS, lambda i: service.request(alice_id, portfolio_id, [aapl_id], f"race-key-{i:04d}")
    )

    accepted = [r for r in results if not isinstance(r, Exception)]
    refused = [r for r in results if isinstance(r, NotEnoughCredits)]
    unexpected = [r for r in results if isinstance(r, Exception) and not isinstance(r, NotEnoughCredits)]
    assert unexpected == []
    assert (len(accepted), len(refused)) == (3, REQUESTS - 3)
    assert _plan_and_counts(seeded_database) == (0, 3, 3, 3)


def test_twenty_simultaneous_retries_with_the_same_key(seeded_database):
    """20 copies of the SAME request (same Idempotency-Key) at once: one report, one hold, one answer."""
    alice_id, portfolio_id, aapl_id = _alice_setup(seeded_database, credits=5)
    service = ReportService(lambda: PostgresUnitOfWork(seeded_database))

    results = _run_at_once(
        REQUESTS, lambda i: service.request(alice_id, portfolio_id, [aapl_id], "one-key-for-all")
    )

    assert not [r for r in results if isinstance(r, Exception)]
    assert len({r.body["id"] for r in results}) == 1, "every retry must get the same report"
    assert sum(not r.replayed for r in results) == 1, "exactly one request did the work"
    assert _plan_and_counts(seeded_database) == (4, 1, 1, 1)
