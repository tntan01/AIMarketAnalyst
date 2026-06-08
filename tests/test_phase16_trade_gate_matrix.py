"""Phase 16.3 — trade gate matrix test: spread, news, M15, R:R, score gap."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.trade_gate_engine import check_trade_gates
from core.reason_codes import (
    SPREAD_ABNORMAL,
    HIGH_IMPACT_NEWS_NEARBY,
    M15_NOT_CONFIRMED,
    M15_LOOSE_CONFIRMATION,
    EXPECTED_RR_TOO_LOW,
    BUY_SELL_SCORE_GAP_LOW,
    MT5_NOT_READY,
)


def _base_context() -> dict:
    return {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "high_impact_event_within_30m": False,
        "m15_quality": "strict",
        "expected_effective_rr": 1.8,
        "score_gap": 20,
        "min_buy_sell_score_gap": 10,
        "zone_broken": False,
        "daily_loss_limit_reached": False,
        "weekly_loss_limit_reached": False,
    }


# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------


def test_clean_context_allows():
    result = check_trade_gates(_base_context())
    assert result["allowed"] is True
    assert result["decision_cap"] is None


# ---------------------------------------------------------------------------
# Spread abnormal
# ---------------------------------------------------------------------------


def test_spread_abnormal_blocks():
    ctx = _base_context()
    ctx["spread_status"] = "abnormal"
    result = check_trade_gates(ctx)
    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert SPREAD_ABNORMAL in result["block_codes"]


# ---------------------------------------------------------------------------
# MT5 not ready
# ---------------------------------------------------------------------------


def test_mt5_not_ready_blocks():
    ctx = _base_context()
    ctx["terminal_connected"] = False
    result = check_trade_gates(ctx)
    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert MT5_NOT_READY in result["block_codes"]


# ---------------------------------------------------------------------------
# High impact news
# ---------------------------------------------------------------------------


def test_high_impact_news_blocks():
    ctx = _base_context()
    ctx["high_impact_event_within_30m"] = True
    result = check_trade_gates(ctx)
    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert HIGH_IMPACT_NEWS_NEARBY in result["block_codes"]


# ---------------------------------------------------------------------------
# M15 none
# ---------------------------------------------------------------------------


def test_m15_none_watch_only():
    ctx = _base_context()
    ctx["m15_quality"] = "none"
    result = check_trade_gates(ctx)
    assert result["allowed"] is True  # still allowed, but capped
    assert result["decision_cap"] == "WATCH_ONLY"
    assert M15_NOT_CONFIRMED in result["warning_codes"]


# ---------------------------------------------------------------------------
# M15 loose
# ---------------------------------------------------------------------------


def test_m15_loose_waiting():
    ctx = _base_context()
    ctx["m15_quality"] = "loose"
    result = check_trade_gates(ctx)
    assert result["allowed"] is True
    assert result["decision_cap"] == "WAITING_CONFIRMATION"
    assert M15_LOOSE_CONFIRMATION in result["warning_codes"]


# ---------------------------------------------------------------------------
# Expected effective R:R low
# ---------------------------------------------------------------------------


def test_low_expected_rr():
    ctx = _base_context()
    ctx["expected_effective_rr"] = 1.1
    result = check_trade_gates(ctx)
    assert result["allowed"] is True
    assert result["decision_cap"] == "WATCH_ONLY"
    assert EXPECTED_RR_TOO_LOW in result["warning_codes"]


# ---------------------------------------------------------------------------
# Score gap low
# ---------------------------------------------------------------------------


def test_score_gap_low():
    ctx = _base_context()
    ctx["score_gap"] = 3  # below min 10
    result = check_trade_gates(ctx)
    assert result["allowed"] is True
    assert result["decision_cap"] == "WAITING_CONFIRMATION"
    assert BUY_SELL_SCORE_GAP_LOW in result["warning_codes"]


# ---------------------------------------------------------------------------
# Zone broken
# ---------------------------------------------------------------------------


def test_zone_broken():
    ctx = _base_context()
    ctx["zone_broken"] = True
    result = check_trade_gates(ctx)
    # zone_broken → WATCH_ONLY cap
    assert result["allowed"] is True
    assert result["decision_cap"] == "WATCH_ONLY"
