from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

from core.market_models import Candle
from core.analysis_engine import analyze_symbol
from core.risk_engine import AnalysisInput
from core.trade_gate_engine import check_trade_gates


# ---------------------------------------------------------------------------
# Test helpers
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


def _base_request() -> AnalysisInput:
    return AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)


# ---------------------------------------------------------------------------
# Test 1 — Gate truc tiep: zone_broken = True -> WATCH_ONLY
# ---------------------------------------------------------------------------

def test_zone_broken_gate_watch_only():
    context: dict = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "zone_broken": True,
        "m15_quality": "strict",
        "score_gap": 30,
    }
    result = check_trade_gates(context)
    assert result["allowed"] is True
    assert result["decision_cap"] == "WATCH_ONLY"
    assert "ZONE_BROKEN" in result["warning_codes"]


# ---------------------------------------------------------------------------
# Test 2 — zone_broken = False -> khong co ZONE_BROKEN warning
# ---------------------------------------------------------------------------

def test_zone_not_broken_no_warning():
    context: dict = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "zone_broken": False,
        "m15_quality": "strict",
        "score_gap": 30,
    }
    result = check_trade_gates(context)
    assert "ZONE_BROKEN" not in result["warning_codes"]
    assert result["allowed"] is True


# ---------------------------------------------------------------------------
# Test 3 — zone broken + spread abnormal -> TRADE_BLOCKED thang WATCH_ONLY
# ---------------------------------------------------------------------------

def test_zone_broken_and_spread_abnormal():
    context: dict = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "abnormal",
        "zone_broken": True,
        "m15_quality": "strict",
    }
    result = check_trade_gates(context)
    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert "ZONE_BROKEN" in result["warning_codes"]
    assert "SPREAD_ABNORMAL" in result["block_codes"]


# ---------------------------------------------------------------------------
# Test 4 — analyze_symbol: zone broken -> khong ready
# ---------------------------------------------------------------------------

def test_zone_broken_prevents_ready_in_analyze_symbol():
    """Du score cao, zone broken van cap WATCH_ONLY, action != ready."""
    request = _base_request()

    fake_smc_flags = {
        "zone_broken": True,
        "choch_against_direction": False,
        "liquidity_sweep_aligned": True,
        "displacement_aligned": True,
        "has_selected_zone": True,
        "selected_zone_type": "demand_zone",
        "selected_zone_score": 80,
        "raw": {},
    }

    with mock.patch("core.analysis_engine.extract_smc_trade_flags", return_value=fake_smc_flags):
        result = analyze_symbol(
            request,
            _base_candles(),
            data_quality={
                "terminal_connected": True,
                "broker_logged_in": True,
                "spread_status": "normal",
            },
        )

    assert result["smc_trade_flags"]["zone_broken"] is True
    assert "ZONE_BROKEN" in result["trade_gate"]["warning_codes"]
    assert result["trade_gate"]["decision_cap"] == "WATCH_ONLY"
    assert result["decision_summary"]["action"] != "ready"


# ---------------------------------------------------------------------------
# Test 5 — analyze_symbol: zone khong broken -> smc_trade_flags.output
# ---------------------------------------------------------------------------

def test_zone_not_broken_output_has_smc_trade_flags():
    """Output analyze_symbol co smc_trade_flags."""
    request = _base_request()

    fake_smc_flags = {
        "zone_broken": False,
        "choch_against_direction": False,
        "liquidity_sweep_aligned": True,
        "displacement_aligned": True,
        "has_selected_zone": True,
        "selected_zone_type": "demand_zone",
        "selected_zone_score": 82,
        "raw": {},
    }

    with mock.patch("core.analysis_engine.extract_smc_trade_flags", return_value=fake_smc_flags):
        result = analyze_symbol(
            request,
            _base_candles(),
            data_quality={
                "terminal_connected": True,
                "broker_logged_in": True,
                "spread_status": "normal",
            },
        )

    assert "smc_trade_flags" in result
    assert result["smc_trade_flags"]["zone_broken"] is False
    assert result["smc_trade_flags"]["has_selected_zone"] is True


# ---------------------------------------------------------------------------
# Test 6 — smc_trade_flags duoc truyen vao gate_context
# ---------------------------------------------------------------------------

def test_smc_zone_broken_in_gate_context():
    """Kiem tra extract_smc_trade_flags duoc goi va zone_broken vao gate_context."""
    request = _base_request()

    fake_smc_flags = {
        "zone_broken": True,
        "choch_against_direction": False,
        "liquidity_sweep_aligned": False,
        "displacement_aligned": False,
        "has_selected_zone": False,
        "selected_zone_type": None,
        "selected_zone_score": None,
        "raw": {},
    }

    with mock.patch("core.analysis_engine.check_trade_gates") as mock_gates:
        mock_gates.return_value = {
            "allowed": True,
            "decision_cap": "WATCH_ONLY",
            "block_codes": [],
            "warning_codes": ["ZONE_BROKEN"],
            "reasons": [],
        }
        with mock.patch("core.analysis_engine.extract_smc_trade_flags", return_value=fake_smc_flags):
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
        assert call_context.get("zone_broken") is True
