"""Phase 16.5 — test expected effective R:R with spread impact."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.risk_engine import calculate_expected_effective_rr
from core.trade_gate_engine import check_trade_gates
from core.reason_codes import EXPECTED_RR_TOO_LOW


# ---------------------------------------------------------------------------
# calculate_expected_effective_rr
# ---------------------------------------------------------------------------


def test_buy_ideal_rr_15_spread_large():
    """Ideal R:R 1.5, spread 30 pips → effective should drop well below 1.3."""
    result = calculate_expected_effective_rr(
        direction="buy",
        entry=1.1000,
        stop_loss=1.0900,
        take_profit=1.1150,
        spread_price=0.0030,
    )
    # ideal: 0.015/0.010 = 1.5
    # spread cost = 0.003
    # effective_risk = 0.010 + 0.003 = 0.013
    # effective_reward = 0.015 - 0.003 = 0.012
    # expected ≈ 0.012/0.013 ≈ 0.9231
    assert result < 1.3
    assert result > 0.0


def test_buy_ideal_rr_15_spread_small():
    """Ideal R:R 1.5, tight spread → stays above 1.3."""
    result = calculate_expected_effective_rr(
        direction="buy",
        entry=1.1000,
        stop_loss=1.0900,
        take_profit=1.1150,
        spread_price=0.0002,
    )
    # effective_risk = 0.010 + 0.0002 = 0.0102
    # effective_reward = 0.015 - 0.0002 = 0.0148
    # ≈ 1.4510
    assert result > 1.3


def test_sell_spread_large():
    """Sell side also impacted by large spread."""
    result = calculate_expected_effective_rr(
        direction="sell",
        entry=1.1000,
        stop_loss=1.1100,
        take_profit=1.0850,
        spread_price=0.0030,
    )
    # risk = 1.110 - 1.100 = 0.010, reward = 1.100 - 1.085 = 0.015
    # effective_risk = 0.013, effective_reward = 0.012 → ≈0.923
    assert result < 1.3
    assert result > 0.0


def test_dirty_data_no_crash():
    assert calculate_expected_effective_rr("buy", None, 1.0, 1.1, 0.001) == 0.0
    assert calculate_expected_effective_rr("sell", 1.0, None, 1.1, 0.001) == 0.0
    assert calculate_expected_effective_rr("buy", 1.0, 1.1, None, 0.001) == 0.0


def test_zero_risk_still_computable():
    """Entry == SL gives extremely high R:R (only spread cost counts as risk)."""
    result = calculate_expected_effective_rr("buy", 1.1000, 1.1000, 1.1200, 0.001)
    # risk = 0, so effective_risk = just spread_cost (0.001)
    # effective_rr = (0.020 - 0.001) / 0.001 = 19.0 — extremely high
    assert result > 10.0  # very high because only spread is the cost


# ---------------------------------------------------------------------------
# Gate integration
# ---------------------------------------------------------------------------


def test_gate_caps_on_low_expected_rr():
    ctx = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "high_impact_event_within_30m": False,
        "m15_quality": "strict",
        "expected_effective_rr": 1.1,
        "score_gap": 15,
        "min_buy_sell_score_gap": 10,
        "zone_broken": False,
        "daily_loss_limit_reached": False,
        "weekly_loss_limit_reached": False,
    }
    result = check_trade_gates(ctx)
    assert result["decision_cap"] == "WATCH_ONLY"
    assert EXPECTED_RR_TOO_LOW in result["warning_codes"]


def test_gate_ok_when_rr_good():
    ctx = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "high_impact_event_within_30m": False,
        "m15_quality": "strict",
        "expected_effective_rr": 2.0,
        "score_gap": 15,
        "min_buy_sell_score_gap": 10,
        "zone_broken": False,
        "daily_loss_limit_reached": False,
        "weekly_loss_limit_reached": False,
    }
    result = check_trade_gates(ctx)
    assert result["allowed"] is True
    assert result["decision_cap"] is None
