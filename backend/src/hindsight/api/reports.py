"""Report routes: request one (202 + polling), then read it."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from hindsight.api.deps import CurrentUser, get_report_service
from hindsight.api.errors import ApiError
from hindsight.api.schemas import ReportAcceptedOut, ReportOut, ReportRequest, ReportResultOut
from hindsight.domain.models import Report, ReportStatus
from hindsight.service.reports import ReportService

router = APIRouter(tags=["reports"])
Reports = Annotated[ReportService, Depends(get_report_service)]


def _money(amount: Decimal | None) -> str:
    """Decimal -> "1234.50" (always two decimals, like the contract's Money type)."""
    return f"{amount:.2f}"


def _report_out(report: Report) -> ReportOut:
    """Domain Report -> response body. `results` is left out (not null) until the report is done."""
    extra = {}
    if report.status is ReportStatus.DONE:
        extra["results"] = [
            ReportResultOut(
                position_id=i.position_id,
                ticker=i.ticker,
                shares=i.shares,
                sold_for=_money(i.sold_for),
                worth_today=_money(i.worth_today),
                difference=_money(i.difference),
            )
            for i in report.items
        ]
    return ReportOut(
        id=report.id,
        portfolio_id=report.portfolio_id,
        status=report.status.value,
        created_at=report.created_at,
        completed_at=report.completed_at,
        credits_charged=report.credits_charged,
        failure_reason=report.failure_reason,
        **extra,
    )


@router.post(
    "/portfolios/{portfolio_id}/hindsight-reports", response_model=ReportAcceptedOut, status_code=202
)
def request_report(
    portfolio_id: str,
    body: ReportRequest,
    user_id: CurrentUser,
    reports: Reports,
    request: Request,
    idempotency_key: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """Hold credits and queue a report. Retrying with the same Idempotency-Key replays the answer."""
    if idempotency_key is None:
        raise ApiError(
            422,
            "idempotency_key_required",
            "Idempotency-Key header required",
            "Send a unique Idempotency-Key header (a UUID works) so retries are safe",
        )
    if not 8 <= len(idempotency_key) <= 128:
        raise ApiError(
            422, "validation_error", "The request is invalid", "Idempotency-Key must be 8 to 128 characters"
        )
    accepted = reports.request(user_id, portfolio_id, body.position_ids, idempotency_key)
    headers = {"Location": request.url_for("get_report", report_id=accepted.body["id"]).path}
    if accepted.replayed:
        headers["Idempotent-Replayed"] = "true"  # tells the client this is the saved answer
    return JSONResponse(accepted.body, status_code=accepted.status, headers=headers)


@router.get("/hindsight-reports/{report_id}", response_model=ReportOut, response_model_exclude_unset=True)
def get_report(report_id: str, user_id: CurrentUser, reports: Reports) -> ReportOut:
    """A report the caller requested; 404 if missing or not theirs. Poll until done or failed."""
    return _report_out(reports.get(user_id, report_id))
