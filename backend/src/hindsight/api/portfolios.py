"""Portfolio routes. Thin: parse the request, call the service, shape the response (Ch5)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from hindsight.api.deps import CurrentUser, get_portfolio_service
from hindsight.api.schemas import PortfolioCreate, PortfolioList, PortfolioOut, PositionCreate, PositionOut
from hindsight.domain.models import Portfolio, Position
from hindsight.service.portfolios import PortfolioService

router = APIRouter(prefix="/portfolios", tags=["portfolios"])
Portfolios = Annotated[PortfolioService, Depends(get_portfolio_service)]


def _position_out(position: Position) -> PositionOut:
    """Domain Position -> response body."""
    return PositionOut(
        id=position.id,
        ticker=position.ticker,
        shares=position.shares,
        buy_date=position.buy_date,
        sell_date=position.sell_date,
    )


def _portfolio_out(portfolio: Portfolio) -> PortfolioOut:
    """Domain Portfolio -> response body."""
    return PortfolioOut(
        id=portfolio.id,
        name=portfolio.name,
        created_at=portfolio.created_at,
        positions=[_position_out(p) for p in portfolio.positions],
    )


@router.get("", response_model=PortfolioList)
def list_portfolios(user_id: CurrentUser, portfolios: Portfolios) -> PortfolioList:
    """The caller's portfolios (never anyone else's)."""
    return PortfolioList(items=[_portfolio_out(p) for p in portfolios.list(user_id)])


@router.post("", response_model=PortfolioOut, status_code=status.HTTP_201_CREATED)
def create_portfolio(
    body: PortfolioCreate, user_id: CurrentUser, portfolios: Portfolios, request: Request, response: Response
) -> PortfolioOut:
    """Create a portfolio owned by the caller; Location points at the new portfolio."""
    portfolio = portfolios.create(user_id, body.name)
    response.headers["Location"] = str(request.url_for("get_portfolio", portfolio_id=portfolio.id).path)
    return _portfolio_out(portfolio)


@router.get("/{portfolio_id}", response_model=PortfolioOut)
def get_portfolio(portfolio_id: str, user_id: CurrentUser, portfolios: Portfolios) -> PortfolioOut:
    """One of the caller's portfolios with its positions; 404 if missing or not theirs."""
    return _portfolio_out(portfolios.get(user_id, portfolio_id))


@router.post("/{portfolio_id}/positions", response_model=PositionOut, status_code=status.HTTP_201_CREATED)
def add_position(
    portfolio_id: str, body: PositionCreate, user_id: CurrentUser, portfolios: Portfolios
) -> PositionOut:
    """Add a position to one of the caller's portfolios; 404 if the portfolio is not theirs."""
    position = portfolios.add_position(
        user_id, portfolio_id, body.ticker, body.shares, body.buy_date, body.sell_date
    )
    return _position_out(position)
