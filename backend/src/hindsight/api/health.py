"""Liveness: is the process up? Readiness: can it serve traffic right now?"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict:
    """Liveness probe: answers 200 as long as the process is running."""
    return {"status": "ok"}


@router.get("/ready")
def ready() -> JSONResponse:
    """Readiness probe: 200 when the service can handle requests, 503 when a dependency is down."""
    # Step 5 adds the real check: a "SELECT 1" against PostgreSQL. Until then nothing can be down.
    return JSONResponse({"status": "ok"})
