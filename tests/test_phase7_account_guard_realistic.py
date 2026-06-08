from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.account_guard import check_account_guard
from core.trade_gate_engine import check_trade_gates

# ---------------------------------------------------------------------------
# Dữ liệu giống thật — 2 lệnh thua trong cùng ngày
# ---------------------------------------------------------------------------
_CLOSED_TRADES = [
    {
        "symbol": "EUR/USD",
        "direction": "buy",
        "result_r": -1.0,
        "result_pct": -1.1,
        "closed_at": "2026-01-05T10:00:00+07:00",
        "exit_reason": "stop_loss",
        "actual_lot": 0.10,
        "planned_lot": 0.10,
    },
    {
        "symbol": "GBP/JPY",
        "direction": "sell",
        "result_r": -0.9,
        "result_pct": -1.0,
        "closed_at": "2026-01-05T14:00:00+07:00",
        "exit_reason": "stop_loss",
        "actual_lot": 0.10,
        "planned_lot": 0.10,
    },
]

_OPEN_TRADES = [
    {"symbol": "USD/JPY", "risk_pct": 1.4},
    {"symbol": "XAU/USD", "risk_pct": 1.8},
]

_SETTINGS = {
    "max_daily_loss_pct": 2.0,
    "max_weekly_loss_pct": 5.0,
    "max_consecutive_losses": 3,
    "max_open_risk_pct": 3.0,
    "trader_timezone": "Asia/Ho_Chi_Minh",
}

_TRADE_DATE = datetime(2026, 1, 5, 14, 30, 0, tzinfo=timezone(timedelta(hours=7)))


# ---------------------------------------------------------------------------
# Test 1 — Daily loss block
# ---------------------------------------------------------------------------
def test_realistic_daily_loss_block() -> None:
    guard = check_account_guard(
        closed_trades=_CLOSED_TRADES,
        open_trades=[],
        settings=_SETTINGS,
        action="open_new_trade",
        now=_TRADE_DATE,
    )
    # daily_result_pct = -1.1 + -1.0 = -2.1 <= -2.0 → BLOCK
    assert guard["blocked"] is True
    assert guard["allowed"] is False
    assert "DAILY_LOSS_LIMIT_REACHED" in guard["block_codes"]
    assert guard["stats"]["daily_result_pct"] == -2.1


# ---------------------------------------------------------------------------
# Test 2 — Max open risk block
# ---------------------------------------------------------------------------
def test_realistic_max_open_risk_block() -> None:
    guard = check_account_guard(
        closed_trades=[],
        open_trades=_OPEN_TRADES,
        settings=_SETTINGS,
        action="open_new_trade",
        now=_TRADE_DATE,
    )
    # open_risk_pct = 1.4 + 1.8 = 3.2 >= 3.0 → BLOCK
    assert guard["blocked"] is True
    assert "MAX_OPEN_RISK_REACHED" in guard["block_codes"]
    assert guard["stats"]["open_risk_pct"] == 3.2


# ---------------------------------------------------------------------------
# Test 3 — close_trade still allowed despite daily loss
# ---------------------------------------------------------------------------
def test_realistic_close_trade_allowed_despite_loss() -> None:
    guard = check_account_guard(
        closed_trades=_CLOSED_TRADES,
        open_trades=[],
        settings=_SETTINGS,
        action="close_trade",
        now=_TRADE_DATE,
    )
    assert guard["allowed"] is True
    assert guard["blocked"] is False
    # Stats still show violation
    assert guard["stats"]["daily_result_pct"] == -2.1


# ---------------------------------------------------------------------------
# Test 4 — Weekly loss block (≥ -5.0%)
# ---------------------------------------------------------------------------
def test_realistic_weekly_loss_block() -> None:
    # Monday to Thursday in same week (2026-01-05 is Monday ICT)
    trades = [
        {"closed_at": "2026-01-05T09:00:00+07:00", "result_pct": -1.8},
        {"closed_at": "2026-01-06T09:00:00+07:00", "result_pct": -1.5},
        {"closed_at": "2026-01-07T09:00:00+07:00", "result_pct": -1.9},
    ]
    now = datetime(2026, 1, 7, 12, 0, 0, tzinfo=timezone(timedelta(hours=7)))
    guard = check_account_guard(
        closed_trades=trades,
        open_trades=[],
        settings={**_SETTINGS, "max_daily_loss_pct": 100.0},
        action="open_new_trade",
        now=now,
    )
    # weekly_result_pct = -1.8 + -1.5 + -1.9 = -5.2 <= -5.0 → BLOCK
    assert guard["blocked"] is True
    assert "WEEKLY_LOSS_LIMIT_REACHED" in guard["block_codes"]
    assert guard["stats"]["weekly_result_pct"] == -5.2


# ---------------------------------------------------------------------------
# Test 5 — Consecutive losses block
# ---------------------------------------------------------------------------
def test_realistic_consecutive_losses_block() -> None:
    now = datetime(2026, 1, 5, 14, 30, 0, tzinfo=timezone(timedelta(hours=7)))
    guard = check_account_guard(
        closed_trades=_CLOSED_TRADES,
        open_trades=[],
        settings={**_SETTINGS, "max_consecutive_losses": 2},
        action="open_new_trade",
        now=now,
    )
    assert guard["blocked"] is True
    assert "MAX_CONSECUTIVE_LOSSES_REACHED" in guard["block_codes"]
    assert guard["stats"]["consecutive_losses"] == 2


# ---------------------------------------------------------------------------
# Test 6 — Trade gate block từ account_guard
# ---------------------------------------------------------------------------
def test_realistic_gate_block_from_account_guard() -> None:
    guard = check_account_guard(
        closed_trades=_CLOSED_TRADES,
        open_trades=[],
        settings=_SETTINGS,
        action="open_new_trade",
        now=_TRADE_DATE,
    )
    assert guard["blocked"] is True  # precondition

    gate = check_trade_gates({
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "m15_quality": "strict",
        "expected_effective_rr": 2.0,
        "score_gap": 25,
        "account_guard": guard,
    })

    assert gate["allowed"] is False
    assert gate["decision_cap"] == "TRADE_BLOCKED"
    assert "DAILY_LOSS_LIMIT_REACHED" in gate["block_codes"]
    assert "account_guard_stats" in gate
    assert gate["account_guard_stats"]["daily_result_pct"] == -2.1


# ---------------------------------------------------------------------------
# Test 7 — All risk-reducing actions still allowed
# ---------------------------------------------------------------------------
def test_realistic_all_risk_reducing_allowed() -> None:
    for action in ("close_trade", "partial_close", "move_sl_closer",
                   "move_sl_to_breakeven", "cancel_pending_order"):
        guard = check_account_guard(
            closed_trades=_CLOSED_TRADES,
            open_trades=_OPEN_TRADES,
            settings=_SETTINGS,
            action=action,
            now=_TRADE_DATE,
        )
        assert guard["allowed"] is True, f"Expected {action} to be allowed"
        assert guard["blocked"] is False, f"Expected {action} not to be blocked"


# ---------------------------------------------------------------------------
# Test 8 — Analysis-level smoke test (via analyze_symbol)
#   Verifies account_guard flows through the full analysis pipeline
#   without requiring MT5 or PyQt6.
# ---------------------------------------------------------------------------
def test_realistic_analysis_smoke_test() -> None:
    from core.analysis_engine import analyze_symbol
    from core.market_models import Candle
    from core.risk_engine import AnalysisInput

    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def _candles(count: int) -> list[Candle]:
        return [
            Candle(
                time=base_time + timedelta(hours=i),
                open=1.05 + i * 0.0005,
                high=1.06 + i * 0.0005,
                low=1.04 + i * 0.0005,
                close=1.05 + i * 0.0005,
                volume=100,
            )
            for i in range(count)
        ]

    result = analyze_symbol(
        AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000),
        {"D1": _candles(240), "H4": _candles(240), "H1": _candles(120)},
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
        closed_trades=_CLOSED_TRADES,
        open_trades=_OPEN_TRADES,
        account_guard_settings=_SETTINGS,
        trade_date=_TRADE_DATE,
    )

    # account_guard output exists
    assert "account_guard" in result
    assert result["account_guard"]["blocked"] is True
    assert "DAILY_LOSS_LIMIT_REACHED" in result["account_guard"]["block_codes"]

    # trade_gate picks up account guard
    assert result["trade_gate"]["allowed"] is False
    assert result["trade_gate"]["decision_cap"] == "TRADE_BLOCKED"

    # decision is overridden to stand_aside
    assert result["decision_summary"]["action"] == "stand_aside"

    # All previous-phase outputs still present
    assert "direction_bias" in result
    assert "trade_permission" in result
    assert "scenario_scores" in result
    assert "technical" in result
    assert "smc" in result
    assert "entry_checklist" in result
    assert "backtest" in result


# ---------------------------------------------------------------------------
# Test 9 — No account guard data → analysis still works
# ---------------------------------------------------------------------------
def test_realistic_no_guard_data_still_works() -> None:
    from core.analysis_engine import analyze_symbol
    from core.market_models import Candle
    from core.risk_engine import AnalysisInput

    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def _candles(count: int) -> list[Candle]:
        return [
            Candle(
                time=base_time + timedelta(hours=i),
                open=1.05 + i * 0.0005,
                high=1.06 + i * 0.0005,
                low=1.04 + i * 0.0005,
                close=1.05 + i * 0.0005,
                volume=100,
            )
            for i in range(count)
        ]

    result = analyze_symbol(
        AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000),
        {"D1": _candles(240), "H4": _candles(240), "H1": _candles(120)},
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
    )

    # Without any guard data, should still work and allow
    assert "account_guard" in result
    assert result["account_guard"]["allowed"] is True
    assert result["account_guard"]["blocked"] is False
    assert result["trade_gate"]["allowed"] is True
    assert "direction_bias" in result
