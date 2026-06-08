from __future__ import annotations

import pytest

from core.risk_engine import calculate_expected_effective_rr, calculate_spread_cost


# ---------------------------------------------------------------------------
# calculate_spread_cost
# ---------------------------------------------------------------------------

def test_spread_cost_valid_float():
    assert calculate_spread_cost(0.0002) == 0.0002


def test_spread_cost_none_returns_zero():
    assert calculate_spread_cost(None) == 0.0


def test_spread_cost_negative_returns_zero():
    assert calculate_spread_cost(-0.001) == 0.0


def test_spread_cost_string_valid():
    assert calculate_spread_cost("0.0002") == 0.0002


def test_spread_cost_string_invalid_returns_zero():
    assert calculate_spread_cost("abc") == 0.0


def test_spread_cost_zero():
    assert calculate_spread_cost(0.0) == 0.0


def test_spread_cost_int():
    assert calculate_spread_cost(2) == 2.0


# ---------------------------------------------------------------------------
# calculate_expected_effective_rr — buy
# ---------------------------------------------------------------------------

def test_buy_normal_rr():
    rr = calculate_expected_effective_rr(
        direction="buy", entry=1.1000, stop_loss=1.0950,
        take_profit=1.1100, spread_price=0.0002,
    )
    # risk=0.0050, reward=0.0100
    # effective_risk=0.0052, effective_reward=0.0098
    # rr = 0.0098 / 0.0052 ~ 1.8846
    assert rr == pytest.approx(1.8846, rel=1e-3)


def test_buy_no_spread():
    rr = calculate_expected_effective_rr(
        direction="buy", entry=1.1000, stop_loss=1.0950,
        take_profit=1.1100, spread_price=0.0,
    )
    # risk=0.0050, reward=0.0100, no spread
    # rr = 0.0100 / 0.0050 = 2.0
    assert rr == 2.0


# ---------------------------------------------------------------------------
# calculate_expected_effective_rr — sell
# ---------------------------------------------------------------------------

def test_sell_normal_rr():
    rr = calculate_expected_effective_rr(
        direction="sell", entry=1.1000, stop_loss=1.1050,
        take_profit=1.0900, spread_price=0.0002,
    )
    # risk=0.0050, reward=0.0100
    # effective_risk=0.0052, effective_reward=0.0098
    assert rr == pytest.approx(1.8846, rel=1e-3)


def test_sell_no_spread():
    rr = calculate_expected_effective_rr(
        direction="sell", entry=1.1000, stop_loss=1.1050,
        take_profit=1.0900, spread_price=0.0,
    )
    assert rr == 2.0


# ---------------------------------------------------------------------------
# Edge cases — spread makes reward negative
# ---------------------------------------------------------------------------

def test_spread_too_large_reward_negative():
    rr = calculate_expected_effective_rr(
        direction="buy", entry=1.1000, stop_loss=1.0990,
        take_profit=1.1005, spread_price=0.0010,
    )
    assert rr == 0.0


# ---------------------------------------------------------------------------
# Edge cases — invalid direction
# ---------------------------------------------------------------------------

def test_invalid_direction_returns_zero():
    assert calculate_expected_effective_rr("hold", 1.1, 1.0, 1.2, 0.0001) == 0.0


def test_empty_direction_returns_zero():
    assert calculate_expected_effective_rr("", 1.1, 1.0, 1.2, 0.0001) == 0.0


# ---------------------------------------------------------------------------
# Edge cases — None inputs
# ---------------------------------------------------------------------------

def test_entry_none_returns_zero():
    assert calculate_expected_effective_rr("buy", None, 1.0, 1.2, 0.0001) == 0.0


def test_stop_loss_none_returns_zero():
    assert calculate_expected_effective_rr("buy", 1.1, None, 1.2, 0.0001) == 0.0


def test_take_profit_none_returns_zero():
    assert calculate_expected_effective_rr("buy", 1.1, 1.0, None, 0.0001) == 0.0


# ---------------------------------------------------------------------------
# Edge cases — zero or negative risk
# ---------------------------------------------------------------------------

def test_entry_equals_stop_loss_returns_zero():
    rr = calculate_expected_effective_rr("buy", 1.1000, 1.1000, 1.1100, 0.0)
    assert rr == 0.0


# ---------------------------------------------------------------------------
# Edge cases — spread default
# ---------------------------------------------------------------------------

def test_spread_default_zero():
    rr = calculate_expected_effective_rr("buy", 1.1000, 1.0950, 1.1100)
    # spread mặc định = 0 → risk=0.005, reward=0.010, rr=2.0
    assert rr == 2.0


# ---------------------------------------------------------------------------
# Edge cases — uppercase direction
# ---------------------------------------------------------------------------

def test_uppercase_direction():
    rr = calculate_expected_effective_rr("BUY", 1.1000, 1.0950, 1.1100, 0.0)
    assert rr == 2.0

    rr = calculate_expected_effective_rr("SELL", 1.1000, 1.1050, 1.0900, 0.0)
    assert rr == 2.0


# ---------------------------------------------------------------------------
# Edge cases — large spread int
# ---------------------------------------------------------------------------

def test_spread_int_large():
    # spread = 3 pips → risk+spread >> reward
    rr = calculate_expected_effective_rr("buy", 1.1000, 1.0990, 1.1005, 0.0030)
    assert rr == 0.0
