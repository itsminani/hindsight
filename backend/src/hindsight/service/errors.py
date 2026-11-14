"""Business errors raised by the service layer. They know nothing about HTTP.

The interface layer (api/errors.py) maps each `code` to an HTTP status and a Problem response,
so the same use case could be called from a CLI or a worker and still make sense.
"""


class ServiceError(Exception):
    """Base class: every business error has a stable machine-readable code and a short title."""

    code = "internal_error"
    title = "Something went wrong"

    def __init__(self, detail: str | None = None) -> None:
        """detail: optional human-readable explanation for this occurrence."""
        super().__init__(detail or self.title)
        self.detail = detail


class InvalidCredentials(ServiceError):
    """Wrong email or password (we never say which one)."""

    code = "invalid_credentials"
    title = "Wrong email or password"


class Unauthorized(ServiceError):
    """Missing, expired or invalid access token."""

    code = "unauthorized"
    title = "Sign in required"


class NotFound(ServiceError):
    """The thing does not exist, or is not yours: same error, so IDs cannot be probed (Ch2)."""

    code = "not_found"
    title = "Not found"


class InvalidInput(ServiceError):
    """The request breaks a business rule that plain field validation could not catch."""

    code = "validation_error"
    title = "The request is invalid"


class NotEnoughCredits(ServiceError):
    """The caller's plan does not have enough available credits."""

    code = "insufficient_credits"
    title = "Not enough credits"


class PositionNotSold(ServiceError):
    """A report can only include positions that were sold."""

    code = "position_not_sold"
    title = "Position not sold"


class IdempotencyKeyReuse(ServiceError):
    """The same Idempotency-Key was sent with a different request."""

    code = "idempotency_key_reuse"
    title = "Idempotency-Key already used"


class NotPlanOwner(ServiceError):
    """Only the plan owner can manage its members."""

    code = "not_plan_owner"
    title = "Only the plan owner can do this"


class AlreadyMember(ServiceError):
    """The user already belongs to a shared plan."""

    code = "already_member"
    title = "Already in a shared plan"
