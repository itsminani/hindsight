"""Background use case: compute queued reports (Ch9 jobs, Ch10 foreign integration).

For each job:
  1. fetch prices from the provider, OUTSIDE any transaction (a slow provider never holds a lock)
  2. success: one transaction locks the plan, charges the held credits, saves the results
  3. temporary provider trouble: retry later with exponential backoff
  4. unknown ticker, or too many failed tries: the report fails and its credits are released
"""

import logging
from collections.abc import Callable
from datetime import date, timedelta

from hindsight.domain.models import (
    Job,
    PriceBar,
    Report,
    ReportStatus,
    hindsight_values,
)
from hindsight.integrations.interfaces import PriceProvider, ProviderUnavailable, UnknownTicker
from hindsight.repositories.interfaces import UnitOfWork

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
FIRST_RETRY_SECONDS = 10
STALE_JOB_SECONDS = 300  # a "running" job untouched this long belongs to a worker that died
PROVIDER_DOWN_MESSAGE = "Market data is unavailable right now. Please try again later."


class ReportFailed(Exception):
    """A report that can never succeed (e.g. unknown ticker). Not retried."""


class ReportProcessor:
    """Takes queued report jobs one at a time and finishes them."""

    def __init__(
        self, uow_factory: Callable[[], UnitOfWork], prices: PriceProvider, today: date | None = None
    ):
        """uow_factory: new unit of work per transaction. prices: the market-data provider."""
        self._uow_factory = uow_factory
        self._prices = prices
        self._today = today

    def run_once(self) -> bool:
        """Process one due job. Returns False when there was nothing to do."""
        with self._uow_factory() as uow:
            job = uow.jobs.claim_next(STALE_JOB_SECONDS)
            uow.commit()  # make "running" visible right away, so no other worker takes it
        if job is None:
            return False
        self.process(job)
        return True

    def process(self, job: Job) -> None:
        """Compute the job's report, then finish, retry, or fail it."""
        with self._uow_factory() as uow:
            report = uow.reports.get(job.report_id)
            portfolio = uow.portfolios.get(report.portfolio_id) if report else None
        if report is None or portfolio is None or report.status is not ReportStatus.PENDING:
            self._close_job(job, "report is gone or already finished")
            return

        sell_dates = {p.id: p.sell_date for p in portfolio.positions}
        try:
            self._fill_results(report, sell_dates)
        except ReportFailed as error:
            self._finish(report, job, failure=str(error))
        except ProviderUnavailable as error:
            if job.attempts >= MAX_ATTEMPTS:
                self._finish(report, job, failure=PROVIDER_DOWN_MESSAGE)
            else:
                delay = FIRST_RETRY_SECONDS * 2 ** (job.attempts - 1)  # 10 s, 20 s, 40 s, 80 s
                log.warning("price provider unavailable, retrying", extra={"job": job.id, "delay": delay})
                with self._uow_factory() as uow:
                    uow.jobs.retry_later(job.id, delay, str(error))
                    uow.commit()
        else:
            self._finish(report, job)

    def _fill_results(self, report: Report, sell_dates: dict) -> None:
        """Fill each item's money values from the provider's prices (one call per ticker)."""
        today = self._today or date.today()
        bars_by_ticker: dict[str, list[PriceBar]] = {}
        for item in report.items:
            sold_on = sell_dates.get(item.position_id)
            if sold_on is None:
                raise ReportFailed(f"Position {item.position_id} has no sell date")
            if item.ticker not in bars_by_ticker:
                earliest = min(d for d in sell_dates.values() if d is not None)
                try:
                    bars_by_ticker[item.ticker] = self._prices.daily_bars(
                        item.ticker, earliest - timedelta(days=10), today
                    )
                except UnknownTicker as error:
                    raise ReportFailed(f"We have no prices for {item.ticker}") from error
            bars = bars_by_ticker[item.ticker]
            at_sale = next((b for b in reversed(bars) if b.day <= sold_on), None)
            if at_sale is None or not bars:
                raise ReportFailed(f"We have no price for {item.ticker} on {sold_on.isoformat()}")
            values = hindsight_values(item.shares, at_sale, bars[-1])
            item.sold_for, item.worth_today, item.difference = values

    def _finish(self, report: Report, job: Job, failure: str | None = None) -> None:
        """One transaction: lock the plan, then charge (success) or release (failure) the credits."""
        with self._uow_factory() as uow:
            plan = uow.plans.get_for_update(report.plan_id)
            current = uow.reports.get(report.id)
            if current is None or current.status is not ReportStatus.PENDING:
                uow.jobs.finish(job.id)  # another worker finished it while we were busy
                uow.commit()
                return
            if failure is None:
                plan.charge(report.credits_held)
                report.status = ReportStatus.DONE
                report.credits_charged = report.credits_held
                report.price_source = self._prices.source.value
                uow.jobs.finish(job.id)
            else:
                plan.release(report.credits_held)  # compensation: the credits go back
                report.status = ReportStatus.FAILED
                report.failure_reason = failure
                uow.jobs.fail(job.id, failure)
            uow.plans.save(plan)
            uow.reports.save_outcome(report)
            uow.commit()
        log.info("report finished", extra={"report": report.id, "status": report.status.value})

    def _close_job(self, job: Job, reason: str) -> None:
        """Mark a job done when there is nothing left to compute."""
        with self._uow_factory() as uow:
            uow.jobs.finish(job.id)
            uow.commit()
        log.info("job closed", extra={"job": job.id, "reason": reason})
