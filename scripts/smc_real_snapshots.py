"""Real-snapshot corpus collector for the SMC acceptance chain (task 131).

Run:  python -X utf8 scripts/smc_real_snapshots.py collect
      python -X utf8 scripts/smc_real_snapshots.py report
      python -X utf8 scripts/smc_real_snapshots.py verify

This is a *tool*, not runtime: nothing here is wired into the live scanner, it
never sends an order, it never writes into operational storage (journal, open
orders, SL/TP) and it never fabricates data.  Every row it stores comes from the
broker's own history through ``services.mt5_service.MT5Service``.

What one row carries (task 15 §4 and task 131):

* ``symbol`` / ``broker_symbol`` plus the terminal that served the history;
* ``as_of`` — the cutoff the snapshot was frozen at, and ``captured_at`` — the
  real wall clock of the fetch that produced the row;
* the closed candles of every timeframe, already filtered at the cutoff, plus
  the *future tail* the broker returned after the cutoff.  The tail is stored
  separately on purpose: the replay task re-feeds ``prefix + tail`` through the
  same seam and compares it with ``prefix`` alone, which is how "no future leak"
  becomes a checkable claim instead of a comment;
* per-timeframe coverage, the tick size and where it came from, the canonical
  input digest (``smc_snapshot_identity``), the rule identity/versions, and the
  core reason codes the seam itself reported;
* the observed SMC verdict of both sides (state, readiness, selected zone/setup,
  raw, plan availability) read from the canonical result — never re-derived.

A snapshot whose window is short is kept as-is: an insufficient input is a real
data-quality observation and is reported, not patched.  Nothing in this file
defaults a cutoff, fills a missing timeframe or scores a forming candle.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.market_models import Candle, closed_candles_at_cutoff  # noqa: E402
from core.scanner_live_producers import derive_live_analysis  # noqa: E402
from core.smc_snapshot_cache import (  # noqa: E402
    smc_rule_versions,
    smc_snapshot_identity,
)
from services.mt5_service import MT5Service  # noqa: E402

OUTPUT_DIR = PROJECT_ROOT / "reports" / "scanner" / "smc_real_snapshots"
CORPUS_PATH = OUTPUT_DIR / "corpus.jsonl.gz"
REPORT_PATH = OUTPUT_DIR / "report.json"

# Production bar counts (config/settings.py AdvancedSettings) — the corpus must
# be the same shape the live scanner feeds the seam, otherwise the numbers would
# describe a different workload.
CORE_BARS = 500
M15_BARS = 100
TIMEFRAMES = ("D1", "H4", "H1", "M15")

# How much history to request *before* the cutoff, per timeframe, so that
# ``CORE_BARS`` closed candles exist even across holidays and weekend gaps.
LOOKBACK_DAYS = {"D1": 900, "H4": 300, "H1": 120, "M15": 20}
# How much history to request *after* the cutoff for the stored future tail.
TAIL_BARS = {"D1": 5, "H4": 10, "H1": 24, "M15": 48}

# The fixed plan.  Cutoffs are broker-server times (the app's candle convention)
# at a mid-session hour of a trading day; the plan is deliberately spread over
# different regimes instead of hand-picked winners, and the matrix report below
# states which group each row actually landed in — a row is never labelled from
# the intent that produced it.
SNAPSHOT_PLAN: tuple[tuple[str, str], ...] = (
    ("EUR/USD", "2026-02-19T12:00:00Z"),
    ("EUR/USD", "2026-04-16T12:00:00Z"),
    ("EUR/USD", "2026-06-11T12:00:00Z"),
    ("EUR/USD", "2026-07-23T12:00:00Z"),
    ("EUR/USD", "2026-09-03T12:00:00Z"),
    ("GBP/USD", "2026-02-19T12:00:00Z"),
    ("GBP/USD", "2026-04-16T12:00:00Z"),
    ("GBP/USD", "2026-06-11T12:00:00Z"),
    ("GBP/USD", "2026-07-23T12:00:00Z"),
    ("GBP/USD", "2026-09-03T12:00:00Z"),
    ("USD/JPY", "2026-02-19T12:00:00Z"),
    ("USD/JPY", "2026-04-16T12:00:00Z"),
    ("USD/JPY", "2026-06-11T12:00:00Z"),
    ("USD/JPY", "2026-07-23T12:00:00Z"),
    ("USD/JPY", "2026-09-03T12:00:00Z"),
    ("AUD/USD", "2026-02-19T12:00:00Z"),
    ("AUD/USD", "2026-04-16T12:00:00Z"),
    ("AUD/USD", "2026-06-11T12:00:00Z"),
    ("AUD/USD", "2026-07-23T12:00:00Z"),
    ("AUD/USD", "2026-09-03T12:00:00Z"),
    ("USD/CAD", "2026-02-19T12:00:00Z"),
    ("USD/CAD", "2026-04-16T12:00:00Z"),
    ("USD/CAD", "2026-06-11T12:00:00Z"),
    ("USD/CAD", "2026-07-23T12:00:00Z"),
    ("USD/CAD", "2026-09-03T12:00:00Z"),
    ("XAU/USD", "2026-02-19T12:00:00Z"),
    ("XAU/USD", "2026-04-16T12:00:00Z"),
    ("XAU/USD", "2026-06-11T12:00:00Z"),
    ("XAU/USD", "2026-07-23T12:00:00Z"),
    ("XAU/USD", "2026-09-03T12:00:00Z"),
    ("EUR/GBP", "2026-02-19T12:00:00Z"),
    ("EUR/GBP", "2026-04-16T12:00:00Z"),
    ("EUR/GBP", "2026-06-11T12:00:00Z"),
    ("EUR/GBP", "2026-07-23T12:00:00Z"),
    ("EUR/GBP", "2026-09-03T12:00:00Z"),
    ("GBP/JPY", "2026-02-19T12:00:00Z"),
    ("GBP/JPY", "2026-04-16T12:00:00Z"),
    ("GBP/JPY", "2026-06-11T12:00:00Z"),
    ("GBP/JPY", "2026-07-23T12:00:00Z"),
    ("GBP/JPY", "2026-09-03T12:00:00Z"),
    ("BTC/USD", "2026-02-19T12:00:00Z"),
    ("BTC/USD", "2026-04-16T12:00:00Z"),
    ("BTC/USD", "2026-06-11T12:00:00Z"),
    ("BTC/USD", "2026-07-23T12:00:00Z"),
    ("BTC/USD", "2026-09-03T12:00:00Z"),
    ("AUD/NZD", "2026-03-12T12:00:00Z"),
    ("AUD/NZD", "2026-05-14T12:00:00Z"),
    ("AUD/NZD", "2026-08-13T12:00:00Z"),
    ("AUD/NZD", "2026-09-03T09:00:00Z"),
    ("AUD/NZD", "2026-08-03T09:00:00Z"),
    ("NZD/USD", "2026-03-12T12:00:00Z"),
    ("NZD/USD", "2026-05-14T12:00:00Z"),
    ("NZD/USD", "2026-08-13T12:00:00Z"),
    ("NZD/USD", "2026-09-03T09:00:00Z"),
    ("NZD/USD", "2026-08-03T09:00:00Z"),
)

# Data-quality rows are collected by BROKER symbol, because the instruments that
# actually expose a partial feed on this broker are ones the application has no
# profile for (BWP/USD, SOL/USD, DOGE/USD, ADA/USD).  They are real terminal
# symbols with real, partial history — used only to exercise the fail-closed
# data-quality path on real bytes, and labelled as such in every artifact.  No
# value here is synthetic and nothing is trimmed to force a state: the counts in
# the corpus are whatever the broker returned.
DATA_QUALITY_PLAN: tuple[tuple[str, str], ...] = (
    ("BWPUSDm", "2026-09-03T12:00:00Z"),   # M15 short (27 bars) + H1 short
    ("BWPUSDm", "2026-06-11T12:00:00Z"),
    ("SOLUSDm", "2026-09-03T12:00:00Z"),   # D1 short (454 bars)
    ("DOGEUSDm", "2026-09-03T12:00:00Z"),  # H4/H1 empty: core coverage gap
    ("ADAUSDm", "2026-09-03T12:00:00Z"),   # H4/H1 empty: core coverage gap
)


def _cutoff(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"cutoff must be timezone-aware: {value}")
    return parsed


def _candle_payload(candle: Candle) -> dict[str, Any]:
    return {
        "t": candle.time.astimezone(timezone.utc).isoformat(),
        "o": candle.open,
        "h": candle.high,
        "l": candle.low,
        "c": candle.close,
        "v": candle.volume,
    }


def _candle_from_payload(payload: dict[str, Any]) -> Candle:
    return Candle(
        time=datetime.fromisoformat(str(payload["t"])),
        open=float(payload["o"]),
        high=float(payload["h"]),
        low=float(payload["l"]),
        close=float(payload["c"]),
        volume=float(payload.get("v") or 0.0),
    )


def _digest(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _terminal_provenance(service: MT5Service) -> dict[str, Any]:
    """Terminal identity of the data source — never the account number."""

    try:
        import MetaTrader5 as mt5
    except ImportError:  # pragma: no cover - MT5 is the documented source
        return {"available": False}
    info = mt5.terminal_info()
    if info is None:
        return {"available": False, "last_error": list(mt5.last_error() or ())}
    return {
        "available": True,
        "name": getattr(info, "name", None),
        "company": getattr(info, "company", None),
        "build": getattr(info, "build", None),
        "connected": getattr(info, "connected", None),
        "trade_allowed": getattr(info, "trade_allowed", None),
        "data_path_hash": _digest(str(getattr(info, "data_path", "")))[:23],
    }


def _load_window(
    service: MT5Service,
    broker_symbol: str,
    timeframe: str,
    cutoff: datetime,
) -> tuple[list[Candle], list[Candle], dict[str, Any]]:
    """Return ``(closed_at_cutoff, future_tail, fetch_notes)`` from the broker.

    The prefix is the broker's own bars whose real close boundary is at or
    before the cutoff; the tail is what the broker returned after it.  Both come
    from one ``copy_rates_range`` call so the two sets cannot disagree about the
    bar that straddles the cutoff.
    """

    start = cutoff - timedelta(days=LOOKBACK_DAYS[timeframe])
    horizon = cutoff + timedelta(days=max(1, LOOKBACK_DAYS[timeframe] // 20))
    notes: dict[str, Any] = {
        "requested_from": start.isoformat(),
        "requested_to": horizon.isoformat(),
    }
    try:
        fetched = service.load_ohlcv_range(broker_symbol, timeframe, start, horizon)
    except Exception as exc:  # broker has nothing for this window — a real state
        notes["error"] = str(exc)
        return [], [], {**notes, "fetched": 0, "closed_at_cutoff": 0, "future_tail": 0}
    closed_all = list(closed_candles_at_cutoff(fetched, timeframe, cutoff))
    # The tail is everything the broker printed AT OR AFTER the cutoff.  It must
    # be derived from the full closed set, not from the truncated window: a
    # candle that is closed but fell outside the production bar count belongs to
    # neither the stored prefix nor the future tail.
    cutoff_candle_times = {candle.time for candle in closed_all}
    tail = [candle for candle in fetched if candle.time not in cutoff_candle_times]
    limit = CORE_BARS if timeframe != "M15" else M15_BARS
    notes.update(
        {
            "fetched": len(fetched),
            "closed_at_cutoff": len(closed_all),
            "future_tail": len(tail),
            "used": min(len(closed_all), limit),
        }
    )
    return closed_all[-limit:], tail[: TAIL_BARS[timeframe]], notes


def _side_observed(selection: Any) -> dict[str, Any]:
    if selection is None:
        return {
            "state": None,
            "readiness_status": None,
            "smc_state": None,
            "selected_zone_id": None,
            "selected_setup_id": None,
            "quality_raw": None,
            "plan_available": False,
            "lifecycle_status": None,
        }
    readiness = getattr(selection, "readiness", None)
    quality = getattr(selection, "quality", None)
    selected = getattr(selection, "selected", None)
    return {
        "state": getattr(selection, "state", None),
        "readiness_status": getattr(readiness, "status", None),
        "smc_state": getattr(readiness, "smc_state", None),
        "selected_zone_id": getattr(selection, "selected_zone_id", None),
        "selected_setup_id": getattr(selection, "selected_setup_id", None),
        "quality_raw": getattr(selection, "selected_quality_raw", None),
        "plan_available": bool(getattr(selection, "plan_available", False)),
        "lifecycle_status": getattr(selected, "lifecycle_status", None),
        "timeframe": getattr(selected, "timeframe", None),
        "family": getattr(selected, "family", None),
        "reason_codes": sorted(
            set(getattr(readiness, "reason_codes", ()) or ())
            | set(getattr(selection, "selection_reason_codes", ()) or ())
        ),
    }


def _classify(row: dict[str, Any]) -> dict[str, Any]:
    """Describe what the canonical chain actually reported — no intent."""

    structure = row["context_structure"]
    events = row.get("context_events") or {}
    confluence = row.get("confluence") or {}
    d1 = str(structure.get("D1") or "unknown")
    h4 = str(structure.get("H4") or "unknown")
    h1 = str(structure.get("H1") or "unknown")
    # The tracked trend follows the parent timeframes; H1 alone is the entry
    # horizon and a reversal there is not a trend change.
    if h4 in {"HH/HL", "LH/LL"}:
        trend = "up" if h4 == "HH/HL" else "down"
    elif d1 in {"HH/HL", "LH/LL"}:
        trend = "up" if d1 == "HH/HL" else "down"
    else:
        trend = "range"

    sides = row["sides"]
    states = {side: sides[side]["state"] for side in ("buy", "sell")}
    terminal_states = {"out_of_strategy", "no_zone", "data_unavailable", "blocked"}
    dead_states = {"ZONE_INVALIDATED", "ZONE_EXPIRED", "ZONE_CONSUMED"}
    # "Bad zone" is read from the lifecycle the chain itself reported, not from
    # whether a zone id survived: an invalidated zone is reported with its
    # identity dropped, and that is exactly the case the QA has to cover.
    dead_sides = [
        side for side in ("buy", "sell") if sides[side]["smc_state"] in dead_states
    ]
    live_sides = [
        side
        for side in ("buy", "sell")
        if sides[side]["selected_zone_id"] and sides[side]["state"] not in terminal_states
    ]
    if dead_sides and not live_sides:
        zone_quality = "invalid"
    elif dead_sides:
        zone_quality = "mixed"
    elif live_sides:
        zone_quality = "good"
    else:
        zone_quality = "none"

    choch = any(
        layer.get("choch") or layer.get("choch_confirmed")
        for layer in events.values()
    )
    countertrend_codes = {
        code
        for side in ("buy", "sell")
        for code in sides[side]["reason_codes"]
        if "COUNTERTREND" in code
    }
    against = _countertrend(row, trend)
    if countertrend_codes:
        countertrend = "countertrend_unconfirmed"
    elif against:
        countertrend = "countertrend_selected"
    elif choch:
        countertrend = "choch"
    else:
        countertrend = "none"

    quality_gaps = []
    if not row["coverage"]["M15"]:
        quality_gaps.append("M15_EMPTY")
    elif row["coverage"]["M15"] < M15_BARS:
        quality_gaps.append("M15_INSUFFICIENT")
    if not row["coverage"]["H4"] or not row["coverage"]["H1"]:
        quality_gaps.append("CORE_TIMEFRAME_EMPTY")
    for timeframe in ("D1", "H4", "H1"):
        if 0 < row["coverage"][timeframe] < CORE_BARS:
            quality_gaps.append(f"{timeframe}_SHORT")
    quality_gaps.extend(row["core_reason_codes"])
    if row["tick_size"] is None:
        quality_gaps.append("SMC_TICK_SIZE_UNAVAILABLE")
    quality_gaps.extend(row.get("plan_policy_status") or ())

    return {
        "trend": trend,
        # "mixed" means the two parent timeframes disagree: the tracked trend is
        # not one-directional, which is the neutral/range case of the matrix.
        "structure_agreement": (
            "mixed"
            if d1 in {"HH/HL", "LH/LL"} and h4 in {"HH/HL", "LH/LL"} and d1 != h4
            else ("unknown" if h4 == "unknown" and d1 == "unknown" else "aligned")
        ),
        "zone_quality": zone_quality,
        "dead_zone_sides": dead_sides,
        "live_zone_sides": live_sides,
        "countertrend": countertrend,
        "countertrend_reason_codes": sorted(countertrend_codes),
        "data_quality": sorted(set(quality_gaps)),
        "m15_present": bool(row["coverage"]["M15"]),
        "has_selected_zone": any(sides[side]["selected_zone_id"] for side in ("buy", "sell")),
        "plan_available": {
            side: bool(sides[side]["plan_available"]) for side in ("buy", "sell")
        },
        "selected_sides": live_sides,
        "confluence_direction": confluence.get("direction"),
    }


def _countertrend(row: dict[str, Any], trend: str) -> bool:
    """A side bet against the tracked trend that still reached a selection."""

    sides = row["sides"]
    dead = {"out_of_strategy", "no_zone", "data_unavailable", "blocked"}
    if trend == "up":
        return bool(sides["sell"]["selected_zone_id"]) and sides["sell"]["state"] not in dead
    if trend == "down":
        return bool(sides["buy"]["selected_zone_id"]) and sides["buy"]["state"] not in dead
    return False


def _structure_of(context: Mapping[str, Any], timeframe: str) -> str | None:
    """The tracked structure vocabulary of one timeframe, as reported."""

    layer = context.get(timeframe)
    if not isinstance(layer, Mapping):
        return None
    structure = layer.get("structure")
    if isinstance(structure, Mapping):
        return structure.get("structure")
    return structure if isinstance(structure, str) else None


def collect_one(
    service: MT5Service,
    app_symbol: str,
    broker_symbol: str,
    cutoff: datetime,
    *,
    data_quality: dict[str, Any],
    min_rr: Any = None,
    group: str = "configured_symbol",
) -> dict[str, Any]:
    windows: dict[str, list[Candle]] = {}
    tails: dict[str, list[Candle]] = {}
    fetch_notes: dict[str, Any] = {}
    for timeframe in TIMEFRAMES:
        closed, tail, notes = _load_window(service, broker_symbol, timeframe, cutoff)
        windows[timeframe] = closed
        tails[timeframe] = tail
        fetch_notes[timeframe] = notes

    captured_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    analysis = derive_live_analysis(
        windows["D1"],
        windows["H4"],
        windows["H1"],
        symbol=app_symbol,
        captured_at=cutoff,
        news_in_3h=False,
        m15_candles=windows["M15"],
        m15_as_of=cutoff,
        tick_size=data_quality.get("tick_size"),
        tick_size_source=data_quality.get("tick_size_source"),
        min_rr=min_rr,
    )
    elapsed = time.perf_counter() - started

    snapshot = analysis["smc_snapshot"]
    evaluation = analysis["smc_evaluation"]
    context = snapshot.smc if isinstance(snapshot.smc, dict) else {}
    selection_payload = evaluation.to_dict()["sides"]

    identity = smc_snapshot_identity(
        symbol=app_symbol,
        as_of=cutoff,
        candles_by_timeframe=windows,
        metadata={
            "tick_size": snapshot.tick_size,
            "tick_size_source": snapshot.tick_size_source,
        },
    )

    row: dict[str, Any] = {
        "row_version": "smc-real-snapshot-v1",
        "symbol": app_symbol,
        "broker_symbol": broker_symbol,
        "symbol_group": group,
        "source": "mt5_history",
        "as_of": cutoff.isoformat(),
        "captured_at": captured_at.isoformat(),
        "terminal": _terminal_provenance(service),
        "timeframes": list(TIMEFRAMES),
        "coverage": {tf: len(windows[tf]) for tf in TIMEFRAMES},
        "fetch": fetch_notes,
        "tick_size": snapshot.tick_size,
        "tick_size_source": snapshot.tick_size_source,
        "core_reason_codes": list(snapshot.core_reason_codes),
        "rule_versions": smc_rule_versions(),
        "snapshot_identity": identity,
        "candles_digest": _digest(
            {tf: [_candle_payload(c) for c in windows[tf]] for tf in TIMEFRAMES}
        ),
        "evaluation_version": evaluation.evaluation_version,
        "evaluate_seconds": round(elapsed, 4),
        "context_structure": {
            timeframe: _structure_of(context, timeframe)
            for timeframe in ("D1", "H4", "H1")
        },
        "context_events": {
            timeframe: {
                "bos": bool((context.get(timeframe) or {}).get("bos")),
                "choch": bool((context.get(timeframe) or {}).get("choch")),
                "choch_confirmed": bool(
                    (context.get(timeframe) or {}).get("choch_confirmed")
                ),
            }
            for timeframe in ("D1", "H4", "H1")
        },
        "confluence": context.get("confluence"),
        "min_rr": min_rr,
        "sides": {
            side: _side_observed(evaluation.selection(side)) for side in ("buy", "sell")
        },
        "selection_payload": selection_payload,
        "candles": {
            tf: [_candle_payload(c) for c in windows[tf]] for tf in TIMEFRAMES
        },
        "future_tail": {tf: [_candle_payload(c) for c in tails[tf]] for tf in TIMEFRAMES},
    }
    row["classification"] = _classify(row)
    return row


def _write_corpus(rows: Sequence[dict[str, Any]]) -> str:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with gzip.open(CORPUS_PATH, "wt", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            line = json.dumps(row, ensure_ascii=False, sort_keys=True)
            digest.update(line.encode("utf-8"))
            handle.write(line + "\n")
    return "sha256:" + digest.hexdigest()


def _with_classification(
    rows: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Recompute the derived view from the stored observations.

    The classification is a *reading* of what the canonical chain reported, so
    it is recomputed from the stored row instead of being trusted as a frozen
    label — a row collected under an older reading must not keep a verdict the
    current reading would not produce.
    """

    refreshed: list[dict[str, Any]] = []
    for row in rows:
        updated = dict(row)
        updated["classification"] = _classify(row)
        refreshed.append(updated)
    return refreshed


def read_corpus(path: Path | None = None) -> list[dict[str, Any]]:
    source = path or CORPUS_PATH
    with gzip.open(source, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def build_matrix(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Coverage of the task 15 §4 matrix measured from the rows themselves.

    The definitions are stated here so the Tech Lead can challenge them instead
    of having to reverse-engineer them:

    * ``trend_up``/``trend_down`` follow the tracked H4 structure (D1 when H4 is
      unknown);
    * ``range`` is the neutral group: the parent timeframes disagree (mixed) or
      both are unknown — a side is never defaulted to a direction there;
    * ``zone_invalid`` counts rows where the chain reported a dead lifecycle
      (``ZONE_INVALIDATED``/``ZONE_EXPIRED``/``ZONE_CONSUMED``) with no live zone
      left, and ``zone_mixed`` the rows that reported both;
    * ``data_quality_gap`` counts rows whose broker window was actually short
      (M15 empty/insufficient, an empty core timeframe, or a short core window).
    """

    groups: dict[str, list[str]] = {
        "trend_up": [],
        "trend_down": [],
        "range": [],
        "zone_good": [],
        "zone_invalid": [],
        "zone_mixed": [],
        "zone_none": [],
        "countertrend": [],
        "m15_present": [],
        "m15_absent_or_short": [],
        "data_quality_gap": [],
        "configured_symbol": [],
        "broker_symbol_only": [],
    }
    for row in rows:
        label = f"{row['symbol']}@{row['as_of']}"
        verdict = row["classification"]
        if verdict["trend"] == "up":
            groups["trend_up"].append(label)
        elif verdict["trend"] == "down":
            groups["trend_down"].append(label)
        if verdict.get("structure_agreement") != "aligned":
            groups["range"].append(label)
        zone_quality = verdict["zone_quality"]
        if zone_quality in ("good", "mixed"):
            groups["zone_good"].append(label)
        if zone_quality in ("invalid", "mixed"):
            groups["zone_invalid"].append(label)
        if zone_quality == "mixed":
            groups["zone_mixed"].append(label)
        if zone_quality == "none":
            groups["zone_none"].append(label)
        if verdict["countertrend"] != "none":
            groups["countertrend"].append(label)
        if verdict["m15_present"] and row["coverage"]["M15"] >= M15_BARS:
            groups["m15_present"].append(label)
        else:
            groups["m15_absent_or_short"].append(label)
        if verdict["data_quality"]:
            groups["data_quality_gap"].append(label)
        if row.get("symbol_group") == "broker_symbol_only":
            groups["broker_symbol_only"].append(label)
        else:
            groups["configured_symbol"].append(label)

    required = {
        "trend_up": 4,
        "trend_down": 4,
        "range": 4,
        "zone_good": 4,
        "zone_invalid": 4,
        "countertrend": 3,
        "data_quality_gap": 3,
        "m15_absent_or_short": 1,
    }
    shortfalls = {
        name: {"required": minimum, "observed": len(groups[name])}
        for name, minimum in required.items()
        if len(groups[name]) < minimum
    }
    return {
        "row_count": len(rows),
        "definitions": {
            "range": "parent timeframes disagree (mixed) or both unknown",
            "zone_invalid": "a dead zone lifecycle was reported",
            "data_quality_gap": "the broker window was genuinely short",
            "m15_absent_or_short": "fewer than the production M15 window",
        },
        "groups": {
            name: {"count": len(value), "rows": value} for name, value in groups.items()
        },
        "required_minimums": required,
        "shortfalls": shortfalls,
        "matrix_complete": not shortfalls,
    }


def _live_min_rr() -> tuple[Any, str]:
    """The R:R floor the live Scanner applies, or the reason it is absent."""

    try:
        from core.scanner_order_policy import load_runtime_order_policy

        policy = load_runtime_order_policy()
    except Exception as exc:  # fail-closed exactly like the controller does
        return None, f"order_policy_unavailable:{type(exc).__name__}"
    threshold = getattr(policy, "threshold", None)
    value = getattr(threshold, "min_risk_reward", None)
    if value is None:
        return None, "order_policy_without_min_rr"
    return float(value), "loaded"


def _run_collect(args) -> int:
    service = MT5Service()
    if not service.connect():
        print("BLOCKED: MT5 terminal is not available; no real snapshot can be collected.")
        return 2
    available = service.available_symbols(market_watch_only=False)
    # The live Scanner passes the owner order policy's R:R floor into the same
    # seam; using anything else would build the corpus against a different plan
    # policy than production runs.
    min_rr, policy_status = _live_min_rr()
    print(f"order policy min_rr={min_rr!r} ({policy_status})")

    existing: list[dict[str, Any]] = []
    if args.merge and CORPUS_PATH.exists():
        existing = read_corpus()
        print(f"merging into {len(existing)} already-collected rows")
    seen = {(row["symbol"], row["as_of"]) for row in existing}

    plan: list[tuple[str, str, str]] = [
        (app, cutoff, "configured_symbol") for app, cutoff in SNAPSHOT_PLAN
    ]
    if args.data_quality:
        plan = [
            (broker, cutoff, "broker_symbol_only")
            for broker, cutoff in DATA_QUALITY_PLAN
        ] + plan

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    quality_cache: dict[str, dict[str, Any]] = {}
    if args.limit:
        plan = plan[: args.limit]
    for app_symbol, cutoff_text, group in plan:
        cutoff = _cutoff(cutoff_text)
        if (app_symbol, cutoff.isoformat()) in seen:
            continue
        if group == "broker_symbol_only":
            broker_symbol = app_symbol if app_symbol in available else None
        else:
            broker_symbol = service.resolve_symbol(app_symbol, available)
        if not broker_symbol:
            failures.append({"symbol": app_symbol, "as_of": cutoff_text, "error": "unresolved_symbol"})
            continue
        if broker_symbol not in quality_cache:
            quality_cache[broker_symbol] = service.symbol_data_quality(app_symbol, broker_symbol)
        try:
            row = collect_one(
                service,
                app_symbol,
                broker_symbol,
                cutoff,
                data_quality=quality_cache[broker_symbol],
                min_rr=min_rr,
                group=group,
            )
        except Exception as exc:  # a real failure is recorded, never papered over
            failures.append(
                {"symbol": app_symbol, "as_of": cutoff_text, "error": f"{type(exc).__name__}: {exc}"}
            )
            print(f"  !! {app_symbol}@{cutoff_text}: {type(exc).__name__}: {exc}")
            continue
        row["plan_policy_status"] = [policy_status] if policy_status != "loaded" else []
        row["classification"] = _classify(row)
        rows.append(row)
        verdict = row["classification"]
        print(
            f"  {app_symbol:8s} {row['as_of']}  trend={verdict['trend']:5s} "
            f"zone={verdict['zone_quality']:7s}  cov="
            f"{row['coverage']['D1']}/{row['coverage']['H4']}/{row['coverage']['H1']}/{row['coverage']['M15']} "
            f" gaps={verdict['data_quality']} {row['evaluate_seconds']}s"
        )

    if not rows:
        print("BLOCKED: every planned snapshot failed; the existing corpus is left untouched.")
        return 1
    combined = _with_classification(existing + rows)
    corpus_digest = _write_corpus(combined)
    report = {
        "report_version": "smc-real-snapshot-report-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commanded_rows": len(plan),
        "collected_this_run": len(rows),
        "corpus_rows": len(combined),
        "failures": failures,
        "corpus_digest": corpus_digest,
        "corpus_path": str(CORPUS_PATH.relative_to(PROJECT_ROOT)),
        "matrix": build_matrix(combined),
        "rule_versions": smc_rule_versions(),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"\ncollected {len(rows)} new rows ({len(combined)} total) -> {CORPUS_PATH}")
    print(json.dumps(report["matrix"]["shortfalls"], ensure_ascii=False))
    return 0


def _run_report(args) -> int:
    if not CORPUS_PATH.exists():
        print(f"BLOCKED: no corpus at {CORPUS_PATH}; run `collect` first.")
        return 2
    rows = _with_classification(read_corpus())
    matrix = build_matrix(rows)
    payload = {"corpus_rows": len(rows), "matrix": matrix}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if getattr(args, "write", False):
        REPORT_PATH.write_text(
            json.dumps(
                {
                    "report_version": "smc-real-snapshot-report-v1",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "corpus_path": str(CORPUS_PATH.relative_to(PROJECT_ROOT)),
                    "corpus_rows": len(rows),
                    "matrix": matrix,
                    "rule_versions": smc_rule_versions(),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"report -> {REPORT_PATH}")
    return 0


def _run_repair(args) -> int:
    """Re-derive the stored future tails exactly, without touching the broker.

    The first collection pass built the tail from the *truncated* closed window
    instead of the full one, so a tail could carry a candle that is closed at
    the cutoff (caught by this tool's own ``verify``).  The correct tail is
    exactly "the bars at or after the cutoff", which is recoverable from the
    stored row without refetching: dropping every tail candle before the cutoff
    leaves the genuine after-cutoff bars.  The stored *prefix* is untouched —
    it was never affected.
    """

    if not CORPUS_PATH.exists():
        print(f"BLOCKED: no corpus at {CORPUS_PATH}; run `collect` first.")
        return 2
    rows = read_corpus()
    changed = 0
    for row in rows:
        cutoff = datetime.fromisoformat(row["as_of"])
        for timeframe in TIMEFRAMES:
            kept = [
                candle
                for candle in row["future_tail"].get(timeframe) or []
                if datetime.fromisoformat(candle["t"]) >= cutoff
            ]
            if len(kept) != len(row["future_tail"].get(timeframe) or []):
                changed += 1
                row["future_tail"][timeframe] = kept
        row["future_tail_policy"] = "bars at or after the cutoff"
    digest = _write_corpus(_with_classification(rows))
    print(f"repaired {changed} timeframe tails across {len(rows)} rows")
    print(f"corpus digest -> {digest}")
    return 0


def _run_verify(_args) -> int:
    """Re-check the stored corpus without touching the network."""

    if not CORPUS_PATH.exists():
        print(f"BLOCKED: no corpus at {CORPUS_PATH}; run `collect` first.")
        return 2
    rows = read_corpus()
    problems: list[str] = []
    for row in rows:
        label = f"{row['symbol']}@{row['as_of']}"
        for timeframe in TIMEFRAMES:
            for candle in row["candles"][timeframe]:
                if datetime.fromisoformat(candle["t"]) >= datetime.fromisoformat(row["as_of"]):
                    problems.append(f"{label}: {timeframe} prefix candle at/after cutoff")
        if row["coverage"]["D1"] != len(row["candles"]["D1"]):
            problems.append(f"{label}: coverage disagrees with stored D1 candles")
        expected = _digest(
            {tf: row["candles"][tf] for tf in TIMEFRAMES}
        )
        if expected != row["candles_digest"]:
            problems.append(f"{label}: candle digest does not match stored candles")
        tail_before = [
            candle
            for timeframe in TIMEFRAMES
            for candle in row["future_tail"][timeframe]
            if datetime.fromisoformat(candle["t"]) < datetime.fromisoformat(row["as_of"])
        ]
        if tail_before:
            problems.append(f"{label}: future tail carries a candle before the cutoff")
    print(json.dumps({"rows": len(rows), "problems": problems}, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Real-snapshot corpus collector (task 131)")
    parser.add_argument("command", choices=("collect", "report", "verify", "repair"))
    parser.add_argument("--limit", type=int, default=0, help="only the first N planned snapshots")
    parser.add_argument(
        "--merge",
        action="store_true",
        help="keep rows already in the corpus and append the new ones",
    )
    parser.add_argument(
        "--data-quality",
        action="store_true",
        help="also collect the real partial-feed rows (broker symbols without an app profile)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="with `report`: also write report.json (no re-evaluation, no network)",
    )
    args = parser.parse_args()
    if args.command == "collect":
        return _run_collect(args)
    if args.command == "report":
        return _run_report(args)
    if args.command == "repair":
        return _run_repair(args)
    return _run_verify(args)


if __name__ == "__main__":
    raise SystemExit(main())
