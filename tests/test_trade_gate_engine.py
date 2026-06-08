from __future__ import annotations

from core.trade_gate_engine import check_trade_gates


# ---------------------------------------------------------------------------
# 1. Normal – everything clean
# ---------------------------------------------------------------------------
def test_normal_all_clear() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "high_impact_event_within_30m": False,
        "m15_quality": "strict",
    }
    result = check_trade_gates(context)
    assert result["allowed"] is True
    assert result["decision_cap"] is None
    assert result["block_codes"] == []


# ---------------------------------------------------------------------------
# 2. Spread abnormal
# ---------------------------------------------------------------------------
def test_spread_abnormal_blocks() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "abnormal",
    }
    result = check_trade_gates(context)
    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert "SPREAD_ABNORMAL" in result["block_codes"]


# ---------------------------------------------------------------------------
# 3. High impact news nearby
# ---------------------------------------------------------------------------
def test_high_impact_news_nearby_blocks() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "high_impact_event_within_30m": True,
    }
    result = check_trade_gates(context)
    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert "HIGH_IMPACT_NEWS_NEARBY" in result["block_codes"]


# ---------------------------------------------------------------------------
# 4. M15 none
# ---------------------------------------------------------------------------
def test_m15_none_caps_watch_only() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "high_impact_event_within_30m": False,
        "m15_quality": "none",
    }
    result = check_trade_gates(context)
    assert result["allowed"] is True
    assert result["decision_cap"] == "WATCH_ONLY"
    assert "M15_NOT_CONFIRMED" in result["warning_codes"]


# ---------------------------------------------------------------------------
# 5. M15 loose
# ---------------------------------------------------------------------------
def test_m15_loose_caps_waiting_confirmation() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "high_impact_event_within_30m": False,
        "m15_quality": "loose",
    }
    result = check_trade_gates(context)
    assert result["allowed"] is True
    assert result["decision_cap"] == "WAITING_CONFIRMATION"
    assert "M15_LOOSE_CONFIRMATION" in result["warning_codes"]


# ---------------------------------------------------------------------------
# 6. Expected effective RR too low
# ---------------------------------------------------------------------------
def test_expected_rr_too_low() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "high_impact_event_within_30m": False,
        "m15_quality": "strict",
        "expected_effective_rr": 1.1,
    }
    result = check_trade_gates(context)
    assert result["allowed"] is True
    assert result["decision_cap"] == "WATCH_ONLY"
    assert "EXPECTED_RR_TOO_LOW" in result["warning_codes"]


# ---------------------------------------------------------------------------
# 7. Daily loss limit reached
# ---------------------------------------------------------------------------
def test_daily_loss_limit_reached() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "high_impact_event_within_30m": False,
        "daily_loss_limit_reached": True,
    }
    result = check_trade_gates(context)
    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert "DAILY_LOSS_LIMIT_REACHED" in result["block_codes"]


# ---------------------------------------------------------------------------
# 8. Score gap too low
# ---------------------------------------------------------------------------
def test_score_gap_low() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "high_impact_event_within_30m": False,
        "m15_quality": "strict",
        "score_gap": 5,
    }
    result = check_trade_gates(context)
    assert result["allowed"] is True
    assert result["decision_cap"] == "WAITING_CONFIRMATION"
    assert "BUY_SELL_SCORE_GAP_LOW" in result["warning_codes"]


# ---------------------------------------------------------------------------
# 9. Multiple gates simultaneously – spread abnormal + m15 none
# ---------------------------------------------------------------------------
def test_multiple_gates_spread_abnormal_and_m15_none() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "abnormal",
        "high_impact_event_within_30m": False,
        "m15_quality": "none",
    }
    result = check_trade_gates(context)
    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert "SPREAD_ABNORMAL" in result["block_codes"]
    assert "M15_NOT_CONFIRMED" in result["warning_codes"]


# ---------------------------------------------------------------------------
# 10. MT5 not ready
# ---------------------------------------------------------------------------
def test_mt5_not_ready() -> None:
    context = {
        "terminal_connected": False,
        "broker_logged_in": True,
    }
    result = check_trade_gates(context)
    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert "MT5_NOT_READY" in result["block_codes"]


# ---------------------------------------------------------------------------
# 11. Data quality warning
# ---------------------------------------------------------------------------
def test_data_quality_warning() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "data_quality_warning": True,
    }
    result = check_trade_gates(context)
    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert "DATA_QUALITY_WARNING" in result["block_codes"]


# ---------------------------------------------------------------------------
# 12. Weekly loss limit reached
# ---------------------------------------------------------------------------
def test_weekly_loss_limit_reached() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "weekly_loss_limit_reached": True,
    }
    result = check_trade_gates(context)
    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert "WEEKLY_LOSS_LIMIT_REACHED" in result["block_codes"]


# ---------------------------------------------------------------------------
# 13. Zone broken
# ---------------------------------------------------------------------------
def test_zone_broken() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "high_impact_event_within_30m": False,
        "zone_broken": True,
    }
    result = check_trade_gates(context)
    assert result["allowed"] is True
    assert result["decision_cap"] == "WATCH_ONLY"
    assert "ZONE_BROKEN" in result["warning_codes"]


# ---------------------------------------------------------------------------
# 14. Cap priority: TRADE_BLOCKED beats WATCH_ONLY when both present
#    (e.g. zone_broken warning + spread abnormal block)
# ---------------------------------------------------------------------------
def test_cap_priority_blocked_beats_watch_only() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "abnormal",
        "m15_quality": "none",
    }
    result = check_trade_gates(context)
    # allowed=False forces TRADE_BLOCKED no matter what warnings say
    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert "SPREAD_ABNORMAL" in result["block_codes"]
    assert "M15_NOT_CONFIRMED" in result["warning_codes"]


# ---------------------------------------------------------------------------
# 15. Empty context defaults – everything missing should pass clean
# ---------------------------------------------------------------------------
def test_empty_context_defaults_pass() -> None:
    result = check_trade_gates({})
    assert result["allowed"] is True
    assert result["decision_cap"] is None
    assert result["block_codes"] == []
    assert result["warning_codes"] == []
    assert result["reasons"] == []
