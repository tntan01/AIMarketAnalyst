from __future__ import annotations

from core.trade_gate_engine import check_trade_gates


# ---------------------------------------------------------------------------
# 1. Account guard daily loss → TRADE_BLOCKED
# ---------------------------------------------------------------------------
def test_account_guard_daily_loss_block() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "m15_quality": "strict",
        "score_gap": 30,
        "expected_effective_rr": 1.8,
        "account_guard": {
            "allowed": False,
            "blocked": True,
            "block_codes": ["DAILY_LOSS_LIMIT_REACHED"],
            "warning_codes": [],
            "reasons": ["Đã chạm giới hạn lỗ trong ngày."],
            "stats": {"daily_result_pct": -2.1},
        },
    }
    result = check_trade_gates(context)
    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert "DAILY_LOSS_LIMIT_REACHED" in result["block_codes"]
    assert "account_guard_stats" in result
    assert result["account_guard_stats"]["daily_result_pct"] == -2.1


# ---------------------------------------------------------------------------
# 2. Account guard weekly loss → TRADE_BLOCKED
# ---------------------------------------------------------------------------
def test_account_guard_weekly_loss_block() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "m15_quality": "strict",
        "account_guard": {
            "allowed": False,
            "blocked": True,
            "block_codes": ["WEEKLY_LOSS_LIMIT_REACHED"],
            "warning_codes": [],
            "reasons": ["Đã chạm giới hạn lỗ trong tuần."],
            "stats": {"weekly_result_pct": -5.2},
        },
    }
    result = check_trade_gates(context)
    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert "WEEKLY_LOSS_LIMIT_REACHED" in result["block_codes"]


# ---------------------------------------------------------------------------
# 3. Account guard max open risk → TRADE_BLOCKED
# ---------------------------------------------------------------------------
def test_account_guard_max_open_risk_block() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "m15_quality": "strict",
        "account_guard": {
            "allowed": False,
            "blocked": True,
            "block_codes": ["MAX_OPEN_RISK_REACHED"],
            "warning_codes": [],
            "reasons": ["Tổng rủi ro lệnh đang mở đã vượt giới hạn."],
            "stats": {"open_risk_pct": 3.5},
        },
    }
    result = check_trade_gates(context)
    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert "MAX_OPEN_RISK_REACHED" in result["block_codes"]


# ---------------------------------------------------------------------------
# 4. Account guard consecutive losses → TRADE_BLOCKED
# ---------------------------------------------------------------------------
def test_account_guard_consecutive_losses_block() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "m15_quality": "strict",
        "account_guard": {
            "allowed": False,
            "blocked": True,
            "block_codes": ["MAX_CONSECUTIVE_LOSSES_REACHED"],
            "warning_codes": [],
            "reasons": ["Đã có 3 lệnh thua liên tiếp."],
            "stats": {"consecutive_losses": 3},
        },
    }
    result = check_trade_gates(context)
    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert "MAX_CONSECUTIVE_LOSSES_REACHED" in result["block_codes"]


# ---------------------------------------------------------------------------
# 5. Account guard allowed → no block
# ---------------------------------------------------------------------------
def test_account_guard_allowed_no_block() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "m15_quality": "strict",
        "expected_effective_rr": 2.0,
        "score_gap": 30,
        "account_guard": {
            "allowed": True,
            "blocked": False,
            "block_codes": [],
            "warning_codes": [],
            "reasons": [],
            "stats": {"daily_result_pct": 0.0},
        },
    }
    result = check_trade_gates(context)
    assert result["allowed"] is True
    assert result["decision_cap"] is None
    assert result["block_codes"] == []
    assert "account_guard_stats" in result


# ---------------------------------------------------------------------------
# 6. Account guard block + M15 none → block wins over WATCH_ONLY
# ---------------------------------------------------------------------------
def test_account_guard_block_beats_m15_watch_only() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "m15_quality": "none",
        "account_guard": {
            "allowed": False,
            "blocked": True,
            "block_codes": ["DAILY_LOSS_LIMIT_REACHED"],
            "warning_codes": [],
            "reasons": ["Đã chạm giới hạn lỗ trong ngày."],
            "stats": {"daily_result_pct": -2.1},
        },
    }
    result = check_trade_gates(context)
    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert "DAILY_LOSS_LIMIT_REACHED" in result["block_codes"]
    # M15 warning still recorded
    assert "M15_NOT_CONFIRMED" in result["warning_codes"]


# ---------------------------------------------------------------------------
# 7. Account guard block + expected RR low + M15 loose → block wins
# ---------------------------------------------------------------------------
def test_account_guard_block_with_multiple_warnings() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "m15_quality": "loose",
        "expected_effective_rr": 1.0,
        "score_gap": 3,
        "account_guard": {
            "allowed": False,
            "blocked": True,
            "block_codes": ["WEEKLY_LOSS_LIMIT_REACHED"],
            "warning_codes": [],
            "reasons": ["Đã chạm giới hạn lỗ trong tuần."],
            "stats": {"weekly_result_pct": -5.2},
        },
    }
    result = check_trade_gates(context)
    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert "WEEKLY_LOSS_LIMIT_REACHED" in result["block_codes"]
    # Warnings still collected
    assert "M15_LOOSE_CONFIRMATION" in result["warning_codes"]
    assert "EXPECTED_RR_TOO_LOW" in result["warning_codes"]
    assert "BUY_SELL_SCORE_GAP_LOW" in result["warning_codes"]


# ---------------------------------------------------------------------------
# 8. No account_guard key → behavior unchanged
# ---------------------------------------------------------------------------
def test_no_account_guard_behavior_unchanged() -> None:
    """Without account_guard key, existing gates should work identically."""
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "abnormal",
    }
    result = check_trade_gates(context)
    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert "SPREAD_ABNORMAL" in result["block_codes"]
    # account_guard_stats only appears when account_guard is present
    assert "account_guard_stats" not in result


# ---------------------------------------------------------------------------
# 9. Account guard is None → no effect
# ---------------------------------------------------------------------------
def test_account_guard_none_no_effect() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "m15_quality": "strict",
        "account_guard": None,
    }
    result = check_trade_gates(context)
    assert result["allowed"] is True
    assert result["decision_cap"] is None


# ---------------------------------------------------------------------------
# 10. Account guard with warnings only → no block, warnings merged
# ---------------------------------------------------------------------------
def test_account_guard_warnings_only_no_block() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "m15_quality": "strict",
        "account_guard": {
            "allowed": True,
            "blocked": False,
            "block_codes": [],
            "warning_codes": ["ACCOUNT_GUARD_WARNING"],
            "reasons": ["Cảnh báo: gần giới hạn lỗ."],
            "stats": {"daily_result_pct": -1.8},
        },
    }
    result = check_trade_gates(context)
    assert result["allowed"] is True
    assert "ACCOUNT_GUARD_WARNING" in result["warning_codes"]


# ---------------------------------------------------------------------------
# 11. Account guard daily loss + spread abnormal → both blocks returned
# ---------------------------------------------------------------------------
def test_account_guard_and_spread_both_block() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "abnormal",
        "account_guard": {
            "allowed": False,
            "blocked": True,
            "block_codes": ["DAILY_LOSS_LIMIT_REACHED"],
            "warning_codes": [],
            "reasons": ["Đã chạm giới hạn lỗ trong ngày."],
            "stats": {"daily_result_pct": -2.1},
        },
    }
    result = check_trade_gates(context)
    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert "SPREAD_ABNORMAL" in result["block_codes"]
    assert "DAILY_LOSS_LIMIT_REACHED" in result["block_codes"]


# ---------------------------------------------------------------------------
# 12. Account guard stats passed through
# ---------------------------------------------------------------------------
def test_account_guard_stats_passed_through() -> None:
    context = {
        "account_guard": {
            "allowed": True,
            "blocked": False,
            "block_codes": [],
            "warning_codes": [],
            "reasons": [],
            "stats": {
                "daily_result_pct": -0.5,
                "weekly_result_pct": -1.2,
                "consecutive_losses": 2,
                "open_risk_pct": 1.5,
            },
        },
    }
    result = check_trade_gates(context)
    assert "account_guard_stats" in result
    stats = result["account_guard_stats"]
    assert stats["daily_result_pct"] == -0.5
    assert stats["weekly_result_pct"] == -1.2
    assert stats["consecutive_losses"] == 2
    assert stats["open_risk_pct"] == 1.5
