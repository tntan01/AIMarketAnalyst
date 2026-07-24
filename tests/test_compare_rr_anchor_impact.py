"""Tests for Phase 4B diagnostic script helpers (scripts/compare_rr_anchor_impact.py).

Covers parse_input, _extract_rr_fields, _find_best_scenario, and compute_impact
across multiple input formats and edge cases.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# Ensure scripts/ is importable
_scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from compare_rr_anchor_impact import (
    _RR_STRONG,
    _RR_WEAK,
    _extract_rr_fields,
    _find_best_scenario,
    _parse_rr_string,
    _resolve_best_side,
    _safe_float,
    compute_impact,
    parse_input,
    report_as_dict,
)


# ---------------------------------------------------------------------------
# _safe_float / _parse_rr_string
# ---------------------------------------------------------------------------


class TestSafeFloat:
    def test_valid_float(self):
        assert _safe_float(1.5) == 1.5
        assert _safe_float("2.3") == 2.3
        assert _safe_float(0) == 0.0

    def test_none_nan_inf(self):
        assert _safe_float(None) is None
        assert _safe_float(float("nan")) is None
        assert _safe_float(float("inf")) is None

    def test_invalid_string(self):
        assert _safe_float("abc") is None
        assert _safe_float("") is None

    def test_dict_list(self):
        assert _safe_float({}) is None
        assert _safe_float([]) is None


class TestParseRRString:
    def test_colon_format(self):
        assert _parse_rr_string("1:2.5") == 2.5
        assert _parse_rr_string("1:1.3") == 1.3

    def test_float_direct(self):
        assert _parse_rr_string(2.5) == 2.5
        assert _parse_rr_string(0.0) == 0.0

    def test_none_invalid(self):
        assert _parse_rr_string(None) is None
        assert _parse_rr_string("abc") is None


# ---------------------------------------------------------------------------
# _resolve_best_side
# ---------------------------------------------------------------------------


class TestResolveBestSide:
    def test_from_direction_bias_dict(self):
        assert _resolve_best_side({"direction_bias": {"best_side": "buy"}}) == "buy"
        assert _resolve_best_side({"direction_bias": {"best_side": "sell"}}) == "sell"

    def test_fallback_to_top_level(self):
        assert _resolve_best_side({"best_side": "sell"}) == "sell"

    def test_neutral_or_missing(self):
        assert _resolve_best_side({"direction_bias": {"best_side": "neutral"}}) == ""
        assert _resolve_best_side({}) == ""


# ---------------------------------------------------------------------------
# _find_best_scenario
# ---------------------------------------------------------------------------


class TestFindBestScenario:
    def test_match_by_type_key(self):
        scenarios = [
            {"type": "buy", "expected_effective_rr": 2.5},
            {"type": "sell", "expected_effective_rr": 1.1},
        ]
        result = _find_best_scenario(scenarios, "sell")
        assert result is not None
        assert result["expected_effective_rr"] == 1.1

    def test_match_by_side_key(self):
        scenarios = [
            {"side": "buy", "expected_effective_rr": 3.0},
            {"side": "sell", "expected_effective_rr": 1.8},
        ]
        result = _find_best_scenario(scenarios, "sell")
        assert result is not None
        assert result["expected_effective_rr"] == 1.8

    def test_fallback_no_match(self):
        scenarios = [{"type": "buy", "value": 10}]
        result = _find_best_scenario(scenarios, "sell")
        assert result is not None  # fallback to first
        assert result["value"] == 10

    def test_empty_side_fallback_first(self):
        scenarios = [
            {"type": "buy", "value": 1},
            {"type": "sell", "value": 2},
        ]
        result = _find_best_scenario(scenarios, "")
        assert result is not None
        assert result["value"] == 1

    def test_empty_list(self):
        assert _find_best_scenario([], "buy") is None

    def test_non_list(self):
        assert _find_best_scenario(None, "buy") is None
        assert _find_best_scenario("abc", "buy") is None

    def test_non_dict_entries_skipped(self):
        scenarios = ["not_a_dict", {"type": "sell", "val": 42}]
        result = _find_best_scenario(scenarios, "sell")
        assert result is not None
        assert result["val"] == 42


# ---------------------------------------------------------------------------
# _extract_rr_fields
# ---------------------------------------------------------------------------


class TestExtractRRFields:
    def test_standard_row_with_all_fields(self):
        row = {
            "symbol": "EUR/USD",
            "direction_bias": {"best_side": "buy"},
            "scanner_group": "ready_now",
            "scanner_action": "ready",
            "best_score": 82,
            "opportunity_score": 103,
            "risk_reward": "1:2.5",
            "expected_effective_rr": 2.3,
            "expected_effective_rr_base": 1.8,
            "expected_effective_rr_worst": 1.2,
            "risk_reward_range": {"best": 2.5, "base": 1.8, "worst": 1.2},
        }
        rr = _extract_rr_fields(row)
        assert rr.symbol == "EUR/USD"
        assert rr.best_side == "buy"
        assert rr.group == "ready_now"
        assert rr.eff_best == 2.3
        assert rr.eff_base == 1.8
        assert rr.eff_worst == 1.2
        assert rr.rr_best == 2.5
        assert rr.rr_base == 1.8
        assert rr.rr_worst == 1.2

    def test_missing_base_still_works(self):
        row = {
            "symbol": "GBP/USD",
            "best_side": "sell",
            "best_score": 60,
            "expected_effective_rr": 1.5,
        }
        rr = _extract_rr_fields(row)
        assert rr.eff_best == 1.5
        assert rr.eff_base is None
        assert rr.rr_best is None

    def test_fallback_to_analysis_result_scenarios(self):
        row = {
            "symbol": "USD/JPY",
            "best_side": "sell",
            "analysis_result": {
                "scenarios": [
                    {"type": "buy", "expected_effective_rr": 3.0, "expected_effective_rr_base": 2.5},
                    {"type": "sell", "expected_effective_rr": 1.2, "expected_effective_rr_base": 0.9},
                ],
            },
        }
        rr = _extract_rr_fields(row)
        assert rr.eff_best == 1.2
        assert rr.eff_base == 0.9

    def test_all_missing_returns_nones(self):
        rr = _extract_rr_fields({"symbol": "X", "best_side": "buy"})
        assert rr.eff_best is None
        assert rr.eff_base is None
        assert rr.rr_best is None


# ---------------------------------------------------------------------------
# parse_input
# ---------------------------------------------------------------------------


class TestParseInput:
    def test_list_input(self):
        rows = parse_input([{"symbol": "A"}, {"symbol": "B"}])
        assert len(rows) == 2
        assert rows[0]["symbol"] == "A"

    def test_dict_rows_wrapper(self):
        rows = parse_input({"rows": [{"symbol": "A"}, {"symbol": "B"}]})
        assert len(rows) == 2

    def test_dict_scanner_rows_wrapper(self):
        rows = parse_input({"scanner_rows": [{"symbol": "C"}]})
        assert len(rows) == 1
        assert rows[0]["symbol"] == "C"

    def test_nested_result_rows(self):
        rows = parse_input({"result": {"rows": [{"symbol": "D"}]}})
        assert len(rows) == 1

    def test_single_row_dict(self):
        rows = parse_input({"symbol": "EUR/USD", "best_side": "buy"})
        assert len(rows) == 1

    def test_empty_input(self):
        assert parse_input(None) == []
        assert parse_input({}) == []
        assert parse_input("not_json") == []

    def test_filters_non_dict_entries(self):
        rows = parse_input([{"symbol": "A"}, None, "string", 42])
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# compute_impact
# ---------------------------------------------------------------------------


class TestComputeImpact:
    def test_empty_rows(self):
        report = compute_impact([], min_rr=1.3)
        assert report.total_rows == 0
        assert report.rows_with_both == 0

    def test_basic_metrics(self):
        rows = [
            {
                "symbol": "EUR/USD", "best_side": "buy",
                "expected_effective_rr": 2.5,
                "expected_effective_rr_base": 2.0,
            },
            {
                "symbol": "GBP/USD", "best_side": "sell",
                "expected_effective_rr": 3.0,
                "expected_effective_rr_base": 1.2,
            },
        ]
        report = compute_impact(rows, min_rr=1.3)
        assert report.total_rows == 2
        assert report.rows_with_both == 2
        assert report.avg_best == 2.75
        assert report.avg_base == 1.6
        assert report.avg_drop == 1.15
        # GBP: best=3.0 >= 1.3, base=1.2 < 1.3 → base_fail_best_pass = 1
        assert report.base_fail_best_pass == 1
        # GBP: best=3.0 >= 2.0, base=1.2 < 2.0 → lost_strong = 1
        assert report.lost_strong_tier == 1
        # EUR: best=2.5 >= 1.3, base=2.0 >= 1.3 → no weak loss
        # GBP: best=3.0 >= 1.3, base=1.2 < 1.3 → lost_weak = 1
        assert report.lost_weak_tier == 1

    def test_missing_base_does_not_count(self):
        rows = [
            {
                "symbol": "A", "best_side": "buy",
                "expected_effective_rr": 2.0,
            },
        ]
        report = compute_impact(rows, min_rr=1.3)
        assert report.rows_with_both == 0
        assert report.base_fail_best_pass == 0

    def test_base_zero_treated_as_none(self):
        rows = [
            {
                "symbol": "A", "best_side": "buy",
                "expected_effective_rr": 2.0,
                "expected_effective_rr_base": 0.0,
            },
        ]
        report = compute_impact(rows, min_rr=1.3)
        # base=0.0 is falsy but _safe_float returns 0.0...
        # Actually 0.0 is a valid float value. Let me check the code...
        # In compute_impact: if rr.eff_base is not None and rr.eff_base > 0
        # So 0.0 would be filtered out by > 0 check. rows_with_both = 0.
        assert report.rows_with_both == 0

    def test_report_as_dict(self):
        rows = [
            {
                "symbol": "A", "best_side": "buy",
                "expected_effective_rr": 2.0,
                "expected_effective_rr_base": 1.5,
            },
        ]
        report = compute_impact(rows, min_rr=1.3)
        d = report_as_dict(report)
        assert d["total_rows"] == 1
        assert d["rows_with_both"] == 1
        assert len(d["rows"]) == 1
        assert d["rows"][0]["drop"] == 0.5

    def test_constants_unchanged(self):
        """Guard: _RR_STRONG and _RR_WEAK must remain at production values."""
        assert _RR_STRONG == 2.0
        assert _RR_WEAK == 1.3
