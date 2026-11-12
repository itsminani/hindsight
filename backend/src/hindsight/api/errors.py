"""Every error leaves the service as RFC 9457 Problem Details with a stable `code`. No stack traces."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from hindsight.logging_setup import request_id_var

PROBLEM_TYPE_BASE = "https://hindsight.example/problems/"

# Default code for errors raised by the framework itself (unknown route, wrong method...).
_CODE_FOR_STATUS = {401: "unauthorized", 404: "not_found", 405: "method_not_allowed"}


class ApiError(Exception):
    """Raised by the interface layer to send a specific Problem to the caller."""

    def __init__(self, status: int, code: str, title: str, detail: str | None = None):
        """status: HTTP status (e.g. 402). code: stable error code (e.g. "insufficient_credits").
        title: short summary. detail: optional human-readable explanation."""
        super().__init__(title)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail


def problem(status: int, code: str, title: str, detail: str | None = None, errors=None) -> JSONResponse:
    """Build an application/problem+json response (RFC 9457) with our stable `code` and the request ID.

    errors: optional list of {"field", "message"} for validation errors.
    """
    body = {
        "type": PROBLEM_TYPE_BASE + code.replace("_", "-"),
        "title": title,
        "status": status,
        "code": code,
        "requestId": request_id_var.get(),
    }
    if detail:
        body["detail"] = detail
    if errors:
        body["errors"] = errors
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
    """Turn an ApiError raised by our code into its Problem response."""
    return problem(exc.status, exc.code, exc.title, exc.detail)


async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Turn framework errors (unknown route, wrong method...) into Problem responses."""
    code = _CODE_FOR_STATUS.get(exc.status_code, "http_error")
    return problem(exc.status_code, code, str(exc.detail))


async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Turn an invalid request body/params into a 422 `validation_error` listing each bad field."""
    errors = [
        {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]}
        for e in exc.errors()
    ]
    return problem(422, "validation_error", "The request is invalid", errors=errors)


def register_error_handlers(app: FastAPI) -> None:
    """Attach the error handlers above to the app."""
    # Unexpected exceptions (500) are handled in RequestIdMiddleware, so they keep the request ID.
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
