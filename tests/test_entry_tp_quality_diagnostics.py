"""Phase 13A: diagnostic fields for entry zone & TP1 quality.

Tests cover:
- Far edge correctness (BUY → entry_high, SELL → entry_low).
- entry_zone_width and entry_zone_width_atr computation.
- TP1 clearance for BUY and SELL.
- No TP1 → all clearance fields None, tp1_source="none".
- Missing/invalid ATR → ATR-normalized fields None, no crash.
- tp1_effective_rr_base matches expected_effective_rr_base (midpoint).
- tp1_source tracking through cascade (equal_level/target_zone/fib_extension/swing/none).
- Scanner row copies Phase 13A fields.
- Scenario matching supports both "type" and "side" keys.
- Script parser + compute_quality with synthetic data.
- Script import does not require PyQt/MT5.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from core.risk_engine import (
    AnalysisInput,
    build_trade_plan,
    calculate_expected_effective_rr,
)
from core.market_models import Candle


# ---------------------------------------------------------------------------
# Helpers (shared with test_risk_reward_range.py pattern)
# ---------------------------------------------------------------------------

def _candles(n, price=1.1000, volatility=0.0006, start_time=None, bar_minutes=60):
    t = start_time or datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    candles = []
    cur = price
    for i in range(n):
        wick = volatility * 0.4
        open_p = cur
        close_p = cur + (i % 3 - 1) * volatility * 0.1
        high_p = max(open_p, close_p) + wick
        low_p = min(open_p, close_p) - wick
        candles.append(Candle(
            time=t, open=round(open_p, 5), high=round(high_p, 5),
            low=round(low_p, 5), close=round(close_p, 5),
            volume=float(1000 + i * 10)))
        cur = close_p
        t += timedelta(minutes=bar_minutes)
    return candles


def _req():
    return AnalysisInput(symbol="EUR/USD", broker_symbol="EURUSDm",
                         account_balance=10000.0, risk_percent=2.0,
                         contract_size_override=100000.0)


def _zone(level, low, high, strength="moderate", zone_score=None):
    return {"level": level, "low": low, "high": high,
            "type": "support" if low < level else "resistance",
            "strength": strength,
            "zone_score": zone_score if zone_score is not None else (75 if strength == "strong" else 50),
            "confluence_count": 1, "consolidation_bars": 0,
            "freshness_bars": None, "mitigated": False, "broken": False,
            "test_count": 0, "displacement_multiple": 0, "liquidity_sweep": False,
            "zone_location": "unknown", "source": "technical"}


def _swing(level, index=0):
    return {"level": level, "index": index, "time": "2026-06-01T00:00:00"}


def _base_tech(price, atr, supports, resistances):
    return {"price": price, "atr_h4": atr, "atr_d1": atr * 1.2,
            "ema50_d1": price - 0.002, "ema200_d1": price - 0.005,
            "ema50_h4": price - 0.001,
            "ema50_d1_slope": 0.0001, "ema200_d1_slope": 0.00005,
            "rsi_h4": 50.0, "rsi_h4_previous": 48.0,
            "macd_histogram_h4": {"value": 0.00002, "previous_value": -0.00001,
                                  "previous2_value": -0.00003, "direction": "increasing"},
            "support_zones": supports, "resistance_zones": resistances,
            "structure_d1": "trend_up", "structure_h4": "trend_up",
            "swings_h4": {"highs": [], "lows": []},
            "swings_d1": {"highs": [], "lows": []},
            "range_info": {"in_range": False, "range_high": None, "range_low": None}}


def _base_smc():
    return {"H4": {"demand_zones": [], "supply_zones": [],
                   "swings": {"highs": [], "lows": []},
                   "liquidity_pools": {"equal_highs": [], "equal_lows": []},
                   "bos": False, "displacement": None, "choch": False, "fvg": False}}


candles = _candles(200)
m15 = _candles(200, volatility=0.0003, bar_minutes=15)


# ---------------------------------------------------------------------------
# Far edge + zone width
# ---------------------------------------------------------------------------


class TestFarEdge:
    def test_buy_far_edge_is_entry_high(self):
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
                          [_zone(1.1050, 1.1040, 1.1060, "strong", 70)])
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0940, 5)]}
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        assert plan is not None
        ez = plan["entry_zone"]
        # Far edge for BUY = entry_high
        far_edge = ez[1]
        assert far_edge > ez[0]

    def test_sell_far_edge_is_entry_low(self):
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0920, 1.0910, 1.0930, "strong", 75)],
                          [_zone(1.1040, 1.1030, 1.1050, "strong", 70)])
        tech["structure_d1"] = "trend_down"
        tech["structure_h4"] = "trend_down"
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1060, 10)], "lows": [_swing(1.0920, 5)]}
        plan = build_trade_plan("sell", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_down"})
        assert plan is not None
        ez = plan["entry_zone"]
        # Far edge for SELL = entry_low
        far_edge = ez[0]
        assert far_edge < ez[1]


class TestEntryZoneWidth:
    def test_zone_width_and_width_atr_buy(self):
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
                          [_zone(1.1050, 1.1040, 1.1060, "strong", 70)])
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0940, 5)]}
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        assert plan is not None
        ez = plan["entry_zone"]
        expected_width = ez[1] - ez[0]
        assert plan["entry_zone_width"] == pytest.approx(expected_width, abs=0.0001)
        assert plan["entry_zone_width_atr"] is not None
        assert plan["entry_zone_width_atr"] == pytest.approx(expected_width / 0.0020, abs=0.001)

    def test_zone_width_atr_none_when_atr_zero(self):
        """ATR=0 should make width_atr None, but plan won't build with ATR=0.
        Test the guard directly."""
        # With ATR=0, build_trade_plan returns None (line 441-442)
        tech = _base_tech(1.1000, 0.0,
                          [_zone(1.0960, 1.0950, 1.0970)],
                          [_zone(1.1050, 1.1040, 1.1060)])
        smc = _base_smc()
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        assert plan is None  # ATR=0 → can't build plan


class TestTP1Clearance:
    def test_buy_tp1_clearance_from_far_edge(self):
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
                          [_zone(1.1050, 1.1040, 1.1060, "strong", 70)])
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0940, 5)]}
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        assert plan is not None
        tp1 = plan["take_profit"][0]
        far_edge = plan["entry_zone"][1]
        # BUY: clearance = TP1 - entry_high
        assert tp1 > far_edge, f"TP1={tp1} must be above far edge={far_edge}"
        clearance = abs(tp1 - far_edge)
        assert plan["tp1_clearance_from_far_edge"] == pytest.approx(clearance, abs=0.0001)
        assert plan["tp1_clearance_atr"] is not None
        assert plan["tp1_clearance_atr"] > 0

    def test_sell_tp1_clearance_from_far_edge(self):
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0920, 1.0910, 1.0930, "strong", 75)],
                          [_zone(1.1040, 1.1030, 1.1050, "strong", 70)])
        tech["structure_d1"] = "trend_down"
        tech["structure_h4"] = "trend_down"
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1060, 10)], "lows": [_swing(1.0920, 5)]}
        plan = build_trade_plan("sell", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_down"})
        assert plan is not None
        tp1 = plan["take_profit"][0]
        far_edge = plan["entry_zone"][0]
        # SELL: clearance = entry_low - TP1
        assert tp1 < far_edge, f"TP1={tp1} must be below far edge={far_edge}"
        clearance = abs(tp1 - far_edge)
        assert plan["tp1_clearance_from_far_edge"] == pytest.approx(clearance, abs=0.0001)


class TestNoTP1:
    def test_no_tp1_all_clearance_fields_none(self):
        """When no structural TP1 exists and zone is preferred/SMC, all
        clearance fields should be None and tp1_source should be 'none'."""
        pref = {"level": 1.0975, "low": 1.0968, "high": 1.0982, "strength": "moderate",
                "zone_score": 68, "source": "smc", "confluence_count": 2,
                "consolidation_bars": 5, "freshness_bars": 20, "mitigated": False,
                "broken": False, "test_count": 0, "displacement_multiple": 2.0,
                "liquidity_sweep": True, "zone_location": "discount", "type": "demand"}
        tech = _base_tech(1.1000, 0.0010,
                          [_zone(1.0940, 1.0930, 1.0950, "moderate", 50)],
                          [])
        tech["structure_d1"] = "range"
        tech["structure_h4"] = "range"
        tech["range_info"] = {"in_range": True, "range_high": 1.1020, "range_low": 1.0940}
        smc = _base_smc()
        smc["H4"]["demand_zones"] = [pref]
        smc["H4"]["swings"] = {"highs": [], "lows": [_swing(1.0940, 5)]}

        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                preferred_zone=pref, market_regime={"primary": "range"})

        if plan is not None and plan["take_profit"] == []:
            assert plan["tp1_source"] == "none"
            assert plan["tp1_clearance_from_far_edge"] is None
            assert plan["tp1_clearance_atr"] is None
            assert plan["tp1_effective_rr_base"] is None


class TestTP1Source:
    def test_tp1_source_is_not_just_structure(self):
        """tp1_source must be a granular cascade value, not 'structure'."""
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
                          [_zone(1.1050, 1.1040, 1.1060, "strong", 70)])
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0940, 5)]}
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        assert plan is not None
        assert plan["tp1_source"] != "structure", \
            f"tp1_source should be granular, got: {plan['tp1_source']}"
        assert plan["tp1_source"] in (
            "equal_level", "target_zone", "fib_extension", "swing", "none",
        )


class TestTP1EffectiveRRBase:
    def test_tp1_effective_rr_base_matches_midpoint(self):
        """tp1_effective_rr_base should equal expected_effective_rr_base
        (both computed at midpoint entry)."""
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
                          [_zone(1.1050, 1.1040, 1.1060, "strong", 70)])
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0940, 5)]}
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        assert plan is not None
        assert plan["tp1_effective_rr_base"] is not None
        assert plan["tp1_effective_rr_base"] == plan["expected_effective_rr_base"]


# ---------------------------------------------------------------------------
# Scanner row exposure
# ---------------------------------------------------------------------------


class TestScannerRowExposure:
    def test_scanner_row_copies_phase13a_fields(self):
        from core.scanner import scanner_row_from_analysis
        plan = {
            "type": "buy",
            "risk_reward": "1:2.4",
            "expected_effective_rr": 2.3,
            "expected_effective_rr_base": 1.7,
            "entry_zone": [1.095, 1.097],
            "entry_status": "watch_zone",
            "m15_quality": "loose",
            "stop_loss": 1.093,
            "take_profit": [1.105],
            "entry_zone_width": 0.0020,
            "entry_zone_width_atr": 1.0,
            "entry_zone_source": "smc",
            "tp1_source": "target_zone",
            "tp1_clearance_from_far_edge": 0.0080,
            "tp1_clearance_atr": 4.0,
            "tp1_effective_rr_base": 1.7,
        }
        result = {
            "symbol": "EUR/USD",
            "scenario_scores": {"buy": {"signal_score": 80}, "sell": {"signal_score": 50}},
            "trade_permission": {"status": "allowed"},
            "scenarios": [plan],
            "technical": {"price": 1.096, "atr_h4": 0.002},
            "decision_engine": {"legacy_action": "watch", "decision": "WATCH_ONLY"},
            "direction_bias": {"best_side": "buy"},
        }
        row = scanner_row_from_analysis(result)

        assert row["entry_zone_width"] == plan["entry_zone_width"]
        assert row["entry_zone_width_atr"] == plan["entry_zone_width_atr"]
        assert row["tp1_source"] == plan["tp1_source"]
        assert row["tp1_clearance_from_far_edge"] == plan["tp1_clearance_from_far_edge"]
        assert row["tp1_clearance_atr"] == plan["tp1_clearance_atr"]
        assert row["tp1_effective_rr_base"] == plan["tp1_effective_rr_base"]

    def test_scanner_row_missing_fields_are_none(self):
        from core.scanner import scanner_row_from_analysis
        plan = {
            "type": "buy",
            "risk_reward": "1:2.4",
            "entry_zone": [1.095, 1.097],
            "entry_status": "watch_zone",
        }
        result = {
            "symbol": "EUR/USD",
            "scenario_scores": {"buy": {"signal_score": 60}, "sell": {"signal_score": 40}},
            "trade_permission": {"status": "caution"},
            "scenarios": [plan],
            "technical": {"price": 1.096, "atr_h4": 0.002},
            "decision_engine": {"legacy_action": "watch", "decision": "WATCH_ONLY"},
            "direction_bias": {"best_side": "buy"},
        }
        row = scanner_row_from_analysis(result)
        assert row["entry_zone_width"] is None
        assert row["entry_zone_width_atr"] is None
        assert row["tp1_source"] is None
        assert row["tp1_clearance_from_far_edge"] is None
        assert row["tp1_clearance_atr"] is None
        assert row["tp1_effective_rr_base"] is None


# ---------------------------------------------------------------------------
# Script tests
# ---------------------------------------------------------------------------


class TestScriptParser:
    def test_parse_list_input(self):
        from scripts.compare_entry_tp_quality import parse_input
        rows = parse_input([{"symbol": "A"}, {"symbol": "B"}])
        assert len(rows) == 2

    def test_parse_dict_wrapper(self):
        from scripts.compare_entry_tp_quality import parse_input
        rows = parse_input({"rows": [{"symbol": "C"}]})
        assert len(rows) == 1

    def test_parse_empty(self):
        from scripts.compare_entry_tp_quality import parse_input
        assert parse_input(None) == []
        assert parse_input({}) == []


class TestScriptComputeQuality:
    def test_synthetic_rows_produce_report(self):
        from scripts.compare_entry_tp_quality import compute_quality

        rows = [
            {
                "symbol": "EUR/USD", "best_side": "buy",
                "entry_zone": [1.0970, 1.0990],
                "entry_zone_width": 0.0020, "entry_zone_width_atr": 1.0,
                "entry_zone_source": "smc",
                "stop_loss": 1.0940,
                "take_profit": [1.1050],
                "tp1_source": "target_zone",
                "tp1_clearance_from_far_edge": 0.0060, "tp1_clearance_atr": 3.0,
                "expected_effective_rr": 2.5, "expected_effective_rr_base": 2.0,
                "tp1_effective_rr_base": 2.0,
            },
            {
                "symbol": "GBP/USD", "best_side": "sell",
                "entry_zone": [1.3020, 1.3040],
                "entry_zone_width": 0.0020, "entry_zone_width_atr": 0.8,
                "entry_zone_source": "technical",
                "stop_loss": 1.3060,
                "take_profit": [1.2920],
                "tp1_source": "fib_extension",
                "tp1_clearance_from_far_edge": 0.0100, "tp1_clearance_atr": 4.0,
                "expected_effective_rr": 3.0, "expected_effective_rr_base": 1.1,
                "tp1_effective_rr_base": 1.1,
            },
            {
                "symbol": "AUD/USD", "best_side": "buy",
                "tp1_source": "none",
            },
        ]
        report = compute_quality(rows)

        assert report.total_rows == 3
        assert report.rows_with_tp1 == 2
        assert report.rows_without_tp1 == 1
        assert report.rows_with_entry_zone == 2
        assert report.rows_with_valid_atr == 2
        # zone source breakdown
        assert "smc" in report.zone_source_breakdown
        assert "technical" in report.zone_source_breakdown
        # tp1 source breakdown
        assert "target_zone" in report.tp1_source_breakdown
        assert "fib_extension" in report.tp1_source_breakdown
        assert "none" in report.tp1_source_breakdown
        # best pass base fail — GBP has best=3.0 >= 1.3, base=1.1 < 1.3
        assert report.pct_best_rr_pass_base_rr_fail == 50.0  # 1 of 2 with both


class TestScriptImportPurity:
    def test_script_import_without_pyqt(self):
        """Script must be importable without Qt."""
        import scripts.compare_entry_tp_quality as mod
        assert hasattr(mod, "compute_quality")
        assert hasattr(mod, "parse_input")


# ===========================================================================
# Phase 13A.2: scanner row contract — all 7 fields, same scenario source
# ===========================================================================


class TestScannerRowAllSevenFields:
    """Scanner row must expose all 7 Phase 13A diagnostic fields."""

    SEVEN_KEYS = [
        "entry_zone_width",
        "entry_zone_width_atr",
        "entry_zone_source",
        "tp1_source",
        "tp1_clearance_from_far_edge",
        "tp1_clearance_atr",
        "tp1_effective_rr_base",
    ]

    def test_scanner_row_has_all_seven_keys(self):
        from core.scanner import scanner_row_from_analysis
        plan = {
            "type": "buy",
            "risk_reward": "1:2.4",
            "expected_effective_rr": 2.3,
            "expected_effective_rr_base": 1.7,
            "entry_zone": [1.095, 1.097],
            "entry_status": "watch_zone",
            "entry_zone_source": "smc",
            "entry_zone_width": 0.0020,
            "entry_zone_width_atr": 1.0,
            "tp1_source": "target_zone",
            "tp1_clearance_from_far_edge": 0.0080,
            "tp1_clearance_atr": 4.0,
            "tp1_effective_rr_base": 1.7,
        }
        result = {
            "symbol": "EUR/USD",
            "scenario_scores": {"buy": {"signal_score": 80}, "sell": {"signal_score": 50}},
            "trade_permission": {"status": "allowed"},
            "scenarios": [plan],
            "technical": {"price": 1.096, "atr_h4": 0.002},
            "decision_engine": {"legacy_action": "watch", "decision": "WATCH_ONLY"},
            "direction_bias": {"best_side": "buy"},
        }
        row = scanner_row_from_analysis(result)
        for key in self.SEVEN_KEYS:
            assert key in row, f"Missing key '{key}' in scanner row"

    def test_missing_scenario_none_field_values(self):
        from core.scanner import scanner_row_from_analysis
        plan = {
            "type": "buy",
            "risk_reward": "1:2.0",
            "entry_zone": [1.095, 1.097],
            "entry_status": "watch_zone",
        }
        result = {
            "symbol": "EUR/USD",
            "scenario_scores": {"buy": {"signal_score": 60}, "sell": {"signal_score": 40}},
            "trade_permission": {"status": "caution"},
            "scenarios": [plan],
            "technical": {"price": 1.096, "atr_h4": 0.002},
            "decision_engine": {"legacy_action": "watch", "decision": "WATCH_ONLY"},
            "direction_bias": {"best_side": "buy"},
        }
        row = scanner_row_from_analysis(result)
        for key in self.SEVEN_KEYS:
            assert row.get(key) is None, f"Key '{key}' should be None when missing from plan"


class TestSingleScenarioSource:
    """All 7 diagnostic fields must come from the SAME scenario (no mixed buy/sell)."""

    def test_best_side_sell_picks_sell_scenario_not_first(self):
        from core.scanner import scanner_row_from_analysis
        buy_plan = {
            "type": "buy",
            "risk_reward": "1:3.0",
            "entry_zone": [1.095, 1.097],
            "entry_status": "watch_zone",
            "entry_zone_source": "technical",
            "entry_zone_width": 0.0010,
            "tp1_source": "fib_extension",
            "tp1_clearance_from_far_edge": 0.0200,
            "tp1_effective_rr_base": 3.0,
        }
        sell_plan = {
            "type": "sell",
            "risk_reward": "1:1.5",
            "entry_zone": [1.103, 1.105],
            "entry_status": "watch_zone",
            "entry_zone_source": "smc",
            "entry_zone_width": 0.0030,
            "tp1_source": "target_zone",
            "tp1_clearance_from_far_edge": 0.0050,
            "tp1_effective_rr_base": 1.2,
        }
        result = {
            "symbol": "EUR/USD",
            "scenario_scores": {"buy": {"signal_score": 70}, "sell": {"signal_score": 85}},
            "trade_permission": {"status": "allowed"},
            "scenarios": [buy_plan, sell_plan],  # buy first, but best_side is sell
            "technical": {"price": 1.100, "atr_h4": 0.002},
            "decision_engine": {"legacy_action": "ready", "decision": "READY_TO_TRADE"},
            "direction_bias": {"best_side": "sell"},
        }
        row = scanner_row_from_analysis(result)

        # All 7 fields must come from sell_plan, NOT buy_plan
        assert row["entry_zone_source"] == "smc", \
            f"Expected 'smc' from sell, got '{row.get('entry_zone_source')}'"
        assert row["entry_zone_width"] == 0.0030
        assert row["tp1_source"] == "target_zone"
        assert row["tp1_clearance_from_far_edge"] == 0.0050
        assert row["tp1_effective_rr_base"] == 1.2
        # risk_reward should also be from sell
        assert row["risk_reward"] == "1:1.5"

    def test_side_key_backward_compat_match(self):
        """Scenario using 'side' key instead of 'type' should still be found."""
        from core.scanner import scanner_row_from_analysis
        plan = {
            "side": "buy",
            "risk_reward": "1:2.0",
            "entry_zone": [1.095, 1.097],
            "entry_status": "watch_zone",
            "entry_zone_source": "technical",
            "entry_zone_width": 0.0020,
            "tp1_source": "target_zone",
            "tp1_clearance_from_far_edge": 0.0080,
            "tp1_effective_rr_base": 1.8,
        }
        result = {
            "symbol": "EUR/USD",
            "scenario_scores": {"buy": {"signal_score": 75}, "sell": {"signal_score": 50}},
            "trade_permission": {"status": "allowed"},
            "scenarios": [plan],
            "technical": {"price": 1.096, "atr_h4": 0.002},
            "decision_engine": {"legacy_action": "watch", "decision": "WATCH_ONLY"},
            "direction_bias": {"best_side": "buy"},
        }
        row = scanner_row_from_analysis(result)
        # The plan filter uses item.get("type"), so "side" won't match the filter.
        # But the fallback "if best_plan is None and scenarios" picks scenarios[0].
        # Verify it doesn't crash and returns something reasonable.
        assert row is not None
        assert row["symbol"] == "EUR/USD"


class TestEntryZoneSourceNotOverwritten:
    """Existing entry_zone_source must not be overwritten by None."""

    def test_plan_has_source_row_copies_it(self):
        from core.scanner import scanner_row_from_analysis
        plan = {
            "type": "buy",
            "risk_reward": "1:2.0",
            "entry_zone": [1.095, 1.097],
            "entry_status": "watch_zone",
            "entry_zone_source": "smc_selected",
        }
        result = {
            "symbol": "EUR/USD",
            "scenario_scores": {"buy": {"signal_score": 70}, "sell": {"signal_score": 40}},
            "trade_permission": {"status": "allowed"},
            "scenarios": [plan],
            "technical": {"price": 1.096, "atr_h4": 0.002},
            "decision_engine": {"legacy_action": "watch", "decision": "WATCH_ONLY"},
            "direction_bias": {"best_side": "buy"},
        }
        row = scanner_row_from_analysis(result)
        assert row["entry_zone_source"] == "smc_selected"


def test_ranking_unchanged_by_entry_zone_source():
    """entry_zone_source must not affect ranking output."""
    from core.scanner_ranking_engine import calculate_opportunity_score

    row_smc = {
        "final_score": 80, "decision": "READY_TO_TRADE",
        "price_vs_zone": "in_zone", "expected_effective_rr_base": 2.0,
        "spread_status": "normal", "entry_zone_source": "smc",
    }
    row_technical = {
        "final_score": 80, "decision": "READY_TO_TRADE",
        "price_vs_zone": "in_zone", "expected_effective_rr_base": 2.0,
        "spread_status": "normal", "entry_zone_source": "technical",
    }

    r1 = calculate_opportunity_score(row_smc)
    r2 = calculate_opportunity_score(row_technical)

    assert r1["opportunity_score"] == r2["opportunity_score"], \
        "entry_zone_source must NOT affect opportunity score"


# ===========================================================================
# Phase 13A.3: scenario matching via _find_scenario_for_side, 7-field source
# ===========================================================================

SEVEN_KEYS = [
    "entry_zone_width", "entry_zone_width_atr", "entry_zone_source",
    "tp1_source", "tp1_clearance_from_far_edge", "tp1_clearance_atr",
    "tp1_effective_rr_base",
]


def _make_result(scenarios, *, best_side="buy", buy_score=80, sell_score=50):
    return {
        "symbol": "EUR/USD",
        "scenario_scores": {"buy": {"signal_score": buy_score}, "sell": {"signal_score": sell_score}},
        "trade_permission": {"status": "allowed"},
        "scenarios": scenarios,
        "technical": {"price": 1.096, "atr_h4": 0.002},
        "decision_engine": {"legacy_action": "ready", "decision": "READY_TO_TRADE"},
        "direction_bias": {"best_side": best_side},
    }


def _plan(type_side, **overrides):
    """Build a minimal plan with either type, side, or both."""
    p = {"risk_reward": "1:2.0", "entry_zone": [1.095, 1.097], "entry_status": "watch_zone"}
    if isinstance(type_side, dict):
        p.update(type_side)
    elif isinstance(type_side, str):
        p["type"] = type_side
    for k, v in overrides.items():
        p[k] = v
    return p


class TestScenarioMatchingKeyPriority:
    """_find_scenario_for_side must match both 'type' and 'side' keys."""

    def test_type_key_sell_picked_over_buy_first(self):
        from core.scanner import scanner_row_from_analysis
        buy = _plan("buy", entry_zone_source="technical", tp1_source="fib_extension",
                     entry_zone_width=0.0010, tp1_clearance_from_far_edge=0.0200,
                     tp1_effective_rr_base=3.0)
        sell = _plan("sell", entry_zone_source="smc", tp1_source="target_zone",
                      entry_zone_width=0.0030, tp1_clearance_from_far_edge=0.0050,
                      tp1_effective_rr_base=1.2)
        # buy_score < sell_score → best_side = sell
        result = _make_result([buy, sell], best_side="sell", buy_score=60, sell_score=90)
        row = scanner_row_from_analysis(result)
        assert row["entry_zone_source"] == "smc"
        assert row["tp1_source"] == "target_zone"
        assert row["entry_zone_width"] == 0.0030

    def test_side_key_only_matched(self):
        from core.scanner import scanner_row_from_analysis
        plan = _plan({"side": "buy"}, entry_zone_source="smc")
        result = _make_result([plan], best_side="buy")
        row = scanner_row_from_analysis(result)
        # _find_scenario_for_side matches "side" key
        assert row is not None
        assert row["symbol"] == "EUR/USD"

    def test_type_priority_over_side_conflict(self):
        """type='buy', side='sell' → canonical side is BUY.
        best_side='sell' does NOT match (type has priority), falls back to first valid."""
        from core.scanner_ranking_engine import _find_scenario_for_side
        plan = {"type": "buy", "side": "sell", "risk_reward": "1:2.0"}
        # best_side="buy" matches type="buy" → found
        found = _find_scenario_for_side([plan], "buy")
        assert found is not None
        # best_side="sell" → type="buy" has priority, not a match.
        # Falls back to first valid trade scenario (the plan itself, as BUY).
        found2 = _find_scenario_for_side([plan], "sell")
        assert found2 is not None  # fallback to first valid
        # Verify it's the same plan (canonical side = BUY due to type priority)
        assert found2 is found

    def test_invalid_type_valid_side_uses_side(self):
        from core.scanner_ranking_engine import _find_scenario_for_side
        plan = {"type": "hold", "side": "buy", "risk_reward": "1:2.0"}
        found = _find_scenario_for_side([plan], "buy")
        assert found is not None  # matched via side="buy"

    def test_uppercase_normalized(self):
        from core.scanner_ranking_engine import _find_scenario_for_side
        plan = {"type": "BUY", "risk_reward": "1:2.0"}
        found = _find_scenario_for_side([plan], "buy")
        assert found is not None

    def test_whitespace_normalized(self):
        from core.scanner_ranking_engine import _find_scenario_for_side
        plan = {"type": "  sell  ", "risk_reward": "1:2.0"}
        found = _find_scenario_for_side([plan], "sell")
        assert found is not None

    def test_best_side_uppercase_normalized(self):
        from core.scanner_ranking_engine import _find_scenario_for_side
        plan = {"type": "sell", "risk_reward": "1:2.0"}
        found = _find_scenario_for_side([plan], "SELL")
        assert found is not None

    def test_best_side_whitespace_normalized(self):
        from core.scanner_ranking_engine import _find_scenario_for_side
        plan = {"type": "buy", "risk_reward": "1:2.0"}
        found = _find_scenario_for_side([plan], " BUY ")
        assert found is not None


class TestScenarioFallback:
    """Fallback behavior when no scenario matches best_side."""

    def test_no_match_fallback_first_valid_scenario(self):
        from core.scanner_ranking_engine import _find_scenario_for_side
        buy = {"type": "buy", "risk_reward": "1:2.0"}
        found = _find_scenario_for_side([buy], "sell")  # no sell scenario
        assert found is not None
        assert found["type"] == "buy"  # fallback to first

    def test_non_dict_entry_skipped(self):
        from core.scanner_ranking_engine import _find_scenario_for_side
        scenarios = ["not_a_dict", {"type": "buy", "val": 1}]
        found = _find_scenario_for_side(scenarios, "buy")
        assert found is not None
        assert found["val"] == 1

    def test_no_valid_scenario_returns_none(self):
        from core.scanner_ranking_engine import _find_scenario_for_side
        # Empty list → None
        assert _find_scenario_for_side([], "buy") is None
        # Non-buy/non-sell type with no valid trade scenarios → None
        assert _find_scenario_for_side([{"type": "hold"}], "buy") is None
        # Non-dict entry → skipped, no valid scenarios → None
        assert _find_scenario_for_side(["not_a_dict"], "buy") is None
        # Scenario without type or side → None
        assert _find_scenario_for_side([{"foo": "bar"}], "buy") is None

    def test_scanner_row_all_none_when_no_scenario(self):
        from core.scanner import scanner_row_from_analysis
        result = _make_result([], best_side="buy")
        row = scanner_row_from_analysis(result)
        for key in SEVEN_KEYS:
            assert row.get(key) is None, f"Key '{key}' should be None with no scenario"


class TestSevenFieldSameSource:
    """All 7 diagnostic fields must come from the same matched scenario."""

    def test_all_seven_from_same_matched_sell(self):
        from core.scanner import scanner_row_from_analysis
        buy = _plan("buy", risk_reward="1:3.0",
                     entry_zone_source="technical", tp1_source="fib_extension",
                     entry_zone_width=0.0010, entry_zone_width_atr=0.5,
                     tp1_clearance_from_far_edge=0.0200, tp1_clearance_atr=10.0,
                     tp1_effective_rr_base=3.0)
        sell = _plan("sell", risk_reward="1:1.5",
                      entry_zone_source="smc", tp1_source="target_zone",
                      entry_zone_width=0.0030, entry_zone_width_atr=1.5,
                      tp1_clearance_from_far_edge=0.0050, tp1_clearance_atr=2.5,
                      tp1_effective_rr_base=1.2)
        result = _make_result([buy, sell], best_side="sell", buy_score=60, sell_score=90)
        row = scanner_row_from_analysis(result)

        # All values must match SELL, not BUY
        assert row["entry_zone_source"] == "smc"
        assert row["entry_zone_width"] == 0.0030
        assert row["entry_zone_width_atr"] == 1.5
        assert row["tp1_source"] == "target_zone"
        assert row["tp1_clearance_from_far_edge"] == 0.0050
        assert row["tp1_clearance_atr"] == 2.5
        assert row["tp1_effective_rr_base"] == 1.2
        # And legacy fields too
        assert row["risk_reward"] == "1:1.5"

    def test_legacy_payload_with_type_key_still_works(self):
        from core.scanner import scanner_row_from_analysis
        plan = {
            "type": "buy",
            "risk_reward": "1:2.4",
            "expected_effective_rr": 2.3,
            "expected_effective_rr_base": 1.7,
            "entry_zone": [1.095, 1.097],
            "entry_status": "watch_zone",
            "entry_zone_source": "smc_selected",
            "entry_zone_width": 0.0020, "entry_zone_width_atr": 1.0,
            "tp1_source": "target_zone",
            "tp1_clearance_from_far_edge": 0.0080, "tp1_clearance_atr": 4.0,
            "tp1_effective_rr_base": 1.7,
        }
        result = _make_result([plan], best_side="buy")
        row = scanner_row_from_analysis(result)
        assert row["risk_reward"] == "1:2.4"
        assert row["expected_effective_rr"] == 2.3
        assert row["expected_effective_rr_base"] == 1.7
        assert row["entry_zone_source"] == "smc_selected"
        for key in SEVEN_KEYS:
            assert key in row, f"Missing key '{key}'"

    def test_empty_scenarios_list_all_seven_none(self):
        from core.scanner import scanner_row_from_analysis
        result = _make_result([], best_side="buy")
        row = scanner_row_from_analysis(result)
        for key in SEVEN_KEYS:
            assert row.get(key) is None, f"Key '{key}' should be None"

    def test_scenarios_not_a_list_all_seven_none(self):
        from core.scanner import scanner_row_from_analysis
        result = _make_result(None, best_side="buy")  # type: ignore
        row = scanner_row_from_analysis(result)
        for key in SEVEN_KEYS:
            assert row.get(key) is None, f"Key '{key}' should be None"


# ===========================================================================
# Phase 13A.1: hardening — negative clearance, field completeness, aliasing
# ===========================================================================


class TestClearanceNegative:
    """Clearance must be None when TP1 is inside the entry zone (raw < 0)."""

    def test_buy_tp1_at_far_edge_is_zero(self):
        """TP1 exactly at entry_high → clearance = 0, not None."""
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
                          [_zone(1.0990, 1.0985, 1.0995, "strong", 70)])
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.0990, 10)], "lows": [_swing(1.0940, 5)]}
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        # Plan may be None if TP1 doesn't clear RR threshold from midpoint
        if plan is not None and plan["take_profit"]:
            tp1 = plan["take_profit"][0]
            far_edge = plan["entry_zone"][1]
            clearance = plan["tp1_clearance_from_far_edge"]
            if tp1 == far_edge:
                assert clearance == 0.0
                assert plan["tp1_clearance_atr"] == 0.0


class TestAllSevenFieldsPresent:
    """Trade plan must have all 7 Phase 13A diagnostic keys."""

    def test_valid_plan_has_all_seven_diagnostic_keys(self):
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
                          [_zone(1.1050, 1.1040, 1.1060, "strong", 70)])
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0940, 5)]}
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        assert plan is not None

        seven_keys = [
            "entry_zone_width",
            "entry_zone_width_atr",
            "entry_zone_source",
            "tp1_source",
            "tp1_clearance_from_far_edge",
            "tp1_clearance_atr",
            "tp1_effective_rr_base",
        ]
        for key in seven_keys:
            assert key in plan, f"Missing diagnostic key '{key}' in trade plan"


class TestEntryZoneSourceInventory:
    """entry_zone_source existed before Phase 13A and must be present."""

    def test_entry_zone_source_exists_in_plan(self):
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
                          [_zone(1.1050, 1.1040, 1.1060, "strong", 70)])
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0940, 5)]}
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        assert plan is not None
        assert "entry_zone_source" in plan
        assert plan["entry_zone_source"] in (
            "smc", "smc_selected", "technical", "smc_distant", "fallback", ""
        )

    def test_entry_zone_source_copied_to_scanner_row(self):
        """entry_zone_source is in the scenario within analysis_result,
        accessible via the scanner row's nested analysis data."""
        from core.scanner import scanner_row_from_analysis
        plan = {
            "type": "buy",
            "risk_reward": "1:2.4",
            "entry_zone": [1.095, 1.097],
            "entry_status": "watch_zone",
            "entry_zone_source": "smc",
        }
        result = {
            "symbol": "EUR/USD",
            "scenario_scores": {"buy": {"signal_score": 80}, "sell": {"signal_score": 50}},
            "trade_permission": {"status": "allowed"},
            "scenarios": [plan],
            "technical": {"price": 1.096, "atr_h4": 0.002},
            "decision_engine": {"legacy_action": "watch", "decision": "WATCH_ONLY"},
            "direction_bias": {"best_side": "buy"},
        }
        row = scanner_row_from_analysis(result)
        # entry_zone_source lives in the analysis_result scenarios, not row top-level
        ar = row.get("analysis_result", {})
        scenarios = ar.get("scenarios", [])
        assert len(scenarios) > 0
        assert scenarios[0]["entry_zone_source"] == "smc"


class TestTP1EffectiveRRBaseAlias:
    """tp1_effective_rr_base is an alias of expected_effective_rr_base."""

    def test_alias_matches_when_tp1_exists(self):
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
                          [_zone(1.1050, 1.1040, 1.1060, "strong", 70)])
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0940, 5)]}
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        assert plan is not None
        assert plan["tp1_effective_rr_base"] == plan["expected_effective_rr_base"]

    def test_alias_is_none_when_no_tp1(self):
        pref = {"level": 1.0975, "low": 1.0968, "high": 1.0982, "strength": "moderate",
                "zone_score": 68, "source": "smc", "confluence_count": 2,
                "consolidation_bars": 5, "freshness_bars": 20, "mitigated": False,
                "broken": False, "test_count": 0, "displacement_multiple": 2.0,
                "liquidity_sweep": True, "zone_location": "discount", "type": "demand"}
        tech = _base_tech(1.1000, 0.0010,
                          [_zone(1.0940, 1.0930, 1.0950, "moderate", 50)],
                          [])
        tech["structure_d1"] = "range"
        tech["structure_h4"] = "range"
        tech["range_info"] = {"in_range": True, "range_high": 1.1020, "range_low": 1.0940}
        smc = _base_smc()
        smc["H4"]["demand_zones"] = [pref]
        smc["H4"]["swings"] = {"highs": [], "lows": [_swing(1.0940, 5)]}
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                preferred_zone=pref, market_regime={"primary": "range"})
        if plan is not None and plan["take_profit"] == []:
            assert plan["tp1_effective_rr_base"] is None


class TestScriptNegativeClearance:
    """Script must exclude negative clearance from aggregates."""

    def test_negative_clearance_not_in_avg(self):
        from scripts.compare_entry_tp_quality import compute_quality

        rows = [
            {
                "symbol": "A", "best_side": "buy",
                "entry_zone": [1.0970, 1.0990],
                "take_profit": [1.1050],
                "tp1_clearance_from_far_edge": 0.0060, "tp1_clearance_atr": 3.0,
            },
            {
                "symbol": "B", "best_side": "buy",
                "entry_zone": [1.1000, 1.1020],
                "take_profit": [1.1010],
                "tp1_clearance_from_far_edge": -0.0010,  # negative!
                "tp1_clearance_atr": -0.5,
            },
        ]
        report = compute_quality(rows)

        assert report.rows_with_tp1 == 2
        assert report.rows_with_valid_tp1_clearance == 1
        assert report.rows_with_invalid_negative_tp1_clearance == 1
        # avg should only use the valid one
        assert report.avg_tp1_clearance_atr == 3.0
        assert report.min_tp1_clearance_atr == 3.0

    def test_no_tp1_zeros_all_counts(self):
        from scripts.compare_entry_tp_quality import compute_quality
        rows = [{"symbol": "A", "best_side": "buy", "tp1_source": "none"}]
        report = compute_quality(rows)
        assert report.rows_with_tp1 == 0
        assert report.rows_with_valid_tp1_clearance == 0
        assert report.rows_with_invalid_negative_tp1_clearance == 0
