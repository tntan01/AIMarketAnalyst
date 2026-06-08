"""Phase 16.4 — verify score_gap prevents READY when Buy/Sell scores are close."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.signal_engine import calculate_direction_bias
from core.decision_engine import make_final_decision
from core.trade_gate_engine import check_trade_gates


# ---------------------------------------------------------------------------
# calculate_direction_bias
# ---------------------------------------------------------------------------


def test_bias_no_clear_when_gap_low():
    buy = {"signal_score": 80}
    sell = {"signal_score": 77}
    result = calculate_direction_bias(buy, sell, min_gap=10)
    assert result["score_gap"] == 3
    assert result["is_clear_bias"] is False
    assert result["best_side"] == "buy"  # buy > sell


def test_bias_clear_when_gap_wide():
    buy = {"signal_score": 82}
    sell = {"signal_score": 65}
    result = calculate_direction_bias(buy, sell, min_gap=10)
    assert result["score_gap"] == 17
    assert result["is_clear_bias"] is True
    assert result["best_side"] == "buy"


def test_bias_sell_clear():
    buy = {"signal_score": 40}
    sell = {"signal_score": 58}
    result = calculate_direction_bias(buy, sell, min_gap=10)
    assert result["score_gap"] == 18
    assert result["is_clear_bias"] is True
    assert result["best_side"] == "sell"


def test_bias_equal_scores():
    buy = {"signal_score": 50}
    sell = {"signal_score": 50}
    result = calculate_direction_bias(buy, sell, min_gap=10)
    assert result["score_gap"] == 0
    assert result["is_clear_bias"] is False
    assert result["best_side"] == "neutral"


def test_bias_uses_total_fallback():
    buy = {"total": 75}
    sell = {"total": 68}
    result = calculate_direction_bias(buy, sell, min_gap=10)
    assert result["score_gap"] == 7
    assert result["is_clear_bias"] is False


# ---------------------------------------------------------------------------
# decision_engine: score gap prevents READY
# ---------------------------------------------------------------------------


def test_decision_not_ready_when_gap_low():
    result = make_final_decision(
        final_score=90,
        gate_result={"allowed": True},
        entry_status="confirmed_entry",
        score_gap=3,
    )
    assert result["decision"] == "WAITING_CONFIRMATION"
    assert result["decision"] != "READY_TO_TRADE"


def test_decision_ready_when_gap_clear():
    result = make_final_decision(
        final_score=90,
        gate_result={"allowed": True},
        entry_status="confirmed_entry",
        score_gap=17,
    )
    assert result["decision"] == "READY_TO_TRADE"


# ---------------------------------------------------------------------------
# trade_gate: score gap gate
# ---------------------------------------------------------------------------


def test_gate_caps_on_low_score_gap():
    ctx = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "high_impact_event_within_30m": False,
        "m15_quality": "strict",
        "expected_effective_rr": 2.0,
        "score_gap": 3,
        "min_buy_sell_score_gap": 10,
        "zone_broken": False,
        "daily_loss_limit_reached": False,
        "weekly_loss_limit_reached": False,
    }
    result = check_trade_gates(ctx)
    assert result["decision_cap"] == "WAITING_CONFIRMATION"


def test_gate_no_cap_when_gap_clear():
    ctx = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "high_impact_event_within_30m": False,
        "m15_quality": "strict",
        "expected_effective_rr": 2.0,
        "score_gap": 17,
        "min_buy_sell_score_gap": 10,
        "zone_broken": False,
        "daily_loss_limit_reached": False,
        "weekly_loss_limit_reached": False,
    }
    result = check_trade_gates(ctx)
    assert result["allowed"] is True
    assert result["decision_cap"] is None
