"""GET /tickers/{ticker}/prices: weekly closes for the report charts."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from hindsight.api.deps import CurrentUser, get_price_service
from hindsight.api.schemas import TICKER_PATTERN, PriceHistoryOut, PricePointOut
from hindsight.service.prices import PriceService

router = APIRouter(prefix="/tickers", tags=["prices"])


@router.get("/{ticker}/prices", response_model=PriceHistoryOut)
def get_price_history(
    ticker: Annotated[str, Path(pattern=TICKER_PATTERN)],
    start: Annotated[date, Query(alias="from")],
    _: CurrentUser,
    prices: Annotated[PriceService, Depends(get_price_service)],
) -> PriceHistoryOut:
    """Weekly adjusted closes since `from`. Signed-in users only (the provider costs money)."""
    bars = prices.weekly(ticker, start)
    return PriceHistoryOut(
        ticker=ticker,
        source=prices.source.value,
        prices=[PricePointOut(date=b.day, close=f"{b.adj_close:.2f}") for b in bars],
    )
