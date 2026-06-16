from __future__ import annotations

from core.reason_codes import CHOCH_AGAINST_DIRECTION, MACRO_CONFLICT
from core.signal_engine import calculate_direction_bias, score_scenario


def _technical_buy_context() -> dict:
    return {
        "price": 100.0,
        "ema50_d1": 90.0,
        "ema200_d1": 80.0,
        "ema50_h4": 95.0,
        "structure_h4": "HH/HL",
        "structure_d1": "HH/HL",
        "rsi_h4": 45.0,
        "rsi_h4_previous": 40.0,
        "macd_histogram_h4": {
            "value": 0.3,
            "previous_value": 0.2,
            "previous2_value": 0.1,
        },
        "atr_h4": 2.0,
        "atr_d1": 2.0,
        "support_zones": [
            {
                "low": 99.0,
                "high": 101.0,
                "strength": "strong",
                "confluence_count": 2,
                "consolidation_bars": 3,
            }
        ],
        "resistance_zones": [{"low": 110.0, "high": 112.0, "strength": "moderate"}],
    }


def _smc_buy_context(*, choch_against: bool = False) -> dict:
    return {
        "H1": {
            "displacement": "bearish" if choch_against else "bullish",
            "bos": not choch_against,
            "choch": choch_against,
            "liquidity_sweeps": {"swept_lows": True},
        },
        "H4": {
            "displacement": "bearish" if choch_against else "bullish",
            "bos": not choch_against,
            "choch": choch_against,
            "demand_zones": [
                {
                    "type": "bullish_order_block",
                    "zone_score": 80,
                    "zone_location": "discount",
                    "liquidity_sweep": True,
                    "broken": False,
                    "mitigated": False,
                    "test_count": 1,
                }
            ],
        },
    }


def test_calculate_direction_bias_requires_minimum_gap():
    result = calculate_direction_bias(
        {"signal_score": 72},
        {"signal_score": 65},
        min_gap=10,
    )

    assert result["best_side"] == "buy"
    assert result["score_gap"] == 7.0
    assert result["is_clear_bias"] is False


def test_calculate_direction_bias_marks_clear_sell_when_gap_is_large():
    result = calculate_direction_bias(
        {"signal_score": 55},
        {"signal_score": 76},
        min_gap=10,
    )

    assert result["best_side"] == "sell"
    assert result["score_gap"] == 21.0
    assert result["is_clear_bias"] is True


def test_score_scenario_applies_macro_conflict_penalty():
    aligned = score_scenario(
        "buy",
        _technical_buy_context(),
        _smc_buy_context(),
        risk_score=15,
        macro_score=25,
        market_regime={"primary": "trend_up"},
        macro_context={"bias": "buy"},
    )
    conflict = score_scenario(
        "buy",
        _technical_buy_context(),
        _smc_buy_context(),
        risk_score=15,
        macro_score=25,
        market_regime={"primary": "trend_up"},
        macro_context={"bias": "sell"},
    )

    assert aligned["signal_score"] > conflict["signal_score"]
    assert conflict["macro_status"] == "conflict"
    assert conflict["macro_modifier"] == -15
    assert MACRO_CONFLICT in conflict["penalty_codes"]


def test_score_scenario_caps_when_choch_is_against_direction():
    result = score_scenario(
        "buy",
        _technical_buy_context(),
        _smc_buy_context(choch_against=True),
        risk_score=15,
        macro_score=30,
        market_regime={"primary": "trend_up"},
        macro_context={"bias": "buy"},
    )

    assert result["signal_score"] <= 60
    assert result["smc_score_cap"] == 60
    assert CHOCH_AGAINST_DIRECTION in result["penalty_codes"]
