from __future__ import annotations

from core.signal_engine import DYNAMIC_WEIGHTS, _detect_macro_status, score_scenario


# ---------------------------------------------------------------------------
# Test _detect_macro_status helper
# ---------------------------------------------------------------------------

def test_detect_none_context():
    assert _detect_macro_status(None, "buy") == "unclear"
    assert _detect_macro_status(None, "sell") == "unclear"


def test_detect_bias_buy_aligned():
    ctx = {"bias": "buy"}
    assert _detect_macro_status(ctx, "buy") == "aligned"


def test_detect_bias_buy_conflict():
    ctx = {"bias": "buy"}
    assert _detect_macro_status(ctx, "sell") == "conflict"


def test_detect_bias_sell_aligned():
    ctx = {"bias": "sell"}
    assert _detect_macro_status(ctx, "sell") == "aligned"


def test_detect_bias_sell_conflict():
    ctx = {"bias": "sell"}
    assert _detect_macro_status(ctx, "buy") == "conflict"


def test_detect_bias_bullish_long_aligned():
    assert _detect_macro_status({"bias": "bullish"}, "buy") == "aligned"
    assert _detect_macro_status({"bias": "long"}, "buy") == "aligned"


def test_detect_bias_bearish_short_aligned():
    assert _detect_macro_status({"bias": "bearish"}, "sell") == "aligned"
    assert _detect_macro_status({"bias": "short"}, "sell") == "aligned"


def test_detect_bias_neutral_mixed():
    assert _detect_macro_status({"bias": "neutral"}, "buy") == "unclear"
    assert _detect_macro_status({"bias": "mixed"}, "sell") == "unclear"


def test_detect_scores_buy_aligned():
    ctx = {"buy": 25, "sell": 10}
    assert _detect_macro_status(ctx, "buy") == "aligned"
    assert _detect_macro_status(ctx, "sell") == "conflict"


def test_detect_scores_sell_aligned():
    ctx = {"buy": 8, "sell": 22}
    assert _detect_macro_status(ctx, "sell") == "aligned"
    assert _detect_macro_status(ctx, "buy") == "conflict"


def test_detect_scores_close():
    ctx = {"buy": 15, "sell": 14}
    assert _detect_macro_status(ctx, "buy") == "unclear"
    assert _detect_macro_status(ctx, "sell") == "unclear"


def test_detect_empty_dict():
    assert _detect_macro_status({}, "buy") == "unclear"


# ---------------------------------------------------------------------------
# Test macro modifier trong score_scenario
# ---------------------------------------------------------------------------

def _make_tech() -> dict:
    return {
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
            {"level": 1.0900, "low": 1.0880, "high": 1.0920, "strength": "moderate", "confluence_count": 1, "consolidation_bars": 1}
        ],
        "resistance_zones": [
            {"level": 1.1150, "low": 1.1130, "high": 1.1170, "strength": "weak", "confluence_count": 0, "consolidation_bars": 0}
        ],
    }


def _make_smc() -> dict:
    return {
        "H4": {
            "bos": True, "choch": False, "displacement": "bullish",
            "demand_zones": [{"type": "demand_zone", "zone_score": 80, "zone_location": "discount", "liquidity_sweep": True, "broken": False, "mitigated": False, "test_count": 0}],
        },
        "H1": {
            "bos": True, "choch": False, "displacement": "bullish",
            "liquidity_sweeps": {"swept_lows": [1.09]},
        },
    }


def _score_buy(macro_context=None):
    return score_scenario("buy", _make_tech(), _make_smc(), 12, 20, macro_confidence=1.0, macro_context=macro_context)


def _score_sell(macro_context=None):
    return score_scenario("sell", _make_tech(), _make_smc(), 12, 10, macro_confidence=1.0, macro_context=macro_context)


def test_macro_aligned_adds_light_bonus():
    """Macro aligned cong nhe <= 5 diem."""
    no_ctx = _score_buy(macro_context=None)   # default: unclear
    aligned_ctx = _score_buy(macro_context={"buy": 25, "sell": 10})  # aligned
    diff = aligned_ctx["signal_score"] - no_ctx["signal_score"]
    assert 0 <= diff <= 5, f"Aligned bonus too large: {diff}"


def test_macro_aligned_has_reason_code():
    result = _score_buy(macro_context={"buy": 25, "sell": 10})
    assert "MACRO_ALIGNED" in result["reason_codes"]
    assert result["macro_modifier"] == 5
    assert result["macro_status"] == "aligned"


def test_macro_conflict_penalizes():
    """Macro conflict tru manh 15 diem."""
    no_ctx = _score_buy(macro_context=None)
    conflict_ctx = _score_buy(macro_context={"buy": 5, "sell": 25})  # conflict
    diff = no_ctx["signal_score"] - conflict_ctx["signal_score"]
    assert diff >= 10, f"Conflict penalty expected >=10, got {diff}"


def test_macro_conflict_has_penalty_code():
    result = _score_buy(macro_context={"buy": 5, "sell": 25})
    assert "MACRO_CONFLICT" in result["penalty_codes"]
    assert result["macro_modifier"] == -15
    assert result["macro_status"] == "conflict"


def test_macro_unclear_no_bonus():
    result = _score_buy(macro_context=None)
    assert "MACRO_UNCLEAR" in result["penalty_codes"]
    assert result["macro_modifier"] == 0
    assert result["macro_status"] == "unclear"


def test_score_never_below_zero():
    """Clamp: signal_score khong bao gio < 0."""
    # Dung input rat yeu + macro conflict de score gan 0
    result = score_scenario(
        "sell",
        {
            "price": 1.1000, "ema50_d1": 1.0700, "ema200_d1": 1.0900,
            "ema50_h4": 1.1050, "structure_h4": "HH/HL", "structure_d1": "HH/HL",
            "rsi_h4": 72.0, "rsi_h4_previous": 74.0,
            "macd_histogram_h4": {"value": 0.03, "previous_value": 0.02, "previous2_value": 0.01},
            "atr_h4": 0.005, "atr_d1": 0.008, "atr_avg_14d": 0.006,
            "support_zones": [{"level": 1.0900, "low": 1.0880, "high": 1.0920, "strength": "moderate", "confluence_count": 0, "consolidation_bars": 0}],
            "resistance_zones": [{"level": 1.0950, "low": 1.0930, "high": 1.0970, "strength": "weak", "confluence_count": 0, "consolidation_bars": 0}],
        },
        {},
        5, 5, macro_confidence=1.0,
        macro_context={"buy": 28, "sell": 2},  # sell side conflict
    )
    assert result["signal_score"] >= 0, f"Score below 0: {result['signal_score']}"


def test_score_never_above_100():
    """Clamp: signal_score khong bao gio vuot 100."""
    result = _score_buy(macro_context={"buy": 30, "sell": 0})
    assert result["signal_score"] <= 100, f"Score above 100: {result['signal_score']}"


def test_backward_compatibility_signal_score_and_total():
    """signal_score va total dong bo."""
    result = _score_buy(macro_context={"buy": 25, "sell": 10})
    assert "signal_score" in result
    assert "total" in result
    assert result["signal_score"] == result["total"]


def test_backward_compatibility_existing_keys():
    """Cac key cu khong bi mat."""
    result = _score_buy(macro_context={"buy": 25, "sell": 10})
    required_old_keys = {
        "trend_alignment", "momentum_alignment", "location_quality",
        "smc_quality", "smc_reason", "technical_raw",
        "risk_condition", "macro_alignment", "macro_raw",
        "macro_confidence", "regime_weights", "signal_score", "total", "rating",
    }
    assert required_old_keys.issubset(result.keys())


def test_backward_compatibility_new_keys():
    """Cac key moi luon co mat."""
    result = _score_buy()
    assert "macro_status" in result
    assert "macro_modifier" in result
    assert "reason_codes" in result
    assert "penalty_codes" in result


def test_no_macro_context_defaults_unclear():
    """Khong pass macro_context -> macro_status='unclear', macro_modifier=0."""
    result = _score_buy(macro_context=None)
    assert result["macro_status"] == "unclear"
    assert result["macro_modifier"] == 0
    assert "MACRO_UNCLEAR" in result["penalty_codes"]


def test_macro_weights_still_reduced():
    """Prompt 1 van con hieu luc: macro weight <= 20."""
    for regime, weights in DYNAMIC_WEIGHTS.items():
        assert weights.get("macro", 0) <= 20


def test_sell_aligned_macro_adds_bonus():
    """Sell side aligned cong nhe."""
    no_ctx = _score_sell(macro_context=None)
    aligned_ctx = _score_sell(macro_context={"buy": 5, "sell": 25})
    diff = aligned_ctx["signal_score"] - no_ctx["signal_score"]
    assert 0 <= diff <= 5, f"Sell aligned bonus too large: {diff}"
    assert aligned_ctx["macro_status"] == "aligned"
    assert "MACRO_ALIGNED" in aligned_ctx["reason_codes"]
