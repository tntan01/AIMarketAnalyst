"""Phase 13.8 — verify final_score metadata appears in analyze_symbol output
without changing decision/gate behaviour."""
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


def test_analyze_symbol_returns_final_score_metadata():
    """analyze_symbol output must include final_score and final_score_detail."""
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
    )

    # New keys
    assert "final_score" in result
    assert "final_score_detail" in result

    # final_score is an int in 0–100
    fs = result["final_score"]
    assert isinstance(fs, int)
    assert 0 <= fs <= 100

    # final_score_detail has required sub-keys
    detail = result["final_score_detail"]
    assert isinstance(detail, dict)
    assert "score_inputs" in detail
    assert "score_weights" in detail
    assert "weighted_components" in detail
    assert "reason_codes" in detail
    assert "score_breakdown" in detail

    # Evidence and execution should be neutral defaults in live analysis
    assert detail["score_inputs"]["evidence_score"] == 50
    assert detail["score_inputs"]["execution_quality_score"] == 100

    # Signal score should match the best side's signal_score or total
    best_side = result["decision_summary"]["best_scenario"]
    scenario_scores = result["scenario_scores"]
    expected_signal = int(
        scenario_scores[best_side].get("signal_score")
        or scenario_scores[best_side].get("total")
        or 0
    )
    assert detail["score_inputs"]["signal_score"] == expected_signal


def test_analyze_symbol_final_score_does_not_break_existing_keys():
    """All pre-Phase-13 keys still present with correct structure."""
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
    )

    # Existing keys must still exist
    assert "symbol" in result
    assert "decision_summary" in result
    assert isinstance(result["decision_summary"]["action"], str)
    assert "trade_permission" in result
    assert isinstance(result["trade_permission"]["status"], str)
    assert "trade_gate" in result
    assert "scenario_scores" in result
    assert "scenarios" in result
    assert "market_regime" in result
    assert "direction_bias" in result
    assert "chart_payload" in result
    assert "entry_checklist" in result
    assert "backtest" in result
    assert "confidence_reason" in result
    assert "risk_management" in result


def test_analyze_symbol_final_score_with_xauusd():
    """XAU/USD also gets final_score metadata."""
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
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
    )

    assert "final_score" in result
    assert isinstance(result["final_score"], int)
    detail = result["final_score_detail"]
    assert detail["score_inputs"]["evidence_score"] == 50
    assert detail["score_inputs"]["execution_quality_score"] == 100


def test_analyze_symbol_decision_unchanged_by_final_score():
    """Decision action is NOT affected by adding final_score metadata."""
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
    )

    # Decision summary unchanged — still has the normal action, best_score, etc.
    decision = result["decision_summary"]
    assert decision["action"] in ("stand_aside", "watch", "wait_for_confirmation", "ready")
    assert isinstance(decision["best_score"], int)
    assert "best_scenario" in decision

    # Trade permission unchanged
    tp = result["trade_permission"]
    assert tp["status"] in ("allowed", "caution", "blocked")
