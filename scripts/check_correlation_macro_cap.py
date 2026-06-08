"""Verify that compute_correlation_adjustment + score_scenario respects
the regime macro weight cap even with strong positive correlation.

The fix in signal_engine.py ensures macro_alignment never exceeds
weights['macro'] after adding correlation_adjustment.

Run:  python scripts/check_correlation_macro_cap.py
Requires: nothing — no MT5, no network, no API key.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.market_models import Candle
from core.signal_engine import score_scenario
from core.correlation_check import compute_correlation_adjustment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candles_from_closes(closes: list[float]) -> list[Candle]:
    """Build realistic Candle list from a series of close prices.
    Each candle spreads OHLC around the close."""
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles: list[Candle] = []
    for i, close in enumerate(closes):
        open_price = close * 0.9995
        high = close * 1.002
        low = close * 0.998
        candles.append(Candle(
            time=base_time + timedelta(days=i),
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=1000,
        ))
    return candles


_TECH = {
    "price": 1.1000,
    "ema50_d1": 1.0900,
    "ema200_d1": 1.0700,
    "ema50_h4": 1.0950,
    "structure_h4": "HH/HL",
    "structure_d1": "HH/HL",
    "rsi_h4": 45.0,
    "rsi_h4_previous": 40.0,
    "macd_histogram_h4": {"value": 0.02, "previous_value": 0.01, "previous2_value": 0.0},
    "atr_h4": 0.005,
    "atr_d1": 0.008,
    "support_zones": [
        {"level": 1.0900, "low": 1.0880, "high": 1.0920, "strength": "moderate",
         "confluence_count": 1, "consolidation_bars": 1}
    ],
    "resistance_zones": [
        {"level": 1.1150, "low": 1.1130, "high": 1.1170, "strength": "weak",
         "confluence_count": 0, "consolidation_bars": 0}
    ],
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    errors: list[str] = []

    def check(cond, msg):
        if not cond:
            errors.append(msg)

    # --- Scenario 1: EUR/USD buy, DXY rising (USD strong → supports SELL EUR/USD,
    #     so for BUY EUR/USD, DXY up = against → negative adjustment).
    #     Need DXY falling to get positive adjustment for BUY EUR/USD. ---
    dxy_down = _candles_from_closes([105.0, 104.5, 103.0, 102.2, 101.8, 101.5])
    vix_low = _candles_from_closes([14.2, 14.1, 13.9, 14.0, 13.8, 14.1])

    for symbol, side, label in [
        ("EUR/USD", "buy", "EUR/USD BUY + DXY down + VIX low"),
        ("EUR/USD", "sell", "EUR/USD SELL + DXY down + VIX low"),
    ]:
        adj = compute_correlation_adjustment(
            symbol=symbol,
            side=side,
            dxy_candles=dxy_down,
            vix_candles=vix_low,
            us10y_candles=None,
        )

        result = score_scenario(
            side=side,
            technical=_TECH,
            smc={},
            risk_score=15,
            macro_score=30,
            macro_confidence=1.0,
            market_regime={"primary": "trend_up", "secondary": []},
            correlation_adjustment=adj,
            macro_context={"buy": 30, "sell": 0},
        )

        macro_cap = result["regime_weights"]["macro"]

        print(f"\n=== {label} ===")
        print(f"  correlation_adjustment = {adj}")
        print(f"  regime macro cap        = {macro_cap}")
        print(f"  macro_alignment         = {result['macro_alignment']}")
        print(f"  signal_score            = {result['signal_score']}")

        check(macro_cap == 15, f"trend_up macro cap expected 15, got {macro_cap}")
        check(result["macro_alignment"] <= macro_cap,
              f"macro_alignment {result['macro_alignment']} > cap {macro_cap}")
        check(result["macro_alignment"] >= 0,
              f"macro_alignment {result['macro_alignment']} < 0")
        check(result["correlation_adjustment"] == adj,
              f"correlation_adjustment mismatch: {result['correlation_adjustment']} != {adj}")

    # --- Scenario 2: volatile regime, cap should be 20 ---
    adj2 = compute_correlation_adjustment(
        symbol="EUR/USD", side="buy",
        dxy_candles=dxy_down, vix_candles=vix_low,
        us10y_candles=None,
    )
    result2 = score_scenario(
        side="buy", technical=_TECH, smc={}, risk_score=15,
        macro_score=30, macro_confidence=1.0,
        market_regime={"primary": "volatile", "secondary": []},
        correlation_adjustment=adj2,
        macro_context={"buy": 30, "sell": 0},
    )

    print(f"\n=== EUR/USD BUY volatile + DXY down + VIX low ===")
    print(f"  correlation_adjustment = {adj2}")
    print(f"  regime macro cap        = {result2['regime_weights']['macro']}")
    print(f"  macro_alignment         = {result2['macro_alignment']}")
    print(f"  signal_score            = {result2['signal_score']}")

    check(result2["regime_weights"]["macro"] == 20,
          f"volatile macro cap expected 20, got {result2['regime_weights']['macro']}")
    check(result2["macro_alignment"] <= 20,
          f"macro_alignment {result2['macro_alignment']} > volatile cap 20")
    check(result2["macro_alignment"] >= 0,
          f"macro_alignment {result2['macro_alignment']} < 0")

    if errors:
        print(f"\nFAILED — {len(errors)} assertion(s):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("\n[PASS] ALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
