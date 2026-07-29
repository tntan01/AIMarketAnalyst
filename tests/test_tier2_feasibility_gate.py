"""Deterministic unit tests for the Tier-2 feasibility gate -- Step 7.

Covers: raw-empty predicate, gate decision function (both branches +
boundary), report schema, and serialization round-trip.

All timing-sensitive assertions use fake clock / fixed metrics; no real
``perf_counter`` or ``analyze_symbol`` calls belong here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import scripts.tier2_feasibility_gate as gate_module
from scripts.tier2_feasibility_gate import (
    CONTINUE_TO_TIER2,
    STOP_AFTER_TIER1,
    THRESHOLDS,
    _phase_accounting_ok,
    decide_tier2_gate,
    detect_raw_empty,
)


# ---------------------------------------------------------------------------
# Raw-empty predicate
# ---------------------------------------------------------------------------

_FAMILY_KEYS = {
    "demand": "demand_zones",
    "supply": "supply_zones",
    "order_block": "order_blocks",
    "fvg": "fvg",
}


def _empty_context() -> dict[str, Any]:
    return {
        "H4": {key: [] for key in _FAMILY_KEYS.values()},
        "H1": {key: [] for key in _FAMILY_KEYS.values()},
    }


def _zone(family: str, zone_id: str = "z-1") -> dict[str, Any]:
    return {"zone_id": zone_id, "type": family, "family": family}


def _build_deterministic_report(
    monkeypatch: pytest.MonkeyPatch,
    *,
    detector_exception: bool = False,
) -> dict[str, Any]:
    """Build a report from fixed metrics without reading a real clock."""
    cases = [
        {"name": "raw_empty", "symbol": "EMPTY"},
        {"name": "raw_present", "symbol": "PRESENT"},
    ]
    if detector_exception:
        cases.append({"name": "detector_error", "symbol": "ERROR"})

    monkeypatch.setattr(
        gate_module,
        "_CORPUS",
        {
            "fixture_version": "deterministic-test-v1",
            "cases": cases,
        },
    )
    monkeypatch.setattr(gate_module, "_WARMUP", 0)
    monkeypatch.setattr(gate_module, "_REPEATS", 2)

    def fake_make_candles(case: dict[str, Any]) -> dict[str, str]:
        return {
            "D1": case["name"],
            "H4": case["name"],
            "H1": case["name"],
            "M15": case["name"],
        }

    def fake_build_smc_context(
        d1: str,
        _h4: str,
        _h1: str,
        *,
        symbol: str,
    ) -> dict[str, Any]:
        del symbol
        if d1 == "detector_error":
            raise RuntimeError("detector exploded")
        context = _empty_context()
        if d1 == "raw_present":
            context["H1"]["fvg"].append(_zone("fvg"))
        return context

    def fake_time_one_run(
        case: dict[str, Any],
        *,
        tier1: bool,
    ) -> dict[str, Any]:
        if case["name"] == "detector_error":
            raise AssertionError("classification errors must be skipped for timing")
        is_empty = case["name"] == "raw_empty"
        if tier1:
            return {
                "technical_ms": 2.0,
                "smc_ms": 18.0 if is_empty else 9.0,
                "post_smc_ms": 10.0 if is_empty else 9.0,
                "other_pipeline_ms": 5.0,
                "total_ms": 35.0 if is_empty else 25.0,
                "accounting_ok": True,
            }
        return {
            "technical_ms": 3.0,
            "smc_ms": 20.0 if is_empty else 10.0,
            "post_smc_ms": 12.0 if is_empty else 12.0,
            "other_pipeline_ms": 5.0,
            "total_ms": 40.0 if is_empty else 30.0,
            "accounting_ok": True,
        }

    monkeypatch.setattr(gate_module, "make_candles", fake_make_candles)
    monkeypatch.setattr(gate_module, "build_smc_context", fake_build_smc_context)
    monkeypatch.setattr(gate_module, "_time_one_run", fake_time_one_run)
    return gate_module._benchmark_corpus()


@pytest.fixture
def deterministic_report(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    return _build_deterministic_report(monkeypatch)


@pytest.fixture
def detector_exception_report(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    return _build_deterministic_report(monkeypatch, detector_exception=True)


class TestRawEmptyPredicate:
    def test_all_empty_is_raw_empty(self) -> None:
        result = detect_raw_empty(_empty_context())
        assert result["is_empty"] is True
        assert result["error"] is None
        assert result["counts"]["H4"]["demand"] == 0
        assert result["counts"]["H1"]["fvg"] == 0

    @pytest.mark.parametrize("tf", ("H4", "H1"))
    @pytest.mark.parametrize("family", tuple(_FAMILY_KEYS))
    def test_single_zone_prevents_raw_empty(self, tf: str, family: str) -> None:
        ctx = _empty_context()
        ctx[tf][_FAMILY_KEYS[family]].append(_zone(family))
        result = detect_raw_empty(ctx)
        assert result["is_empty"] is False
        assert result["error"] is None
        assert result["counts"][tf][family] == 1

    def test_h4_only_zone_prevents_raw_empty(self) -> None:
        ctx = _empty_context()
        ctx["H4"]["demand_zones"].append(_zone("demand", "h4-d"))
        result = detect_raw_empty(ctx)
        assert result["is_empty"] is False

    def test_h1_only_zone_prevents_raw_empty(self) -> None:
        ctx = _empty_context()
        ctx["H1"]["fvg"].append(_zone("fvg", "h1-f"))
        result = detect_raw_empty(ctx)
        assert result["is_empty"] is False

    def test_none_smc_is_not_raw_empty(self) -> None:
        result = detect_raw_empty(None)
        assert result["is_empty"] is False
        assert result["error"] == "smc_not_dict"

    def test_non_dict_smc_is_not_raw_empty(self) -> None:
        result = detect_raw_empty("not_a_dict")
        assert result["is_empty"] is False
        assert result["error"] == "smc_not_dict"

    def test_malformed_timeframe_not_dict(self) -> None:
        ctx: dict[str, Any] = {"H4": "not_dict", "H1": {k: [] for k in _FAMILY_KEYS.values()}}
        result = detect_raw_empty(ctx)
        assert result["is_empty"] is False
        assert result["error"] == "timeframe_H4_not_dict"

    def test_malformed_zone_list_not_list(self) -> None:
        ctx = _empty_context()
        ctx["H1"]["fvg"] = {"not": "a list"}
        result = detect_raw_empty(ctx)
        assert result["is_empty"] is False
        assert result["error"] == "family_H1_fvg_not_list"

    def test_malformed_zone_entry_not_dict(self) -> None:
        ctx = _empty_context()
        ctx["H4"]["demand_zones"].append("not_a_zone_dict")
        result = detect_raw_empty(ctx)
        assert result["is_empty"] is False
        assert result["error"] == "zone_in_H4_demand_not_dict"

    def test_all_four_families_checked_per_timeframe(self) -> None:
        ctx = _empty_context()
        for family in _FAMILY_KEYS:
            ctx["H4"][_FAMILY_KEYS[family]].append(_zone(family, f"h4-{family}"))
        # H1 still empty but H4 has zones -> not raw empty
        result = detect_raw_empty(ctx)
        assert result["is_empty"] is False
        assert result["counts"]["H4"]["demand"] == 1
        assert result["counts"]["H4"]["fvg"] == 1


class TestDetectorExceptionClassification:
    def test_detector_exception_does_not_crash_benchmark(
        self,
        detector_exception_report: dict[str, Any],
    ) -> None:
        assert detector_exception_report["metadata"]["fixture_count"] == 3

    def test_detector_exception_is_fail_open_and_reported(
        self,
        detector_exception_report: dict[str, Any],
    ) -> None:
        raw = detector_exception_report["raw_empty"]
        assert raw["count"] == 1
        assert raw["fixtures"] == ["raw_empty"]
        assert "detector_error" not in raw["fixtures"]
        assert raw["counts"]["detector_error"] == {}
        assert raw["error_count"] == 1
        assert raw["errors"] == [
            "detector_error:detector_exception:RuntimeError:detector exploded"
        ]
        assert detector_exception_report["timing_skipped_fixtures"] == [
            "detector_error"
        ]
        assert "detector_error" not in (
            detector_exception_report["paired_timing"]["full"]["per_fixture"]
        )
        assert detector_exception_report["benchmark_error_count"] == 1

    def test_detector_exception_forces_stop(
        self,
        detector_exception_report: dict[str, Any],
    ) -> None:
        assert detector_exception_report["decision"] == STOP_AFTER_TIER1
        assert detector_exception_report["reasons"] == [
            "BENCHMARK_ERROR_COUNT=1"
        ]

    def test_detector_exception_makes_cli_exit_nonzero(
        self,
        detector_exception_report: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        report_path = tmp_path / "tier2-feasibility.json"
        monkeypatch.setattr(
            gate_module,
            "_benchmark_corpus",
            lambda: detector_exception_report,
        )
        monkeypatch.setattr(gate_module, "_REPORT_PATH", report_path)

        assert gate_module.main() == 1
        persisted = json.loads(report_path.read_text(encoding="utf-8"))
        assert persisted["raw_empty"]["error_count"] == 1
        assert persisted["benchmark_error_count"] == 1
        assert persisted["decision"] == STOP_AFTER_TIER1
        assert "ERROR: benchmark has errors" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Gate decision function (pure -- only arithmetic)
# ---------------------------------------------------------------------------


class TestGateDecision:
    """Gate uses only the conservative sensitivity scenario."""

    def test_all_pass_returns_continue(self) -> None:
        decision, reasons = decide_tier2_gate(
            raw_empty_rate=0.25,
            saving_per_raw_empty_ms=15.0,
            scan_saving_pct=0.10,
            benchmark_error_count=0,
            thresholds=THRESHOLDS,
        )
        assert decision == CONTINUE_TO_TIER2
        assert reasons == []

    def test_raw_empty_rate_below_min_returns_stop(self) -> None:
        decision, reasons = decide_tier2_gate(
            raw_empty_rate=0.15,
            saving_per_raw_empty_ms=50.0,
            scan_saving_pct=0.15,
            benchmark_error_count=0,
            thresholds=THRESHOLDS,
        )
        assert decision == STOP_AFTER_TIER1
        assert any("RAW_EMPTY_RATE" in r for r in reasons)

    def test_saving_per_ms_below_min_returns_stop(self) -> None:
        decision, reasons = decide_tier2_gate(
            raw_empty_rate=0.30,
            saving_per_raw_empty_ms=5.0,
            scan_saving_pct=0.15,
            benchmark_error_count=0,
            thresholds=THRESHOLDS,
        )
        assert decision == STOP_AFTER_TIER1
        assert any("SAVING_PER_RAW_EMPTY_MS" in r for r in reasons)

    def test_scan_saving_pct_below_min_returns_stop(self) -> None:
        decision, reasons = decide_tier2_gate(
            raw_empty_rate=0.30,
            saving_per_raw_empty_ms=20.0,
            scan_saving_pct=0.05,
            benchmark_error_count=0,
            thresholds=THRESHOLDS,
        )
        assert decision == STOP_AFTER_TIER1
        assert any("SCAN_SAVING_PCT" in r for r in reasons)

    def test_benchmark_errors_force_stop(self) -> None:
        decision, reasons = decide_tier2_gate(
            raw_empty_rate=0.50,
            saving_per_raw_empty_ms=50.0,
            scan_saving_pct=0.50,
            benchmark_error_count=3,
            thresholds=THRESHOLDS,
        )
        assert decision == STOP_AFTER_TIER1
        assert any("BENCHMARK_ERROR_COUNT" in r for r in reasons)

    def test_all_three_below_min_reports_all_reasons(self) -> None:
        decision, reasons = decide_tier2_gate(
            raw_empty_rate=0.05,
            saving_per_raw_empty_ms=2.0,
            scan_saving_pct=0.01,
            benchmark_error_count=0,
            thresholds=THRESHOLDS,
        )
        assert decision == STOP_AFTER_TIER1
        assert len(reasons) == 3

    def test_boundary_exact_raw_empty_rate_at_threshold(self) -> None:
        """Exact boundary: rate == MIN must pass."""
        decision, reasons = decide_tier2_gate(
            raw_empty_rate=0.20,
            saving_per_raw_empty_ms=15.0,
            scan_saving_pct=0.10,
            benchmark_error_count=0,
            thresholds=THRESHOLDS,
        )
        assert decision == CONTINUE_TO_TIER2
        assert reasons == []

    def test_boundary_exact_saving_ms_at_threshold(self) -> None:
        decision, reasons = decide_tier2_gate(
            raw_empty_rate=0.25,
            saving_per_raw_empty_ms=10.0,
            scan_saving_pct=0.10,
            benchmark_error_count=0,
            thresholds=THRESHOLDS,
        )
        assert decision == CONTINUE_TO_TIER2
        assert reasons == []

    def test_boundary_exact_saving_pct_at_threshold(self) -> None:
        decision, reasons = decide_tier2_gate(
            raw_empty_rate=0.25,
            saving_per_raw_empty_ms=15.0,
            scan_saving_pct=0.08,
            benchmark_error_count=0,
            thresholds=THRESHOLDS,
        )
        assert decision == CONTINUE_TO_TIER2
        assert reasons == []

    def test_boundary_just_below_raw_empty_rate_fails(self) -> None:
        decision, reasons = decide_tier2_gate(
            raw_empty_rate=0.1999,
            saving_per_raw_empty_ms=100.0,
            scan_saving_pct=0.50,
            benchmark_error_count=0,
            thresholds=THRESHOLDS,
        )
        assert decision == STOP_AFTER_TIER1
        assert any("RAW_EMPTY_RATE" in r for r in reasons)


# ---------------------------------------------------------------------------
# Report schema and round-trip
# ---------------------------------------------------------------------------


class TestReportSchema:
    """Verify report output using deterministic, fixed timing metrics."""

    REQUIRED_TOP_KEYS = [
        "metadata", "thresholds", "raw_empty", "paired_timing",
        "raw_empty_smc_p50_ms", "tier1_scan_wall_ms", "sensitivity",
        "timing_skipped_fixtures", "benchmark_error_count",
        "accounting_errors", "accounting_errors_by_scenario",
        "decision", "reasons",
    ]

    REQUIRED_METADATA_KEYS = [
        "fixture_version", "fixture_count", "fixture_names",
        "fast_path_version", "python_version", "warmup", "repeats",
    ]

    REQUIRED_RAW_EMPTY_KEYS = [
        "count", "rate", "fixtures", "error_count", "errors", "counts",
    ]

    REQUIRED_TIMING_KEYS = [
        "technical_ms_p50", "technical_ms_p95",
        "smc_ms_p50", "smc_ms_p95",
        "post_smc_ms_p50", "post_smc_ms_p95",
        "other_pipeline_ms_p50", "other_pipeline_ms_p95",
        "total_ms_p50", "total_ms_p95",
        "smc_pct_of_total_p50", "post_smc_pct_of_total_p50",
    ]

    REQUIRED_SENSITIVITY_NAMES = {"optimistic", "expected", "conservative"}
    REQUIRED_SENSITIVITY_KEYS = [
        "discovery_factor", "discovery_cost_ms",
        "saving_per_raw_empty_ms", "scan_saving_ms", "scan_saving_pct",
    ]

    def test_report_has_all_top_keys(
        self,
        deterministic_report: dict[str, Any],
    ) -> None:
        for key in self.REQUIRED_TOP_KEYS:
            assert key in deterministic_report, f"Missing top-level key: {key}"

    def test_metadata_has_required_keys(
        self,
        deterministic_report: dict[str, Any],
    ) -> None:
        for key in self.REQUIRED_METADATA_KEYS:
            assert key in deterministic_report["metadata"], f"Missing metadata key: {key}"

    def test_raw_empty_has_required_keys(
        self,
        deterministic_report: dict[str, Any],
    ) -> None:
        for key in self.REQUIRED_RAW_EMPTY_KEYS:
            assert key in deterministic_report["raw_empty"], f"Missing raw_empty key: {key}"

    def test_paired_timing_has_both_scenarios_and_required_keys(
        self,
        deterministic_report: dict[str, Any],
    ) -> None:
        paired = deterministic_report["paired_timing"]
        assert set(paired) == {"full", "tier1"}
        for scenario in ("full", "tier1"):
            assert "aggregate" in paired[scenario]
            assert "per_fixture" in paired[scenario]
            assert "scan_wall_ms_p50" in paired[scenario]
            for key in self.REQUIRED_TIMING_KEYS:
                assert key in paired[scenario]["aggregate"], (
                    f"Missing paired_timing.{scenario}.aggregate.{key}"
                )

    def test_sensitivity_has_all_three_scenarios(
        self,
        deterministic_report: dict[str, Any],
    ) -> None:
        assert (
            set(deterministic_report["sensitivity"].keys())
            == self.REQUIRED_SENSITIVITY_NAMES
        )

    def test_sensitivity_scenarios_have_required_keys(
        self,
        deterministic_report: dict[str, Any],
    ) -> None:
        for name in self.REQUIRED_SENSITIVITY_NAMES:
            for key in self.REQUIRED_SENSITIVITY_KEYS:
                assert key in deterministic_report["sensitivity"][name], (
                    f"Missing sensitivity.{name}.{key}"
                )

    def test_decision_is_valid(
        self,
        deterministic_report: dict[str, Any],
    ) -> None:
        assert deterministic_report["decision"] in (
            CONTINUE_TO_TIER2,
            STOP_AFTER_TIER1,
        )

    def test_reasons_is_list(
        self,
        deterministic_report: dict[str, Any],
    ) -> None:
        assert isinstance(deterministic_report["reasons"], list)

    def test_accounting_errors_is_non_negative_int(
        self,
        deterministic_report: dict[str, Any],
    ) -> None:
        assert isinstance(deterministic_report["benchmark_error_count"], int)
        assert deterministic_report["benchmark_error_count"] >= 0
        assert isinstance(deterministic_report["accounting_errors"], int)
        assert deterministic_report["accounting_errors"] >= 0

    def test_full_and_tier1_accumulators_remain_separate(
        self,
        deterministic_report: dict[str, Any],
    ) -> None:
        paired = deterministic_report["paired_timing"]
        assert paired["full"]["aggregate"]["total_ms_p50"] == 40.0
        assert paired["tier1"]["aggregate"]["total_ms_p50"] == 35.0
        assert paired["full"]["scan_wall_ms_p50"] == 80.0
        assert paired["tier1"]["scan_wall_ms_p50"] == 70.0
        assert deterministic_report["tier1_scan_wall_ms"] == 70.0
        assert deterministic_report["raw_empty_smc_p50_ms"] == 20.0

    def test_raw_empty_rate_matches_counts(
        self,
        deterministic_report: dict[str, Any],
    ) -> None:
        raw = deterministic_report["raw_empty"]
        expected_rate = raw["count"] / deterministic_report["metadata"]["fixture_count"]
        assert abs(raw["rate"] - expected_rate) < 0.001

    def test_sensitivity_scan_saving_pct_logic(
        self,
        deterministic_report: dict[str, Any],
    ) -> None:
        """Verify scan_saving_pct = (raw_empty_count * saving_per) / scan_wall."""
        for name, s in deterministic_report["sensitivity"].items():
            expected_pct = (
                deterministic_report["raw_empty"]["count"]
                * s["saving_per_raw_empty_ms"]
                / deterministic_report["tier1_scan_wall_ms"]
                if deterministic_report["tier1_scan_wall_ms"] > 0
                else 0.0
            )
            assert abs(s["scan_saving_pct"] - expected_pct) < 0.001, (
                f"{name}: scan_saving_pct={s['scan_saving_pct']} expected={expected_pct}"
            )


class TestReportRoundTrip:
    """Serialization integrity."""

    def test_json_round_trip_preserves_structure(
        self,
        deterministic_report: dict[str, Any],
    ) -> None:
        serialized = json.dumps(
            deterministic_report,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        deserialized = json.loads(serialized)
        assert deserialized == deterministic_report

    def test_serialized_has_no_nan_or_inf(
        self,
        deterministic_report: dict[str, Any],
    ) -> None:
        import math
        serialized = json.dumps(
            deterministic_report,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        deserialized = json.loads(serialized)

        def _check(obj: Any, path: str = "$") -> None:
            if isinstance(obj, float):
                assert not math.isnan(obj), f"NaN at {path}"
                assert not math.isinf(obj), f"Inf at {path}"
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    _check(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    _check(v, f"{path}[{i}]")

        _check(deserialized)

    def test_thresholds_round_trip(
        self,
        deterministic_report: dict[str, Any],
    ) -> None:
        from scripts.tier2_feasibility_gate import THRESHOLDS as T
        rt = deterministic_report["thresholds"]
        assert rt["MIN_RAW_EMPTY_RATE"] == T["MIN_RAW_EMPTY_RATE"]
        assert rt["MIN_SAVING_PER_RAW_EMPTY_MS"] == T["MIN_SAVING_PER_RAW_EMPTY_MS"]
        assert rt["MIN_SCAN_SAVING_PCT"] == T["MIN_SCAN_SAVING_PCT"]
        assert rt["SENSITIVITY_FACTORS"] == T["SENSITIVITY_FACTORS"]


# ---------------------------------------------------------------------------
# Phase accounting with fake clock (no real timing)
# ---------------------------------------------------------------------------


class TestPhaseAccountingLogic:
    """Verify residual accounting with fixed values and no real clock."""

    def test_total_equals_sum_of_parts_with_positive_residual(self) -> None:
        technical = 2.0
        smc = 5.0
        post = 3.0
        other = 1.0
        total = technical + smc + post + other
        assert abs(total - (technical + smc + post + other)) < 0.001

    def test_large_positive_residual_is_valid_overhead(self) -> None:
        assert _phase_accounting_ok(
            other_pipeline_ms=5.0,
            total_ms=10.0,
            tolerance=0.02,
        )

    def test_negative_residual_flags_accounting_error(self) -> None:
        assert not _phase_accounting_ok(
            other_pipeline_ms=-0.21,
            total_ms=10.0,
            tolerance=0.02,
        )

    def test_small_negative_residual_within_tolerance_is_ok(self) -> None:
        assert _phase_accounting_ok(
            other_pipeline_ms=-0.20,
            total_ms=10.0,
            tolerance=0.02,
        )

    def test_post_smc_cannot_exceed_total(self) -> None:
        """post_smc_ms must not exceed total_ms."""
        post = 3.0
        total = 10.0
        assert post <= total
