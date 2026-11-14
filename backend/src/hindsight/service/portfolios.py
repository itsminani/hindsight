"""Portfolio use cases: list, create, view, and add positions. Callers only ever see their own."""

from collections.abc import Callable
from datetime import date

from hindsight.domain.ids import new_id
from hindsight.domain.models import Portfolio, Position
from hindsight.repositories.interfaces import UnitOfWork
from hindsight.service.errors import InvalidInput, NotFound


class PortfolioService:
    """Use cases on portfolios. Every method takes the caller's user ID and enforces ownership."""

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        """uow_factory: makes a new unit of work (one transaction) per call."""
        self._uow_factory = uow_factory

    def list(self, user_id: str) -> list[Portfolio]:
        """The caller's portfolios, with their positions."""
        with self._uow_factory() as uow:
            return uow.portfolios.list_for_owner(user_id)

    def create(self, user_id: str, name: str) -> Portfolio:
        """Create an empty portfolio owned by the caller."""
        with self._uow_factory() as uow:
            portfolio = uow.portfolios.add(Portfolio(id=new_id("portfolio"), owner_id=user_id, name=name))
            uow.commit()
            return portfolio

    def get(self, user_id: str, portfolio_id: str) -> Portfolio:
        """The caller's portfolio. Someone else's portfolio is NotFound, exactly like a missing one."""
        with self._uow_factory() as uow:
            return owned_portfolio(uow, user_id, portfolio_id)

    def add_position(
        self, user_id: str, portfolio_id: str, ticker: str, shares: int, buy_date: date, sell_date: date | None
    ) -> Position:
        """Add a position to the caller's portfolio."""
        try:
            position = Position(new_id("position"), ticker, shares, buy_date, sell_date)
        except ValueError as error:
            raise InvalidInput(str(error)) from error
        with self._uow_factory() as uow:
            owned_portfolio(uow, user_id, portfolio_id)
            uow.portfolios.add_position(portfolio_id, position)
            uow.commit()
        return position


def owned_portfolio(uow: UnitOfWork, user_id: str, portfolio_id: str) -> Portfolio:
    """Load a portfolio only if the user owns it; otherwise NotFound (404 for "not yours", Ch2)."""
    portfolio = uow.portfolios.get(portfolio_id)
    if portfolio is None or portfolio.owner_id != user_id:
        raise NotFound("No portfolio with this ID")
    return portfolio
