"""Request-ID middleware: one correlation ID per request, in the logs and in the response."""

import logging
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from hindsight.api.errors import problem
from hindsight.logging_setup import request_id_var

REQUEST_ID_HEADER = "X-Request-ID"
log = logging.getLogger("hindsight.access")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Wraps every request: assigns a request ID, logs the request, and turns crashes into a clean 500."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Handle one request.

        request: the incoming HTTP request.
        call_next: runs the rest of the app (routes) and returns its response.
        Returns the response with an X-Request-ID header added.
        """
        # Reuse the caller's ID if it sent one (so a trace can cross services), else make one.
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if 0 < len(incoming) <= 128 else f"req_{uuid.uuid4().hex}"
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:
                # Caught here (not only in a global handler) so the 500 still carries the request ID.
                log.exception("unhandled error")
                response = problem(500, "internal_error", "Something went wrong on our side")
            response.headers[REQUEST_ID_HEADER] = request_id
            log.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "durationMs": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            return response
        finally:
            request_id_var.reset(token)
