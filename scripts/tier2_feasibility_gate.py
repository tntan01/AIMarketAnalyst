"""Feasibility gate for Scanner Tier-2 (pre-SMC prefilter) -- Step 7.

Instruments the real AnalysisPipeline to measure technical / SMC / post-SMC
phase timing independently, then applies codified thresholds to decide
whether a Tier-2 refactor (risk 9/10) is justified.

Run from the repo root::

    python scripts/tier2_feasibility_gate.py

Writes ``reports/scanner_fast_path/tier2-feasibility.json`` atomically.
Exit code 0 = STOP_AFTER_TIER1 or CONTINUE_TO_TIER2 (both valid).
Exit code 1 = benchmark error (instrumentation, accounting, or I/O failure).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Any

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import core.analysis_pipeline as pipeline_module
from core.analysis_engine import analyze_symbol
from core.smc_context import build_smc_context
from tests.scanner_fast_path_fixtures import make_candles, make_request

logging.getLogger("core.smc_context").setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_FIXTURE_DIR = _REPO / "tests" / "fixtures" / "scanner_fast_path"
_CORPUS = json.loads((_FIXTURE_DIR / "corpus.json").read_text(encoding="utf-8"))
_REPORT_PATH = _REPO / "reports" / "scanner_fast_path" / "tier2-feasibility.json"

# ---------------------------------------------------------------------------
# Benchmark config
# ---------------------------------------------------------------------------

_WARMUP = 5
_REPEATS = 50
_SCENARIO_ORDER_ALTERNATE = True  # alternate full/tier1 per round
_SCENARIOS = ("full", "tier1")
_TIMING_KEYS = (
    "technical_ms",
    "smc_ms",
    "post_smc_ms",
    "other_pipeline_ms",
    "total_ms",
)

# ---------------------------------------------------------------------------
# Codified thresholds (section 5.3 + Step 7 item 7)
# ---------------------------------------------------------------------------

THRESHOLDS = {
    "MIN_RAW_EMPTY_RATE": 0.20,
    "MIN_SAVING_PER_RAW_EMPTY_MS": 10.0,
    "MIN_SCAN_SAVING_PCT": 0.08,
    "SENSITIVITY_FACTORS": {
        "optimistic": 0.20,
        "expected": 0.35,
        "conservative": 0.50,
    },
    # Phase-accounting tolerance: residual must be within this percentage of
    # total_ms.  Negative residuals larger than this are flagged as errors.
    "PHASE_ACCOUNTING_TOLERANCE": 0.02,
}

# ---------------------------------------------------------------------------
# Raw-empty predicate (pure, no side effects)
# ---------------------------------------------------------------------------

_FAMILY_KEYS = {
    "demand": "demand_zones",
    "supply": "supply_zones",
    "order_block": "order_blocks",
    "fvg": "fvg",
}
_TIMEFRAMES = ("H4", "H1")


def detect_raw_empty(smc: dict[str, Any] | None) -> dict[str, Any]:
    """Return {is_empty, counts, error} -- pure predicate, never raises."""
    error = None
    if not isinstance(smc, dict):
        return {"is_empty": False, "counts": {}, "error": "smc_not_dict"}
    counts: dict[str, dict[str, int]] = {}
    for tf in _TIMEFRAMES:
        tf_data = smc.get(tf)
        if not isinstance(tf_data, dict):
            error = f"timeframe_{tf}_not_dict"
            counts[tf] = {f: 0 for f in _FAMILY_KEYS}
            continue
        tf_counts: dict[str, int] = {}
        for family, key in _FAMILY_KEYS.items():
            zones = tf_data.get(key, [])
            if not isinstance(zones, list):
                error = f"family_{tf}_{family}_not_list"
                tf_counts[family] = 0
                continue
            # Each zone must be a dict
            for z in zones:
                if not isinstance(z, dict):
                    error = f"zone_in_{tf}_{family}_not_dict"
            tf_counts[family] = len(zones)
        counts[tf] = tf_counts
    is_empty = (
        error is None
        and all(counts[tf][f] == 0 for tf in _TIMEFRAMES for f in _FAMILY_KEYS)
    )
    return {"is_empty": is_empty, "counts": counts, "error": error}


# ---------------------------------------------------------------------------
# Gate decision (pure function -- no clock, no file I/O)
# ---------------------------------------------------------------------------

CONTINUE_TO_TIER2 = "CONTINUE_TO_TIER2"
STOP_AFTER_TIER1 = "STOP_AFTER_TIER1"


def decide_tier2_gate(
    *,
    raw_empty_rate: float,
    saving_per_raw_empty_ms: float,
    scan_saving_pct: float,
    benchmark_error_count: int,
    thresholds: dict[str, Any],
) -> tuple[str, list[str]]:
    """Return (decision, reasons).  Pure -- only arithmetic and comparisons."""

    reasons: list[str] = []

    if benchmark_error_count > 0:
        reasons.append(f"BENCHMARK_ERROR_COUNT={benchmark_error_count}")
        return STOP_AFTER_TIER1, reasons

    min_rate = float(thresholds["MIN_RAW_EMPTY_RATE"])
    min_saving_ms = float(thresholds["MIN_SAVING_PER_RAW_EMPTY_MS"])
    min_saving_pct = float(thresholds["MIN_SCAN_SAVING_PCT"])

    if raw_empty_rate < min_rate:
        reasons.append(
            f"RAW_EMPTY_RATE={raw_empty_rate:.4f} < MIN={min_rate:.2f}"
        )
    if saving_per_raw_empty_ms < min_saving_ms:
        reasons.append(
            f"SAVING_PER_RAW_EMPTY_MS={saving_per_raw_empty_ms:.2f} < MIN={min_saving_ms:.1f}"
        )
    if scan_saving_pct < min_saving_pct:
        reasons.append(
            f"SCAN_SAVING_PCT={scan_saving_pct:.4f} < MIN={min_saving_pct:.2f}"
        )

    if reasons:
        return STOP_AFTER_TIER1, reasons
    return CONTINUE_TO_TIER2, []


# ---------------------------------------------------------------------------
# Sensitivity analysis (pure)
# ---------------------------------------------------------------------------

def _sensitivity_scenarios(
    *,
    raw_empty_smc_p50_ms: float,
    raw_empty_count: int,
    tier1_scan_wall_ms: float,
    factors: dict[str, float],
) -> dict[str, dict[str, float]]:
    scenarios: dict[str, dict[str, float]] = {}
    for name, factor in factors.items():
        discovery_cost = raw_empty_smc_p50_ms * factor
        saving_per = raw_empty_smc_p50_ms - discovery_cost
        scan_saving = raw_empty_count * saving_per
        scan_pct = scan_saving / tier1_scan_wall_ms if tier1_scan_wall_ms > 0 else 0.0
        scenarios[name] = {
            "discovery_factor": factor,
            "discovery_cost_ms": round(discovery_cost, 4),
            "saving_per_raw_empty_ms": round(saving_per, 4),
            "scan_saving_ms": round(scan_saving, 4),
            "scan_saving_pct": round(scan_pct, 6),
        }
    return scenarios


# ---------------------------------------------------------------------------
# Phase timing instrumentation
# ---------------------------------------------------------------------------

def _phase_accounting_ok(
    *,
    other_pipeline_ms: float,
    total_ms: float,
    tolerance: float,
) -> bool:
    """Only a negative residual beyond tolerance is an accounting error.

    A positive residual is valid pipeline overhead outside the three
    instrumented calls/phases and is intentionally retained as
    ``other_pipeline_ms``.
    """
    return other_pipeline_ms >= -(total_ms * tolerance)


def _time_one_run(case: dict[str, Any], *, tier1: bool) -> dict[str, Any]:
    """Run *one* pipeline call with instrumented technical/SMC wrappers.

    Returns phase timings in milliseconds and the accounting result.
    """

    candles = make_candles(case)

    # ---- Instrument the pipeline module to capture smc_end ----
    _original_technical = pipeline_module.build_technical_snapshot
    _original_smc = pipeline_module.build_smc_context
    _state: dict[str, float] = {}

    def _wrap_technical(*args: Any, **kwargs: Any) -> Any:
        _state["technical_start"] = perf_counter()
        result = _original_technical(*args, **kwargs)
        _state["technical_end"] = perf_counter()
        return result

    def _wrap_smc(*args: Any, **kwargs: Any) -> Any:
        _state["smc_start"] = perf_counter()
        result = _original_smc(*args, **kwargs)
        _state["smc_end"] = perf_counter()
        return result

    pipeline_module.build_technical_snapshot = _wrap_technical
    pipeline_module.build_smc_context = _wrap_smc

    try:
        pipeline_start = perf_counter()
        analyze_symbol(
            make_request(case, _CORPUS["analysis_input"]),
            candles,
            m15_candles=candles["M15"],
            thresholds=_CORPUS["thresholds"],
            scanner_fast_tier1=tier1,
        )
        pipeline_end = perf_counter()
    finally:
        pipeline_module.build_technical_snapshot = _original_technical
        pipeline_module.build_smc_context = _original_smc

    total_ms = (pipeline_end - pipeline_start) * 1_000

    # Extract instrumented timings
    tech_start = _state.get("technical_start", pipeline_start)
    tech_end = _state.get("technical_end", tech_start)
    smc_start = _state.get("smc_start", tech_end)
    smc_end = _state.get("smc_end", smc_start)

    tech_pipeline_ms = (tech_end - tech_start) * 1_000
    smc_pipeline_ms = (smc_end - smc_start) * 1_000
    post_smc_ms = (pipeline_end - smc_end) * 1_000
    other_pipeline_ms = total_ms - tech_pipeline_ms - smc_pipeline_ms - post_smc_ms

    # Validate phase accounting
    tol = THRESHOLDS["PHASE_ACCOUNTING_TOLERANCE"]
    accounting_ok = _phase_accounting_ok(
        other_pipeline_ms=other_pipeline_ms,
        total_ms=total_ms,
        tolerance=tol,
    )

    return {
        "technical_ms": round(tech_pipeline_ms, 4),
        "smc_ms": round(smc_pipeline_ms, 4),
        "post_smc_ms": round(post_smc_ms, 4),
        "other_pipeline_ms": round(other_pipeline_ms, 4),
        "total_ms": round(total_ms, 4),
        "accounting_ok": accounting_ok,
    }


# ---------------------------------------------------------------------------
# Paired benchmark loop
# ---------------------------------------------------------------------------

def _benchmark_corpus() -> dict[str, Any]:
    cases = _CORPUS["cases"]
    fixture_names = [c["name"] for c in cases]

    # ---- Phase 1: raw-empty classification (independent) ----
    raw_empty_names: list[str] = []
    raw_counts_all: dict[str, Any] = {}
    raw_errors: list[str] = []
    timing_skipped_names: list[str] = []
    for case in cases:
        name = str(case["name"])
        candles = make_candles(case)
        try:
            smc = build_smc_context(
                candles["D1"],
                candles["H4"],
                candles["H1"],
                symbol=str(case.get("symbol", "EUR/USD")),
            )
        except Exception as exc:
            error = f"detector_exception:{type(exc).__name__}:{exc}"
            raw_counts_all[name] = {}
            raw_errors.append(f"{name}:{error}")
            timing_skipped_names.append(name)
            continue

        raw = detect_raw_empty(smc)
        raw_counts_all[name] = raw["counts"]
        if raw["error"]:
            raw_errors.append(f"{name}:{raw['error']}")
        if raw["is_empty"] and not raw["error"]:
            raw_empty_names.append(name)

    raw_empty_count = len(raw_empty_names)
    raw_empty_rate = raw_empty_count / len(cases) if cases else 0.0
    timed_cases = [
        case for case in cases
        if str(case["name"]) not in timing_skipped_names
    ]
    timed_fixture_names = [str(case["name"]) for case in timed_cases]

    # ---- Phase 2: timed runs ----
    accum: dict[str, dict[str, dict[str, list[float]]]] = {
        scenario: {
            name: {key: [] for key in _TIMING_KEYS}
            for name in timed_fixture_names
        }
        for scenario in _SCENARIOS
    }
    accounting_errors_by_scenario = {scenario: 0 for scenario in _SCENARIOS}

    # Warm-up
    for rep in range(_WARMUP):
        tier1_first = rep % 2 == 1 if _SCENARIO_ORDER_ALTERNATE else False
        for case in timed_cases:
            order = [False, True] if tier1_first else [True, False]
            for tier1 in order:
                _time_one_run(case, tier1=tier1)

    # Measurement
    for rep in range(_REPEATS):
        tier1_first = rep % 2 == 1 if _SCENARIO_ORDER_ALTERNATE else False
        for case in timed_cases:
            order = [False, True] if tier1_first else [True, False]
            for tier1 in order:
                t = _time_one_run(case, tier1=tier1)
                name = case["name"]
                scenario = "tier1" if tier1 else "full"
                for key in _TIMING_KEYS:
                    accum[scenario][name][key].append(t[key])
                if not t["accounting_ok"]:
                    accounting_errors_by_scenario[scenario] += 1

    # ---- Phase 3: compute percentiles ----
    def _p(arr: list[float], pct: float) -> float:
        if not arr:
            return 0.0
        s = sorted(arr)
        n = len(s)
        idx = max(0, min(n - 1, int(n * pct / 100)))
        return round(s[idx], 4)

    paired_timing: dict[str, dict[str, Any]] = {}
    for scenario in _SCENARIOS:
        scenario_accum = accum[scenario]
        per_fixture: dict[str, dict[str, float]] = {}
        for name in timed_fixture_names:
            times = scenario_accum[name]
            per_fixture[name] = {
                f"{key}_p{pct}": _p(times[key], pct)
                for key in _TIMING_KEYS
                for pct in (50, 95)
            }

        aggregate = {
            f"{key}_p{pct}": _p(
                [value for times in scenario_accum.values() for value in times[key]],
                pct,
            )
            for key in _TIMING_KEYS
            for pct in (50, 95)
        }
        total_p50 = aggregate["total_ms_p50"]
        aggregate["smc_pct_of_total_p50"] = (
            round(aggregate["smc_ms_p50"] / total_p50, 6) if total_p50 else 0
        )
        aggregate["post_smc_pct_of_total_p50"] = (
            round(aggregate["post_smc_ms_p50"] / total_p50, 6)
            if total_p50
            else 0
        )
        paired_timing[scenario] = {
            "aggregate": aggregate,
            "per_fixture": per_fixture,
            "scan_wall_ms_p50": round(total_p50 * len(timed_cases), 4),
        }

    # ---- Phase 4: sensitivity on raw-empty symbols ----
    raw_empty_smc_p50 = 0.0
    if raw_empty_names:
        raw_empty_smc_p50 = _p(
            [
                value
                for name in raw_empty_names
                for value in accum["full"][name]["smc_ms"]
            ],
            50,
        )

    tier1_scan_wall = paired_timing["tier1"]["scan_wall_ms_p50"]

    sensitivity = _sensitivity_scenarios(
        raw_empty_smc_p50_ms=raw_empty_smc_p50,
        raw_empty_count=raw_empty_count,
        tier1_scan_wall_ms=tier1_scan_wall,
        factors=THRESHOLDS["SENSITIVITY_FACTORS"],
    )

    # ---- Phase 5: gate decision (using conservative) ----
    cons = sensitivity["conservative"]
    accounting_errors = sum(accounting_errors_by_scenario.values())
    benchmark_error_count = accounting_errors + len(raw_errors)
    decision, reasons = decide_tier2_gate(
        raw_empty_rate=raw_empty_rate,
        saving_per_raw_empty_ms=cons["saving_per_raw_empty_ms"],
        scan_saving_pct=cons["scan_saving_pct"],
        benchmark_error_count=benchmark_error_count,
        thresholds=THRESHOLDS,
    )

    return {
        "metadata": {
            "fixture_version": _CORPUS["fixture_version"],
            "fixture_count": len(cases),
            "fixture_names": fixture_names,
            "fast_path_version": "scanner-fast-path-v1",
            "prefilter_version": "smc-prefilter-v1",
            "python_version": sys.version,
            "warmup": _WARMUP,
            "repeats": _REPEATS,
            "scenario_order_alternate": _SCENARIO_ORDER_ALTERNATE,
        },
        "thresholds": THRESHOLDS,
        "raw_empty": {
            "count": raw_empty_count,
            "rate": round(raw_empty_rate, 6),
            "fixtures": raw_empty_names,
            "error_count": len(raw_errors),
            "errors": raw_errors,
            "counts": raw_counts_all,
        },
        "paired_timing": paired_timing,
        "raw_empty_smc_p50_ms": round(raw_empty_smc_p50, 4),
        "tier1_scan_wall_ms": round(tier1_scan_wall, 4),
        "timing_skipped_fixtures": timing_skipped_names,
        "sensitivity": sensitivity,
        "benchmark_error_count": benchmark_error_count,
        "accounting_errors": accounting_errors,
        "accounting_errors_by_scenario": accounting_errors_by_scenario,
        "decision": decision,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 72)
    print("Scanner Tier-2 Feasibility Gate -- Step 7")
    print(f"Fixtures: {len(_CORPUS['cases'])}  Warm-up: {_WARMUP}  Repeats: {_REPEATS}")
    print(f"Thresholds: {json.dumps({k: v for k, v in THRESHOLDS.items() if k != 'SENSITIVITY_FACTORS'})}")
    print("=" * 72)

    report = _benchmark_corpus()

    # Print summary
    md = report["metadata"]
    raw = report["raw_empty"]
    sens = report["sensitivity"]

    print(f"\n--- Raw-Empty ---")
    print(f"  count = {raw['count']}/{md['fixture_count']}  rate = {raw['rate']:.2%}")
    print(f"  fixtures: {raw['fixtures']}")
    if raw['errors']:
        print(f"  errors: {raw['errors']}")

    print(f"\n--- Paired Phase Timing ---")
    for scenario in _SCENARIOS:
        tim = report["paired_timing"][scenario]["aggregate"]
        print(f"  [{scenario}]")
        print(f"    technical_ms p50/p95 = {tim['technical_ms_p50']:.2f}/{tim['technical_ms_p95']:.2f}ms")
        print(f"    smc_ms       p50/p95 = {tim['smc_ms_p50']:.2f}/{tim['smc_ms_p95']:.2f}ms")
        print(f"    post_smc_ms  p50/p95 = {tim['post_smc_ms_p50']:.2f}/{tim['post_smc_ms_p95']:.2f}ms")
        print(f"    other_ms     p50/p95 = {tim['other_pipeline_ms_p50']:.2f}/{tim['other_pipeline_ms_p95']:.2f}ms")
        print(f"    total_ms     p50/p95 = {tim['total_ms_p50']:.2f}/{tim['total_ms_p95']:.2f}ms")
        print(f"    scan_wall_ms p50     = {report['paired_timing'][scenario]['scan_wall_ms_p50']:.2f}ms")

    print(f"\n--- Sensitivity Analysis ---")
    for name in ("optimistic", "expected", "conservative"):
        s = sens[name]
        tag = " <-- OFFICIAL" if name == "conservative" else ""
        print(f"  {name:15s}: discovery={s['discovery_factor']:.0%}  "
              f"saving_per={s['saving_per_raw_empty_ms']:.2f}ms  "
              f"scan_saving={s['scan_saving_pct']:.2%}{tag}")

    print(f"\n--- Decision ---")
    print(f"  benchmark_errors  = {report['benchmark_error_count']}")
    print(f"  accounting_errors = {report['accounting_errors']}")
    print(f"  by_scenario       = {report['accounting_errors_by_scenario']}")
    print(f"  decision          = {report['decision']}")
    for r in report["reasons"]:
        print(f"    reason: {r}")

    # Write JSON atomically
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    fd, tmp = tempfile.mkstemp(dir=str(_REPORT_PATH.parent), suffix=".json", text=True)
    try:
        os.write(fd, json_text.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, str(_REPORT_PATH))
    print(f"\nReport written to: {_REPORT_PATH}")

    # Exit code
    if report["benchmark_error_count"] > 0:
        print("ERROR: benchmark has errors -- check report.")
        return 1
    print(f"Decision '{report['decision']}' is valid. Step 7 complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
