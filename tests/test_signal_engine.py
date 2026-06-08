from core.signal_engine import best_side, momentum_alignment_score, smc_quality_score, score_scenario


def test_score_scenario_output_includes_signal_score() -> None:
    """score_scenario() returns both 'signal_score' (new) and 'total' (deprecated)."""
    tech = {
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
        "support_zones": [{"level": 1.0900, "low": 1.0880, "high": 1.0920, "strength": "moderate", "confluence_count": 1, "consolidation_bars": 1}],
        "resistance_zones": [{"level": 1.1150, "low": 1.1130, "high": 1.1170, "strength": "weak", "confluence_count": 0, "consolidation_bars": 0}],
    }
    smc = {
        "H4": {"bos": True, "choch": False, "displacement": "bullish", "demand_zones": [
            {"type": "demand_zone", "zone_score": 80, "zone_location": "discount", "liquidity_sweep": True, "broken": False, "mitigated": False, "test_count": 0}
        ]},
        "H1": {"bos": True, "choch": False, "displacement": "bullish", "liquidity_sweeps": {"swept_lows": [1.09]}},
    }

    result = score_scenario("buy", tech, smc, 12, 20, macro_confidence=1.0)

    assert "signal_score" in result, "Phai co signal_score trong output"
    assert "total" in result, "Phai giu total de tuong thich nguoc"
    assert result["signal_score"] == result["total"], "signal_score và total phai bang nhau"
    assert result["signal_score"] > 50  # setup nay phai co diem kha


def test_best_side_buy_sell_neutral() -> None:
    assert best_side(70, 50) == "buy"
    assert best_side(40, 60) == "sell"
    assert best_side(55, 50) == "neutral"


def _momentum_snapshot(rsi: float, rsi_previous: float) -> dict:
    return {
        "rsi_h4": rsi,
        "rsi_h4_previous": rsi_previous,
        "macd_histogram_h4": {
            "value": 0.0,
            "previous_value": 0.0,
            "previous2_value": 0.0,
        },
    }


def test_buy_rsi_pullback_scores_high_only_when_rising() -> None:
    assert momentum_alignment_score("buy", _momentum_snapshot(45, 35)) == 8
    assert momentum_alignment_score("buy", _momentum_snapshot(45, 55)) == 0


def test_sell_rsi_pullback_scores_high_only_when_falling() -> None:
    assert momentum_alignment_score("sell", _momentum_snapshot(60, 70)) == 8
    assert momentum_alignment_score("sell", _momentum_snapshot(60, 50)) == 0


def test_smc_quality_rewards_side_aligned_zone_and_context() -> None:
    smc = {
        "H4": {
            "bos": True,
            "choch": False,
            "displacement": "bullish",
            "demand_zones": [
                {
                    "type": "demand_zone",
                    "zone_score": 82,
                    "zone_location": "discount",
                    "liquidity_sweep": True,
                    "broken": False,
                    "mitigated": False,
                    "test_count": 0,
                }
            ],
        },
        "H1": {
            "bos": True,
            "choch": False,
            "displacement": "bullish",
            "liquidity_sweeps": {"swept_lows": [1.1]},
        },
    }

    score, reason = smc_quality_score("buy", smc)

    assert score >= 13
    assert "discount" in reason
    assert "zone_score=82" in reason


def test_smc_quality_caps_when_choch_opposes_side() -> None:
    smc = {
        "H4": {
            "bos": False,
            "choch": True,
            "displacement": "bearish",
            "demand_zones": [
                {
                    "type": "demand_zone",
                    "zone_score": 90,
                    "zone_location": "discount",
                    "liquidity_sweep": True,
                    "broken": False,
                }
            ],
        },
        "H1": {"liquidity_sweeps": {"swept_lows": [1.1]}},
    }

    score, reason = smc_quality_score("buy", smc)

    assert score <= 4
    assert "cap: H4 CHOCH bearish" in reason


# ---------------------------------------------------------------------------
# Macro correlation cap regression (Phase 4 Prompt 3)
# ---------------------------------------------------------------------------

_TECH_BUY = {
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


def test_correlation_adjustment_cannot_exceed_trending_macro_weight():
    """trending_up has weights['macro']=15.  Even with max macro_raw=30
    and correlation_adjustment=+10, macro_alignment must be capped at 15."""
    result = score_scenario(
        side="buy",
        technical=_TECH_BUY,
        smc={},
        risk_score=15,
        macro_score=30,
        macro_confidence=1.0,
        market_regime={"primary": "trend_up", "secondary": []},
        correlation_adjustment=10,
        macro_context={"buy": 30, "sell": 0},
    )
    assert result["regime_weights"]["macro"] == 15
    assert result["macro_alignment"] == 15, (
        f"Expected macro_alignment=15 (capped by regime weight), "
        f"got {result['macro_alignment']}"
    )
    assert result["correlation_adjustment"] == 10


def test_correlation_adjustment_cannot_exceed_volatile_macro_weight():
    """volatile has weights['macro']=20.  macro_alignment must be capped at 20."""
    result = score_scenario(
        side="buy",
        technical=_TECH_BUY,
        smc={},
        risk_score=15,
        macro_score=30,
        macro_confidence=1.0,
        market_regime={"primary": "volatile", "secondary": []},
        correlation_adjustment=10,
        macro_context={"buy": 30, "sell": 0},
    )
    assert result["regime_weights"]["macro"] == 20
    assert result["macro_alignment"] == 20, (
        f"Expected macro_alignment=20 (capped by regime weight), "
        f"got {result['macro_alignment']}"
    )


def test_negative_correlation_adjustment_does_not_make_macro_negative():
    """Correlation_adjustment must not push macro_alignment below 0."""
    result = score_scenario(
        side="buy",
        technical=_TECH_BUY,
        smc={},
        risk_score=15,
        macro_score=0,
        macro_confidence=1.0,
        market_regime={"primary": "trend_up", "secondary": []},
        correlation_adjustment=-10,
        macro_context={"buy": 15, "sell": 15},
    )
    assert result["macro_alignment"] == 0, (
        f"Expected macro_alignment=0 (floor), got {result['macro_alignment']}"
    )
