"""Frozen MT5 history corpus builder for the SMC demote study (task SD-C1).

Run:  python -X utf8 scripts/smc_demote_corpus.py fetch
      python -X utf8 scripts/smc_demote_corpus.py plan
      python -X utf8 scripts/smc_demote_corpus.py verify

``fetch`` reads the broker's own D1/H4/H1/M15 history **once** through
``services.mt5_service.MT5Service`` and freezes it into one gzip-JSON file per
symbol.  ``plan`` turns that frozen history into the list of cutoff instants the
downstream replay (SD-C2) will re-scan.  ``verify`` re-checks the frozen bytes
without touching the terminal at all.

This is a *tool*, not runtime: nothing here is wired into the live scanner, no
order function of MT5 is ever called, and nothing is fabricated.  Only ``fetch``
reads the wall clock (the freeze instant); ``plan`` and ``verify`` are pure
functions of the stored files, so the same corpus always produces the same
cutoffs.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
_SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from config.constants import SUPPORTED_SYMBOLS  # noqa: E402
from core.market_models import (  # noqa: E402
    Candle,
    candle_close_at,
    closed_candles_at_cutoff,
)
from services.mt5_service import MT5Service  # noqa: E402

# Reuse the already-reviewed helpers of the real-snapshot collector instead of
# copying candle/JSON logic.  Never copy the closed-candle filter: always call
# ``closed_candles_at_cutoff``.
import smc_real_snapshots as _real_snapshots  # noqa: E402

OUTPUT_DIR = PROJECT_ROOT / "reports" / "scanner" / "smc_demote"
DATA_DIR = OUTPUT_DIR / "data"            # KHÔNG commit (xem .gitignore)
MANIFEST_PATH = OUTPUT_DIR / "corpus_manifest.json"
CUTOFFS_PATH = OUTPUT_DIR / "cutoffs.json"
TIMEFRAMES = ("D1", "H4", "H1", "M15")
FETCH_DAYS = {"D1": 1000, "H4": 400, "H1": 220, "M15": 120}   # lùi từ thời điểm fetch
WINDOW_BARS = {"D1": 500, "H4": 500, "H1": 500, "M15": 100}   # cửa sổ production
TAIL_BARS = {"H1": 48, "M15": 192}                            # nến sau cutoff
CUTOFF_HOURS_UTC = (4, 12, 20)
PERIOD_DAYS = 92                                              # ~3 tháng

_candle_payload = _real_snapshots._candle_payload
_candle_from_payload = _real_snapshots._candle_from_payload
_digest = _real_snapshots._digest
_live_min_rr = _real_snapshots._live_min_rr


def _safe_name(app_symbol: str) -> str:
    return app_symbol.replace("/", "")


def _file_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(_file_bytes(path)).hexdigest()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _atomic_write_gzip(path: Path, payload: dict[str, Any]) -> str:
    """Write ``payload`` as gzip JSON atomically and return its file hash."""

    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    blob = gzip.compress(raw, mtime=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, path)
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def load_symbol_data(path: Path) -> dict[str, Any]:
    """Read one frozen ``.json.gz`` and decode its candles to ``Candle`` lists."""

    with gzip.open(path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    payload["candles"] = {
        timeframe: [_candle_from_payload(item) for item in payload["candles"][timeframe]]
        for timeframe in TIMEFRAMES
    }
    return payload


def windows_at(
    data: dict[str, Any],
    cutoff: datetime,
) -> tuple[dict[str, list[Candle]], dict[str, list[Candle]]]:
    """Return ``(prefix, tail)`` for ``cutoff`` from frozen symbol ``data``.

    ``prefix[tf]`` is the closed-at-cutoff candles, last ``WINDOW_BARS[tf]`` kept.
    ``tail[tf]`` (H1/M15) is every candle the broker printed that is *not* part
    of the full closed-at-cutoff set, first ``TAIL_BARS[tf]`` kept — exactly the
    derivation of ``smc_real_snapshots._load_window``.
    """

    if not isinstance(cutoff, datetime):
        raise ValueError("cutoff must be a datetime")
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("cutoff must be timezone-aware")
    cutoff_utc = cutoff.astimezone(timezone.utc)

    candles = data["candles"]
    closed_by_tf = {
        timeframe: closed_candles_at_cutoff(candles[timeframe], timeframe, cutoff_utc)
        for timeframe in TIMEFRAMES
    }
    prefix = {
        timeframe: list(closed_by_tf[timeframe][-WINDOW_BARS[timeframe] :])
        for timeframe in TIMEFRAMES
    }
    tail: dict[str, list[Candle]] = {}
    for timeframe, count in TAIL_BARS.items():
        closed_times = {candle.time for candle in closed_by_tf[timeframe]}
        after = [candle for candle in candles[timeframe] if candle.time not in closed_times]
        tail[timeframe] = after[:count]
    return prefix, tail


def _timeframe_summary(candles: list[Candle]) -> dict[str, Any]:
    if not candles:
        return {"candles": 0, "first": None, "last": None}
    return {
        "candles": len(candles),
        "first": candles[0].time.astimezone(timezone.utc).isoformat(),
        "last": candles[-1].time.astimezone(timezone.utc).isoformat(),
    }


def _fetch_symbol(
    service: MT5Service,
    app_symbol: str,
    available: list[str],
    fetched_at: datetime,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Fetch one symbol.  Returns ``(data_payload, manifest_entry)``.

    ``data_payload`` is ``None`` when the symbol could not be frozen (unresolved
    broker symbol, or any timeframe fetch failed) — that symbol is then treated
    as missing data and only its reason is recorded.
    """

    broker_symbol = service.resolve_symbol(app_symbol, available)
    if not broker_symbol:
        return None, {"status": "symbol_not_found"}

    reasons: list[str] = []
    quality: dict[str, Any] = {}
    try:
        quality = service.symbol_data_quality(app_symbol, broker_symbol)
    except Exception as exc:
        reasons.append(f"quality_error:{type(exc).__name__}:{exc}")

    candles_by_tf: dict[str, list[Candle]] = {}
    for timeframe in TIMEFRAMES:
        start = fetched_at - timedelta(days=FETCH_DAYS[timeframe])
        try:
            raw = service.load_ohlcv_range(broker_symbol, timeframe, start, fetched_at)
        except Exception as exc:
            reasons.append(f"fetch_error:{timeframe}:{exc}")
            continue
        candles_by_tf[timeframe] = list(
            closed_candles_at_cutoff(raw, timeframe, fetched_at)
        )

    entry: dict[str, Any] = {"broker_symbol": broker_symbol}
    if reasons:
        entry["status"] = "; ".join(reasons)
        return None, entry

    payload = {
        "symbol": app_symbol,
        "broker_symbol": broker_symbol,
        "tick_size": quality.get("tick_size"),
        "tick_size_source": quality.get("tick_size_source"),
        "fetched_at": fetched_at.isoformat(),
        "candles": {
            timeframe: [_candle_payload(candle) for candle in candles_by_tf[timeframe]]
            for timeframe in TIMEFRAMES
        },
    }
    data_path = DATA_DIR / f"{_safe_name(app_symbol)}.json.gz"
    file_hash = _atomic_write_gzip(data_path, payload)

    entry["status"] = "ok"
    entry["tick_size"] = quality.get("tick_size")
    entry["tick_size_source"] = quality.get("tick_size_source")
    entry["sha256"] = file_hash
    entry["timeframes"] = {
        timeframe: _timeframe_summary(candles_by_tf[timeframe])
        for timeframe in TIMEFRAMES
    }
    return payload, entry


def _run_fetch(_args) -> int:
    service = MT5Service()
    if not service.connect():
        print("BLOCKED: MT5 terminal is not available")
        return 2

    fetched_at = datetime.now(timezone.utc)
    available = service.available_symbols(market_watch_only=False)
    min_rr, min_rr_status = _live_min_rr()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    symbols_manifest: dict[str, Any] = {}
    print(f"fetch @ {fetched_at.isoformat()}  min_rr={min_rr!r} ({min_rr_status})")
    print(
        f"{'symbol':10s} {'status':16s} "
        f"{'D1':>5s} {'H4':>5s} {'H1':>5s} {'M15':>5s}"
    )
    for app_symbol in SUPPORTED_SYMBOLS:
        payload, entry = _fetch_symbol(service, app_symbol, available, fetched_at)
        symbols_manifest[app_symbol] = entry
        coverage = entry.get("timeframes") or {}
        counts = [
            str(coverage.get(timeframe, {}).get("candles", "-"))
            for timeframe in TIMEFRAMES
        ]
        print(
            f"{app_symbol:10s} {str(entry['status'])[:16]:16s} "
            f"{counts[0]:>5s} {counts[1]:>5s} {counts[2]:>5s} {counts[3]:>5s}"
        )

    manifest = {
        "fetched_at": fetched_at.isoformat(),
        "min_rr": min_rr,
        "min_rr_status": min_rr_status,
        "fetch_days": FETCH_DAYS,
        "timeframes": list(TIMEFRAMES),
        "window_bars": WINDOW_BARS,
        "tail_bars": TAIL_BARS,
        "cutoff_hours_utc": list(CUTOFF_HOURS_UTC),
        "period_days": PERIOD_DAYS,
        "supported_symbols": list(SUPPORTED_SYMBOLS),
        "symbols": symbols_manifest,
    }
    _atomic_write_text(
        MANIFEST_PATH,
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    elapsed = time.perf_counter() - started
    ok_count = sum(1 for entry in symbols_manifest.values() if entry["status"] == "ok")
    print(f"\nfetch: {ok_count}/{len(SUPPORTED_SYMBOLS)} symbols ok in {elapsed:.1f}s")
    print(f"manifest -> {MANIFEST_PATH}")
    return 0


def _plan_symbol_cutoffs(
    app_symbol: str,
    broker_symbol: str,
    data: dict[str, Any],
    rejected: dict[str, int],
) -> list[dict[str, Any]]:
    h1 = data["candles"]["H1"]
    if not h1:
        return []
    last_day = h1[-1].time.astimezone(timezone.utc).date()
    first_day = last_day - timedelta(days=PERIOD_DAYS)

    kept: list[dict[str, Any]] = []
    for offset in range(PERIOD_DAYS + 1):
        day = first_day + timedelta(days=offset)
        hour = CUTOFF_HOURS_UTC[day.toordinal() % 3]
        cutoff = datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc)
        window_start = cutoff - timedelta(hours=4)
        market_open = any(window_start <= candle.time < cutoff for candle in h1)

        prefix, tail = windows_at(data, cutoff)
        missing = [
            timeframe
            for timeframe in WINDOW_BARS
            if len(prefix[timeframe]) < WINDOW_BARS[timeframe]
        ]
        tail_short = len(tail["H1"]) < TAIL_BARS["H1"]

        if not market_open:
            rejected["market_closed"] += 1
        if missing:
            rejected["insufficient_history"] += 1
        if tail_short:
            rejected["insufficient_tail"] += 1

        if market_open and not missing and not tail_short:
            kept.append(
                {
                    "symbol": app_symbol,
                    "broker_symbol": broker_symbol,
                    "cutoff": cutoff.isoformat(),
                }
            )
    return kept


def _run_plan(_args) -> int:
    if not MANIFEST_PATH.exists():
        print(f"BLOCKED: no manifest at {MANIFEST_PATH}; run `fetch` first.")
        return 2

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    cutoffs: list[dict[str, Any]] = []
    rejected = {
        "market_closed": 0,
        "insufficient_history": 0,
        "insufficient_tail": 0,
    }

    for app_symbol in sorted(manifest.get("symbols", {})):
        entry = manifest["symbols"][app_symbol]
        if entry.get("status") != "ok":
            continue
        data_path = DATA_DIR / f"{_safe_name(app_symbol)}.json.gz"
        if not data_path.exists():
            print(f"  !! {app_symbol}: manifest says ok but {data_path.name} missing")
            continue
        data = load_symbol_data(data_path)
        cutoffs.extend(
            _plan_symbol_cutoffs(
                app_symbol,
                entry.get("broker_symbol", app_symbol),
                data,
                rejected,
            )
        )

    cutoffs.sort(key=lambda item: (item["symbol"], item["cutoff"]))

    by_symbol: dict[str, int] = {}
    by_hour = {str(hour): 0 for hour in CUTOFF_HOURS_UTC}
    by_month: dict[str, int] = {}
    for item in cutoffs:
        cutoff = datetime.fromisoformat(item["cutoff"])
        by_symbol[item["symbol"]] = by_symbol.get(item["symbol"], 0) + 1
        by_hour[str(cutoff.hour)] = by_hour.get(str(cutoff.hour), 0) + 1
        month = cutoff.strftime("%Y-%m")
        by_month[month] = by_month.get(month, 0) + 1

    summary = {
        "total": len(cutoffs),
        "by_symbol": dict(sorted(by_symbol.items())),
        "by_hour": dict(sorted(by_hour.items(), key=lambda kv: int(kv[0]))),
        "by_month": dict(sorted(by_month.items())),
        "rejected": rejected,
    }
    _atomic_write_text(
        CUTOFFS_PATH,
        json.dumps(
            {"cutoffs": cutoffs, "summary": summary},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    print(f"plan: {len(cutoffs)} cutoffs")
    print(f"  by_hour: {summary['by_hour']}")
    print(f"  by_month: {summary['by_month']}")
    print(f"  rejected: {rejected}")
    print(f"cutoffs -> {CUTOFFS_PATH}")
    return 0


def _run_verify(_args) -> int:
    if not CUTOFFS_PATH.exists():
        print(f"BLOCKED: no cutoffs at {CUTOFFS_PATH}; run `plan` first.")
        return 2
    if not MANIFEST_PATH.exists():
        print(f"BLOCKED: no manifest at {MANIFEST_PATH}; run `fetch` first.")
        return 2

    cutoffs = json.loads(CUTOFFS_PATH.read_text(encoding="utf-8"))["cutoffs"]
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    symbols_manifest = manifest.get("symbols", {})

    problems: list[str] = []
    data_cache: dict[str, dict[str, Any]] = {}
    for item in cutoffs:
        symbol = item["symbol"]
        cutoff = datetime.fromisoformat(item["cutoff"])
        label = f"{symbol}@{item['cutoff']}"
        data_path = DATA_DIR / f"{_safe_name(symbol)}.json.gz"

        if symbol not in data_cache:
            if not data_path.exists():
                problems.append(f"{label}: data file missing")
                continue
            data_cache[symbol] = load_symbol_data(data_path)
            expected_hash = (symbols_manifest.get(symbol) or {}).get("sha256")
            actual_hash = _file_sha256(data_path)
            if expected_hash != actual_hash:
                problems.append(f"{label}: file hash {actual_hash} != manifest {expected_hash}")
        data = data_cache[symbol]

        prefix, tail = windows_at(data, cutoff)
        for timeframe in TIMEFRAMES:
            closed_all = closed_candles_at_cutoff(
                data["candles"][timeframe], timeframe, cutoff
            )
            if len(prefix[timeframe]) != WINDOW_BARS[timeframe]:
                problems.append(
                    f"{label}: {timeframe} prefix {len(prefix[timeframe])} "
                    f"!= {WINDOW_BARS[timeframe]}"
                )
            if prefix[timeframe] != list(closed_all[-WINDOW_BARS[timeframe] :]):
                problems.append(f"{label}: {timeframe} prefix != closed-at-cutoff window")
            for candle in prefix[timeframe]:
                if candle_close_at(candle.time, timeframe) > cutoff:
                    problems.append(f"{label}: {timeframe} prefix candle closes after cutoff")
                    break

        for timeframe, count in TAIL_BARS.items():
            for candle in tail[timeframe]:
                if candle.time < cutoff:
                    problems.append(f"{label}: {timeframe} tail candle before cutoff")
                    break
            if len(tail[timeframe]) != count:
                problems.append(
                    f"{label}: {timeframe} tail {len(tail[timeframe])} != {count}"
                )

    if problems:
        for line in problems[:20]:
            print(f"  {line}")
        print(f"verify: {len(cutoffs)} cutoffs, {len(problems)} problems")
        return 1
    print(f"verify: {len(cutoffs)} cutoffs, 0 problems")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Frozen MT5 history corpus builder (task SD-C1)"
    )
    parser.add_argument("command", choices=("fetch", "plan", "verify"))
    args = parser.parse_args()
    if args.command == "fetch":
        return _run_fetch(args)
    if args.command == "plan":
        return _run_plan(args)
    return _run_verify(args)


if __name__ == "__main__":
    raise SystemExit(main())
