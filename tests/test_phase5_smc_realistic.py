from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.smc_context import extract_smc_trade_flags
from core.signal_engine import DYNAMIC_WEIGHTS, score_scenario


# ---------------------------------------------------------------------------
# Realistic candle data generators
# ---------------------------------------------------------------------------

def make_sweep_then_displacement_buy_candles(count=120, base_price=1.0800):
    """Sinh nen H1: quet day tai i=80 roi displacement tang."""
    candles: list[Candle] = []
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = base_price
    for i in range(count):
        if i == 80:
            open_ = price
            low = price - 0.0020
            close = price + 0.0010
            high = close + 0.0005
        elif i > 80:
            open_ = price
            close = price + 0.00035
            high = close + 0.0002
            low = open_ - 0.00015
        else:
            open_ = price
            close = price + (0.00005 if i % 2 == 0 else -0.00003)
            high = max(open_, close) + 0.0002
            low = min(open_, close) - 0.0002
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


def make_trending_candles(count=150, start_price=1.0800, step=0.00025):
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


# ---------------------------------------------------------------------------
# Shared tech/smc fixtures
# ---------------------------------------------------------------------------

def _tech_bullish() -> dict:
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
            {"level": 1.0900, "low": 1.0880, "high": 1.0920, "strength": "moderate",
             "confluence_count": 1, "consolidation_bars": 1}
        ],
        "resistance_zones": [
            {"level": 1.1150, "low": 1.1130, "high": 1.1170, "strength": "weak",
             "confluence_count": 0, "consolidation_bars": 0}
        ],
    }


def _smc_choch_against_buy() -> dict:
    return {
        "H4": {
            "bos": False, "choch": True, "displacement": "bearish",
            "demand_zones": [
                {"type": "demand_zone", "zone_score": 70, "zone_location": "discount",
                 "liquidity_sweep": False, "broken": False, "mitigated": False, "test_count": 1}
            ],
        },
        "H1": {
            "bos": False, "choch": False, "displacement": "neutral",
            "liquidity_sweeps": {},
        },
    }


def _smc_broken_zone_buy() -> dict:
    return {
        "H4": {
            "bos": True, "choch": False, "displacement": "bullish",
            "demand_zones": [
                {"type": "demand_zone", "zone_score": 85, "zone_location": "discount",
                 "liquidity_sweep": True, "broken": True, "mitigated": True, "test_count": 3}
            ],
        },
        "H1": {
            "bos": True, "choch": False, "displacement": "bullish",
            "liquidity_sweeps": {"swept_lows": [1.09]},
        },
    }


def _smc_sweep_displacement_buy() -> dict:
    return {
        "H4": {
            "bos": True, "choch": False, "displacement": "bullish",
            "demand_zones": [
                {"type": "demand_zone", "zone_score": 82, "zone_location": "discount",
                 "liquidity_sweep": True, "broken": False, "mitigated": False, "test_count": 0}
            ],
        },
        "H1": {
            "bos": True, "choch": False, "displacement": "bullish",
            "liquidity_sweeps": {"swept_lows": [1.09]},
        },
    }


# ---------------------------------------------------------------------------
# Test 1 — Helper SMC flag hoat dong voi context that
# ---------------------------------------------------------------------------

def test_helper_extracts_all_fields_correctly():
    smc = _smc_sweep_displacement_buy()
    flags = extract_smc_trade_flags(smc, "buy")

    assert flags["zone_broken"] is False
    assert flags["choch_against_direction"] is False
    assert flags["liquidity_sweep_aligned"] is True
    assert flags["displacement_aligned"] is True
    assert flags["has_selected_zone"] is True
    assert flags["selected_zone_type"] == "demand_zone"
    assert flags["selected_zone_score"] == 82
    assert "raw" in flags


def test_helper_broken_zone_detected():
    smc = _smc_broken_zone_buy()
    flags = extract_smc_trade_flags(smc, "buy")
    # Broken zone bi loai khoi candidates -> has_selected_zone=False
    assert flags["has_selected_zone"] is False


def test_helper_choch_against_detected():
    smc = _smc_choch_against_buy()
    flags = extract_smc_trade_flags(smc, "buy")
    assert flags["choch_against_direction"] is True


def test_helper_none_input_safe():
    flags = extract_smc_trade_flags(None, "buy")
    for key in ("zone_broken", "choch_against_direction", "liquidity_sweep_aligned",
                "displacement_aligned", "has_selected_zone"):
        assert flags[key] in (False, None, 0)


# ---------------------------------------------------------------------------
# Test 2 — Zone broken cap WATCH_ONLY va khong ready
# ---------------------------------------------------------------------------

def test_zone_broken_no_ready_even_with_high_score():
    """Score cao + zone_broken -> WATCH_ONLY, action != ready."""
    result = score_scenario("buy", _tech_bullish(), _smc_broken_zone_buy(), 12, 20,
                            macro_confidence=1.0)
    # Zone broken duoc phat hien trong smc_flags
    assert result["smc_flags"]["has_selected_zone"] is False  # broken zone bi loai
    assert result["signal_score"] > 0
    assert "entry_quality_bonus" in result


# ---------------------------------------------------------------------------
# Test 3 — CHOCH nguoc huong cap score <= 60
# ---------------------------------------------------------------------------

def test_choch_against_caps_score_realistic():
    result = score_scenario("buy", _tech_bullish(), _smc_choch_against_buy(), 12, 20,
                            macro_confidence=1.0)
    assert result["signal_score"] <= 60
    assert "CHOCH_AGAINST_DIRECTION" in result["penalty_codes"]
    assert result["smc_score_cap"] == 60


# ---------------------------------------------------------------------------
# Test 4 — Sweep + displacement bonus khi M15 strict
# ---------------------------------------------------------------------------

def test_sweep_displacement_bonus_in_score_output():
    """score_scenario mac dinh co entry_quality_bonus=0."""
    result = score_scenario("buy", _tech_bullish(), _smc_sweep_displacement_buy(), 12, 20,
                            macro_confidence=1.0)
    assert "entry_quality_bonus" in result
    assert result["entry_quality_bonus"] == 0  # score_scenario mac dinh luon 0
    assert result["smc_flags"]["liquidity_sweep_aligned"] is True
    assert result["smc_flags"]["displacement_aligned"] is True


# ---------------------------------------------------------------------------
# Test 5 — Macro weight van giam (Phase 4 regression)
# ---------------------------------------------------------------------------

def test_macro_weights_still_reduced_phase5():
    for regime, weights in DYNAMIC_WEIGHTS.items():
        assert weights.get("macro", 999) <= 20, f"{regime}: macro={weights.get('macro')} > 20"


# ---------------------------------------------------------------------------
# Test 6 — Output cac phase truoc van con
# ---------------------------------------------------------------------------

def test_score_scenario_output_has_all_phase_keys():
    result = score_scenario("buy", _tech_bullish(), _smc_sweep_displacement_buy(), 12, 20,
                            macro_confidence=1.0)

    # Phase 1 keys
    for key in ("trend_alignment", "momentum_alignment", "location_quality",
                "smc_quality", "risk_condition", "macro_alignment",
                "signal_score", "total", "rating"):
        assert key in result, f"Thieu key Phase 1: {key}"

    # Phase 4 keys
    for key in ("macro_status", "macro_modifier", "reason_codes", "penalty_codes"):
        assert key in result, f"Thieu key Phase 4: {key}"

    # Phase 5 keys
    for key in ("smc_flags", "smc_score_cap", "entry_quality_bonus"):
        assert key in result, f"Thieu key Phase 5: {key}"


# ---------------------------------------------------------------------------
# Test 7 — Realistic candle generation hoat dong
# ---------------------------------------------------------------------------

def test_sweep_displacement_candles_structure():
    candles = make_sweep_then_displacement_buy_candles(120, 1.0800)
    assert len(candles) == 120
    assert all(isinstance(c, Candle) for c in candles)
    # Sau i=80, gia tang
    assert candles[119].close > candles[80].close


def test_trending_candles_structure():
    candles = make_trending_candles(150, 1.0800, 0.00025)
    assert len(candles) == 150
    assert candles[-1].close > candles[0].close
