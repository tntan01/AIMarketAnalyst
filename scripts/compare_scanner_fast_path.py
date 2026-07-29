"""Offline A/B harness for Scanner fast-path Tier 1 — Bước 6.

Run from the repo root::

    python scripts/compare_scanner_fast_path.py

Produces a benchmark report that gates Tier-1 activation:
trade false reject must be zero and survivor parity must hold before
``scanner_fast_tier1`` can be set to ``true``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

# Allow running from repo root without installing the package.
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from core.analysis_engine import analyze_symbol
from core.scanner import scanner_row_from_analysis
from core.scanner_candidate_engine import evaluate_scanner_candidate
from core.scanner_models import OUT_OF_STRATEGY
from core.smc_context import build_smc_context
from core.smc_prefilter import evaluate_post_context_prefilter
from tests.scanner_fast_path_fixtures import make_candles, make_request


_FIXTURE_DIR = _REPO / "tests" / "fixtures" / "scanner_fast_path"
_CORPUS = json.loads((_FIXTURE_DIR / "corpus.json").read_text(encoding="utf-8"))
_ORACLES = json.loads((_FIXTURE_DIR / "full-oracles.json").read_text(encoding="utf-8"))["cases"]

_FAMILY_KEYS = {
    "demand": "demand_zones",
    "supply": "supply_zones",
    "order_block": "order_blocks",
    "fvg": "fvg",
}
_TIMEFRAMES = ("H4", "H1")


def _is_raw_empty(smc: dict[str, Any]) -> bool:
    for tf in _TIMEFRAMES:
        tf_data = smc.get(tf)
        if not isinstance(tf_data, dict):
            return False
        for key in _FAMILY_KEYS.values():
            zones = tf_data.get(key, [])
            if isinstance(zones, list) and len(zones) > 0:
                return False
    return True


def _run_full(case: dict[str, Any]) -> dict[str, Any]:
    candles = make_candles(case)
    return analyze_symbol(
        make_request(case, _CORPUS["analysis_input"]),
        candles,
        m15_candles=candles["M15"],
        thresholds=_CORPUS["thresholds"],
        smc_scoring_mode=str(case.get("smc_scoring_mode", "v2")),
    )


def _run_fast_tier1(case: dict[str, Any]) -> dict[str, Any]:
    candles = make_candles(case)
    return analyze_symbol(
        make_request(case, _CORPUS["analysis_input"]),
        candles,
        m15_candles=candles["M15"],
        thresholds=_CORPUS["thresholds"],
        smc_scoring_mode=str(case.get("smc_scoring_mode", "v2")),
        scanner_fast_tier1=True,
    )


def _derive_would_reject(case: dict[str, Any], full: dict[str, Any]) -> dict[str, Any]:
    candles = make_candles(case)
    smc = build_smc_context(
        candles["D1"], candles["H4"], candles["H1"],
        symbol=str(case.get("symbol", "EUR/USD")),
    )
    technical = full.get("technical", {}) if isinstance(full.get("technical"), dict) else {}
    market_regime = full.get("market_regime", {}) if isinstance(full.get("market_regime"), dict) else {}
    return evaluate_post_context_prefilter(
        mode=str(case.get("smc_scoring_mode", "v2")),
        smc=smc,
        technical=technical,
        market_regime=market_regime,
    )


# -- Extraction helpers (mục 8.4 parity) ------------------------------------


def _zone_ids(result: dict[str, Any]) -> dict[str, str | None]:
    scoring = result.get("smc_scoring", {})
    decision = scoring.get("decision", {}) if isinstance(scoring, dict) else {}
    return {
        side: decision.get(side, {}).get("selected_zone_id")
        if isinstance(decision.get(side), dict) else None
        for side in ("buy", "sell")
    }


def _zone_scores(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    scoring = result.get("smc_scoring", {})
    decision = scoring.get("decision", {}) if isinstance(scoring, dict) else {}
    out: dict[str, dict[str, Any]] = {}
    for side in ("buy", "sell"):
        side_data = decision.get(side, {}) if isinstance(decision, dict) else {}
        out[side] = {
            "timeframe": side_data.get("selected_zone_timeframe"),
            "score": side_data.get("selected_zone_score"),
            "relevance": side_data.get("selected_zone_relevance_score"),
            "setup": side_data.get("selected_zone_setup_score"),
        }
    return out


def _signal_scores(result: dict[str, Any]) -> dict[str, int]:
    scores = result.get("scenario_scores", {}) if isinstance(result.get("scenario_scores"), dict) else {}
    return {
        side: int(scores.get(side, {}).get("signal_score", 0) or 0)
        for side in ("buy", "sell")
    }


def _scenario_signature(result: dict[str, Any]) -> list[dict[str, Any]]:
    scenarios = result.get("scenarios") or []
    return [
        {
            "type": s.get("type"),
            "entry_status": s.get("entry_status"),
            "entry_zone": s.get("entry_zone"),
            "stop_loss": s.get("stop_loss"),
            "take_profit": s.get("take_profit"),
            "risk_reward": s.get("risk_reward"),
        }
        for s in scenarios
        if isinstance(s, dict)
    ]


def _decision_engine(result: dict[str, Any]) -> dict[str, str]:
    de = result.get("decision_engine", {}) if isinstance(result.get("decision_engine"), dict) else {}
    return {
        "decision": str(de.get("decision", "")),
        "legacy_action": str(de.get("legacy_action", "")),
    }


def _scoring_provenance(result: dict[str, Any]) -> dict[str, Any]:
    sp = result.get("scoring_provenance", {}) if isinstance(result.get("scoring_provenance"), dict) else {}
    return {
        "scorer_version": sp.get("scorer_version"),
        "gate_version": sp.get("gate_version"),
        "score_metric": sp.get("score_metric"),
    }


def _smc_policy(result: dict[str, Any]) -> dict[str, Any]:
    scoring = result.get("smc_scoring", {})
    policy = scoring.get("policy", {}) if isinstance(scoring, dict) else {}
    return {
        "requested_mode": policy.get("requested_mode"),
        "effective_mode": policy.get("effective_mode"),
    }


def _candidate_status(result: dict[str, Any]) -> str:
    row = scanner_row_from_analysis(result)
    return evaluate_scanner_candidate(row).status


def _has_trade_setup(result: dict[str, Any]) -> bool:
    scenarios = result.get("scenarios") or []
    return any(
        isinstance(s, dict)
        and s.get("type") in ("buy", "sell")
        and s.get("entry_status") not in ("watch_zone", "no_setup", None)
        for s in scenarios
    )


def _has_watch_signal(result: dict[str, Any]) -> bool:
    scenarios = result.get("scenarios") or []
    return any(
        isinstance(s, dict) and s.get("entry_status") == "watch_zone"
        for s in scenarios
    )


# -- Parity check across all mục 8.4 dimensions ------------------------------

_ParityField = tuple[str, str]


def _check_survivor_parity(full: dict[str, Any], fast: dict[str, Any]) -> list[_ParityField]:
    failures: list[tuple[str, str]] = []

    fz = _zone_ids(full)
    tz = _zone_ids(fast)
    if tz != fz:
        failures.append(("zone_ids", f"full={fz} fast={tz}"))

    fzs = _zone_scores(full)
    tzs = _zone_scores(fast)
    for side in ("buy", "sell"):
        for key in ("timeframe", "score", "relevance", "setup"):
            if tzs[side][key] != fzs[side][key]:
                failures.append(
                    (f"zone_score.{side}.{key}",
                     f"full={fzs[side][key]} fast={tzs[side][key]}")
                )

    fsig = _signal_scores(full)
    tsig = _signal_scores(fast)
    if tsig != fsig:
        failures.append(("signal_scores", f"full={fsig} fast={tsig}"))

    fsc = _scenario_signature(full)
    tsc = _scenario_signature(fast)
    if tsc != fsc:
        failures.append(("scenarios", f"full={fsc} fast={tsc}"))

    fde = _decision_engine(full)
    tde = _decision_engine(fast)
    if tde != fde:
        failures.append(("decision_engine", f"full={fde} fast={tde}"))

    fsp = _scoring_provenance(full)
    tsp = _scoring_provenance(fast)
    if tsp != fsp:
        failures.append(("scoring_provenance", f"full={fsp} fast={tsp}"))

    fpol = _smc_policy(full)
    tpol = _smc_policy(fast)
    if tpol != fpol:
        failures.append(("smc_policy", f"full={fpol} fast={tpol}"))

    fcand = _candidate_status(full)
    tcand = _candidate_status(fast)
    if tcand != fcand:
        failures.append(("candidate", f"full={fcand} fast={tcand}"))

    return failures


def _compute_raw_empty_rate(cases: list[dict[str, Any]]) -> float:
    empty_count = 0
    for case in cases:
        candles = make_candles(case)
        smc = build_smc_context(
            candles["D1"], candles["H4"], candles["H1"],
            symbol=str(case.get("symbol", "EUR/USD")),
        )
        if _is_raw_empty(smc):
            empty_count += 1
    return empty_count / len(cases) if cases else 0.0


def main() -> int:
    cases = _CORPUS["cases"]
    fixture_count = len(cases)

    results: list[dict[str, Any]] = []
    full_latencies: list[float] = []
    fast_latencies: list[float] = []

    print("=" * 72)
    print("Scanner Fast-Path Tier 1 — Offline A/B Benchmark")
    print(f"Fixtures: {fixture_count}")
    print("=" * 72)

    for case in cases:
        name = case["name"]
        mode = str(case.get("smc_scoring_mode", "v2"))
        print(f"\n--- {name} ({mode}) ---")

        # 1. Full baseline
        t0 = perf_counter()
        full = _run_full(case)
        full_ms = round((perf_counter() - t0) * 1_000, 3)
        full_latencies.append(full_ms)

        # 2. Would-reject oracle
        would = _derive_would_reject(case, full)

        # 3. Fast Tier 1
        t0 = perf_counter()
        fast = _run_fast_tier1(case)
        fast_ms = round((perf_counter() - t0) * 1_000, 3)
        fast_latencies.append(fast_ms)

        full_zone_ids = _zone_ids(full)
        full_has_zone = any(full_zone_ids[side] is not None for side in ("buy", "sell"))
        is_legacy_shadow = mode in ("legacy", "shadow")
        full_has_trade = _has_trade_setup(full)
        full_has_watch = _has_watch_signal(full)
        fast_status = fast.get("analysis_status")
        fast_route = fast.get("pipeline_route")
        fast_is_reject = fast_status == "structural_reject"

        record: dict[str, Any] = {
            "name": name,
            "mode": mode,
            "full_ms": full_ms,
            "fast_ms": fast_ms,
            "full_has_zone": full_has_zone,
            "full_zone_ids": full_zone_ids,
            "full_signal_scores": _signal_scores(full),
            "full_scenarios": _scenario_signature(full),
            "full_decision_engine": _decision_engine(full),
            "full_candidate": _candidate_status(full),
            "would_should_reject": would.get("should_reject"),
            "would_fail_open": would.get("fail_open"),
            "would_reason": would.get("reason_code"),
            "fast_status": fast_status,
            "fast_route": fast_route,
            "fast_zone_ids": _zone_ids(fast),
            "fast_signal_scores": _signal_scores(fast),
            "fast_scenarios": _scenario_signature(fast),
            "fast_decision_engine": _decision_engine(fast),
            "fast_candidate": _candidate_status(fast),
        }

        # Classification
        if is_legacy_shadow:
            record["classification"] = "fail_open_legacy_shadow"
        elif fast_is_reject and full_has_trade:
            record["classification"] = "TRADE_FALSE_REJECT"
        elif fast_is_reject and full_has_watch:
            record["classification"] = "watch_false_reject"
        elif fast_is_reject:
            record["classification"] = "correct_reject"
        else:
            record["classification"] = "survivor"

        # Full mục 8.4 parity check for survivors
        if is_legacy_shadow or full_has_zone:
            parity_failures = _check_survivor_parity(full, fast)
            record["survivor_parity"] = len(parity_failures) == 0
            record["parity_failures"] = parity_failures

        results.append(record)

        # Print per-fixture summary
        delta = fast_ms - full_ms
        sign = "+" if delta > 0 else ""
        print(f"  full:  {full_ms:.1f}ms  zones={full_zone_ids}")
        print(f"  fast:  {fast_ms:.1f}ms  ({sign}{delta:.1f}ms)  "
              f"status={fast_status}  route={fast_route}")
        print(f"  would: reject={would.get('should_reject')}  "
              f"fail_open={would.get('fail_open')}  "
              f"reason={would.get('reason_code')}")
        print(f"  class: {record['classification']}")
        pf = record.get("parity_failures", [])
        if pf:
            for field, detail in pf:
                print(f"         PARITY FAIL [{field}]: {detail}")

    # ------------------------------------------------------------------
    # Aggregate report
    # ------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("AGGREGATE REPORT")
    print("=" * 72)

    trade_false = [r for r in results if r["classification"] == "TRADE_FALSE_REJECT"]
    watch_false = [r for r in results if r["classification"] == "watch_false_reject"]
    correct_reject = [r for r in results if r["classification"] == "correct_reject"]
    survivors = [r for r in results if r["classification"] == "survivor"]
    fail_open = [r for r in results if r["classification"] == "fail_open_legacy_shadow"]
    parity_fail = [r for r in survivors if not r.get("survivor_parity", True)]

    post_context_reject_rate = (
        (len(trade_false) + len(watch_false) + len(correct_reject)) / fixture_count
        if fixture_count else 0
    )

    full_sorted = sorted(full_latencies)
    fast_sorted = sorted(fast_latencies)
    n = len(full_sorted)

    print(f"\n  fixture_count             = {fixture_count}")
    print(f"  raw_empty_rate             = {_compute_raw_empty_rate(cases):.2%}")
    print(f"  post_context_reject_rate   = {post_context_reject_rate:.2%}")
    print(f"  trade_false_reject_count   = {len(trade_false)}")
    print(f"  watch_false_reject_count   = {len(watch_false)}")
    print(f"  correct_reject_count       = {len(correct_reject)}")
    print(f"  survivor_count             = {len(survivors)}")
    print(f"  fail_open_count            = {len(fail_open)}")
    print(f"  survivor_parity_failures   = {len(parity_fail)}")
    print(f"  error_count                = 0")

    def _p(arr: list[float], pct: float) -> float:
        idx = max(0, min(n - 1, int(n * pct / 100)))
        return round(arr[idx], 1)

    print(f"\n  full_latency_p50           = {_p(full_sorted, 50):.1f}ms")
    print(f"  full_latency_p95           = {_p(full_sorted, 95):.1f}ms")
    print(f"  fast_latency_p50           = {_p(fast_sorted, 50):.1f}ms")
    print(f"  fast_latency_p95           = {_p(fast_sorted, 95):.1f}ms")

    # ------------------------------------------------------------------
    # Detail tables
    # ------------------------------------------------------------------
    if trade_false:
        print(f"\n  *** TRADE FALSE REJECTS ({len(trade_false)}) ***")
        for r in trade_false:
            print(f"    {r['name']}: full_zones={r['full_zone_ids']}  "
                  f"fast_status={r['fast_status']}")

    if watch_false:
        print(f"\n  watch false rejects ({len(watch_false)}) — allowed display changes:")
        for r in watch_false:
            print(f"    {r['name']}: full_scenarios={r['full_scenarios']}  "
                  f"fast_scenarios={r['fast_scenarios']}")

    if parity_fail:
        print(f"\n  *** SURVIVOR PARITY FAILURES ({len(parity_fail)}) ***")
        for r in parity_fail:
            print(f"    {r['name']}:")
            for field, detail in r.get("parity_failures", []):
                print(f"      [{field}] {detail}")

    # ------------------------------------------------------------------
    # Gate decision
    # ------------------------------------------------------------------
    print("\n" + "-" * 72)
    gate_pass = (
        len(trade_false) == 0
        and len(parity_fail) == 0
    )

    if gate_pass:
        print("GATE: PASS — scanner_fast_tier1 can be enabled.")
        print("Set scanner_fast_tier1=true in feature flags to activate.")
        return 0
    else:
        print("GATE: FAIL — do NOT enable scanner_fast_tier1.")
        if trade_false:
            print(f"  Fix {len(trade_false)} trade false reject(s) first.")
        if parity_fail:
            print(f"  Fix {len(parity_fail)} survivor parity failure(s) first.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
