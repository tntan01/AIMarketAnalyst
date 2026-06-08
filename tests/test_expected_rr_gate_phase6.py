from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

from core.market_models import Candle
from core.analysis_engine import analyze_symbol
from core.risk_engine import AnalysisInput
from core.trade_gate_engine import check_trade_gates


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Test 1 — gate truc tiep: expected_effective_rr < min → WATCH_ONLY
# ---------------------------------------------------------------------------

def test_low_expected_rr_caps_watch_only():
    context: dict = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "m15_quality": "strict",
        "score_gap": 30,
        "expected_effective_rr": 1.1,
        "min_expected_effective_rr": 1.3,
    }
    result = check_trade_gates(context)
    assert result["allowed"] is True
    assert result["decision_cap"] == "WATCH_ONLY"
    assert "EXPECTED_RR_TOO_LOW" in result["warning_codes"]


# ---------------------------------------------------------------------------
# Test 2 — expected_effective_rr du cao → khong cap
# ---------------------------------------------------------------------------

def test_good_expected_rr_no_cap():
    context: dict = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "m15_quality": "strict",
        "score_gap": 30,
        "expected_effective_rr": 1.8,
    }
    result = check_trade_gates(context)
    assert "EXPECTED_RR_TOO_LOW" not in result["warning_codes"]
    assert result["allowed"] is True


# ---------------------------------------------------------------------------
# Test 3 — expected_effective_rr = None → khong cap
# ---------------------------------------------------------------------------

def test_none_expected_rr_no_cap():
    context: dict = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "m15_quality": "strict",
        "score_gap": 30,
        "expected_effective_rr": None,
    }
    result = check_trade_gates(context)
    assert "EXPECTED_RR_TOO_LOW" not in result["warning_codes"]


# ---------------------------------------------------------------------------
# Test 4 — RR thap + spread abnormal → TRADE_BLOCKED thang WATCH_ONLY
# ---------------------------------------------------------------------------

def test_low_rr_and_spread_abnormal_blocked():
    context: dict = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "abnormal",
        "expected_effective_rr": 1.1,
    }
    result = check_trade_gates(context)
    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert "EXPECTED_RR_TOO_LOW" in result["warning_codes"]
    assert "SPREAD_ABNORMAL" in result["block_codes"]


# ---------------------------------------------------------------------------
# Test 5 — analyze_symbol: RR thap → action != ready
# ---------------------------------------------------------------------------

def test_low_rr_prevents_ready_in_analyze_symbol():
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    fake_scenario = {
        "type": "buy",
        "priority": "primary",
        "score": 85,
        "ready_to_trade": True,
        "price_in_entry_zone": True,
        "h1_confirmation": True,
        "m15_quality": "strict",
        "entry_zone": [1.10, 1.12],
        "stop_loss": 1.09,
        "take_profit": [1.14],
        "risk_reward": "1:2.0",
        "expected_effective_rr": 1.1,
        "entry_status": "confirmed_entry",
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

    assert "EXPECTED_RR_TOO_LOW" in result["trade_gate"]["warning_codes"]
    assert result["trade_gate"]["decision_cap"] == "WATCH_ONLY"
    assert result["decision_summary"]["action"] != "ready"


# ---------------------------------------------------------------------------
# Test 6 — expected_effective_rr duoc truyen vao gate_context
# ---------------------------------------------------------------------------

def test_expected_rr_in_gate_context():
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    fake_scenario = {
        "type": "buy",
        "priority": "primary",
        "score": 85,
        "ready_to_trade": True,
        "price_in_entry_zone": True,
        "h1_confirmation": True,
        "m15_quality": "strict",
        "entry_zone": [1.10, 1.12],
        "stop_loss": 1.09,
        "take_profit": [1.14],
        "risk_reward": "1:2.0",
        "expected_effective_rr": 1.5,
        "entry_status": "confirmed_entry",
        "trigger_type": "engulfing",
    }

    with mock.patch("core.analysis_engine.check_trade_gates") as mock_gates:
        mock_gates.return_value = {
            "allowed": True,
            "decision_cap": None,
            "block_codes": [],
            "warning_codes": [],
            "reasons": [],
        }
        with mock.patch("core.analysis_engine.build_scenarios", return_value=[fake_scenario]):
            analyze_symbol(
                request,
                _base_candles(),
                data_quality={
                    "terminal_connected": True,
                    "broker_logged_in": True,
                    "spread_status": "normal",
                },
            )
        call_context = mock_gates.call_args[0][0]
        assert call_context.get("expected_effective_rr") == 1.5


# ---------------------------------------------------------------------------
# Test 7 — gate_context khong crash khi scenario thieu expected_effective_rr
# ---------------------------------------------------------------------------

def test_missing_expected_rr_no_crash():
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    fake_scenario = {
        "type": "buy",
        "priority": "primary",
        "score": 85,
        "ready_to_trade": True,
        "price_in_entry_zone": True,
        "h1_confirmation": True,
        "m15_quality": "strict",
        "entry_zone": [1.10, 1.12],
        "stop_loss": 1.09,
        "take_profit": [1.14],
        "risk_reward": "1:2.0",
        # khong co expected_effective_rr
        "entry_status": "confirmed_entry",
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

    # Khong crash, gate van chay
    assert "trade_gate" in result
    assert "EXPECTED_RR_TOO_LOW" not in result["trade_gate"]["warning_codes"]
