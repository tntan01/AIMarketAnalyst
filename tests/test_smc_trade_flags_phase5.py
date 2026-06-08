from __future__ import annotations

from core.smc_context import extract_smc_trade_flags


# ---------------------------------------------------------------------------
# Test 1 — None input: tra ve flags an toan
# ---------------------------------------------------------------------------

def test_none_input_returns_safe_flags():
    flags = extract_smc_trade_flags(None, "buy")
    assert flags["zone_broken"] is False
    assert flags["choch_against_direction"] is False
    assert flags["liquidity_sweep_aligned"] is False
    assert flags["displacement_aligned"] is False
    assert flags["has_selected_zone"] is False
    assert flags["selected_zone_type"] is None
    assert flags["selected_zone_score"] is None
    assert isinstance(flags["raw"], dict)


# ---------------------------------------------------------------------------
# Test 2 — Empty dict: khong crash
# ---------------------------------------------------------------------------

def test_empty_dict_returns_safe_flags():
    flags = extract_smc_trade_flags({}, "buy")
    assert flags["zone_broken"] is False
    assert flags["choch_against_direction"] is False
    assert flags["has_selected_zone"] is False


# ---------------------------------------------------------------------------
# Test 3 — Zone broken khi best zone co broken=True
# ---------------------------------------------------------------------------

def test_zone_broken_detected():
    smc = {
        "H4": {
            "demand_zones": [
                {
                    "type": "demand_zone",
                    "zone_score": 85,
                    "broken": True,
                    "mitigated": False,
                    "test_count": 2,
                }
            ],
        },
        "H1": {},
    }
    flags = extract_smc_trade_flags(smc, "buy")
    # Zone bi broken -> bi loai khoi candidates, nen has_selected_zone=False
    # nhung flags van khong crash
    assert flags["zone_broken"] is False  # broken zone bi skip
    assert flags["has_selected_zone"] is False  # khong con zone hop le


def test_zone_not_broken_buy():
    smc = {
        "H4": {
            "demand_zones": [
                {
                    "type": "demand_zone",
                    "zone_score": 80,
                    "broken": False,
                    "mitigated": False,
                    "test_count": 0,
                }
            ],
        },
        "H1": {},
    }
    flags = extract_smc_trade_flags(smc, "buy")
    assert flags["has_selected_zone"] is True
    assert flags["selected_zone_type"] == "demand_zone"
    assert flags["selected_zone_score"] == 80
    assert flags["zone_broken"] is False


# ---------------------------------------------------------------------------
# Test 4 — CHOCH nguoc huong buy
# ---------------------------------------------------------------------------

def test_choch_against_buy():
    smc = {
        "H4": {
            "choch": True,
            "displacement": "bearish",
        },
        "H1": {},
    }
    flags = extract_smc_trade_flags(smc, "buy")
    assert flags["choch_against_direction"] is True


def test_choch_against_buy_h1():
    """CHOCH bearish tren H1 cung la against buy."""
    smc = {
        "H4": {"choch": False, "displacement": "neutral"},
        "H1": {"choch": True, "displacement": "bearish"},
    }
    flags = extract_smc_trade_flags(smc, "buy")
    assert flags["choch_against_direction"] is True


# ---------------------------------------------------------------------------
# Test 5 — CHOCH nguoc huong sell
# ---------------------------------------------------------------------------

def test_choch_against_sell():
    smc = {
        "H4": {
            "choch": True,
            "displacement": "bullish",
        },
        "H1": {},
    }
    flags = extract_smc_trade_flags(smc, "sell")
    assert flags["choch_against_direction"] is True


def test_choch_not_against_sell():
    """CHOCH bearish khong phai against sell."""
    smc = {
        "H4": {
            "choch": True,
            "displacement": "bearish",
        },
        "H1": {},
    }
    flags = extract_smc_trade_flags(smc, "sell")
    assert flags["choch_against_direction"] is False


# ---------------------------------------------------------------------------
# Test 6 — Liquidity sweep aligned buy
# ---------------------------------------------------------------------------

def test_liquidity_sweep_aligned_buy():
    smc = {
        "H1": {
            "liquidity_sweeps": {"swept_lows": [1.0900], "swept_highs": []},
        },
        "H4": {},
    }
    flags = extract_smc_trade_flags(smc, "buy")
    assert flags["liquidity_sweep_aligned"] is True


def test_liquidity_sweep_not_aligned_buy():
    """Swept highs khong phai aligned cho buy."""
    smc = {
        "H1": {
            "liquidity_sweeps": {"swept_lows": [], "swept_highs": [1.1200]},
        },
        "H4": {},
    }
    flags = extract_smc_trade_flags(smc, "buy")
    assert flags["liquidity_sweep_aligned"] is False


# ---------------------------------------------------------------------------
# Test 7 — Liquidity sweep aligned sell
# ---------------------------------------------------------------------------

def test_liquidity_sweep_aligned_sell():
    smc = {
        "H1": {
            "liquidity_sweeps": {"swept_highs": [1.1200], "swept_lows": []},
        },
        "H4": {},
    }
    flags = extract_smc_trade_flags(smc, "sell")
    assert flags["liquidity_sweep_aligned"] is True


def test_liquidity_sweep_not_aligned_sell():
    smc = {
        "H1": {
            "liquidity_sweeps": {"swept_lows": [1.0900], "swept_highs": []},
        },
        "H4": {},
    }
    flags = extract_smc_trade_flags(smc, "sell")
    assert flags["liquidity_sweep_aligned"] is False


# ---------------------------------------------------------------------------
# Test 8 — Displacement aligned
# ---------------------------------------------------------------------------

def test_displacement_aligned_buy():
    smc = {"H4": {"displacement": "bullish"}, "H1": {}}
    flags = extract_smc_trade_flags(smc, "buy")
    assert flags["displacement_aligned"] is True


def test_displacement_aligned_sell():
    smc = {"H4": {"displacement": "bearish"}, "H1": {}}
    flags = extract_smc_trade_flags(smc, "sell")
    assert flags["displacement_aligned"] is True


def test_displacement_not_aligned_buy():
    smc = {"H4": {"displacement": "bearish"}, "H1": {}}
    flags = extract_smc_trade_flags(smc, "buy")
    assert flags["displacement_aligned"] is False


# ---------------------------------------------------------------------------
# Test 9 — Invalid direction tra ve an toan
# ---------------------------------------------------------------------------

def test_invalid_direction_returns_safe():
    flags = extract_smc_trade_flags({"H4": {"displacement": "bullish"}}, "long")
    assert flags["choch_against_direction"] is False
    assert flags["liquidity_sweep_aligned"] is False
    assert flags["displacement_aligned"] is False


# ---------------------------------------------------------------------------
# Test 10 — Full smc real structure
# ---------------------------------------------------------------------------

def test_full_smc_structure_buy_aligned():
    smc = {
        "H4": {
            "structure": "HH/HL",
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
            "supply_zones": [],
            "order_blocks": [],
            "fvg": [],
        },
        "H1": {
            "bos": True,
            "choch": False,
            "displacement": "bullish",
            "liquidity_sweeps": {"swept_lows": [1.09], "swept_highs": []},
        },
    }
    flags = extract_smc_trade_flags(smc, "buy")
    assert flags["choch_against_direction"] is False
    assert flags["liquidity_sweep_aligned"] is True
    assert flags["displacement_aligned"] is True
    assert flags["has_selected_zone"] is True
    assert flags["selected_zone_type"] == "demand_zone"
    assert flags["selected_zone_score"] == 82
    assert flags["zone_broken"] is False


# ---------------------------------------------------------------------------
# Test 11 — Full smc cho sell aligned
# ---------------------------------------------------------------------------

def test_full_smc_structure_sell_aligned():
    smc = {
        "H4": {
            "structure": "LH/LL",
            "bos": True,
            "choch": False,
            "displacement": "bearish",
            "supply_zones": [
                {
                    "type": "supply_zone",
                    "zone_score": 78,
                    "zone_location": "premium",
                    "liquidity_sweep": True,
                    "broken": False,
                    "mitigated": False,
                    "test_count": 0,
                }
            ],
            "demand_zones": [],
            "order_blocks": [],
            "fvg": [],
        },
        "H1": {
            "bos": True,
            "choch": False,
            "displacement": "bearish",
            "liquidity_sweeps": {"swept_highs": [1.15], "swept_lows": []},
        },
    }
    flags = extract_smc_trade_flags(smc, "sell")
    assert flags["choch_against_direction"] is False
    assert flags["liquidity_sweep_aligned"] is True
    assert flags["displacement_aligned"] is True
    assert flags["has_selected_zone"] is True
    assert flags["selected_zone_type"] == "supply_zone"
    assert flags["selected_zone_score"] == 78
    assert flags["zone_broken"] is False


# ---------------------------------------------------------------------------
# Test 12 — raw snapshot co mat
# ---------------------------------------------------------------------------

def test_raw_snapshot_present():
    smc = {
        "H4": {"structure": "HH/HL", "bos": True, "choch": False, "displacement": "bullish"},
        "H1": {"liquidity_sweeps": {"swept_lows": [1.09]}},
    }
    flags = extract_smc_trade_flags(smc, "buy")
    raw = flags["raw"]
    assert raw["h4_structure"] == "HH/HL"
    assert raw["h4_bos"] is True
    assert raw["h4_choch"] is False
    assert raw["h4_displacement"] == "bullish"
    assert raw["h1_liquidity_sweeps"] is True
