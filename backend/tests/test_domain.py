"""Unit tests for the domain layer: no database, no HTTP, so they run in milliseconds."""

import re
from datetime import date

import pytest

from hindsight.domain.ids import new_id
from hindsight.domain.models import Position


def test_new_id_has_prefix_and_matches_contract_pattern():
    """IDs look like the contract says: prefix, underscore, letters and digits only."""
    assert re.fullmatch(r"pf_[A-Za-z0-9]+", new_id("portfolio"))
    assert new_id("user").startswith("us_")


def test_new_ids_are_unique():
    """Many IDs in a row never repeat."""
    ids = {new_id("report") for _ in range(10_000)}
    assert len(ids) == 10_000


def test_position_rejects_sell_before_buy():
    """A sale cannot happen before the purchase."""
    with pytest.raises(ValueError):
        Position(id="ps_1", ticker="AAPL", shares=1, buy_date=date(2024, 5, 1), sell_date=date(2024, 1, 1))


def test_position_rejects_zero_shares():
    """A position needs at least one share."""
    with pytest.raises(ValueError):
        Position(id="ps_1", ticker="AAPL", shares=0, buy_date=date(2024, 1, 1))


def test_position_is_sold_only_with_sell_date():
    """is_sold follows the sell date."""
    held = Position(id="ps_1", ticker="AAPL", shares=1, buy_date=date(2024, 1, 1))
    sold = Position(id="ps_2", ticker="AAPL", shares=1, buy_date=date(2024, 1, 1), sell_date=date(2024, 2, 1))
    assert not held.is_sold and sold.is_sold
