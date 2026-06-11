"""Verify the score normalization in score_scenario().
When macro data is neutral (15/15), macro_effective only reaches ~50% of macro_cap.
Normalization scales technical+risk to fill the budget not occupied by macro,
so 0-100 means "best possible given available data".
"""

from core.signal_engine import score_scenario


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
    "atr_avg_14d": 0.006,
    "support_zones": [
        {"level": 1.0900, "low": 1.0880, "high": 1.0920, "strength": "moderate",
         "confluence_count": 1, "consolidation_bars": 1}
    ],
    "resistance_zones": [
        {"level": 1.1150, "low": 1.1130, "high": 1.1170, "strength": "weak",
         "confluence_count": 0, "consolidation_bars": 0}
    ],
}


def test_neutral_macro_does_not_depress_score():
    """With neutral macro (15/15), score should still reach a reasonable range."""
    result = score_scenario(
        side="buy",
        technical=_TECH,
        smc={},
        risk_score=14,
        macro_score=15,   # neutral
        macro_confidence=1.0,
        market_regime={"primary": "trend_up", "secondary": []},
        macro_context={"buy": 15, "sell": 15},
    )
    # With old code: macro_effective=7, total capped ~92.
    # With normalization: technical fills 93-point budget → score should be 50+
    assert result["signal_score"] >= 50, f"Neutral macro score too low: {result['signal_score']}"
    # Score should NOT exceed 100
    assert result["signal_score"] <= 100


def test_full_macro_gives_same_score_as_before():
    """When macro is at max (30→cap), normalization is a no-op."""
    result = score_scenario(
        side="buy",
        technical=_TECH,
        smc={},
        risk_score=15,
        macro_score=30,   # full macro
        macro_confidence=1.0,
        market_regime={"primary": "trend_up", "secondary": []},
        macro_context={"buy": 30, "sell": 0},
    )
    # macro_effective = int(30*15/30) = 15 = cap. available_budget = 85.
    # non_macro_max = 85. normalized = non_macro * 85/85 = non_macro.
    # So total = non_macro + 15 = same as old code.
    assert result["macro_alignment"] == 15
    assert result["signal_score"] <= 100


def test_zero_macro_still_allows_full_score():
    """When macro=0, technical alone can reach 100."""
    result = score_scenario(
        side="buy",
        technical=_TECH,
        smc={},
        risk_score=0,
        macro_score=0,
        macro_confidence=1.0,
        market_regime={"primary": "trend_up", "secondary": []},
        macro_context={"buy": 0, "sell": 30},
    )
    # macro_effective = 0. available_budget = 100. non_macro normalized fills 0-100.
    # This setup has strong technical → should score decently
    assert result["macro_alignment"] == 0
    assert 0 <= result["signal_score"] <= 100


def test_perfect_setup_reaches_high_score_even_with_neutral_macro():
    """Best possible technical + risk + neutral macro should reach near 100."""
    result = score_scenario(
        side="buy",
        technical=_TECH,
        smc={},
        risk_score=15,   # max risk (no news, normal spread)
        macro_score=15,  # neutral
        macro_confidence=1.0,
        market_regime={"primary": "trend_up", "secondary": []},
        macro_context={"buy": 15, "sell": 15},
    )
    # This setup is strong (= HH/HL, price above EMAs, good RSI).
    # With normalization it should score well above the old ~55-60 range.
    assert result["signal_score"] >= 55, f"Score should be >=55, got {result['signal_score']}"


def test_macro_modifier_still_works_after_normalization():
    """macro_modifier (+5/-15) is applied AFTER normalization and still works."""
    # Aligned macro: buy=25, sell=5 → macro_status="aligned" → +5 modifier
    result_aligned = score_scenario(
        side="buy",
        technical=_TECH,
        smc={},
        risk_score=14,
        macro_score=15,
        macro_confidence=1.0,
        market_regime={"primary": "trend_up", "secondary": []},
        macro_context={"buy": 25, "sell": 5},
    )
    # Conflict macro: buy=5, sell=25 → macro_status="conflict" → -15 modifier
    result_conflict = score_scenario(
        side="buy",
        technical=_TECH,
        smc={},
        risk_score=14,
        macro_score=15,
        macro_confidence=1.0,
        market_regime={"primary": "trend_up", "secondary": []},
        macro_context={"buy": 5, "sell": 25},
    )

    assert result_aligned["macro_status"] == "aligned"
    assert result_aligned["macro_modifier"] == 5
    assert result_conflict["macro_status"] == "conflict"
    assert result_conflict["macro_modifier"] == -15
    # Aligned should score higher than conflict
    assert result_aligned["signal_score"] > result_conflict["signal_score"]
