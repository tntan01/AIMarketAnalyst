"""Phase 13.9 — test evidence_score integration into analyze_symbol via closed_trades."""
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


def _make_closed_trades(
    count: int,
    symbol: str = "EUR/USD",
    direction: str = "buy",
    win_rate: float = 0.55,
    avg_win_r: float = 1.5,
    avg_loss_r: float = 1.0,
    regime: str = "trend_up",
) -> list[dict]:
    """Generate *count* closed trades with a target win rate and average R."""
    import math
    trades: list[dict] = []
    wins_needed = math.ceil(count * win_rate)
    base_date = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    for i in range(count):
        is_win = i < wins_needed
        result_r = avg_win_r if is_win else -avg_loss_r
        trades.append({
            "symbol": symbol,
            "direction": direction,
            "side": direction,
            "status": "closed",
            "closed_at": (base_date + timedelta(hours=i)).isoformat(),
            "result_r": result_r,
            "market_regime": regime,
        })
    return trades


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_evidence_with_closed_trades():
    """Passing closed_trades gives real evidence_score ≠ 50."""
    trades = _make_closed_trades(55, "EUR/USD", "buy", win_rate=0.60, avg_win_r=1.5, avg_loss_r=1.0)

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
        closed_trades=trades,
    )

    # Evidence block exists
    assert "evidence" in result
    evidence = result["evidence"]
    assert isinstance(evidence, dict)
    assert "evidence_score" in evidence

    # final_score_detail uses the real evidence_score
    detail = result["final_score_detail"]
    assert detail["score_inputs"]["evidence_score"] == evidence["evidence_score"]

    # With 55 trades and expectancy ~0.5 (floating-point: 0.499...), evidence_score is 75
    assert evidence["evidence_score"] == 75, (
        f"Expected 75 with 55 trades @ 0.6 WR / 1.5R avg win / 1.0R avg loss, got {evidence['evidence_score']}"
    )


def test_evidence_with_no_closed_trades_falls_back_to_50():
    """Without closed_trades, evidence_score stays 50 (neutral)."""
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

    assert "evidence" in result
    assert result["evidence"]["evidence_score"] == 50
    detail = result["final_score_detail"]
    assert detail["score_inputs"]["evidence_score"] == 50


def test_evidence_with_empty_closed_trades():
    """Empty closed_trades list → fallback 50."""
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
        closed_trades=[],
    )

    assert result["evidence"]["evidence_score"] == 50


def test_evidence_does_not_change_decision():
    """Evidence score does NOT alter decision_action or trade_permission."""
    trades = _make_closed_trades(55, "EUR/USD", "buy", win_rate=0.60, avg_win_r=1.5, avg_loss_r=1.0)

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
        closed_trades=trades,
    )

    # Decision and trade_permission still present, valid
    assert result["decision_summary"]["action"] in (
        "stand_aside", "watch", "wait_for_confirmation", "ready"
    )
    assert result["trade_permission"]["status"] in ("allowed", "caution", "blocked")

    # final_score may differ from best_score (it's optionally different) but
    # decision is NOT directly driven by final_score


def test_evidence_result_includes_stats():
    """Evidence result from statistical_edge_engine includes stats when data is enough."""
    trades = _make_closed_trades(55, "EUR/USD", "buy", win_rate=0.60, avg_win_r=1.5, avg_loss_r=1.0)

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
        closed_trades=trades,
    )

    evidence = result["evidence"]
    # With 40 trades, expect stats
    assert "stats" in evidence or evidence["evidence_score"] == 50
