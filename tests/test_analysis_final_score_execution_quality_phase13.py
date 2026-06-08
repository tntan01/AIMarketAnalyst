"""Phase 13.10 — test execution_quality_score input into analyze_symbol."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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


def test_execution_quality_score_provided():
    """Passing execution_quality_score=40 is reflected in output."""
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        **_common_kwargs(),
        execution_quality_score=40,
    )

    assert "execution_quality" in result
    eq = result["execution_quality"]
    assert eq["execution_quality_score"] == 40
    assert eq["source"] == "provided"

    detail = result["final_score_detail"]
    assert detail["score_inputs"]["execution_quality_score"] == 40


def test_execution_quality_lowers_final_score():
    """Lower execution_quality → lower final_score vs fallback 100."""
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    result_low = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        **_common_kwargs(),
        execution_quality_score=40,
    )

    result_default = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        **_common_kwargs(),
    )

    # Low execution_quality should yield a lower final_score
    assert result_low["final_score"] < result_default["final_score"]


def test_execution_quality_default_no_caller_input():
    """Without execution_quality_score param, fallback to 100."""
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

    eq = result["execution_quality"]
    assert eq["execution_quality_score"] == 100
    assert eq["source"] == "fallback_no_closed_trade_execution_data"


def test_execution_quality_bad_string_no_crash():
    """Bogus execution_quality_score string → fallback 100 without crash."""
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        **_common_kwargs(),
        execution_quality_score="bad",  # type: ignore[arg-type]
    )

    eq = result["execution_quality"]
    assert eq["execution_quality_score"] == 100
    assert "fallback" in eq["source"]


def test_execution_quality_does_not_change_decision():
    """execution_quality_score does NOT alter decision_action."""
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        **_common_kwargs(),
        execution_quality_score=10,
    )

    assert result["decision_summary"]["action"] in (
        "stand_aside", "watch", "wait_for_confirmation", "ready",
    )
    assert result["trade_permission"]["status"] in ("allowed", "caution", "blocked")
