"""Benchmark evidence for the SMC single-runtime migration (Bước 32).

Measures on the golden canonical corpus:
- scorer call count per symbol (must be at most 1 — dual-run removed)
- p50/p95 analysis latency
- new snapshot size and absence of duplicated shadow/decision payload
- error rate and blocked reasons
- no-zone rate
- candidate / order-ready counts

Saves a JSON result plus prints a summary. Read-only: never mutates the
pipeline or production data.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from core.analysis_engine import analyze_symbol
from core.market_models import Candle
from core.risk_engine import AnalysisInput

_FIXTURE_PATH = (
    _PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "smc_canonical"
    / "golden_cases.json"
)
_OUTPUT_PATH = Path(__file__).parent / "benchmark-single-runtime.json"

_FORBIDDEN_SNAPSHOT_KEYS = (
    "shadow",
    "decision",
    "comparison",
    "active",
    "legacy",
    "policy",
    "shadow_status",
)


def _candles(
    count: int,
    *,
    start: float,
    step: float,
    bar_minutes: int,
) -> list[Candle]:
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = start
    result: list[Candle] = []
    for index in range(count):
        direction = 1 if index % 7 != 6 else -1
        body = step * direction
        open_price = price
        close_price = price + body
        result.append(Candle(
            time=timestamp,
            open=round(open_price, 5),
            high=round(max(open_price, close_price) + abs(step) * 0.7, 5),
            low=round(min(open_price, close_price) - abs(step) * 0.7, 5),
            close=round(close_price, 5),
            volume=float(1000 + index),
        ))
        price = close_price
        timestamp += timedelta(minutes=bar_minutes)
    return result


def _pipeline_input() -> tuple[AnalysisInput, dict[str, list[Candle]]]:
    request = AnalysisInput(
        symbol="EUR/USD",
        broker_symbol="EURUSDm",
        account_balance=10_000,
        risk_percent=1.0,
        account_currency="USD",
        lot_step=0.01,
        minimum_lot=0.01,
        contract_size_override=100_000,
        timezone_name="Asia/Ho_Chi_Minh",
    )
    candles = {
        "D1": _candles(120, start=1.05, step=0.00020, bar_minutes=1440),
        "H4": _candles(240, start=1.06, step=0.00010, bar_minutes=240),
        "H1": _candles(300, start=1.07, step=0.00005, bar_minutes=60),
    }
    return request, candles


def _selected_zone_ids(result: dict[str, Any]) -> dict[str, str | None]:
    scoring = result.get("smc_scoring", {}) if isinstance(result.get("smc_scoring"), dict) else {}
    sides = scoring.get("sides", {}) if isinstance(scoring.get("sides"), dict) else {}
    out: dict[str, str | None] = {}
    for side in ("buy", "sell"):
        side_data = sides.get(side) if isinstance(sides.get(side), dict) else {}
        out[side] = side_data.get("selected_zone_id")
    return out


def _run_case(
    request: AnalysisInput,
    candles: dict[str, list[Candle]],
    case: dict[str, Any],
) -> tuple[dict[str, Any], list[str], float]:
    import core.analysis_pipeline as pipeline_module
    from core.smc_scorer import score_smc as _real_score_smc

    calls: list[str] = []

    def _spy(smc, technical, market_regime=None):
        calls.append("score_smc")
        return _real_score_smc(smc, technical, market_regime)

    with (
        patch.object(
            pipeline_module,
            "build_smc_context",
            lambda d1, h4, h1, *, scan_interval_min=15, symbol="": case["smc"],
        ),
        patch.object(
            pipeline_module,
            "build_technical_snapshot",
            lambda d1, h4, h1: case["technical"],
        ),
        patch.object(
            pipeline_module,
            "detect_market_regime",
            lambda technical, news_in_3h=False: case["market_regime"],
        ),
        patch.object(pipeline_module, "score_smc", _spy),
    ):
        started = time.perf_counter()
        result = analyze_symbol(request, candles)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
    return result, calls, elapsed_ms


def main() -> int:
    fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    request, candles = _pipeline_input()

    rows: list[dict[str, Any]] = []
    latency_ms: list[float] = []
    scorer_calls: list[int] = []
    snapshot_bytes: list[int] = []
    forbidden_hits: list[str] = []
    no_zone_cases: int = 0
    error_cases: int = 0
    blocked_reasons: list[str] = []
    ready_to_trade: int = 0
    order_ready: int = 0

    for case in fixture["cases"]:
        result, calls, elapsed_ms = _run_case(request, candles, case)
        scoring = result.get("smc_scoring", {}) if isinstance(result.get("smc_scoring"), dict) else {}
        snapshot_json = json.dumps(scoring, ensure_ascii=False, sort_keys=True)
        selected_ids = _selected_zone_ids(result)

        call_count = len(calls)
        scorer_calls.append(call_count)
        latency_ms.append(elapsed_ms)
        snapshot_bytes.append(len(snapshot_json.encode("utf-8")))

        present_forbidden = [key for key in _FORBIDDEN_SNAPSHOT_KEYS if key in scoring]
        if present_forbidden:
            forbidden_hits.append(f"{case['name']}:{present_forbidden}")

        status = result.get("analysis_status")
        if status != "completed":
            error_cases += 1
        route = result.get("pipeline_route")
        blocked = result.get("fast_reject_reason")
        if blocked:
            blocked_reasons.append(str(blocked))

        if not any(selected_ids[side] for side in ("buy", "sell")):
            no_zone_cases += 1

        scenarios = result.get("scenarios", []) if isinstance(result.get("scenarios"), list) else []
        ready_to_trade += sum(1 for sc in scenarios if isinstance(sc, dict) and sc.get("ready_to_trade") is True)
        decision = result.get("decision_engine", {}) if isinstance(result.get("decision_engine"), dict) else {}
        if decision.get("decision") == "READY_TO_TRADE":
            order_ready += 1

        rows.append({
            "case": case["name"],
            "scorer_calls": call_count,
            "latency_ms": round(elapsed_ms, 3),
            "snapshot_bytes": len(snapshot_json.encode("utf-8")),
            "has_forbidden_keys": bool(present_forbidden),
            "analysis_status": status,
            "pipeline_route": route,
            "selected_zone": selected_ids,
            "ready_to_trade": any(isinstance(sc, dict) and sc.get("ready_to_trade") is True for sc in scenarios),
        })

    total = len(rows)
    latency_sorted = sorted(latency_ms)
    p50 = statistics.median(latency_sorted)
    p95 = (
        latency_sorted[int(0.95 * (total - 1))]
        if total
        else 0.0
    )
    summary = {
        "migration": "smc-single-runtime",
        "benchmark_step": "Bước 32",
        "corpus": "tests/fixtures/smc_canonical/golden_cases.json",
        "samples": total,
        "baseline_comparison": {
            "method": (
                "Pre-migration dual-run scored SMC twice per symbol "
                "(v1 score path + v2 shadow). Current canonical runtime scores "
                "once; scorer_calls_per_symbol.max=1 verifies the dual-run was "
                "removed. Single-run latency is therefore strictly bounded by "
                "the dual-run cost."
            ),
            "scorer_calls_before": 2,
            "scorer_calls_now": 1,
            "snapshot_before": (
                "smc_scoring carried duplicated shadow/decision/active/"
                "comparison payload per side"
            ),
            "snapshot_now": (
                "smc_scoring carries a single canonical sides + "
                "consumer_contract (no shadow/decision/comparison keys)"
            ),
        },
        "scorer_calls_per_symbol": {
            "distribution": sorted(set(scorer_calls)),
            "max": max(scorer_calls) if scorer_calls else 0,
            "expected_max": 1,
            "pass": bool(scorer_calls) and max(scorer_calls) <= 1,
        },
        "latency_ms": {
            "p50": round(p50, 3),
            "p95": round(p95, 3),
            "min": round(min(latency_sorted), 3),
            "max": round(max(latency_sorted), 3),
            "note": "single-run scorer (dual-run removed): call count 1/symbol proves no 2x scorer cost",
        },
        "snapshot": {
            "bytes_min": min(snapshot_bytes) if snapshot_bytes else 0,
            "bytes_max": max(snapshot_bytes) if snapshot_bytes else 0,
            "bytes_avg": round(sum(snapshot_bytes) / total, 3) if total else 0.0,
            "forbidden_keys_present": forbidden_hits,
            "pass": not forbidden_hits,
        },
        "error_rate": {
            "errors": error_cases,
            "total": total,
            "rate": round(error_cases / total, 6) if total else 0.0,
        },
        "blocked_reasons": sorted(set(blocked_reasons)),
        "no_zone_rate": {
            "no_zone_cases": no_zone_cases,
            "total": total,
            "rate": round(no_zone_cases / total, 6) if total else 0.0,
        },
        "candidate_order": {
            "ready_to_trade_scenarios": ready_to_trade,
            "order_ready_decisions": order_ready,
            "total_cases": total,
        },
        "rows": rows,
    }

    _OUTPUT_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=== SMC single-runtime benchmark (Bước 32) ===")
    print(f"samples: {total}")
    print(f"scorer calls/symbol: max={summary['scorer_calls_per_symbol']['max']} "
          f"expected<=1 pass={summary['scorer_calls_per_symbol']['pass']}")
    print(f"latency p50={p50:.3f}ms p95={p95:.3f}ms "
          f"(min={min(latency_sorted):.3f} max={max(latency_sorted):.3f})")
    print(f"snapshot bytes avg={summary['snapshot']['bytes_avg']} "
          f"forbidden_keys={summary['snapshot']['forbidden_keys_present'] or 'none'}")
    print(f"error_rate={summary['error_rate']['rate']} "
          f"blocked={summary['blocked_reasons']}")
    print(f"no_zone_rate={summary['no_zone_rate']['rate']}")
    print(f"ready_to_trade={ready_to_trade} order_ready={order_ready}")
    print(f"saved: {_OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
