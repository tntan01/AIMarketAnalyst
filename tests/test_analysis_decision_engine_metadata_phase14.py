"""Phase 14.7 — verify decision_engine metadata appears in analyze_symbol output
without changing legacy decision_summary["action"]."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.analysis_engine import analyze_symbol
from core.risk_engine import AnalysisInput
from core.decision_engine import VALID_DECISIONS


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


def _common_kwargs():
    return {
        "data_quality": {
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_analyze_symbol_returns_decision_engine():
    """result has decision_engine metadata."""
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        **_common_kwargs(),
    )

    assert "decision_engine" in result
    de = result["decision_engine"]
    assert isinstance(de, dict)
    assert "decision" in de
    assert de["decision"] in VALID_DECISIONS


def test_decision_engine_has_required_keys():
    """decision_engine result has standard structure."""
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        **_common_kwargs(),
    )

    de = result["decision_engine"]
    assert "final_score" in de
    assert "decision_label" in de
    assert "reason_codes" in de
    assert "warning_codes" in de
    assert "block_codes" in de
    assert "allowed" in de
    assert "score_breakdown" in de


def test_legacy_decision_summary_unchanged():
    """decision_summary["action"] still exists and is valid."""
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        **_common_kwargs(),
    )

    assert "decision_summary" in result
    ds = result["decision_summary"]
    assert "action" in ds
    assert ds["action"] in ("stand_aside", "watch", "wait_for_confirmation", "ready")
    assert "best_score" in ds
    assert "best_scenario" in ds


def test_trade_gate_still_present():
    """trade_gate and trade_permission remain in output."""
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        **_common_kwargs(),
    )

    assert "trade_gate" in result
    assert "trade_permission" in result
    assert result["trade_gate"]["allowed"] is not None


def test_xauusd_also_has_decision_engine():
    """XAU/USD output also includes decision_engine."""
    request = AnalysisInput(
        "XAU/USD", "XAUUSDm", 10_000, 1,
        lot_step=0.01, minimum_lot=0.01, contract_size_override=100,
    )

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 2340, 0.8, 15),
            "H4": _candles(240, 2380, 0.5, 10),
            "H1": _candles(120, 2400, 0.3, 8),
        },
        **_common_kwargs(),
    )

    assert "decision_engine" in result
    assert result["decision_engine"]["decision"] in VALID_DECISIONS
