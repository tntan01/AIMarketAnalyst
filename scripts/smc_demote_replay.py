"""Replay the frozen SMC demote corpus and label future outcomes (task SD-C2).

Run:
    python -X utf8 scripts/smc_demote_replay.py parity
    python -X utf8 scripts/smc_demote_replay.py run [--symbols ...] [--from ...] [--to ...]
    python -X utf8 scripts/smc_demote_replay.py summary

``parity`` proves ``live_analysis_at`` still reaches the live seam exactly like the
existing parity tool; ``run`` replays every SD-C1 cutoff through
``derive_live_analysis`` and stores one row per cutoff (resumable); ``summary``
aggregates the stored rows.  Nothing here scores, ranks or analyses — that is
SD-C3.  No MT5 call and no order function is ever used.
"""

from __future__ import annotations

import argparse
import ctypes
import gzip
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
_SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from smc_demote_corpus import (  # noqa: E402
    CUTOFFS_PATH,
    DATA_DIR,
    MANIFEST_PATH,
    OUTPUT_DIR,
    TAIL_BARS,
    load_symbol_data,
    windows_at,
)

import smc_replay_parity as _parity  # noqa: E402
from core.indicators import atr  # noqa: E402
from core.scanner_live_producers import derive_live_analysis  # noqa: E402
from core.scanner_scenario_producers import (  # noqa: E402
    plans_from_canonical_selection,
)
from core.smc_snapshot_cache import smc_rule_versions  # noqa: E402

ROWS_PATH = DATA_DIR / "replay_rows.jsonl"        # KHÔNG commit (data/ đã ignore)
ERRORS_PATH = DATA_DIR / "replay_errors.jsonl"    # KHÔNG commit
SUMMARY_PATH = OUTPUT_DIR / "replay_summary.json" # commit
PARITY_PATH = OUTPUT_DIR / "replay_parity_c2.json" # commit
TRIAL_PATH = OUTPUT_DIR / "replay_trial.json"     # commit
SIDES = ("buy", "sell")
FWD_HOURS = (8, 24)
ATR_PERIOD = 14

_PARITY_TIMEFRAMES = ("D1", "H4", "H1", "M15")


class RowsFileError(ValueError):
    """A non-final line of a JSONL store could not be parsed."""


def _safe_name(app_symbol: str) -> str:
    return app_symbol.replace("/", "")


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], bool]:
    """Read a JSONL store; a corrupt *final* line is dropped with a warning flag.

    Any corrupt line that is not the last one is a real corruption (an interrupted
    append can only damage the tail), so it raises instead of silently losing data.
    """

    if not path.exists():
        return [], False
    raw = path.read_text(encoding="utf-8")
    lines = [(index, line) for index, line in enumerate(raw.split("\n")) if line.strip()]
    rows: list[dict[str, Any]] = []
    for position, (index, line) in enumerate(lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            if position == len(lines) - 1:
                return rows, True
            raise RowsFileError(f"corrupt JSON at line {index + 1} of {path.name}")
        rows.append(payload)
    return rows, False


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class _PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def _peak_rss_mb() -> float | None:
    if sys.platform != "win32":
        return None
    kernel32 = ctypes.WinDLL("kernel32"); psapi = ctypes.WinDLL("psapi")
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
    pmc = _PMC(); pmc.cb = ctypes.sizeof(_PMC)
    if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
        return None
    return round(pmc.PeakWorkingSetSize / 2**20, 1)


def live_analysis_at(
    data: dict[str, Any],
    cutoff: datetime,
    min_rr: float | None,
) -> tuple[dict[str, Any], dict[str, list[Any]], dict[str, list[Any]]]:
    """Run the live seam at ``cutoff`` and return ``(analysis, prefix, tail)``."""

    prefix, tail = windows_at(data, cutoff)
    analysis = derive_live_analysis(
        prefix["D1"],
        prefix["H4"],
        prefix["H1"],
        symbol=data["symbol"],
        captured_at=cutoff,
        news_in_3h=False,
        m15_candles=prefix["M15"],
        m15_as_of=cutoff,
        tick_size=data["tick_size"],
        tick_size_source=data["tick_size_source"],
        min_rr=min_rr,
    )
    return analysis, prefix, tail


def _selection_of(canonical_smc: Any, side: str) -> Any:
    side_result = canonical_smc.side(side) if hasattr(canonical_smc, "side") else None
    return getattr(side_result, "selection", None)


def analyze_cutoff(
    data: dict[str, Any],
    cutoff: datetime,
    min_rr: float | None,
) -> dict[str, Any]:
    """Replay one cutoff and build the stored row (scores + future labels)."""

    analysis, prefix, tail = live_analysis_at(data, cutoff, min_rr)

    h1 = prefix["H1"]
    if not h1:
        raise ValueError("prefix_h1_empty")
    ref_close = h1[-1].close
    atr_series = atr(
        [candle.high for candle in h1],
        [candle.low for candle in h1],
        [candle.close for candle in h1],
        ATR_PERIOD,
    )
    atr_h1 = atr_series[-1] if atr_series else None
    if atr_h1 is None or atr_h1 <= 0:
        raise ValueError("atr_h1_unavailable")

    canonical_smc = analysis["canonical_smc"]
    plans = plans_from_canonical_selection(canonical_smc)

    sides: dict[str, Any] = {}
    for side in SIDES:
        raw = analysis["raws"].per_side[side]
        selection = _selection_of(canonical_smc, side)
        payload: dict[str, Any] = {
            "trend": raw.trend,
            "momentum": raw.momentum,
            "location": raw.location,
            "smc_raw": raw.smc,
        }
        if selection is None:
            payload.update(
                {
                    "smc_state": None,
                    "quality_raw": None,
                    "quality_score": None,
                    "b": None,
                    "q": None,
                    "l": None,
                    "c": None,
                    "zone_low": None,
                    "zone_high": None,
                    "plan_available": None,
                    "readiness_status": None,
                    "smc_readiness_state": None,
                }
            )
        else:
            readiness = selection.readiness or {}
            payload.update(
                {
                    "smc_state": selection.state,
                    "quality_raw": selection.quality_raw,
                    "quality_score": selection.quality_score,
                    "b": selection.b,
                    "q": selection.q,
                    "l": selection.l,
                    "c": selection.c,
                    "zone_low": selection.zone_low,
                    "zone_high": selection.zone_high,
                    "plan_available": selection.plan_available,
                    "readiness_status": readiness.get("status"),
                    "smc_readiness_state": readiness.get("smc_state"),
                }
            )
        plan = plans.get(side)
        payload["entry"] = plan.entry if plan is not None else None
        payload["stop_loss"] = plan.stop_loss if plan is not None else None
        payload["take_profit"] = plan.take_profit if plan is not None else None
        payload["labels"] = label_side(
            side, plan, ref_close, atr_h1, cutoff, tail
        )
        sides[side] = payload

    return {
        "symbol": data["symbol"],
        "broker_symbol": data.get("broker_symbol"),
        "cutoff": cutoff.astimezone(timezone.utc).isoformat(),
        "regime": analysis["regime"],
        "ref_close": ref_close,
        "atr_h1": atr_h1,
        "sides": sides,
    }


def label_side(
    side: str,
    plan: Any,
    ref_close: float,
    atr_h1: float,
    cutoff: datetime,
    tail: dict[str, list[Any]],
) -> dict[str, Any]:
    """Label one side from the future tail only (never the prefix).

    Prices are the broker's own bars; no spread or cost is applied (Q9).  A
    limit entry is assumed filled at its own price ``E`` (documented limit of the
    replay, see report).
    """

    for timeframe in ("H1", "M15"):
        for candle in tail.get(timeframe, []):
            if candle.time < cutoff:
                raise ValueError("tail_before_cutoff")

    direction = 1 if side == "buy" else -1
    labels: dict[str, Any] = {
        "fwd_8h_atr": None,
        "fwd_24h_atr": None,
        "tp_sl": None,
        "fill_bar": None,
        "resolve_bar": None,
        "mfe_r": None,
        "mae_r": None,
    }

    h1 = tail.get("H1", [])
    if len(h1) >= FWD_HOURS[0]:
        labels["fwd_8h_atr"] = (h1[7].close - ref_close) * direction / atr_h1
    if len(h1) >= FWD_HOURS[1]:
        labels["fwd_24h_atr"] = (h1[23].close - ref_close) * direction / atr_h1

    if plan is None:
        return labels

    entry = plan.entry
    stop_loss = plan.stop_loss
    take_profit = plan.take_profit
    if side == "buy":
        valid = stop_loss < entry < take_profit
    else:
        valid = take_profit < entry < stop_loss
    if not valid:
        labels["tp_sl"] = "plan_invalid"
        return labels
    risk = abs(entry - stop_loss)
    if risk <= 0:
        labels["tp_sl"] = "plan_invalid"
        return labels

    m15 = tail.get("M15", [])
    fill_bar: int | None = None
    for index, candle in enumerate(m15):
        if side == "buy" and candle.low <= entry:
            fill_bar = index
            break
        if side == "sell" and candle.high >= entry:
            fill_bar = index
            break
    if fill_bar is None:
        labels["tp_sl"] = "not_filled"
        return labels
    labels["fill_bar"] = fill_bar

    resolution: str | None = None
    resolve_bar: int | None = None
    for index in range(fill_bar, len(m15)):
        candle = m15[index]
        if side == "buy":
            sl_hit = candle.low <= stop_loss
            tp_hit = candle.high >= take_profit
        else:
            sl_hit = candle.high >= stop_loss
            tp_hit = candle.low <= take_profit
        if index == fill_bar:
            tp_hit = False
        if sl_hit:
            resolution = "sl_first"
            resolve_bar = index
            break
        if tp_hit:
            resolution = "tp_first"
            resolve_bar = index
            break
    labels["tp_sl"] = resolution or "unresolved"
    labels["resolve_bar"] = resolve_bar

    end = resolve_bar if resolve_bar is not None else len(m15) - 1
    window = m15[fill_bar : end + 1]
    if window:
        highest = max(candle.high for candle in window)
        lowest = min(candle.low for candle in window)
        if side == "buy":
            labels["mfe_r"] = (highest - entry) / risk
            labels["mae_r"] = (entry - lowest) / risk
        else:
            labels["mfe_r"] = (entry - lowest) / risk
            labels["mae_r"] = (highest - entry) / risk
    return labels


def _row_side_fields(row: dict[str, Any], side: str) -> dict[str, Any]:
    return row["sides"][side]


def _run_parity(_args) -> int:
    if not _parity.CORPUS_PATH.exists():
        print(f"BLOCKED: no corpus at {_parity.CORPUS_PATH}")
        return 2

    with gzip.open(_parity.CORPUS_PATH, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]

    def fingerprint(analysis: dict[str, Any]) -> dict[str, Any]:
        return _parity._live_side_fields(
            _parity.decision_fingerprint(analysis["smc_evaluation"])
        )

    mismatches: list[dict[str, Any]] = []
    matched = 0
    frozen_compare_count = 0
    frozen_match_count = 0
    frozen_mismatches: list[dict[str, Any]] = []
    for row in rows:
        cutoff = datetime.fromisoformat(row["as_of"])
        label = f"{row['symbol']}@{row['as_of']}"

        expected_prefix = {
            timeframe: _parity._candles(row, timeframe, bars=500, tail=False)
            for timeframe in _PARITY_TIMEFRAMES
        }
        expected = fingerprint(_parity._live(expected_prefix, row))

        data = {
            "symbol": row["symbol"],
            "broker_symbol": row.get("broker_symbol"),
            "tick_size": row["tick_size"],
            "tick_size_source": row["tick_size_source"],
            "candles": {
                timeframe: _parity._candles(row, timeframe, bars=500, tail=True)
                for timeframe in _PARITY_TIMEFRAMES
            },
        }
        analysis, _, _ = live_analysis_at(data, cutoff, row.get("min_rr"))
        got = fingerprint(analysis)

        row_c2 = analyze_cutoff(data, cutoff, row.get("min_rr"))

        row_mismatch: dict[str, Any] = {"symbol": row["symbol"], "as_of": row["as_of"], "fields": []}
        if got != expected:
            row_mismatch["fields"].append(
                {"check": "fingerprint", "expected": expected, "got": got}
            )
        for side in SIDES:
            side_row = _row_side_fields(row_c2, side)
            side_got = got[side]
            for c2_field, got_field in (
                ("smc_state", "state"),
                ("quality_raw", "quality_raw"),
                ("plan_available", "plan_available"),
                ("readiness_status", "readiness_status"),
                ("smc_readiness_state", "smc_state"),
            ):
                if side_row.get(c2_field) != side_got.get(got_field):
                    row_mismatch["fields"].append(
                        {
                            "check": f"{side}.{c2_field}",
                            "expected": side_got.get(got_field),
                            "got": side_row.get(c2_field),
                        }
                    )
        if row_mismatch["fields"]:
            mismatches.append(row_mismatch)
        else:
            matched += 1

        frozen_path = DATA_DIR / f"{_safe_name(row['symbol'])}.json.gz"
        if frozen_path.exists():
            frozen = load_symbol_data(frozen_path)
            frozen_prefix, _ = windows_at(frozen, cutoff)
            if all(
                len(frozen_prefix[timeframe]) == (100 if timeframe == "M15" else 500)
                for timeframe in _PARITY_TIMEFRAMES
            ):
                frozen_compare_count += 1
                row_prefix = {
                    timeframe: _parity._candles(row, timeframe, bars=500, tail=False)
                    for timeframe in _PARITY_TIMEFRAMES
                }
                all_equal = True
                for timeframe in _PARITY_TIMEFRAMES:
                    left = [
                        (c.time, c.open, c.high, c.low, c.close)
                        for c in frozen_prefix[timeframe]
                    ]
                    right = [
                        (c.time, c.open, c.high, c.low, c.close)
                        for c in row_prefix[timeframe]
                    ]
                    if left != right:
                        all_equal = False
                        frozen_mismatches.append(
                            {
                                "symbol": row["symbol"],
                                "as_of": row["as_of"],
                                "timeframe": timeframe,
                                "frozen_candles": len(left),
                                "row_candles": len(right),
                            }
                        )
                if all_equal:
                    frozen_match_count += 1

        print(
            f"  {label:40s} match={not row_mismatch['fields']} "
            f"frozen_compare={'y' if frozen_path.exists() else 'n'}"
        )

    report = {
        "rows": len(rows),
        "matched": matched,
        "mismatches": mismatches,
        "rule_versions": smc_rule_versions(),
        "frozen_vs_corpus": {
            "compared": frozen_compare_count,
            "fully_matched": frozen_match_count,
            "mismatches": frozen_mismatches,
        },
    }
    _atomic_write_text(
        PARITY_PATH,
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    print(f"parity: {len(rows)} rows, {len(mismatches)} mismatches")
    print(f"report -> {PARITY_PATH}")
    return 0 if not mismatches else 1


def _select_cutoffs(
    cutoffs: list[dict[str, Any]],
    symbols: set[str] | None,
    from_date: str | None,
    to_date: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for item in cutoffs:
        if symbols is not None and item["symbol"] not in symbols:
            continue
        cutoff = datetime.fromisoformat(item["cutoff"])
        day = cutoff.date().isoformat()
        if from_date is not None and day < from_date:
            continue
        if to_date is not None and day > to_date:
            continue
        selected.append(item)
    if limit:
        selected = selected[:limit]
    return selected


def _matches_filter(
    item: dict[str, Any],
    symbols: set[str] | None,
    from_date: str | None,
    to_date: str | None,
) -> bool:
    if symbols is not None and item["symbol"] not in symbols:
        return False
    cutoff = datetime.fromisoformat(item["cutoff"])
    day = cutoff.date().isoformat()
    if from_date is not None and day < from_date:
        return False
    if to_date is not None and day > to_date:
        return False
    return True


_WORKER_CACHE: dict[str, dict[str, Any]] = {}


def _run_one(task: tuple[str, str, float | None]) -> dict[str, Any]:
    symbol, cutoff_iso, min_rr = task
    started = time.perf_counter()
    try:
        data = _WORKER_CACHE.get(symbol)
        if data is None:
            data = load_symbol_data(DATA_DIR / f"{_safe_name(symbol)}.json.gz")
            _WORKER_CACHE[symbol] = data
        row = analyze_cutoff(data, datetime.fromisoformat(cutoff_iso), min_rr)
        row["elapsed_s"] = round(time.perf_counter() - started, 4)
        row["peak_rss_mb"] = _peak_rss_mb()
        return row
    except Exception as exc:  # a real per-cutoff failure is recorded, never hidden
        return {
            "symbol": symbol,
            "cutoff": cutoff_iso,
            "error_type": type(exc).__name__,
            "message": str(exc),
            "elapsed_s": round(time.perf_counter() - started, 4),
            "peak_rss_mb": _peak_rss_mb(),
        }


def _run_run(args) -> int:
    if not CUTOFFS_PATH.exists():
        print(f"BLOCKED: no cutoffs at {CUTOFFS_PATH}; run `plan` first.")
        return 2
    if not MANIFEST_PATH.exists():
        print(f"BLOCKED: no manifest at {MANIFEST_PATH}; run `fetch` first.")
        return 2
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    min_rr = manifest.get("min_rr")
    all_cutoffs = json.loads(CUTOFFS_PATH.read_text(encoding="utf-8"))["cutoffs"]

    symbols = (
        {item.strip() for item in args.symbols.split(",") if item.strip()}
        if args.symbols
        else None
    )

    rows, trailing_corrupt = read_jsonl(ROWS_PATH)
    if trailing_corrupt:
        print(f"warning: dropped a corrupt final line of {ROWS_PATH.name}")
        _atomic_write_text(
            ROWS_PATH,
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        )

    if args.redo:
        kept = [
            row
            for row in rows
            if not _matches_filter(row, symbols, args.from_date, args.to_date)
        ]
        dropped = len(rows) - len(kept)
        rows = kept
        _atomic_write_text(
            ROWS_PATH,
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        )
        print(f"redo: dropped {dropped} stored rows matching the filter")
    elif trailing_corrupt:
        pass

    existing_keys = {f"{row['symbol']}@{row['cutoff']}" for row in rows}
    existing_errors, _ = read_jsonl(ERRORS_PATH)
    error_keys = {
        f"{error.get('symbol')}@{error.get('cutoff')}" for error in existing_errors
    }
    selected = _select_cutoffs(all_cutoffs, symbols, args.from_date, args.to_date, args.limit)
    tasks = [
        (item["symbol"], item["cutoff"], min_rr)
        for item in selected
        if f"{item['symbol']}@{item['cutoff']}" not in existing_keys
    ]
    retry_count = sum(
        1 for symbol, cutoff, _ in tasks if f"{symbol}@{cutoff}" in error_keys
    )
    new_count = len(tasks) - retry_count

    if not tasks:
        print("run: 0 snapshot mới")
        return 0

    errors = existing_errors
    task_keys = {f"{symbol}@{cutoff}" for symbol, cutoff, _ in tasks}
    kept_errors = [
        error
        for error in errors
        if f"{error.get('symbol')}@{error.get('cutoff')}" not in task_keys
    ]
    _atomic_write_text(
        ERRORS_PATH,
        "".join(json.dumps(error, ensure_ascii=False, sort_keys=True) + "\n" for error in kept_errors),
    )

    workers = max(1, int(args.workers))
    print(
        f"run: {len(tasks)} snapshots ({new_count} new, {retry_count} retry), "
        f"workers={workers}"
    )
    started = time.perf_counter()
    elapsed_samples: list[float] = []
    peak_rss_samples: list[float] = []
    done = 0
    error_count = 0
    with ROWS_PATH.open("a", encoding="utf-8") as rows_handle, ERRORS_PATH.open(
        "a", encoding="utf-8"
    ) as errors_handle:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_run_one, task): task for task in tasks}
            for future in as_completed(futures):
                result = future.result()
                done += 1
                if "error_type" in result:
                    error_count += 1
                    errors_handle.write(
                        json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n"
                    )
                    errors_handle.flush()
                else:
                    rows_handle.write(
                        json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n"
                    )
                    rows_handle.flush()
                if result.get("elapsed_s") is not None:
                    elapsed_samples.append(float(result["elapsed_s"]))
                if result.get("peak_rss_mb") is not None:
                    peak_rss_samples.append(float(result["peak_rss_mb"]))
                if done % 50 == 0 or done == len(tasks):
                    elapsed = time.perf_counter() - started
                    rate = done / elapsed if elapsed > 0 else 0.0
                    eta = (len(tasks) - done) / rate if rate > 0 else 0.0
                    print(
                        f"  {done}/{len(tasks)}  errors={error_count}  "
                        f"{rate:.2f}/s  ETA {eta:.0f}s"
                    )

    total_elapsed = time.perf_counter() - started
    print(
        f"run: done {done}, errors {error_count}, total {total_elapsed:.1f}s"
    )
    if args.trial:
        _write_trial(
            len(tasks),
            len(all_cutoffs),
            total_elapsed,
            elapsed_samples,
            peak_rss_samples,
            workers,
        )
    return 0


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
    return ordered[index]


def _write_trial(
    snapshots: int,
    full_lot: int,
    total_elapsed: float,
    elapsed_samples: list[float],
    peak_rss_samples: list[float],
    workers: int,
) -> None:
    mean = sum(elapsed_samples) / len(elapsed_samples) if elapsed_samples else None
    payload = {
        "snapshots": snapshots,
        "full_lot": full_lot,
        "total_elapsed_s": total_elapsed,
        "seconds_per_snapshot_mean": mean,
        "seconds_per_snapshot_p95": _percentile(elapsed_samples, 0.95),
        "peak_rss_mb_max": max(peak_rss_samples) if peak_rss_samples else None,
        "workers": workers,
        "estimated_total_seconds": {
            str(count): (mean * full_lot / count if mean is not None else None)
            for count in (1, 4, 8)
        },
    }
    _atomic_write_text(
        TRIAL_PATH,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    print(f"trial -> {TRIAL_PATH}")


def _run_summary(_args) -> int:
    if not CUTOFFS_PATH.exists():
        print(f"BLOCKED: no cutoffs at {CUTOFFS_PATH}; run `plan` first.")
        return 2
    all_cutoffs = json.loads(CUTOFFS_PATH.read_text(encoding="utf-8"))["cutoffs"]
    rows, _ = read_jsonl(ROWS_PATH)
    errors, _ = read_jsonl(ERRORS_PATH)

    row_keys = {f"{row['symbol']}@{row['cutoff']}" for row in rows}
    error_keys = {f"{error.get('symbol')}@{error.get('cutoff')}" for error in errors}
    cutoffs_total = len(all_cutoffs)
    missing = sum(
        1
        for item in all_cutoffs
        if f"{item['symbol']}@{item['cutoff']}" not in row_keys
        and f"{item['symbol']}@{item['cutoff']}" not in error_keys
    )

    error_types: dict[str, int] = {}
    for error in errors:
        key = str(error.get("error_type") or "unknown")
        error_types[key] = error_types.get(key, 0) + 1

    regime_counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("regime"))
        regime_counts[key] = regime_counts.get(key, 0) + 1

    smc_state_counts = {side: {} for side in SIDES}
    tp_sl_counts = {side: {} for side in SIDES}
    for row in rows:
        for side in SIDES:
            side_row = row["sides"][side]
            state = str(side_row.get("smc_state"))
            smc_state_counts[side][state] = smc_state_counts[side].get(state, 0) + 1
            tp_sl = side_row.get("labels", {}).get("tp_sl")
            key = str(tp_sl)
            tp_sl_counts[side][key] = tp_sl_counts[side].get(key, 0) + 1

    rows_sha256 = None
    if ROWS_PATH.exists():
        rows_sha256 = "sha256:" + hashlib.sha256(ROWS_PATH.read_bytes()).hexdigest()

    error_rate = errors.__len__() / cutoffs_total if cutoffs_total else 0.0
    payload = {
        "cutoffs_total": cutoffs_total,
        "rows": len(rows),
        "errors": len(errors),
        "error_rate": error_rate,
        "missing": missing,
        "error_types": dict(sorted(error_types.items())),
        "regime": dict(sorted(regime_counts.items())),
        "smc_state": {side: dict(sorted(counts.items())) for side, counts in smc_state_counts.items()},
        "tp_sl": {side: dict(sorted(counts.items())) for side, counts in tp_sl_counts.items()},
        "rule_versions": smc_rule_versions(),
        "rows_sha256": rows_sha256,
    }
    _atomic_write_text(
        SUMMARY_PATH,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    print(f"summary: cutoffs={cutoffs_total} rows={len(rows)} errors={len(errors)} missing={missing}")
    print(f"  error_rate={error_rate:.4f} error_types={payload['error_types']}")
    print(f"  regime={payload['regime']}")
    for side in SIDES:
        print(f"  {side}: smc_state={payload['smc_state'][side]}")
        print(f"  {side}: tp_sl={payload['tp_sl'][side]}")
    print(f"summary -> {SUMMARY_PATH}")
    return 0 if missing == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="SMC demote corpus replay (task SD-C2)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("parity")

    run = sub.add_parser("run")
    run.add_argument("--symbols", default="")
    run.add_argument("--from", dest="from_date", default=None)
    run.add_argument("--to", dest="to_date", default=None)
    run.add_argument("--workers", type=int, default=1)
    run.add_argument("--limit", type=int, default=0)
    run.add_argument("--redo", action="store_true")
    run.add_argument("--trial", action="store_true")

    sub.add_parser("summary")

    args = parser.parse_args()
    if args.command == "parity":
        return _run_parity(args)
    if args.command == "run":
        return _run_run(args)
    return _run_summary(args)


if __name__ == "__main__":
    raise SystemExit(main())
