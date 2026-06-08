from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

from core.market_models import Candle
from core.analysis_engine import analyze_symbol
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
# 1. Spread abnormal -> TRADE_BLOCKED
# ---------------------------------------------------------------------------
def test_spread_abnormal_blocks_via_gate() -> None:
    request = _base_request()
    result = analyze_symbol(
        request,
        _base_candles(),
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "abnormal",
        },
    )

    assert result["trade_gate"]["allowed"] is False
    assert result["trade_gate"]["decision_cap"] == "TRADE_BLOCKED"
    assert "SPREAD_ABNORMAL" in result["trade_gate"]["block_codes"]
    assert result["trade_permission"]["status"] == "blocked"
    assert result["decision_summary"]["action"] == "stand_aside"


# ---------------------------------------------------------------------------
# 2. High impact news within 30m -> TRADE_BLOCKED
# ---------------------------------------------------------------------------
def test_high_impact_news_nearby_blocks_via_gate() -> None:
    request = _base_request()
    result = analyze_symbol(
        request,
        _base_candles(),
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "high_impact_event_within_30m": True,
        },
    )

    assert "HIGH_IMPACT_NEWS_NEARBY" in result["trade_gate"]["block_codes"]
    assert result["trade_gate"]["allowed"] is False
    assert result["trade_gate"]["decision_cap"] == "TRADE_BLOCKED"
    assert result["trade_permission"]["status"] == "blocked"
    assert result["decision_summary"]["action"] == "stand_aside"


# ---------------------------------------------------------------------------
# 3. M15 loose -> WAITING_CONFIRMATION
# ---------------------------------------------------------------------------
def test_m15_loose_caps_waiting_confirmation() -> None:
    request = _base_request()

    fake_scenario = {
        "type": "buy",
        "priority": "primary",
        "score": 85,
        "ready_to_trade": True,
        "price_in_entry_zone": True,
        "h1_confirmation": True,
        "m15_quality": "loose",
        "entry_zone": [1.10, 1.12],
        "stop_loss": 1.09,
        "take_profit": [1.14],
        "risk_reward": "1:2.0",
        "entry_status": "waiting_confirmation",
        "trigger_type": "engulfing",
    }

    with mock.patch("core.analysis_engine.build_scenarios", return_value=[fake_scenario]):
        result = analyze_symbol(
            request,
            _base_candles(),
            data_quality={
                "terminal_connected": True,
                "broker_logged_in": True,
                "spread_status": "normal",
            },
        )

    assert result["trade_gate"]["allowed"] is True
    assert result["trade_gate"]["decision_cap"] == "WAITING_CONFIRMATION"
    assert "M15_LOOSE_CONFIRMATION" in result["trade_gate"]["warning_codes"]
    assert result["decision_summary"]["action"] != "ready"


# ---------------------------------------------------------------------------
# 4. M15 none -> WATCH_ONLY
# ---------------------------------------------------------------------------
def test_m15_none_caps_watch_only() -> None:
    request = _base_request()

    fake_scenario = {
        "type": "buy",
        "priority": "primary",
        "score": 85,
        "ready_to_trade": True,
        "price_in_entry_zone": True,
        "h1_confirmation": True,
        "m15_quality": "none",
        "entry_zone": [1.10, 1.12],
        "stop_loss": 1.09,
        "take_profit": [1.14],
        "risk_reward": "1:2.0",
        "entry_status": "waiting_confirmation",
        "trigger_type": "none",
    }

    with mock.patch("core.analysis_engine.build_scenarios", return_value=[fake_scenario]):
        result = analyze_symbol(
            request,
            _base_candles(),
            data_quality={
                "terminal_connected": True,
                "broker_logged_in": True,
                "spread_status": "normal",
            },
        )

    assert result["trade_gate"]["allowed"] is True
    assert result["trade_gate"]["decision_cap"] == "WATCH_ONLY"
    assert "M15_NOT_CONFIRMED" in result["trade_gate"]["warning_codes"]
    assert result["decision_summary"]["action"] != "ready"


# ---------------------------------------------------------------------------
# 5. Normal clean path – gate passes, no caps
# ---------------------------------------------------------------------------
def test_normal_clean_path_gate_passes() -> None:
    request = _base_request()
    result = analyze_symbol(
        request,
        _base_candles(),
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
    )

    assert "trade_gate" in result
    assert result["trade_gate"]["allowed"] is True
    # decision_cap may be None (if everything clean) or a soft cap from the scenario
    assert result["trade_gate"]["decision_cap"] != "TRADE_BLOCKED"
    assert "decision_summary" in result
    assert "gate_decision_cap" in result["decision_summary"]
    assert "gate_allowed" in result["decision_summary"]


# ---------------------------------------------------------------------------
# 6. Gate fields present in decision_summary
# ---------------------------------------------------------------------------
def test_decision_summary_has_gate_fields() -> None:
    request = _base_request()
    result = analyze_symbol(
        request,
        _base_candles(),
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
    )

    ds = result["decision_summary"]
    assert "gate_decision_cap" in ds
    assert "gate_allowed" in ds
    assert "gate_block_codes" in ds
    assert "gate_warning_codes" in ds


# ---------------------------------------------------------------------------
# 7. MT5 not ready -> TRADE_BLOCKED
# ---------------------------------------------------------------------------
def test_mt5_not_ready_blocks_via_gate() -> None:
    request = _base_request()
    result = analyze_symbol(
        request,
        _base_candles(),
        data_quality={
            "terminal_connected": False,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
    )

    assert result["trade_gate"]["allowed"] is False
    assert result["trade_gate"]["decision_cap"] == "TRADE_BLOCKED"
    assert "MT5_NOT_READY" in result["trade_gate"]["block_codes"]
    assert result["trade_permission"]["status"] == "blocked"
    assert result["decision_summary"]["action"] == "stand_aside"


# ---------------------------------------------------------------------------
# 8. trade_permission keeps backward-compatible keys
# ---------------------------------------------------------------------------
def test_trade_permission_keeps_status_and_reason() -> None:
    request = _base_request()
    result = analyze_symbol(
        request,
        _base_candles(),
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
    )

    tp = result["trade_permission"]
    assert "status" in tp
    assert "reason" in tp
    assert "resume_after" in tp


# ---------------------------------------------------------------------------
# Phase 9.5: aggregated reason codes in analysis output
# ---------------------------------------------------------------------------


class TestPhase9AggregatedReasonCodes:

    def test_output_has_aggregated_code_lists(self):
        """Analysis output must have top-level reason/penalty/warning/block lists."""
        request = _base_request()
        result = analyze_symbol(
            request, _base_candles(),
            data_quality={"terminal_connected": True, "broker_logged_in": True, "spread_status": "normal"},
        )
        assert isinstance(result["reason_codes"], list)
        assert isinstance(result["penalty_codes"], list)
        assert isinstance(result["warning_codes"], list)
        assert isinstance(result["block_codes"], list)
        assert isinstance(result["reason_messages"], list)

    def test_spread_abnormal_block_code_in_top_level(self):
        """Spread abnormal -> block_codes has SPREAD_ABNORMAL at top level."""
        request = _base_request()
        result = analyze_symbol(
            request, _base_candles(),
            data_quality={"terminal_connected": True, "broker_logged_in": True, "spread_status": "abnormal"},
        )
        assert "SPREAD_ABNORMAL" in result["block_codes"]

    def test_daily_loss_block_in_top_level(self):
        """Account guard daily loss -> block_codes at top level."""
        from datetime import datetime, timezone
        today = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = analyze_symbol(
            _base_request(), _base_candles(),
            data_quality={"terminal_connected": True, "broker_logged_in": True, "spread_status": "normal"},
            closed_trades=[{"closed_at": today.isoformat(), "result_pct": -2.1}],
            account_guard_settings={"max_daily_loss_pct": 2.0, "trader_timezone": "UTC"},
            trade_date=today,
        )
        assert "DAILY_LOSS_LIMIT_REACHED" in result["block_codes"]

    def test_no_duplicate_codes_in_aggregated_lists(self):
        """Aggregated lists must not have duplicate entries."""
        request = _base_request()
        result = analyze_symbol(
            request, _base_candles(),
            data_quality={"terminal_connected": True, "broker_logged_in": True, "spread_status": "abnormal"},
        )
        for key in ("reason_codes", "penalty_codes", "warning_codes", "block_codes"):
            lst = result[key]
            assert len(lst) == len(set(lst)), f"{key} has duplicates: {lst}"

    def test_decision_unchanged_with_new_codes(self):
        """Adding reason codes must not change decision output."""
        request = _base_request()
        result = analyze_symbol(
            request, _base_candles(),
            data_quality={"terminal_connected": True, "broker_logged_in": True, "spread_status": "normal"},
        )
        assert "decision_summary" in result
        assert "action" in result["decision_summary"]
        assert "trade_permission" in result
        assert "trade_gate" in result

    def test_reason_messages_not_empty_when_codes_present(self):
        """When block_codes exist, reason_messages should have translations."""
        request = _base_request()
        result = analyze_symbol(
            request, _base_candles(),
            data_quality={"terminal_connected": True, "broker_logged_in": True, "spread_status": "abnormal"},
        )
        assert len(result["reason_messages"]) > 0
        assert any("bất thường" in m for m in result["reason_messages"])
