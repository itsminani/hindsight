"""Unit tests for the domain layer: no database, no HTTP, so they run in milliseconds."""

import re
from datetime import date

import pytest

from hindsight.domain.ids import new_id
from hindsight.domain.models import InsufficientCredits, Plan, PlanKind, Position, report_cost


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


def _plan(available: int, held: int = 0) -> Plan:
    """A shared plan with the given balances."""
    return Plan("pl_1", "us_1", PlanKind.SHARED, credits_available=available, credits_held=held)


def test_hold_moves_credits_from_available_to_held():
    """Holding 2 of 3 credits leaves 1 available and 2 held."""
    plan = _plan(3)
    plan.hold(2)
    assert (plan.credits_available, plan.credits_held) == (1, 2)


def test_hold_refuses_more_than_available():
    """Asking for more than the plan has raises InsufficientCredits and changes nothing."""
    plan = _plan(1)
    with pytest.raises(InsufficientCredits) as caught:
        plan.hold(2)
    assert (caught.value.needed, caught.value.available) == (2, 1)
    assert (plan.credits_available, plan.credits_held) == (1, 0)


def test_charge_spends_held_credits_for_good():
    """A finished report: its held credits disappear (they were paid)."""
    plan = _plan(1, held=2)
    plan.charge(2)
    assert (plan.credits_available, plan.credits_held) == (1, 0)


def test_release_gives_held_credits_back():
    """A failed report: its held credits go back to available (compensation)."""
    plan = _plan(1, held=2)
    plan.release(2)
    assert (plan.credits_available, plan.credits_held) == (3, 0)


@pytest.mark.parametrize("operation", ["charge", "release"])
def test_cannot_charge_or_release_more_than_held(operation):
    """Charging or releasing more than is held is a bug, refused loudly."""
    with pytest.raises(ValueError):
        getattr(_plan(5, held=1), operation)(2)


def test_report_cost_is_one_credit_per_distinct_ticker():
    """Two AAPL lots and one MSFT lot cost 2 credits."""
    lots = [
        Position("ps_1", "AAPL", 1, date(2020, 1, 2), date(2021, 1, 4)),
        Position("ps_2", "AAPL", 5, date(2020, 3, 2), date(2021, 1, 4)),
        Position("ps_3", "MSFT", 2, date(2020, 1, 2), date(2021, 1, 4)),
    ]
    assert report_cost(lots) == 2
