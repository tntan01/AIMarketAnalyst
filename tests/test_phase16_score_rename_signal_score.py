"""Phase 16.2 — verify signal_score/total backward compatibility in score_scenario()."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.signal_engine import score_scenario


def _make_technical(side: str = "buy") -> dict:
    """Build realistic technical snapshot.  side="sell" flips structure."""
    struct = "HH/HL" if side == "buy" else "LH/LL"
    rsi = 45.0 if side == "buy" else 55.0
    macd = {"value": 0.002, "previous_value": 0.001, "previous2_value": 0.0} if side == "buy" else \
           {"value": -0.002, "previous_value": -0.001, "previous2_value": -0.0}
    return {
        "price": 1.1000,
        "ema50_d1": 1.0900,
        "ema200_d1": 1.0700,
        "ema50_h4": 1.0950,
        "structure_h4": struct,
        "structure_d1": struct,
        "rsi_h4": rsi,
        "rsi_h4_previous": rsi - 5.0,
        "macd_histogram_h4": macd,
        "atr_h4": 0.005,
        "atr_d1": 0.008,
        "atr_avg_14d": 0.006,
        "support_zones": [
            {"level": 1.0900, "low": 1.0880, "high": 1.0920, "strength": "moderate",
             "confluence_count": 1, "consolidation_bars": 1},
        ],
        "resistance_zones": [
            {"level": 1.1150, "low": 1.1130, "high": 1.1170, "strength": "weak",
             "confluence_count": 0, "consolidation_bars": 0},
        ],
    }


def _make_smc(side: str = "buy") -> dict:
    if side == "buy":
        return {
            "H4": {"bos": True, "choch": False, "displacement": "bullish", "demand_zones": [
                {"type": "demand_zone", "zone_score": 80, "zone_location": "discount",
                 "liquidity_sweep": True, "broken": False, "mitigated": False, "test_count": 0},
            ]},
            "H1": {"bos": True, "choch": False, "displacement": "bullish",
                   "liquidity_sweeps": {"swept_lows": [1.09]}},
        }
    return {
        "H4": {"bos": True, "choch": False, "displacement": "bearish", "supply_zones": [
            {"type": "supply_zone", "zone_score": 75, "zone_location": "premium",
             "liquidity_sweep": True, "broken": False, "mitigated": False, "test_count": 0},
        ]},
        "H1": {"bos": True, "choch": False, "displacement": "bearish",
               "liquidity_sweeps": {"swept_highs": [1.12]}},
    }


def test_buy_signal_score_equals_total():
    result = score_scenario(
        "buy", _make_technical("buy"), _make_smc("buy"),
        risk_score=12, macro_score=20, macro_confidence=1.0,
        market_regime={"primary": "trend_up"},
    )
    assert "signal_score" in result
    assert "total" in result
    assert result["signal_score"] == result["total"]
    assert isinstance(result["signal_score"], int)
    assert 0 <= result["signal_score"] <= 100


def test_sell_signal_score_equals_total():
    result = score_scenario(
        "sell", _make_technical("sell"), _make_smc("sell"),
        risk_score=12, macro_score=20, macro_confidence=1.0,
        market_regime={"primary": "trend_down"},
    )
    assert result["signal_score"] == result["total"]
    assert isinstance(result["signal_score"], int)
    assert 0 <= result["signal_score"] <= 100


def test_component_keys_present():
    result = score_scenario(
        "buy", _make_technical("buy"), _make_smc("buy"),
        risk_score=12, macro_score=20,
    )
    assert "trend_alignment" in result
    assert "momentum_alignment" in result
    assert "location_quality" in result
    assert "smc_quality" in result
    assert "risk_condition" in result
    assert "macro_alignment" in result


def test_backward_compatible_access():
    """Code using get(signal_score, get(total, 0)) still works."""
    result = score_scenario(
        "buy", _make_technical("buy"), _make_smc("buy"),
        risk_score=12, macro_score=20,
    )
    score = result.get("signal_score", result.get("total", 0))
    assert score == result["signal_score"]
    # total-only fallback also works
    score2 = result.get("total", 0)
    assert score2 == result["signal_score"]


def test_signal_score_is_int():
    for side in ("buy", "sell"):
        result = score_scenario(
            side, _make_technical(side), _make_smc(side),
            risk_score=12, macro_score=20,
        )
        assert isinstance(result["signal_score"], int)
        assert isinstance(result["total"], int)
