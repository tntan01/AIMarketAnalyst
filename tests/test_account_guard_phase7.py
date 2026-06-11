from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.account_guard import (
    RISK_INCREASING_ACTIONS,
    RISK_REDUCING_ACTIONS,
    calculate_loss_stats,
    calculate_open_risk_pct,
    check_account_guard,
    get_day_range,
    get_week_range,
)


# ---------------------------------------------------------------------------
# get_day_range / get_week_range
# ---------------------------------------------------------------------------
def test_day_range_returns_start_end() -> None:
    start, end = get_day_range(timezone_name="Asia/Ho_Chi_Minh")
    assert start < end
    assert (end - start) == timedelta(days=1)
    assert start.hour == 0 and start.minute == 0


def test_day_range_fallback_timezone() -> None:
    start, end = get_day_range(timezone_name="Not/A_Real_Zone")
    assert start < end
    assert (end - start) == timedelta(days=1)


def test_week_range_monday_start() -> None:
    tz_name = "Asia/Ho_Chi_Minh"
    start, end = get_week_range(timezone_name=tz_name)
    assert start.weekday() == 0
    assert (end - start) == timedelta(days=7)


def test_week_range_fallback_timezone() -> None:
    start, end = get_week_range(timezone_name="Not/A_Real_Zone")
    assert start < end
    assert (end - start) == timedelta(days=7)


# ---------------------------------------------------------------------------
# calculate_loss_stats
# ---------------------------------------------------------------------------
def test_loss_stats_no_trades() -> None:
    stats = calculate_loss_stats()
    assert stats["daily_result_pct"] == 0.0
    assert stats["weekly_result_pct"] == 0.0
    assert stats["consecutive_losses"] == 0
    assert stats["daily_trade_count"] == 0
    assert stats["weekly_trade_count"] == 0


def test_loss_stats_none_trades() -> None:
    stats = calculate_loss_stats(None)
    assert stats["daily_result_pct"] == 0.0


def test_loss_stats_empty_list() -> None:
    stats = calculate_loss_stats([])
    assert stats["daily_result_pct"] == 0.0


def test_loss_stats_daily_only() -> None:
    today = datetime.now(UTC)
    trades = [
        {"closed_at": today.isoformat(), "result_pct": -1.5},
        {"closed_at": today.isoformat(), "result_pct": -0.8},
    ]
    stats = calculate_loss_stats(trades, now=today, timezone_name="UTC")
    assert stats["daily_result_pct"] == -2.3
    assert stats["daily_trade_count"] == 2
    assert stats["weekly_trade_count"] == 2
    # Both are losses → consecutive = 2
    assert stats["consecutive_losses"] == 2


def test_loss_stats_consecutive_mixed() -> None:
    today = datetime.now(UTC)
    trades = [
        {"closed_at": (today - timedelta(days=3)).isoformat(), "result_pct": -0.5},
        {"closed_at": (today - timedelta(days=2)).isoformat(), "result_pct": 0.3},
        {"closed_at": (today - timedelta(days=1)).isoformat(), "result_pct": -0.7},
        {"closed_at": today.isoformat(), "result_pct": -0.9},
    ]
    stats = calculate_loss_stats(trades, now=today, timezone_name="UTC")
    # Only today's trades count for consecutive losses (daily reset).
    assert stats["consecutive_losses"] == 1
    # Only today's trade in daily
    assert stats["daily_trade_count"] == 1
    assert stats["daily_result_pct"] == -0.9


def test_loss_stats_uses_result_r_fallback() -> None:
    today = datetime.now(UTC)
    trades = [
        {"closed_at": today.isoformat(), "result_pct": 0.0, "result_r": -0.5},
    ]
    stats = calculate_loss_stats(trades, now=today, timezone_name="UTC")
    # result_pct == 0 → check result_r (< 0 → loss)
    assert stats["consecutive_losses"] == 1


def test_loss_stats_weekly_aggregation() -> None:
    today = datetime.now(UTC)
    monday = today - timedelta(days=today.weekday())
    trades = [
        {"closed_at": monday.isoformat(), "result_pct": -2.0},
        {"closed_at": (monday + timedelta(days=1)).isoformat(), "result_pct": -1.5},
        {"closed_at": (monday + timedelta(days=2)).isoformat(), "result_pct": -1.7},
    ]
    stats = calculate_loss_stats(trades, now=today, timezone_name="UTC")
    assert stats["weekly_result_pct"] == -5.2
    assert stats["weekly_trade_count"] == 3


def test_loss_stats_closed_at_iso_string() -> None:
    today = datetime.now(UTC)
    trades = [
        {
            "closed_at": today.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "result_pct": -1.0,
        },
    ]
    stats = calculate_loss_stats(trades, now=today, timezone_name="UTC")
    assert stats["daily_result_pct"] == -1.0


def test_loss_stats_closed_at_datetime_object() -> None:
    today = datetime.now(UTC)
    trades = [
        {"closed_at": today, "result_pct": -1.0},
    ]
    stats = calculate_loss_stats(trades, now=today, timezone_name="UTC")
    assert stats["daily_result_pct"] == -1.0


# ---------------------------------------------------------------------------
# calculate_open_risk_pct
# ---------------------------------------------------------------------------
def test_open_risk_no_trades() -> None:
    assert calculate_open_risk_pct() == 0.0
    assert calculate_open_risk_pct(None) == 0.0
    assert calculate_open_risk_pct([]) == 0.0


def test_open_risk_sums_correctly() -> None:
    trades = [
        {"risk_pct": 1.5},
        {"risk_pct": 0.8},
    ]
    assert calculate_open_risk_pct(trades) == 2.3


def test_open_risk_fallback_keys() -> None:
    trades = [
        {"planned_risk_pct": 1.0},
        {"current_risk_pct": 0.5},
        {"risk_pct": 0.3},
    ]
    assert calculate_open_risk_pct(trades) == 1.8


def test_open_risk_skips_invalid() -> None:
    trades = [
        {"risk_pct": "abc"},
        {"risk_pct": None},
        {},
        {"risk_pct": 1.0},
    ]
    # "abc" → float("abc") raises → 0.0; None → 0.0; missing → 0.0; 1.0=1.0
    assert calculate_open_risk_pct(trades) == 1.0


# ---------------------------------------------------------------------------
# check_account_guard — no trades
# ---------------------------------------------------------------------------
def test_guard_no_trades_allowed() -> None:
    result = check_account_guard()
    assert result["allowed"] is True
    assert result["blocked"] is False
    assert result["block_codes"] == []


def test_guard_none_inputs() -> None:
    result = check_account_guard(
        closed_trades=None,
        open_trades=None,
        settings=None,
        action="open_new_trade",
    )
    assert result["allowed"] is True
    assert result["blocked"] is False


# ---------------------------------------------------------------------------
# check_account_guard — daily loss
# ---------------------------------------------------------------------------
def test_guard_daily_loss_reached() -> None:
    today = datetime.now(UTC)
    trades = [
        {"closed_at": today.isoformat(), "result_pct": -2.1},
    ]
    settings = {"max_daily_loss_pct": 2.0, "trader_timezone": "UTC"}
    result = check_account_guard(
        closed_trades=trades,
        settings=settings,
        action="open_new_trade",
        now=today,
    )
    assert result["allowed"] is False
    assert result["blocked"] is True
    assert "DAILY_LOSS_LIMIT_REACHED" in result["block_codes"]
    assert result["stats"]["daily_result_pct"] == -2.1


# ---------------------------------------------------------------------------
# check_account_guard — weekly loss
# ---------------------------------------------------------------------------
def test_guard_weekly_loss_reached() -> None:
    today = datetime.now(UTC)
    monday = today - timedelta(days=today.weekday())
    trades = [
        {"closed_at": monday.isoformat(), "result_pct": -2.5},
        {"closed_at": (monday + timedelta(days=2)).isoformat(), "result_pct": -2.7},
    ]
    settings = {"max_weekly_loss_pct": 5.0, "trader_timezone": "UTC"}
    result = check_account_guard(
        closed_trades=trades,
        settings=settings,
        action="open_new_trade",
        now=today,
    )
    assert "WEEKLY_LOSS_LIMIT_REACHED" in result["block_codes"]
    assert result["allowed"] is False


# ---------------------------------------------------------------------------
# check_account_guard — consecutive losses
# ---------------------------------------------------------------------------
def test_guard_consecutive_losses_reached() -> None:
    today = datetime.now(UTC)
    # 3 losses all within the same day to trigger consecutive loss guard
    trades = [
        {"closed_at": today.replace(hour=9).isoformat(), "result_pct": -0.3},
        {"closed_at": today.replace(hour=10).isoformat(), "result_pct": -0.4},
        {"closed_at": today.replace(hour=11).isoformat(), "result_pct": -0.5},
    ]
    settings = {
        "max_daily_loss_pct": 100.0,
        "max_weekly_loss_pct": 100.0,
        "max_consecutive_losses": 3,
        "trader_timezone": "UTC",
    }
    result = check_account_guard(
        closed_trades=trades,
        settings=settings,
        action="open_new_trade",
        now=today,
    )
    assert "MAX_CONSECUTIVE_LOSSES_REACHED" in result["block_codes"]
    assert result["allowed"] is False


def test_guard_consecutive_losses_not_reached_yet() -> None:
    today = datetime.now(UTC)
    trades = [
        {"closed_at": (today - timedelta(days=1)).isoformat(), "result_pct": -0.3},
        {"closed_at": today.isoformat(), "result_pct": -0.4},
    ]
    settings = {
        "max_consecutive_losses": 3,
        "trader_timezone": "UTC",
    }
    result = check_account_guard(
        closed_trades=trades,
        settings=settings,
        action="open_new_trade",
        now=today,
    )
    assert result["allowed"] is True


# ---------------------------------------------------------------------------
# check_account_guard — max open risk
# ---------------------------------------------------------------------------
def test_guard_max_open_risk_reached() -> None:
    open_trades = [
        {"risk_pct": 2.0},
        {"risk_pct": 1.2},
    ]
    settings = {"max_open_risk_pct": 3.0}
    result = check_account_guard(
        open_trades=open_trades,
        settings=settings,
        action="open_new_trade",
    )
    assert "MAX_OPEN_RISK_REACHED" in result["block_codes"]
    assert result["allowed"] is False
    assert result["stats"]["open_risk_pct"] == 3.2


# ---------------------------------------------------------------------------
# check_account_guard — risk-reducing actions always allowed
# ---------------------------------------------------------------------------
def test_guard_risk_reducing_always_allowed() -> None:
    today = datetime.now(UTC)
    trades = [
        {"closed_at": today.isoformat(), "result_pct": -5.0},
    ]
    settings = {"max_daily_loss_pct": 2.0, "trader_timezone": "UTC"}
    result = check_account_guard(
        closed_trades=trades,
        settings=settings,
        action="close_trade",
        now=today,
    )
    assert result["allowed"] is True
    assert result["blocked"] is False
    # Stats still show the violation
    assert result["stats"]["daily_result_pct"] == -5.0
    assert "DAILY_LOSS_LIMIT_REACHED" in result["block_codes"]


def test_guard_all_risk_reducing_actions_always_allowed() -> None:
    today = datetime.now(UTC)
    trades = [
        {"closed_at": today.isoformat(), "result_pct": -10.0},
    ]
    settings = {"max_daily_loss_pct": 2.0, "max_weekly_loss_pct": 5.0, "trader_timezone": "UTC"}
    for action in RISK_REDUCING_ACTIONS:
        result = check_account_guard(
            closed_trades=trades,
            settings=settings,
            action=action,
            now=today,
        )
        assert result["allowed"] is True, f"Expected {action} to be allowed even with loss"
        assert result["blocked"] is False, f"Expected {action} not to be blocked"


# ---------------------------------------------------------------------------
# Data safety — malformed inputs do not crash
# ---------------------------------------------------------------------------
def test_guard_malformed_result_pct_does_not_crash() -> None:
    today = datetime.now(UTC)
    trades = [
        {"closed_at": today.isoformat(), "result_pct": "bad_value"},
    ]
    result = check_account_guard(
        closed_trades=trades,
        settings={"trader_timezone": "UTC"},
        action="open_new_trade",
        now=today,
    )
    assert result["allowed"] is True
    assert result["stats"]["daily_result_pct"] == 0.0


def test_guard_malformed_closed_at_does_not_crash() -> None:
    trades = [
        {"closed_at": "not_a_date", "result_pct": -2.0},
    ]
    result = check_account_guard(
        closed_trades=trades,
        action="open_new_trade",
    )
    assert result["allowed"] is True
    assert result["stats"]["daily_result_pct"] == 0.0  # skipped


def test_guard_skips_non_dict_items() -> None:
    trades: list[dict] = [
        {"closed_at": "2024-01-01T00:00:00Z", "result_pct": -2.0},  # type: ignore[list-item]
        None,  # type: ignore[list-item]
    ]
    result = check_account_guard(
        closed_trades=trades,  # type: ignore[arg-type]
        action="open_new_trade",
        now=datetime(2024, 1, 1, tzinfo=UTC),
    )
    # Only the valid dict is processed; None is skipped
    assert isinstance(result, dict)
    assert result["allowed"] is False
    assert "DAILY_LOSS_LIMIT_REACHED" in result["block_codes"]


def test_guard_default_settings_used_when_none() -> None:
    today = datetime.now(UTC)
    # -2.1% > default 2.0 → blocked
    trades = [
        {"closed_at": today.isoformat(), "result_pct": -2.1},
    ]
    result = check_account_guard(
        closed_trades=trades,
        settings=None,
        action="open_new_trade",
        now=today,
    )
    assert result["allowed"] is False
    assert "DAILY_LOSS_LIMIT_REACHED" in result["block_codes"]


def test_guard_multiple_blocks_accumulate() -> None:
    today = datetime.now(UTC)
    trades = [
        {"closed_at": (today - timedelta(days=1)).isoformat(), "result_pct": -0.5},
        {"closed_at": today.isoformat(), "result_pct": -0.4},
        {"closed_at": today.isoformat(), "result_pct": -0.3},
    ]
    open_trades = [
        {"risk_pct": 4.0},
    ]
    settings = {
        "max_daily_loss_pct": 0.5,
        "max_consecutive_losses": 2,
        "max_open_risk_pct": 3.0,
        "trader_timezone": "UTC",
    }
    result = check_account_guard(
        closed_trades=trades,
        open_trades=open_trades,
        settings=settings,
        action="open_new_trade",
        now=today,
    )
    assert result["allowed"] is False
    assert "DAILY_LOSS_LIMIT_REACHED" in result["block_codes"]
    assert "MAX_CONSECUTIVE_LOSSES_REACHED" in result["block_codes"]
    assert "MAX_OPEN_RISK_REACHED" in result["block_codes"]
    # reasons should contain Vietnamese text
    assert any("lỗ trong ngày" in r for r in result["reasons"])
    assert any("liên tiếp" in r for r in result["reasons"])
    assert any("rủi ro" in r for r in result["reasons"])


def test_guard_with_timezone_vietnam() -> None:
    """Verify stats work correctly with Asia/Ho_Chi_Minh timezone."""
    result = check_account_guard(
        closed_trades=[],
        open_trades=[],
        settings={"trader_timezone": "Asia/Ho_Chi_Minh"},
        action="open_new_trade",
    )
    assert result["allowed"] is True
    assert result["blocked"] is False
    assert "daily_result_pct" in result["stats"]
    assert "consecutive_losses" in result["stats"]
    assert "open_risk_pct" in result["stats"]
