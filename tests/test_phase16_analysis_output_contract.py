"""Phase 16.10 — verify analyze_symbol output contract has all fields needed by scanner/UI."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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


def _clean_data_quality() -> dict:
    return {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "news_in_3h": False,
        "high_impact_event_within_30m": False,
    }


# ---------------------------------------------------------------------------
# Output contract
# ---------------------------------------------------------------------------


def test_analyze_symbol_has_all_required_top_level_keys():
    request = AnalysisInput("EUR/USD", "EURUSD", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        data_quality=_clean_data_quality(),
        macro_alignment={"buy": 15, "sell": 15},
        macro_confidence=1.0,
    )

    # Required top-level keys
    for key in [
        "symbol",
        "scenario_scores",
        "decision_summary",
        "trade_permission",
        "trade_gate",
        "scenarios",
        "final_score",
        "final_score_detail",
        "decision_engine",
        "chart_payload",
    ]:
        assert key in result, f"Missing required key: {key}"


def test_final_score_is_valid():
    request = AnalysisInput("EUR/USD", "EURUSD", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        data_quality=_clean_data_quality(),
    )

    assert isinstance(result["final_score"], int)
    assert 0 <= result["final_score"] <= 100

    detail = result["final_score_detail"]
    assert isinstance(detail["weighted_components"], dict)


def test_decision_engine_present():
    request = AnalysisInput("EUR/USD", "EURUSD", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        data_quality=_clean_data_quality(),
    )

    de = result["decision_engine"]
    assert isinstance(de, dict)
    assert "decision" in de
    assert "legacy_action" in de


def test_decision_summary_has_score_gap():
    request = AnalysisInput("EUR/USD", "EURUSD", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        data_quality=_clean_data_quality(),
    )

    ds = result["decision_summary"]
    assert "score_gap" in ds
    assert "action" in ds
    assert "best_score" in ds


def test_scenarios_non_empty():
    request = AnalysisInput("EUR/USD", "EURUSD", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        data_quality=_clean_data_quality(),
    )

    scenarios = result["scenarios"]
    assert isinstance(scenarios, list)
    assert len(scenarios) >= 1


def test_trade_gate_present():
    request = AnalysisInput("EUR/USD", "EURUSD", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        data_quality=_clean_data_quality(),
    )

    tg = result["trade_gate"]
    assert isinstance(tg, dict)
    assert "allowed" in tg
    assert "block_codes" in tg
    assert "warning_codes" in tg
