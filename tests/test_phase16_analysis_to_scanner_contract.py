"""Phase 16.11 — end-to-end analysis result → scanner row → sort contract."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.market_models import Candle
from core.analysis_engine import analyze_symbol
from core.risk_engine import AnalysisInput
from core.scanner import (
    scanner_row_from_analysis,
    sort_scanner_rows,
    scanner_summary,
    build_scanner_output,
    blocked_scanner_row,
    ScannerRequest,
)
from core.scanner_ranking_engine import READY_NOW, BLOCKED


# ---------------------------------------------------------------------------
# Fake result factory (Option A — stable)
# ---------------------------------------------------------------------------


def _fake_analysis_result(symbol="EUR/USD", final_score=82, decision="READY_TO_TRADE",
                          legacy_action="ready", entry_status="confirmed_entry",
                          score_gap=18, risk_reward="1:2.0",
                          expected_effective_rr=1.8, m15_quality="strict",
                          permission="allowed") -> dict:
    return {
        "symbol": symbol,
        "data_quality": {"broker_symbol": f"{symbol.replace('/', '')}m", "terminal_connected": True,
                         "broker_logged_in": True, "spread_status": "normal"},
        "market_regime": {"primary": "trend_up"},
        "direction_bias": "buy",
        "trade_permission": {"status": permission, "reason": "ok"},
        "scenario_scores": {
            "buy": {"signal_score": 82, "total": 82, "macro_alignment": 18, "macro_confidence": 0.8},
            "sell": {"signal_score": 55, "total": 55, "macro_alignment": 10, "macro_confidence": 0.8},
        },
        "final_score": final_score,
        "decision_engine": {"decision": decision, "legacy_action": legacy_action},
        "decision_summary": {
            "best_score": final_score, "best_scenario": "buy",
            "score_gap": score_gap, "action": legacy_action,
        },
        "scenarios": [{
            "type": "buy",
            "entry_status": entry_status,
            "ready_to_trade": entry_status == "confirmed_entry",
            "m15_quality": m15_quality,
            "expected_effective_rr": expected_effective_rr,
            "entry_zone": [1.10, 1.12],
            "risk_reward": risk_reward,
            "stop_loss": 1.09,
            "take_profit": [1.15],
            "price_in_entry_zone": True,
            "h1_confirmation": True,
        }],
        "technical": {"price": 1.11, "atr_h4": 0.005},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_scanner_row_from_fake_result_has_phase15_fields():
    result = _fake_analysis_result()
    row = scanner_row_from_analysis(result)

    assert row["symbol"] == "EUR/USD"
    assert row["best_score"] > 0
    assert row["final_score"] == 82
    assert row["scanner_decision"] == "READY_TO_TRADE"
    assert row["opportunity_score"] > 0
    assert row["scanner_group"] == READY_NOW
    assert row["score_gap"] == 18
    assert row["entry_status"] == "confirmed_entry"
    assert row["analysis_result"] is result


def test_blocked_row_is_blocked():
    result = _fake_analysis_result(permission="blocked", decision="TRADE_BLOCKED",
                                   legacy_action="stand_aside", entry_status="invalidated")
    row = scanner_row_from_analysis(result)
    assert row["scanner_group"] == BLOCKED


def test_sort_ready_before_blocked():
    ready_row = scanner_row_from_analysis(_fake_analysis_result())
    blocked_row = blocked_scanner_row("GBP/JPY", "MT5 error")
    rows = [blocked_row, ready_row]  # intentionally in wrong order
    sorted_rows = sort_scanner_rows(rows)
    assert sorted_rows[0]["scanner_group"] == READY_NOW
    assert sorted_rows[1]["scanner_group"] == BLOCKED


def test_build_scanner_output_has_summary():
    rows = [
        scanner_row_from_analysis(_fake_analysis_result()),
        blocked_scanner_row("GBP/JPY", "test"),
    ]
    output = build_scanner_output(rows, ScannerRequest(["EUR/USD", "GBP/JPY"], 10_000, 1, "Asia/Ho_Chi_Minh"), ai_called=0)
    assert output["mode"] == "scanner"
    assert output["symbols_scanned"] == 2
    summary = output["summary"]
    assert "ready_now_count" in summary
    assert "blocked_count" in summary
    assert "ready_count" in summary  # legacy key


# ---------------------------------------------------------------------------
# Realistic analyze_symbol → row (Option B)
# ---------------------------------------------------------------------------


def _candles(count, start, step, amplitude):
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(count):
        wave = amplitude * ((index % 10) - 5) / 5
        close = start + index * step + wave
        open_price = close - step * 0.2
        rows.append(Candle(
            time=base_time + timedelta(hours=index),
            open=open_price, high=max(open_price, close) + amplitude * 0.8,
            low=min(open_price, close) - amplitude * 0.8, close=close, volume=100,
        ))
    return rows


def test_real_analyze_to_scanner_row():
    request = AnalysisInput("EUR/USD", "EURUSD", 10_000, 1, contract_size_override=100_000)
    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        data_quality={
            "terminal_connected": True, "broker_logged_in": True, "spread_status": "normal",
        },
    )
    row = scanner_row_from_analysis(result)

    # All Phase 13-15 contract fields present
    assert "final_score" in row
    assert "scanner_decision" in row
    assert "opportunity_score" in row
    assert "scanner_group" in row
    assert "score_gap" in row
    assert "entry_status" in row
    assert "analysis_result" in row
    assert isinstance(row["opportunity_score"], int)
