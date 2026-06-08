"""Check that entry_quality_bonus correctly updates direction_bias / score_gap.

This script verifies the fix in core/analysis_engine.py: after the
entry_quality_bonus (+10) is applied to the best side, the downstream
fields (direction_bias, score_gap, gate warnings, decision_engine
warnings, final_score) all reflect the post-bonus scores.

Run:  python scripts/check_entry_quality_bonus_score_gap.py
Requires: nothing — no MT5, no network, no API key.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

# Ensure the project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.market_models import Candle
from core.analysis_engine import analyze_symbol
from core.risk_engine import AnalysisInput


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
# Mock helpers
# ---------------------------------------------------------------------------

def _fake_score_scenario(side, technical, smc, risk_score, macro_score, **kw):
    """Buy=72, Sell=65 so pre-bonus gap=7 (<10). Post-bonus gap=17."""
    score = 72 if side == "buy" else 65
    return {
        "signal_score": score,
        "total": score,
        "trend_alignment": 18,
        "momentum_alignment": 12,
        "location_quality": 18,
        "smc_quality": 10,
        "smc_reason": "BOS H4 bullish",
        "risk_condition": 8,
        "macro_alignment": 15,
        "macro_confidence": 1.0,
        "correlation_adjustment": 0.0,
        "regime_weights": {"trend": 22, "momentum": 14, "location": 13, "smc": 11, "risk": 10, "macro": 30},
        "rating": "cân nhắc được",
        "reason_codes": [],
        "penalty_codes": [],
    }


def _fake_smc_flags():
    return {
        "zone_broken": False,
        "choch_against_direction": False,
        "liquidity_sweep_aligned": True,
        "displacement_aligned": True,
        "has_selected_zone": True,
        "selected_zone_type": "demand_zone",
        "selected_zone_score": 80,
        "raw": {},
    }


def _fake_scenario():
    return [{
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

    with (
        mock.patch("core.analysis_engine.score_scenario", side_effect=_fake_score_scenario),
        mock.patch("core.analysis_engine.extract_smc_trade_flags", return_value=_fake_smc_flags()),
        mock.patch("core.analysis_engine.build_scenarios", return_value=_fake_scenario()),
    ):
        result = analyze_symbol(
            request,
            candles,
            data_quality=data_quality,
            use_decision_engine_action=True,
        )

    buy_scores = result["scenario_scores"]["buy"]
    sell_scores = result["scenario_scores"]["sell"]
    db = result["direction_bias"]
    ds = result["decision_summary"]
    tg = result["trade_gate"]
    de = result["decision_engine"]
    fs_detail = result["final_score_detail"]

    print("=== Scenario Scores ===")
    print(f"  buy.signal_score  = {buy_scores['signal_score']}  (expect 82)")
    print(f"  buy.entry_quality_bonus = {buy_scores['entry_quality_bonus']}  (expect 10)")
    print(f"  buy.total         = {buy_scores['total']}  (expect 82)")
    print(f"  sell.signal_score = {sell_scores['signal_score']}  (expect 65)")

    print("\n=== Direction Bias ===")
    print(f"  best_side    = {db['best_side']}")
    print(f"  buy_score    = {db['buy_score']}  (expect 82)")
    print(f"  sell_score   = {db['sell_score']}  (expect 65)")
    print(f"  score_gap    = {db['score_gap']}  (expect 17)")
    print(f"  is_clear_bias = {db['is_clear_bias']}  (expect True)")

    print("\n=== Decision Summary ===")
    print(f"  best_score   = {ds['best_score']}  (expect 82)")
    print(f"  score_gap    = {ds['score_gap']}  (expect 17)")
    print(f"  is_clear_bias = {ds['is_clear_bias']}  (expect True)")
    print(f"  action       = {ds['action']}")

    print("\n=== Trade Gate ===")
    print(f"  allowed       = {tg['allowed']}")
    print(f"  warning_codes = {tg['warning_codes']}")
    print(f"  (expect BUY_SELL_SCORE_GAP_LOW NOT in warning_codes)")

    print("\n=== Decision Engine ===")
    print(f"  decision      = {de['decision']}")
    print(f"  warning_codes = {de['warning_codes']}")
    print(f"  (expect DECISION_SCORE_GAP_LOW NOT in warning_codes)")

    print("\n=== Final Score Detail ===")
    print(f"  signal_score = {fs_detail['score_inputs']['signal_score']}  (expect 82)")

    # ---- Asserts ----
    errors: list[str] = []

    def check(cond, msg):
        if not cond:
            errors.append(msg)

    check(buy_scores["signal_score"] == 82, f"buy.signal_score expected 82, got {buy_scores['signal_score']}")
    check(buy_scores["entry_quality_bonus"] == 10, f"entry_quality_bonus expected 10, got {buy_scores['entry_quality_bonus']}")
    check(buy_scores["total"] == 82, f"buy.total expected 82, got {buy_scores['total']}")
    check(sell_scores["signal_score"] == 65, f"sell.signal_score expected 65, got {sell_scores['signal_score']}")

    check(db["buy_score"] == 82, f"direction_bias.buy_score expected 82, got {db['buy_score']}")
    check(db["sell_score"] == 65, f"direction_bias.sell_score expected 65, got {db['sell_score']}")
    check(db["score_gap"] == 17, f"direction_bias.score_gap expected 17, got {db['score_gap']}")
    check(db["is_clear_bias"] is True, f"direction_bias.is_clear_bias expected True, got {db['is_clear_bias']}")

    check(ds["score_gap"] == 17, f"decision_summary.score_gap expected 17, got {ds['score_gap']}")
    check(ds["is_clear_bias"] is True, f"decision_summary.is_clear_bias expected True, got {ds['is_clear_bias']}")

    check("BUY_SELL_SCORE_GAP_LOW" not in tg["warning_codes"],
          f"BUY_SELL_SCORE_GAP_LOW should NOT be in gate warning_codes: {tg['warning_codes']}")
    check("DECISION_SCORE_GAP_LOW" not in de["warning_codes"],
          f"DECISION_SCORE_GAP_LOW should NOT be in decision_engine warning_codes: {de['warning_codes']}")

    check(fs_detail["score_inputs"]["signal_score"] == 82,
          f"final_score_detail.signal_score expected 82, got {fs_detail['score_inputs']['signal_score']}")

    if errors:
        print(f"\n❌ FAILED — {len(errors)} assertion(s):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("\n[PASS] ALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
