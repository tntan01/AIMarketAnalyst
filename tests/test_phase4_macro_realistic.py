from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

from core.market_models import Candle
from core.analysis_engine import analyze_symbol
from core.risk_engine import AnalysisInput
from core.signal_engine import (
    DYNAMIC_WEIGHTS,
    _detect_macro_status,
    score_scenario,
)


# ---------------------------------------------------------------------------
# Realistic candle data helper
# ---------------------------------------------------------------------------

def make_trending_candles(count=150, start_price=1.0800, step=0.00025):
    """Sinh nen H1 xu huong tang deu."""
    candles: list[Candle] = []
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = start_price
    for i in range(count):
        open_ = price
        close = price + step
        high = max(open_, close) + 0.00015
        low = min(open_, close) - 0.00015
        candles.append(
            Candle(
                time=t + timedelta(hours=i),
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=1000 + i,
            )
        )
        price = close
    return candles


def make_ranging_candles(count=150, center=1.1000, amplitude=0.002):
    """Sinh nen H1 di ngang."""
    candles: list[Candle] = []
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(count):
        offset = amplitude * ((i % 20) - 10) / 10
        open_ = center + offset - 0.0001
        close = center + offset + 0.0001
        high = center + offset + 0.0003
        low = center + offset - 0.0003
        candles.append(
            Candle(
                time=t + timedelta(hours=i),
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=1000 + i,
            )
        )
    return candles


def _candle_dict(h1_list):
    """Tao dict candles_by_timeframe tu H1 cho analyze_symbol."""
    return {"D1": h1_list[-250:], "H4": h1_list[-200:], "H1": h1_list[-150:]}


# ---------------------------------------------------------------------------
# Test 1 — Macro aligned chi cong nhe (<= 5 diem)
# ---------------------------------------------------------------------------

def test_macro_aligned_bonus_light_realistic():
    """Dung score_scenario truc tiep: aligned vs unclear chenh lech khong qua 5."""
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
        "support_zones": [
            {"level": 1.0900, "low": 1.0880, "high": 1.0920, "strength": "moderate", "confluence_count": 1, "consolidation_bars": 1}
        ],
        "resistance_zones": [
            {"level": 1.1150, "low": 1.1130, "high": 1.1170, "strength": "weak", "confluence_count": 0, "consolidation_bars": 0}
        ],
    }
    smc = {
        "H4": {"bos": True, "choch": False, "displacement": "bullish",
               "demand_zones": [{"type": "demand_zone", "zone_score": 80, "zone_location": "discount",
                                 "liquidity_sweep": True, "broken": False, "mitigated": False, "test_count": 0}]},
        "H1": {"bos": True, "choch": False, "displacement": "bullish", "liquidity_sweeps": {"swept_lows": [1.09]}},
    }

    unclear = score_scenario("buy", tech, smc, 12, 20, macro_confidence=1.0, macro_context=None)
    aligned = score_scenario("buy", tech, smc, 12, 20, macro_confidence=1.0,
                             macro_context={"buy": 25, "sell": 10})

    diff = aligned["signal_score"] - unclear["signal_score"]
    assert 0 <= diff <= 5, f"aligned bonus phai <= 5, got {diff}"

    assert aligned["macro_modifier"] == 5
    assert aligned["macro_status"] == "aligned"
    assert "MACRO_ALIGNED" in aligned["reason_codes"]


# ---------------------------------------------------------------------------
# Test 2 — Macro conflict tru ro (>= 10 diem so voi unclear)
# ---------------------------------------------------------------------------

def test_macro_conflict_penalty_clear_realistic():
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
        "support_zones": [
            {"level": 1.0900, "low": 1.0880, "high": 1.0920, "strength": "moderate", "confluence_count": 1, "consolidation_bars": 1}
        ],
        "resistance_zones": [
            {"level": 1.1150, "low": 1.1130, "high": 1.1170, "strength": "weak", "confluence_count": 0, "consolidation_bars": 0}
        ],
    }
    smc = {
        "H4": {"bos": True, "choch": False, "displacement": "bullish",
               "demand_zones": [{"type": "demand_zone", "zone_score": 80, "zone_location": "discount",
                                 "liquidity_sweep": True, "broken": False, "mitigated": False, "test_count": 0}]},
        "H1": {"bos": True, "choch": False, "displacement": "bullish", "liquidity_sweeps": {"swept_lows": [1.09]}},
    }

    unclear = score_scenario("buy", tech, smc, 12, 20, macro_confidence=1.0, macro_context=None)
    conflict = score_scenario("buy", tech, smc, 12, 20, macro_confidence=1.0,
                              macro_context={"buy": 5, "sell": 25})

    diff = unclear["signal_score"] - conflict["signal_score"]
    assert diff >= 10, f"conflict penalty phai >= 10, got {diff}"

    assert conflict["macro_modifier"] == -15
    assert conflict["macro_status"] == "conflict"
    assert "MACRO_CONFLICT" in conflict["penalty_codes"]


# ---------------------------------------------------------------------------
# Test 3 — Macro unclear khong cong diem
# ---------------------------------------------------------------------------

def test_macro_unclear_no_bonus_realistic():
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
        "support_zones": [
            {"level": 1.0900, "low": 1.0880, "high": 1.0920, "strength": "moderate", "confluence_count": 1, "consolidation_bars": 1}
        ],
        "resistance_zones": [
            {"level": 1.1150, "low": 1.1130, "high": 1.1170, "strength": "weak", "confluence_count": 0, "consolidation_bars": 0}
        ],
    }
    smc = {
        "H4": {"bos": True, "choch": False, "displacement": "bullish",
               "demand_zones": [{"type": "demand_zone", "zone_score": 80, "zone_location": "discount",
                                 "liquidity_sweep": True, "broken": False, "mitigated": False, "test_count": 0}]},
        "H1": {"bos": True, "choch": False, "displacement": "bullish", "liquidity_sweeps": {"swept_lows": [1.09]}},
    }

    # Thieu macro_context -> unclear
    result = score_scenario("buy", tech, smc, 12, 20, macro_confidence=1.0, macro_context=None)
    assert result["macro_modifier"] == 0
    assert result["macro_status"] == "unclear"
    assert "MACRO_UNCLEAR" in result["penalty_codes"]

    # Neutral bias -> unclear
    result2 = score_scenario("buy", tech, smc, 12, 20, macro_confidence=1.0,
                             macro_context={"bias": "neutral"})
    assert result2["macro_modifier"] == 0
    assert result2["macro_status"] == "unclear"


# ---------------------------------------------------------------------------
# Test 4 — High impact news nearby block (thong qua analyze_symbol)
# ---------------------------------------------------------------------------

def test_high_impact_news_nearby_block_realistic():
    """Dung analyze_symbol: high_impact_event_within_30m=True -> stand_aside."""
    h1 = make_trending_candles(200, 1.0800, 0.00025)
    candles = _candle_dict(h1)
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        candles,
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "high_impact_event_within_30m": True,
        },
    )

    assert result["trade_gate"]["allowed"] is False
    assert result["trade_gate"]["decision_cap"] == "TRADE_BLOCKED"
    assert "HIGH_IMPACT_NEWS_NEARBY" in result["trade_gate"]["block_codes"]
    assert result["decision_summary"]["action"] == "stand_aside"


# ---------------------------------------------------------------------------
# Test 5 — Output Phase 1/2/3 van con day du
# ---------------------------------------------------------------------------

def test_phase4_preserves_all_legacy_output_keys():
    """Kiem tra cac key quan trong tu Phase 1/2/3 khong bi mat."""
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
        "support_zones": [
            {"level": 1.0900, "low": 1.0880, "high": 1.0920, "strength": "moderate", "confluence_count": 1, "consolidation_bars": 1}
        ],
        "resistance_zones": [
            {"level": 1.1150, "low": 1.1130, "high": 1.1170, "strength": "weak", "confluence_count": 0, "consolidation_bars": 0}
        ],
    }
    smc = {
        "H4": {"bos": True, "choch": False, "displacement": "bullish",
               "demand_zones": [{"type": "demand_zone", "zone_score": 80, "zone_location": "discount",
                                 "liquidity_sweep": True, "broken": False, "mitigated": False, "test_count": 0}]},
        "H1": {"bos": True, "choch": False, "displacement": "bullish", "liquidity_sweeps": {"swept_lows": [1.09]}},
    }

    result = score_scenario("buy", tech, smc, 12, 20, macro_confidence=1.0,
                            macro_context={"buy": 25, "sell": 10})

    # Phase 1 keys (legacy scoring)
    for key in ("trend_alignment", "momentum_alignment", "location_quality",
                "smc_quality", "risk_condition", "macro_alignment", "macro_raw",
                "signal_score", "total", "rating"):
        assert key in result, f"Thieu key Phase 1: {key}"

    # Phase 4 keys
    for key in ("macro_status", "macro_modifier", "reason_codes", "penalty_codes"):
        assert key in result, f"Thieu key Phase 4: {key}"


# ---------------------------------------------------------------------------
# Test 6 — analyze_symbol output co day du key qua cac phase
# ---------------------------------------------------------------------------

def test_analyze_symbol_has_all_phase_keys():
    """Output analyze_symbol co du trade_gate, direction_bias, decision_summary."""
    h1 = make_trending_candles(200, 1.0800, 0.00025)
    candles = _candle_dict(h1)
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        candles,
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
    )

    # Phase 2: trade_gate
    assert "trade_gate" in result
    assert "allowed" in result["trade_gate"]
    assert "decision_cap" in result["trade_gate"]

    # Phase 3: direction_bias
    assert "direction_bias" in result
    for key in ("best_side", "buy_score", "sell_score", "score_gap", "is_clear_bias"):
        assert key in result["direction_bias"], f"Thieu direction_bias key: {key}"

    # Phase 3: decision_summary
    assert "decision_summary" in result
    for key in ("action", "best_score", "best_side", "score_gap", "gate_allowed"):
        assert key in result["decision_summary"], f"Thieu decision_summary key: {key}"

    # Scenario scores
    assert "scenario_scores" in result
    assert "buy" in result["scenario_scores"]
    assert "sell" in result["scenario_scores"]

    # Phase 4: macro keys trong score_scenario
    for side in ("buy", "sell"):
        score = result["scenario_scores"][side]
        for key in ("signal_score", "total", "macro_modifier", "macro_status", "reason_codes", "penalty_codes"):
            assert key in score, f"Thieu key {key} trong scenario_scores[{side}]"


# ---------------------------------------------------------------------------
# Test 7 — Macro weight da giam (Prompt 1 van hieu luc)
# ---------------------------------------------------------------------------

def test_macro_weights_reduced_in_all_regimes():
    for regime, weights in DYNAMIC_WEIGHTS.items():
        assert weights.get("macro", 999) <= 20, f"{regime}: macro={weights.get('macro')} > 20"


def test_dynamic_weights_total_reasonable_in_all_regimes():
    for regime, weights in DYNAMIC_WEIGHTS.items():
        total = sum(weights.values())
        assert 95 <= total <= 105, f"{regime}: total={total}"


# ---------------------------------------------------------------------------
# Test 8 — _detect_macro_status helper (Prompt 2)
# ---------------------------------------------------------------------------

def test_detect_macro_status_edge_cases():
    # None
    assert _detect_macro_status(None, "buy") == "unclear"
    # Empty
    assert _detect_macro_status({}, "buy") == "unclear"
    # Missing buy/sell
    assert _detect_macro_status({"other": "data"}, "buy") == "unclear"
    # Exactly at threshold
    assert _detect_macro_status({"buy": 21, "sell": 15}, "buy") == "aligned"
    assert _detect_macro_status({"buy": 15, "sell": 21}, "sell") == "aligned"
    # Just below threshold (gap=5 is NOT > 5)
    assert _detect_macro_status({"buy": 20, "sell": 15}, "buy") == "unclear"
    assert _detect_macro_status({"buy": 15, "sell": 20}, "sell") == "unclear"
