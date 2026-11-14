"""Liveness: is the process up? Readiness: can it serve traffic right now? (Book Ch11 p.132)"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/health", tags=["health"])
log = logging.getLogger(__name__)


@router.get("/live")
def live() -> dict:
    """Liveness probe: answers 200 as long as the process is running. Never checks dependencies,
    so a database outage does not make the orchestrator restart healthy API processes."""
    return {"status": "ok"}


@router.get("/ready")
def ready(request: Request) -> JSONResponse:
    """Readiness probe: 200 when PostgreSQL answers SELECT 1, otherwise 503 "unavailable".

    A load balancer stops sending traffic to an instance that is not ready, then sends it again
    once the database is back, with no restart needed.
    """
    database = request.app.state.database
    if database is None:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    try:
        database.ping()
    except Exception as error:  # any failure to reach the database means "not ready"
        log.warning("readiness check failed", extra={"error": error.__class__.__name__})
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ok"})
