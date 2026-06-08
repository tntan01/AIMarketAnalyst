from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.analysis_engine import analyze_symbol
from core.market_models import Candle
from core.risk_engine import AnalysisInput


def _candles(count: int, start: float, step: float, amplitude: float) -> list[Candle]:
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows: list[Candle] = []
    for index in range(count):
        wave = amplitude * ((index % 10) - 5) / 5
        close = start + index * step + wave
        open_price = close - step * 0.2
        rows.append(
            Candle(
                time=base_time + timedelta(hours=index),
                open=open_price,
                high=max(open_price, close) + amplitude * 0.8,
                low=min(open_price, close) - amplitude * 0.8,
                close=close,
                volume=100,
            )
        )
    return rows


def _base_candles() -> dict[str, list[Candle]]:
    return {
        "D1": _candles(240, 1.05, 0.0005, 0.002),
        "H4": _candles(240, 1.08, 0.00035, 0.0015),
        "H1": _candles(120, 1.12, 0.0002, 0.001),
    }


def _base_request() -> AnalysisInput:
    return AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)


# ---------------------------------------------------------------------------
# 1. No trades → account guard allows, no block
# ---------------------------------------------------------------------------
def test_no_trades_account_guard_allows() -> None:
    result = analyze_symbol(
        _base_request(),
        _base_candles(),
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
        closed_trades=[],
        open_trades=[],
        account_guard_settings={"max_daily_loss_pct": 2.0, "trader_timezone": "UTC"},
    )

    assert "account_guard" in result
    assert result["account_guard"]["allowed"] is True
    assert result["account_guard"]["blocked"] is False
    assert result["decision_summary"]["account_guard_blocked"] is False
    # Account guard should be in gate_context
    assert "account_guard_stats" in result["trade_gate"]


# ---------------------------------------------------------------------------
# 2. Daily loss → TRADE_BLOCKED via gate
# ---------------------------------------------------------------------------
def test_daily_loss_block_through_gate() -> None:
    today = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = analyze_symbol(
        _base_request(),
        _base_candles(),
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
        closed_trades=[
            {"closed_at": today.isoformat(), "result_pct": -2.1},
        ],
        open_trades=[],
        account_guard_settings={
            "max_daily_loss_pct": 2.0,
            "max_consecutive_losses": 10,
            "trader_timezone": "UTC",
        },
        trade_date=today,
    )

    assert result["account_guard"]["blocked"] is True
    assert "DAILY_LOSS_LIMIT_REACHED" in result["account_guard"]["block_codes"]
    assert "DAILY_LOSS_LIMIT_REACHED" in result["trade_gate"]["block_codes"]
    assert result["trade_gate"]["decision_cap"] == "TRADE_BLOCKED"
    assert result["trade_gate"]["allowed"] is False
    assert result["decision_summary"]["action"] == "stand_aside"
    assert result["trade_permission"]["status"] == "blocked"


# ---------------------------------------------------------------------------
# 3. Max open risk → TRADE_BLOCKED
# ---------------------------------------------------------------------------
def test_max_open_risk_block_through_gate() -> None:
    result = analyze_symbol(
        _base_request(),
        _base_candles(),
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
        closed_trades=[],
        open_trades=[{"risk_pct": 1.5}, {"risk_pct": 1.7}],
        account_guard_settings={
            "max_open_risk_pct": 3.0,
            "trader_timezone": "UTC",
        },
    )

    assert result["account_guard"]["blocked"] is True
    assert "MAX_OPEN_RISK_REACHED" in result["account_guard"]["block_codes"]
    assert "MAX_OPEN_RISK_REACHED" in result["trade_gate"]["block_codes"]
    assert result["trade_gate"]["decision_cap"] == "TRADE_BLOCKED"
    assert result["decision_summary"]["action"] == "stand_aside"


# ---------------------------------------------------------------------------
# 4. Missing journal data → no crash, account guard allows
# ---------------------------------------------------------------------------
def test_none_closed_trades_no_crash() -> None:
    result = analyze_symbol(
        _base_request(),
        _base_candles(),
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
        closed_trades=None,
        open_trades=None,
        account_guard_settings=None,
    )

    assert "account_guard" in result
    assert result["account_guard"]["allowed"] is True
    assert result["account_guard"]["blocked"] is False


# ---------------------------------------------------------------------------
# 5. decision_summary holds account_guard info
# ---------------------------------------------------------------------------
def test_decision_summary_has_account_guard_info() -> None:
    result = analyze_symbol(
        _base_request(),
        _base_candles(),
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
    )

    assert "account_guard_blocked" in result["decision_summary"]
    assert "account_guard_block_codes" in result["decision_summary"]
    # With no trades, nothing blocked
    assert result["decision_summary"]["account_guard_blocked"] is False
    assert result["decision_summary"]["account_guard_block_codes"] == []


# ---------------------------------------------------------------------------
# 6. account_guard_stats in trade_gate
# ---------------------------------------------------------------------------
def test_account_guard_stats_in_trade_gate_output() -> None:
    result = analyze_symbol(
        _base_request(),
        _base_candles(),
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
        closed_trades=[],
        open_trades=[],
        account_guard_settings={"trader_timezone": "UTC"},
    )

    assert "account_guard_stats" in result["trade_gate"]
    stats = result["trade_gate"]["account_guard_stats"]
    assert "daily_result_pct" in stats
    assert "weekly_result_pct" in stats
    assert "consecutive_losses" in stats
    assert stats["daily_result_pct"] == 0.0


# ---------------------------------------------------------------------------
# 7. Weekly loss → blocked
# ---------------------------------------------------------------------------
def test_weekly_loss_block_through_gate() -> None:
    today = datetime(2026, 1, 8, tzinfo=timezone.utc)  # Thursday
    trades = [
        {"closed_at": (today - timedelta(days=3)).isoformat(), "result_pct": -2.5},
        {"closed_at": (today - timedelta(days=1)).isoformat(), "result_pct": -2.7},
    ]
    result = analyze_symbol(
        _base_request(),
        _base_candles(),
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
        closed_trades=trades,
        open_trades=[],
        account_guard_settings={
            "max_weekly_loss_pct": 5.0,
            "max_consecutive_losses": 10,
            "trader_timezone": "UTC",
        },
        trade_date=today,
    )

    assert "WEEKLY_LOSS_LIMIT_REACHED" in result["account_guard"]["block_codes"]
    assert "WEEKLY_LOSS_LIMIT_REACHED" in result["trade_gate"]["block_codes"]
    assert result["trade_gate"]["decision_cap"] == "TRADE_BLOCKED"


# ---------------------------------------------------------------------------
# 8. Backward-compatible: old callers without new params still work
# ---------------------------------------------------------------------------
def test_old_api_signature_still_works() -> None:
    """Callers that don't pass the new kwarg should get allowed=True."""
    result = analyze_symbol(
        _base_request(),
        _base_candles(),
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
    )

    assert "account_guard" in result
    assert result["account_guard"]["allowed"] is True
    assert result["account_guard"]["blocked"] is False
