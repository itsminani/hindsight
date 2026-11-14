"""Request and response bodies, mirroring the schemas in contract/openapi.yaml.

Python uses snake_case; the JSON uses camelCase like the contract. Requests refuse unknown
fields (the contract says additionalProperties: false).
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """Base for every body: camelCase in JSON, snake_case in Python."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class RequestModel(ApiModel):
    """Base for request bodies: unknown fields are a 422, not silently ignored."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class TokenRequest(RequestModel):
    """POST /auth/token body."""

    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(min_length=1)


class TokenResponse(ApiModel):
    """POST /auth/token 200 response."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int


TICKER_PATTERN = r"^[A-Z][A-Z0-9.\-]{0,9}$"


class PortfolioCreate(RequestModel):
    """POST /portfolios body."""

    name: str = Field(min_length=1, max_length=100)


class PositionCreate(RequestModel):
    """POST /portfolios/{id}/positions body."""

    ticker: str = Field(pattern=TICKER_PATTERN)
    shares: int = Field(ge=1)
    buy_date: date
    sell_date: date | None = None

    @field_validator("sell_date")
    @classmethod
    def _sell_not_before_buy(cls, sell_date: date | None, info: ValidationInfo) -> date | None:
        """A sale cannot happen before the purchase (422 pointing at the sellDate field)."""
        buy_date = info.data.get("buy_date")
        if sell_date is not None and buy_date is not None and sell_date < buy_date:
            raise ValueError("sellDate must not be before buyDate")
        return sell_date


class PositionOut(ApiModel):
    """A position as returned by the API."""

    id: str
    ticker: str
    shares: int
    buy_date: date
    sell_date: date | None


class PortfolioOut(ApiModel):
    """A portfolio as returned by the API, with its positions."""

    id: str
    name: str
    created_at: datetime
    positions: list[PositionOut]


class PortfolioList(ApiModel):
    """GET /portfolios response."""

    items: list[PortfolioOut]
