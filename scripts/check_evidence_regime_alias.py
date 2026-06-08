"""Verify that analyze_symbol with regime='trend_up' correctly matches journal
trades stored with regime='trending_up' via the evidence engine.

After the regime alias fix in statistical_edge_engine._VALID_REGIMES,
calculate_evidence_score must normalise 'trend_up' → 'trending_up' and
select the symbol_direction_regime group instead of falling back to neutral.

Run:  python scripts/check_evidence_regime_alias.py
Requires: nothing — no MT5, no network, no API key.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.market_models import Candle
from core.analysis_engine import analyze_symbol
from core.risk_engine import AnalysisInput
from core.statistical_edge_engine import STRONG_SAMPLE_SIZE


# ---------------------------------------------------------------------------
# Realistic candle data
# ---------------------------------------------------------------------------

def _candles(count: int, start: float, step: float, amplitude: float) -> list[Candle]:
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows: list[Candle] = []
    for index in range(count):
        wave = amplitude * ((index % 10) - 5) / 5
        close = start + index * step + wave
        open_price = close - step * 0.2
        rows.append(Candle(
            time=base_time + timedelta(hours=index),
            open=open_price,
            high=max(open_price, close) + amplitude * 0.8,
            low=min(open_price, close) - amplitude * 0.8,
            close=close,
            volume=100,
        ))
    return rows


# ---------------------------------------------------------------------------
# Journal trades with canonical regime 'trending_up'
# ---------------------------------------------------------------------------

def _make_closed_trades(count: int, symbol: str, direction: str, regime: str) -> list[dict]:
    trades: list[dict] = []
    for i in range(count):
        rr = 0.35 if i % 2 == 0 else -0.15  # positive expectancy
        trades.append({
            "symbol": symbol,
            "direction": direction,
            "regime": regime,
            "result_r": rr,
            "status": "closed",
            "closed_at": (datetime(2026, 1, 1, tzinfo=timezone.utc)
                          + timedelta(days=i)).isoformat(),
        })
    return trades


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    request = AnalysisInput("EUR/USD", "EURUSD", 10_000, 1.0, contract_size_override=100_000)
    candles = {
        "D1": _candles(240, 1.05, 0.0005, 0.002),
        "H4": _candles(240, 1.08, 0.00035, 0.0015),
        "H1": _candles(120, 1.12, 0.0002, 0.001),
    }
    data_quality = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
    }

    # Journal trades stored with canonical regime 'trending_up'
    closed_trades = _make_closed_trades(
        STRONG_SAMPLE_SIZE, "EUR/USD", "buy", "trending_up"
    )

    # Patch detect_market_regime to return 'trend_up' (what analysis_engine
    # would get from technical_context), and build_scenarios to avoid complex
    # SMC dependencies.
    fake_regime = {"primary": "trend_up", "secondary": []}
    fake_scenario = [{
        "type": "buy",
        "priority": "primary",
        "score": 72,
        "ready_to_trade": True,
        "price_in_entry_zone": True,
        "h1_confirmation": True,
        "m15_quality": "strict",
        "entry_zone": [1.10, 1.12],
        "stop_loss": 1.09,
        "take_profit": [1.14],
        "risk_reward": "1:2.0",
        "expected_effective_rr": 2.0,
        "entry_status": "confirmed_entry",
        "trigger_type": "engulfing",
    }]

    with (
        mock.patch("core.analysis_engine.detect_market_regime", return_value=fake_regime),
        mock.patch("core.analysis_engine.build_scenarios", return_value=fake_scenario),
    ):
        result = analyze_symbol(
            request,
            candles,
            data_quality=data_quality,
            closed_trades=closed_trades,
        )

    mr = result["market_regime"]
    evidence = result["evidence"]
    fs_inputs = result["final_score_detail"]["score_inputs"]

    print("=== Market Regime ===")
    print(f"  primary   = {mr['primary']}  (expect trend_up)")

    print("\n=== Evidence Result ===")
    print(f"  normalized_regime = {evidence['normalized_regime']}  (expect trending_up)")
    print(f"  group_used        = {evidence['group_used']}  (expect symbol_direction_regime)")
    print(f"  sample_size       = {evidence['sample_size']}  (expect >= {STRONG_SAMPLE_SIZE})")
    print(f"  evidence_score    = {evidence['evidence_score']}  (expect > 50)")

    print("\n=== Final Score Inputs ===")
    print(f"  evidence_score    = {fs_inputs['evidence_score']}  (must match evidence.evidence_score)")

    # ---- Asserts ----
    errors: list[str] = []

    def check(cond, msg):
        if not cond:
            errors.append(msg)

    check(evidence["normalized_regime"] == "trending_up",
          f"normalized_regime expected 'trending_up', got {evidence['normalized_regime']}")
    check(evidence["group_used"] == "symbol_direction_regime",
          f"group_used expected 'symbol_direction_regime', got {evidence['group_used']}")
    check(evidence["sample_size"] >= STRONG_SAMPLE_SIZE,
          f"sample_size {evidence['sample_size']} < {STRONG_SAMPLE_SIZE}")
    check(evidence["evidence_score"] > 50,
          f"evidence_score expected > 50, got {evidence['evidence_score']}")
    check(fs_inputs["evidence_score"] == evidence["evidence_score"],
          f"final_score evidence_score {fs_inputs['evidence_score']} != evidence {evidence['evidence_score']}")

    if errors:
        print(f"\nFAILED — {len(errors)} assertion(s):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("\n[PASS] ALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
