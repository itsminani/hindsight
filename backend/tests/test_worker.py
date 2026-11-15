"""The report worker: charge on success, release on failure, retry with backoff, never twice."""

import threading
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from hindsight.domain.models import PriceBar, PriceSource, ReportStatus
from hindsight.integrations.demo_prices import DemoPriceProvider
from hindsight.integrations.interfaces import PriceProvider, ProviderUnavailable
from hindsight.repositories.postgres import PostgresUnitOfWork
from hindsight.service import report_jobs
from hindsight.service.report_jobs import ReportProcessor
from hindsight.service.reports import ReportService

TODAY = date(2026, 11, 13)


class DownProvider(PriceProvider):
    """A provider that is always unavailable (timeouts, rate limits...)."""

    source = PriceSource.DEMO

    def daily_bars(self, ticker: str, start: date, end: date) -> list[PriceBar]:
        """Always fails with a temporary error."""
        raise ProviderUnavailable("down for the test")


@pytest.fixture
def setup(seeded_database):
    """Alice's ids, a report service and a unit-of-work factory on the seeded test database."""
    uow_factory = lambda: PostgresUnitOfWork(seeded_database)  # noqa: E731
    with uow_factory() as uow:
        alice = uow.users.get_by_email("alice@example.com")
        tech = next(p for p in uow.portfolios.list_for_owner(alice.id) if p.name == "Tech I sold too early")
        plan_id = uow.plans.membership_of(alice.id).plan_id
    sold = {p.ticker: p.id for p in tech.positions if p.sell_date}
    return {
        "db": seeded_database,
        "uow": uow_factory,
        "alice": alice.id,
        "portfolio": tech.id,
        "sold": sold,
        "plan": plan_id,
        "reports": ReportService(uow_factory),
    }


def _request(setup, *tickers: str, key: str = "worker-test-key") -> str:
    """Request a report on Alice's sold lots for these tickers; returns the report id."""
    ids = [setup["sold"][t] for t in tickers]
    return setup["reports"].request(setup["alice"], setup["portfolio"], ids, key).body["id"]


def _plan(setup) -> tuple[int, int]:
    """(available, held) credits on Alice's plan."""
    with setup["uow"]() as uow:
        plan = uow.plans.get(setup["plan"])
    return plan.credits_available, plan.credits_held


def _job(setup, report_id: str):
    """The job row of a report."""
    with setup["db"].engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT status, attempts, run_after > now() AS later, last_error"
                " FROM jobs WHERE report_id = :r"
            ),
            {"r": report_id},
        ).one()


def test_success_fills_results_and_charges_the_held_credits(setup):
    """10 available -> 8 available + 2 held -> after the worker: 8 available, 0 held, report done."""
    report_id = _request(setup, "AAPL", "NVDA")
    assert _plan(setup) == (8, 2)

    processor = ReportProcessor(setup["uow"], DemoPriceProvider(today=TODAY), today=TODAY)
    assert processor.run_once() is True
    assert processor.run_once() is False  # queue empty

    with setup["uow"]() as uow:
        report = uow.reports.get(report_id)
    assert report.status is ReportStatus.DONE
    assert report.credits_charged == 2 and report.price_source == "demo"
    assert all(i.sold_for > 0 and i.difference == i.worth_today - i.sold_for for i in report.items)
    assert _plan(setup) == (8, 0)
    assert _job(setup, report_id).status == "done"


def test_unknown_ticker_fails_the_report_and_releases_the_credits(setup, monkeypatch):
    """Compensation: a report that can never succeed gives its credits back."""
    report_id = _request(setup, "AAPL")

    class Unknown(DemoPriceProvider):
        """Knows no ticker at all."""

        def daily_bars(self, ticker, start, end):
            """Delegates with a ZZ ticker, which the demo provider doesn't know."""
            return super().daily_bars("ZZ" + ticker, start, end)

    ReportProcessor(setup["uow"], Unknown(today=TODAY), today=TODAY).run_once()
    with setup["uow"]() as uow:
        report = uow.reports.get(report_id)
    assert report.status is ReportStatus.FAILED and "AAPL" in report.failure_reason
    assert _plan(setup) == (10, 0)
    assert _job(setup, report_id).status == "failed"


def test_provider_down_retries_with_backoff_then_gives_up(setup, monkeypatch):
    """Temporary errors put the job back in the queue for later; after MAX_ATTEMPTS, fail + release."""
    report_id = _request(setup, "AAPL")
    processor = ReportProcessor(setup["uow"], DownProvider(), today=TODAY)

    processor.run_once()
    job = _job(setup, report_id)
    assert (job.status, job.attempts, job.later) == ("queued", 1, True)
    assert _plan(setup) == (9, 1), "credits stay held while retrying"

    monkeypatch.setattr(report_jobs, "MAX_ATTEMPTS", 2)
    with setup["db"].engine.begin() as conn:  # pretend the backoff delay has passed
        conn.execute(text("UPDATE jobs SET run_after = now() - interval '1 second'"))
    processor.run_once()
    with setup["uow"]() as uow:
        assert uow.reports.get(report_id).status is ReportStatus.FAILED
    assert _plan(setup) == (10, 0)


def test_a_job_whose_worker_died_is_picked_up_again(setup):
    """A job stuck in 'running' for too long (its worker crashed) is claimed by another worker."""
    report_id = _request(setup, "AAPL")
    with setup["db"].engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE jobs SET status = 'running', locked_at = now() - interval '1 hour'"
                " WHERE report_id = :r"
            ),
            {"r": report_id},
        )
    assert ReportProcessor(setup["uow"], DemoPriceProvider(today=TODAY), today=TODAY).run_once() is True
    assert _job(setup, report_id).status == "done"


def test_two_workers_never_process_the_same_job(setup):
    """SKIP LOCKED: 6 reports, 2 workers racing; every report charged exactly once."""
    for i, ticker in enumerate(["AAPL", "NVDA", "TSLA", "AAPL", "NVDA", "TSLA"]):
        _request(setup, ticker, key=f"two-workers-{i}")
    assert _plan(setup) == (4, 6)
    processed: list[int] = [0, 0]

    def work(n: int) -> None:
        """Keep taking jobs until the queue is empty."""
        processor = ReportProcessor(setup["uow"], DemoPriceProvider(today=TODAY), today=TODAY)
        while processor.run_once():
            processed[n] += 1

    threads = [threading.Thread(target=work, args=(n,)) for n in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert sum(processed) == 6
    assert _plan(setup) == (4, 0)
    with setup["db"].engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM reports WHERE status = 'done'")).scalar() == 6


def test_backoff_delay_doubles():
    """10 s, 20 s, 40 s, 80 s between tries."""
    assert [report_jobs.FIRST_RETRY_SECONDS * 2 ** (n - 1) for n in range(1, 5)] == [10, 20, 40, 80]
    assert timedelta(seconds=report_jobs.STALE_JOB_SECONDS) == timedelta(minutes=5)
