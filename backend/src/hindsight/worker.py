"""The background worker process: computes queued reports until it is told to stop.

Run:  python -m hindsight.worker        (Docker Compose runs it as the "worker" service)

Several workers can run at once: jobs are claimed with FOR UPDATE SKIP LOCKED, so each job
goes to exactly one of them. On SIGTERM (docker stop, a deploy) it finishes the current job
and exits cleanly instead of being killed halfway (Book Ch11: graceful shutdown).
"""

import logging
import signal
import threading

from hindsight.config import get_settings
from hindsight.integrations.factory import price_provider_from
from hindsight.logging_setup import configure_logging
from hindsight.repositories.db import Database
from hindsight.repositories.postgres import PostgresUnitOfWork
from hindsight.service.report_jobs import ReportProcessor

log = logging.getLogger("hindsight.worker")


def main() -> None:
    """Wire the worker from settings and loop until SIGTERM or Ctrl+C."""
    settings = get_settings()
    configure_logging(settings.log_level)
    database = Database(settings.require_database_url())
    prices = price_provider_from(settings)
    processor = ReportProcessor(lambda: PostgresUnitOfWork(database), prices)

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    log.info("worker started", extra={"priceSource": prices.source.value})

    while not stop.is_set():
        try:
            worked = processor.run_once()
        except Exception:
            # One bad job must not kill the worker; it is logged, and the job is retried later.
            log.exception("job crashed")
            worked = False
        if not worked:
            stop.wait(settings.worker_poll_seconds)  # idle: wait, but wake up at once on SIGTERM

    database.dispose()
    log.info("worker stopped")


if __name__ == "__main__":
    main()
