"""Local scan-performance harness for the canonical SMC chain (task 136).

Run:
    python -X utf8 scripts/smc_performance.py --dataset reports/scanner/smc_real_snapshots/corpus.jsonl.gz --repeats 10 --report reports/scanner/smc_real_snapshots/performance.json

The task-15 dossier locked this command shape before the harness existed, so the
way the number is produced cannot drift after the fact.

What it measures, on one machine and one frozen dataset (the real-snapshot
corpus of task 131):

* ``scan_cpu`` — the wall clock of ``derive_live_analysis`` (candles → analysis),
  i.e. the symbol cost *after* the broker has answered.  Reported as p50/p95 per
  snapshot and per repeat pass, cold (first pass, lazy imports included) and warm.
* ``scan_end_to_end`` — the same path with the MT5 history fetch in front of it,
  measured for a subset of rows so the broker latency is visible instead of
  hidden behind a local corpus.
* ``evaluator_calls`` — how many times the canonical evaluator actually ran for
  one snapshot.  Task 102 froze this at one evaluation per snapshot; a number
  above one means a caller re-scored the same input.
* ``context_builder_calls`` — how many times the canonical context was rebuilt,
  which is the other half of "scored once".

Nothing here changes a score, a gate or a threshold, and no order is ever sent.
A measured value that misses the task-8 target (p50 <= 2s, p95 <= 5s) is reported
as a miss; the harness never softens it into a pass.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.market_models import closed_candles_at_cutoff  # noqa: E402
from core.scanner_live_producers import derive_live_analysis  # noqa: E402
from core.smc_snapshot_cache import smc_rule_versions  # noqa: E402

DEFAULT_DATASET = (
    PROJECT_ROOT / "reports" / "scanner" / "smc_real_snapshots" / "corpus.jsonl.gz"
)
DEFAULT_REPORT = (
    PROJECT_ROOT / "reports" / "scanner" / "smc_real_snapshots" / "performance.json"
)

# Task 8 target, frozen in docs/plans/smc-parameter-table.md and repeated in the
# task-15 dossier §3.5.
TARGET_P50_SECONDS = 2.0
TARGET_P95_SECONDS = 5.0
# Task 102: one result build per snapshot.
TARGET_EVALUATOR_CALLS_PER_SNAPSHOT = 1

LOOKBACK_DAYS = {"D1": 900, "H4": 300, "H1": 120, "M15": 20}


class _Counter:
    """Count one callable without touching the module it lives in."""

    def __init__(self, module: Any, attribute: str) -> None:
        self._module = module
        self._attribute = attribute
        self._original = getattr(module, attribute)
        self.count = 0

    def __enter__(self) -> "_Counter":
        def wrapped(*args, **kwargs):
            self.count += 1
            return self._original(*args, **kwargs)

        setattr(self._module, self._attribute, wrapped)
        return self

    def __exit__(self, *_exc) -> None:
        setattr(self._module, self._attribute, self._original)


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def _summarize(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0}
    rounded = [round(value, 4) for value in values]
    return {
        "count": len(rounded),
        "min": min(rounded),
        "p50": round(statistics.median(rounded), 4),
        "p95": round(_percentile(rounded, 0.95), 4),
        "max": max(rounded),
        "mean": round(statistics.fmean(rounded), 4),
    }


def load_dataset(path: Path) -> list[dict[str, Any]]:
    import gzip

    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _candles(row: dict[str, Any], timeframe: str, *, wide: bool) -> list[Any]:
    from core.market_models import Candle

    payload = list(row["candles"][timeframe])
    if wide:
        payload = payload + list(row["future_tail"].get(timeframe) or [])
    return [
        Candle(
            time=datetime.fromisoformat(item["t"]),
            open=float(item["o"]),
            high=float(item["h"]),
            low=float(item["l"]),
            close=float(item["c"]),
            volume=float(item.get("v") or 0.0),
        )
        for item in payload
    ]


def _run_snapshot(row: dict[str, Any], *, wide: bool = False) -> dict[str, Any]:
    return derive_live_analysis(
        _candles(row, "D1", wide=wide),
        _candles(row, "H4", wide=wide),
        _candles(row, "H1", wide=wide),
        symbol=row["symbol"],
        captured_at=datetime.fromisoformat(row["as_of"]),
        news_in_3h=False,
        m15_candles=_candles(row, "M15", wide=wide),
        m15_as_of=datetime.fromisoformat(row["as_of"]),
        tick_size=row["tick_size"],
        tick_size_source=row["tick_size_source"],
        min_rr=row.get("min_rr"),
    )


def measure_cpu(rows: Sequence[dict[str, Any]], repeats: int) -> dict[str, Any]:
    """Cold pass + warm passes of the candle→analysis path on the local corpus."""

    import core.smc_canonical_context as canonical_context
    import core.smc_snapshot as snapshot_module

    cold: list[float] = []
    warm: list[float] = []
    pass_totals: list[float] = []
    evaluator_calls = 0
    context_calls = 0
    with _Counter(snapshot_module, "evaluate_smc_snapshot") as evaluator:
        with _Counter(canonical_context, "build_canonical_smc_context") as context:
            for index in range(repeats + 1):
                pass_started = time.perf_counter()
                for row in rows:
                    started = time.perf_counter()
                    _run_snapshot(row)
                    elapsed = time.perf_counter() - started
                    (cold if index == 0 else warm).append(elapsed)
                pass_totals.append(time.perf_counter() - pass_started)
            evaluator_calls = evaluator.count
            context_calls = context.count
    passes = repeats + 1
    return {
        "cold_first_pass": _summarize(cold),
        "warm_passes": _summarize(warm),
        "pass_totals_seconds": [round(value, 4) for value in pass_totals],
        "pass_total_p50_seconds": round(statistics.median(pass_totals), 4),
        "evaluator_calls": evaluator_calls,
        "evaluator_calls_per_snapshot": round(evaluator_calls / (len(rows) * passes), 4),
        "context_builder_calls": context_calls,
        "context_builder_calls_per_snapshot": round(
            context_calls / (len(rows) * passes), 4
        ),
    }


def _live_min_rr() -> float | None:
    """The owner order policy's R:R floor, exactly as the live Scanner reads it."""

    try:
        from core.scanner_order_policy import load_runtime_order_policy

        value = getattr(
            getattr(load_runtime_order_policy(), "threshold", None),
            "min_risk_reward",
            None,
        )
    except Exception:
        return None
    return float(value) if value is not None else None


def measure_end_to_end(symbols: Sequence[str], cutoff_text: str) -> dict[str, Any]:
    """The same path with the real broker fetch in front of it."""

    from services.mt5_service import MT5Service

    service = MT5Service()
    if not service.connect():
        return {"available": False, "reason": "mt5_unavailable"}
    available = service.available_symbols(market_watch_only=False)
    cutoff = datetime.fromisoformat(cutoff_text)
    samples: list[dict[str, Any]] = []
    for app_symbol in symbols:
        broker_symbol = service.resolve_symbol(app_symbol, available)
        if not broker_symbol:
            samples.append({"symbol": app_symbol, "error": "unresolved_symbol"})
            continue
        quality = service.symbol_data_quality(app_symbol, broker_symbol)
        fetch_started = time.perf_counter()
        windows = {}
        for timeframe in ("D1", "H4", "H1", "M15"):
            start = cutoff - timedelta(days=LOOKBACK_DAYS[timeframe])
            try:
                fetched = service.load_ohlcv_range(
                    broker_symbol, timeframe, start, cutoff + timedelta(days=1)
                )
            except Exception as exc:
                fetched = []
                samples.append(
                    {"symbol": app_symbol, "timeframe": timeframe, "error": str(exc)}
                )
            limit = 100 if timeframe == "M15" else 500
            windows[timeframe] = list(
                closed_candles_at_cutoff(fetched, timeframe, cutoff)
            )[-limit:]
        fetch_seconds = time.perf_counter() - fetch_started
        analysis_started = time.perf_counter()
        derive_live_analysis(
            windows["D1"],
            windows["H4"],
            windows["H1"],
            symbol=app_symbol,
            captured_at=cutoff,
            m15_candles=windows["M15"],
            m15_as_of=cutoff,
            tick_size=quality.get("tick_size"),
            tick_size_source=quality.get("tick_size_source"),
            min_rr=_live_min_rr(),
        )
        analysis_seconds = time.perf_counter() - analysis_started
        samples.append(
            {
                "symbol": app_symbol,
                "broker_symbol": broker_symbol,
                "fetch_seconds": round(fetch_seconds, 4),
                "analysis_seconds": round(analysis_seconds, 4),
                "total_seconds": round(fetch_seconds + analysis_seconds, 4),
                "coverage": {tf: len(windows[tf]) for tf in windows},
            }
        )
    good = [sample for sample in samples if "total_seconds" in sample]
    return {
        "available": True,
        "cutoff": cutoff_text,
        "samples": samples,
        "fetch_seconds": _summarize([s["fetch_seconds"] for s in good]),
        "analysis_seconds": _summarize([s["analysis_seconds"] for s in good]),
        "total_seconds": _summarize([s["total_seconds"] for s in good]),
    }


def profile_one(row: dict[str, Any], top: int = 25) -> dict[str, Any]:
    """Where the per-snapshot time actually goes, measured not guessed.

    ``cProfile`` inflates absolute numbers (roughly fourfold here because the
    hot path is many small Python calls), so the report keeps the *shape* of the
    cost — which function dominates, and how many times the repeated work runs —
    and leaves the absolute seconds to ``scan_cpu``.
    """

    import cProfile
    import io
    import pstats

    _run_snapshot(row)  # warm: imports and lazy caches are not part of the cost
    profiler = cProfile.Profile()
    profiler.enable()
    _run_snapshot(row)
    profiler.disable()
    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream).sort_stats("cumulative")
    stats.print_stats(top)
    lines = [line.rstrip() for line in stream.getvalue().splitlines()]
    totals = [line for line in lines if "function calls" in line]
    return {
        "symbol": row["symbol"],
        "as_of": row["as_of"],
        "profiled_calls": totals[0] if totals else None,
        "top": lines[-top:],
    }


def build_report(args) -> dict[str, Any]:
    dataset = Path(args.dataset)
    if not dataset.exists():
        raise SystemExit(f"BLOCKED: no dataset at {dataset}")
    rows = load_dataset(dataset)
    if args.limit:
        rows = rows[: args.limit]
    started = time.perf_counter()
    cpu = measure_cpu(rows, max(1, args.repeats))
    report: dict[str, Any] = {
        "report_version": "smc-performance-report-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(dataset.relative_to(PROJECT_ROOT)),
        "dataset_rows": len(rows),
        "repeats": max(1, args.repeats),
        "measurement": {
            "harness": "scripts/smc_performance.py",
            "scan_cpu": "candle->analysis wall clock, broker fetch excluded",
            "scan_end_to_end": "MT5 fetch + the same candle->analysis path",
            "machine": sys.platform,
            "python": sys.version.split()[0],
        },
        "rule_versions": smc_rule_versions(),
        "scan_cpu": cpu,
        "targets": {
            "p50_seconds": TARGET_P50_SECONDS,
            "p95_seconds": TARGET_P95_SECONDS,
            "evaluator_calls_per_snapshot": TARGET_EVALUATOR_CALLS_PER_SNAPSHOT,
            "source": "docs/plans/smc-parameter-table.md (task 8) + task 15 dossier §3.5",
        },
    }
    warm_p50 = cpu["warm_passes"].get("p50")
    warm_p95 = cpu["warm_passes"].get("p95")
    report["verdict"] = {
        "p50_within_target": bool(warm_p50 is not None and warm_p50 <= TARGET_P50_SECONDS),
        "p95_within_target": bool(warm_p95 is not None and warm_p95 <= TARGET_P95_SECONDS),
        "evaluator_calls_within_target": cpu["evaluator_calls_per_snapshot"]
        <= TARGET_EVALUATOR_CALLS_PER_SNAPSHOT,
        "note": (
            "A miss is a miss: it is reported for Tech Lead decision, never "
            "turned into a pass by relaxing the target."
        ),
    }
    if args.end_to_end_symbols:
        report["scan_end_to_end"] = measure_end_to_end(
            [item for item in args.end_to_end_symbols.split(",") if item],
            args.end_to_end_cutoff,
        )
    if args.profile and rows:
        report["profile"] = profile_one(rows[0])
    report["harness_seconds"] = round(time.perf_counter() - started, 4)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Local SMC scan performance (task 136)")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--end-to-end-symbols", default="")
    parser.add_argument("--end-to-end-cutoff", default="2026-09-03T12:00:00+00:00")
    parser.add_argument(
        "--profile",
        action="store_true",
        help="also store a cProfile top-N of one snapshot (shape of the cost)",
    )
    args = parser.parse_args()
    report = build_report(args)
    target = Path(args.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({k: report[k] for k in ("scan_cpu", "verdict")}, ensure_ascii=False, indent=2))
    print(f"report -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
