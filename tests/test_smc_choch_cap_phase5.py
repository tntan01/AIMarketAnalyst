from __future__ import annotations

from core.signal_engine import score_scenario


# ---------------------------------------------------------------------------
# Shared test fixtures
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


def _smc_bullish_buy() -> dict:
    """SMC buy-aligned: BOS bullish, demand zone, sweep lows."""
    return {
        "H4": {
            "bos": True, "choch": False, "displacement": "bullish",
            "demand_zones": [
                {"type": "demand_zone", "zone_score": 80, "zone_location": "discount",
                 "liquidity_sweep": True, "broken": False, "mitigated": False, "test_count": 0}
            ],
        },
        "H1": {
            "bos": True, "choch": False, "displacement": "bullish",
            "liquidity_sweeps": {"swept_lows": [1.09]},
        },
    }


def _smc_choch_against_buy() -> dict:
    """SMC: CHOCH bearish tren H4 -> nguoc huong buy."""
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


def _smc_choch_against_sell() -> dict:
    """SMC: CHOCH bullish tren H4 -> nguoc huong sell."""
    return {
        "H4": {
            "bos": False, "choch": True, "displacement": "bullish",
            "supply_zones": [
                {"type": "supply_zone", "zone_score": 70, "zone_location": "premium",
                 "liquidity_sweep": False, "broken": False, "mitigated": False, "test_count": 1}
            ],
        },
        "H1": {
            "bos": False, "choch": False, "displacement": "neutral",
            "liquidity_sweeps": {},
        },
    }


# ---------------------------------------------------------------------------
# Test 1 — CHOCH nguoc huong cap Buy signal_score <= 60
# ---------------------------------------------------------------------------

def test_choch_against_buy_caps_score():
    """Buy setup bi CHOCH bearish -> score khong vuot qua 60."""
    result = score_scenario("buy", _tech_bullish(), _smc_choch_against_buy(), 12, 20,
                            macro_confidence=1.0)
    assert result["signal_score"] <= 60
    assert "CHOCH_AGAINST_DIRECTION" in result["penalty_codes"]
    assert result["smc_score_cap"] == 60


# ---------------------------------------------------------------------------
# Test 2 — CHOCH nguoc huong cap Sell signal_score <= 60
# ---------------------------------------------------------------------------

def test_choch_against_sell_caps_score():
    """Sell setup bi CHOCH bullish -> score khong vuot qua 60."""
    result = score_scenario("sell", _tech_bullish(), _smc_choch_against_sell(), 12, 20,
                            macro_confidence=1.0)
    assert result["signal_score"] <= 60
    assert "CHOCH_AGAINST_DIRECTION" in result["penalty_codes"]
    assert result["smc_score_cap"] == 60


# ---------------------------------------------------------------------------
# Test 3 — Khong co CHOCH nguoc -> khong cap
# ---------------------------------------------------------------------------

def test_no_choch_against_no_cap():
    """SMC buy-aligned, khong co CHOCH nguoc -> khong bi cap."""
    result = score_scenario("buy", _tech_bullish(), _smc_bullish_buy(), 12, 20,
                            macro_confidence=1.0)
    assert "CHOCH_AGAINST_DIRECTION" not in result["penalty_codes"]
    assert result["smc_score_cap"] is None


# ---------------------------------------------------------------------------
# Test 4 — Khong append trung penalty
# ---------------------------------------------------------------------------

def test_choch_penalty_not_duplicated():
    """CHOCH_AGAINST_DIRECTION chi xuat hien 1 lan."""
    result = score_scenario("buy", _tech_bullish(), _smc_choch_against_buy(), 12, 20,
                            macro_confidence=1.0)
    assert result["penalty_codes"].count("CHOCH_AGAINST_DIRECTION") == 1


# ---------------------------------------------------------------------------
# Test 5 — Backward compatibility
# ---------------------------------------------------------------------------

def test_choch_cap_preserves_output_keys():
    """Cac key cu van ton tai sau khi them CHOCH cap."""
    result = score_scenario("buy", _tech_bullish(), _smc_choch_against_buy(), 12, 20,
                            macro_confidence=1.0)
    assert "signal_score" in result
    assert "total" in result
    assert result["signal_score"] == result["total"]
    assert "macro_status" in result
    assert "macro_modifier" in result
    assert "reason_codes" in result
    assert "penalty_codes" in result


# ---------------------------------------------------------------------------
# Test 6 — smc_flags va smc_score_cap co trong output
# ---------------------------------------------------------------------------

def test_smc_flags_in_output():
    result = score_scenario("buy", _tech_bullish(), _smc_bullish_buy(), 12, 20,
                            macro_confidence=1.0)
    assert "smc_flags" in result
    assert "smc_score_cap" in result
    assert isinstance(result["smc_flags"], dict)
    assert "choch_against_direction" in result["smc_flags"]


# ---------------------------------------------------------------------------
# Test 7 — Score vua cap CHOCH vua co macro modifier
# ---------------------------------------------------------------------------

def test_choch_cap_with_macro_conflict():
    """CHOCH nguoc + macro conflict: ca 2 penalty deu co mat."""
    result = score_scenario("buy", _tech_bullish(), _smc_choch_against_buy(), 12, 20,
                            macro_confidence=1.0,
                            macro_context={"buy": 5, "sell": 25})
    assert result["signal_score"] <= 60
    assert "CHOCH_AGAINST_DIRECTION" in result["penalty_codes"]
    assert "MACRO_CONFLICT" in result["penalty_codes"]
    assert result["macro_status"] == "conflict"
    assert result["smc_score_cap"] == 60


# ---------------------------------------------------------------------------
# Test 8 — None SMC context khong crash
# ---------------------------------------------------------------------------

def test_none_smc_no_crash():
    """score_scenario khong crash khi smc la None."""
    result = score_scenario("buy", _tech_bullish(), None, 12, 20, macro_confidence=1.0)
    assert "signal_score" in result
    assert "smc_flags" in result
    assert result["smc_flags"]["choch_against_direction"] is False
