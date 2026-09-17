"""Short replay parity check on real closed candles (task 133).

Run:
    python -X utf8 scripts/smc_replay_parity.py --report reports/scanner/smc_real_snapshots/replay_parity.json

The check answers three questions on the task-131 corpus, and each answer is a
stored observation rather than a claim:

1. **Route parity.**  The same frozen snapshot goes through the live seam
   (``derive_live_analysis``) and through the documented replay entry point
   (``core.smc_validation.replay_canonical_snapshot``).  Both must report the
   same decision-relevant fields; a difference means replay reaches the
   evaluator with a different input set than live.
2. **No future leak.**  A caller that only ever saw the closed candles at the
   cutoff must get the same verdict as a caller whose window also contained the
   bars the broker printed *after* the cutoff.  The corpus stores that future
   tail separately for exactly this comparison.  In addition, every timestamp
   the verdict itself carries (visit anchor, confirmation/trigger times,
   lifecycle times) must be at or before the cutoff.
3. **Determinism across repeats.**  Re-running the identical input must return
   the identical verdict, so a difference seen elsewhere is caused by the input
   and not by the harness.

Nothing is written outside ``reports/scanner/smc_real_snapshots/``, no
operational storage is touched and no order is ever sent.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.market_models import Candle  # noqa: E402
from core.scanner_live_producers import derive_live_analysis  # noqa: E402
from core.smc_snapshot import build_smc_snapshot  # noqa: E402
from core.smc_snapshot_cache import smc_rule_versions  # noqa: E402
from core.smc_validation import replay_canonical_snapshot  # noqa: E402

OUTPUT_DIR = PROJECT_ROOT / "reports" / "scanner" / "smc_real_snapshots"
CORPUS_PATH = OUTPUT_DIR / "corpus.jsonl.gz"
DEFAULT_REPORT = OUTPUT_DIR / "replay_parity.json"

# The representative slices the task asks for: the full production window and a
# short one, both ending at the same cutoff.  A shorter slice is a legitimate
# caller that received less history; the check records what it observed instead
# of assuming it agrees.  Each slice costs four evaluations of a real snapshot
# (~9s each), so the set stays deliberately small.
SEGMENTS = (500, 120)


def _candle(payload: Mapping[str, Any]) -> Candle:
    return Candle(
        time=datetime.fromisoformat(str(payload["t"])),
        open=float(payload["o"]),
        high=float(payload["h"]),
        low=float(payload["l"]),
        close=float(payload["c"]),
        volume=float(payload.get("v") or 0.0),
    )


def _candles(row: Mapping[str, Any], timeframe: str, *, bars: int | None, tail: bool) -> list[Candle]:
    """The window a caller would have: its bar count, then the later bars.

    The truncation happens BEFORE the tail is appended, because that is what a
    real caller sees: it asks for the last N bars at a later moment, so the
    extra bars push the window forward in time and the seam then keeps only what
    was closed at the cutoff.  Appending the tail first and truncating after
    would silently *shorten* the closed window instead — which is a different
    input, and the reason this check exists at all.
    """

    values = [_candle(item) for item in row["candles"][timeframe]]
    if bars is not None:
        limit = 100 if timeframe == "M15" else bars
        values = values[-limit:]
    if tail:
        values = values + [_candle(item) for item in row["future_tail"].get(timeframe) or []]
    return values


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if dataclasses.is_dataclass(value):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    return repr(value)


def decision_fingerprint(evaluation: Any) -> dict[str, Any]:
    """Every decision-relevant field of one evaluation, as plain JSON.

    ``SideSelection`` keeps its identity on derived properties
    (``selected_zone_id`` and friends), which a plain dataclass dump would drop,
    so they are captured explicitly — a fingerprint that lost the zone id would
    compare two verdicts that differ in the only field that matters.
    """

    sides: dict[str, Any] = {}
    for side in ("buy", "sell"):
        selection = evaluation.selection(side)
        if selection is None:
            sides[side] = None
            continue
        candidate = getattr(selection, "selected", None)
        sides[side] = {
            "state": getattr(selection, "state", None),
            "selected_zone_id": getattr(selection, "selected_zone_id", None),
            "selected_setup_id": getattr(selection, "selected_setup_id", None),
            "selected_candidate_id": getattr(selection, "selected_candidate_id", None),
            "selected_quality_raw": getattr(selection, "selected_quality_raw", None),
            "plan_available": bool(getattr(selection, "plan_available", False)),
            "plan_rejection_codes": _jsonable(
                getattr(selection, "plan_rejection_codes", ())
            ),
            "selection_reason_codes": _jsonable(
                getattr(selection, "selection_reason_codes", ())
            ),
            "readiness": _jsonable(getattr(selection, "readiness", None)),
            "selected": _jsonable(candidate),
            "quality": _jsonable(getattr(selection, "quality", None)),
            "plan": _jsonable(getattr(selection, "plan", None)),
        }
    return {
        "evaluation_version": getattr(evaluation, "evaluation_version", None),
        "sides": sides,
    }


def _live(candles: Mapping[str, list[Candle]], row: Mapping[str, Any]):
    return derive_live_analysis(
        candles["D1"],
        candles["H4"],
        candles["H1"],
        symbol=row["symbol"],
        captured_at=datetime.fromisoformat(row["as_of"]),
        news_in_3h=False,
        m15_candles=candles["M15"],
        m15_as_of=datetime.fromisoformat(row["as_of"]),
        tick_size=row["tick_size"],
        tick_size_source=row["tick_size_source"],
        # The same R:R floor the live Scanner passes; without it the coordinator
        # accepts no plan and the comparison would silently be against a
        # different plan policy than production.
        min_rr=row.get("min_rr"),
    )


# Timestamps that are forward-looking by design: a trigger expiry names a
# moment that has not happened yet, and a plan/expiry horizon is a decision the
# chain is allowed to take at the cutoff.  Everything else — when a visit
# opened, when a confirmation happened, when a life cycle event occurred — must
# belong to the past the caller actually had.
_FORWARD_LOOKING_KEYS = ("expires_at", "expiry", "expires")


def _times_after_cutoff(payload: Any, cutoff: datetime) -> list[str]:
    """Verdict timestamps that sit after the cutoff, with the field that owns them.

    A field whose meaning is a future moment (an expiry) is excluded; anything
    else after the cutoff would mean the verdict used information the caller did
    not have.
    """

    found: list[str] = []

    def walk(value: Any, path: str = "") -> None:
        if isinstance(value, str):
            key = path.rsplit(".", 1)[-1].lower() if path else ""
            if any(token in key for token in _FORWARD_LOOKING_KEYS):
                return
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return
            if parsed.tzinfo is None:
                return
            if parsed > cutoff:
                found.append(f"{path}={value}")
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                walk(item, f"{path}.{key}" if path else str(key))
            return
        if isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    walk(payload)
    return sorted(set(found))


def _segment_case(row: Mapping[str, Any], bars: int) -> dict[str, Any]:
    cutoff = datetime.fromisoformat(row["as_of"])
    prefix = {tf: _candles(row, tf, bars=bars, tail=False) for tf in ("D1", "H4", "H1", "M15")}
    wide = {tf: _candles(row, tf, bars=bars, tail=True) for tf in ("D1", "H4", "H1", "M15")}

    live_prefix = _live(prefix, row)
    live_prefix_again = _live(prefix, row)
    live_wide = _live(wide, row)

    snapshot = build_smc_snapshot(
        prefix,
        symbol=row["symbol"],
        as_of=cutoff,
        m15_as_of=cutoff,
        tick_size=row["tick_size"],
        tick_size_source=row["tick_size_source"],
    )
    replay = replay_canonical_snapshot(snapshot, min_rr=row.get("min_rr"))
    replay_payload = _jsonable(replay)

    live_fp = decision_fingerprint(live_prefix["smc_evaluation"])
    repeat_fp = decision_fingerprint(live_prefix_again["smc_evaluation"])
    wide_fp = decision_fingerprint(live_wide["smc_evaluation"])

    # The replay payload carries both sides under ``sides``; compare that same
    # vocabulary with what the live seam's typed selection says, field by field.
    replay_sides = {
        side: {
            key: (replay_payload.get("sides", {}).get(side) or {}).get(key)
            for key in (
                "state",
                "quality_raw",
                "selected_zone_id",
                "selected_setup_id",
                "plan_available",
                "readiness_status",
                "smc_state",
            )
        }
        for side in ("buy", "sell")
    }
    live_sides = _live_side_fields(live_fp)

    after_cutoff = _times_after_cutoff(live_fp, cutoff)
    production_window = bars == SEGMENTS[0]
    stored_match = _stored_matches(row, live_sides)
    short_segment = not production_window
    return {
        "bars": bars,
        "production_window": production_window,
        "coverage": {tf: len(prefix[tf]) for tf in prefix},
        "route_parity": live_sides == replay_sides,
        "live_sides": live_sides,
        "replay_sides": replay_sides,
        "prefix_equals_wide": live_fp == wide_fp,
        "deterministic_repeat": live_fp == repeat_fp,
        "timestamps_after_cutoff": after_cutoff,
        "replay_status": replay_payload.get("status"),
        "replay_declared_status": replay_payload.get("declared_status"),
        "stored_verdict_matches": stored_match,
        # A shorter segment is a caller that received less history: the
        # canonical gates may legitimately answer differently (a thin window is
        # exactly what SMC_CORE_DATA_UNAVAILABLE is for).  That is recorded, not
        # asserted, so a real gate behaviour is never mistaken for a defect.
        "short_segment": short_segment,
        "short_segment_state": live_sides if short_segment else None,
    }


def _live_side_fields(live_fp: Mapping[str, Any]) -> dict[str, Any]:
    """The live verdict in the replay payload's own field names."""

    fields: dict[str, Any] = {}
    for side in ("buy", "sell"):
        typed = live_fp["sides"].get(side)
        if not isinstance(typed, Mapping):
            fields[side] = {
                key: None
                for key in (
                    "state",
                    "quality_raw",
                    "selected_zone_id",
                    "selected_setup_id",
                    "plan_available",
                    "readiness_status",
                    "smc_state",
                )
            }
            continue
        readiness = typed.get("readiness") or {}
        fields[side] = {
            "state": typed.get("state"),
            "quality_raw": typed.get("selected_quality_raw"),
            "selected_zone_id": typed.get("selected_zone_id"),
            "selected_setup_id": typed.get("selected_setup_id"),
            "plan_available": bool(typed.get("plan_available")),
            "readiness_status": readiness.get("status"),
            "smc_state": readiness.get("smc_state"),
        }
    return fields

def _stored_matches(row: Mapping[str, Any], live_sides: Mapping[str, Any]) -> bool:
    """The verdict observed at collection time, re-observed now."""

    stored = row.get("sides") or {}
    for side in ("buy", "sell"):
        observed = stored.get(side) or {}
        current = live_sides.get(side) or {}
        if observed.get("selected_zone_id") != current.get("selected_zone_id"):
            return False
        if observed.get("selected_setup_id") != current.get("selected_setup_id"):
            return False
        if observed.get("quality_raw") != current.get("quality_raw"):
            return False
        if observed.get("readiness_status") != current.get("readiness_status"):
            return False
        if bool(observed.get("plan_available")) != bool(current.get("plan_available")):
            return False
        if observed.get("state") != current.get("state"):
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Short replay parity (task 133)")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--limit", type=int, default=0, help="only the first N corpus rows")
    parser.add_argument(
        "--rows",
        default="",
        help="comma-separated 'SYMBOL@AS_OF' rows to replay instead of the whole corpus",
    )
    args = parser.parse_args()

    if not CORPUS_PATH.exists():
        print(f"BLOCKED: no corpus at {CORPUS_PATH}; run scripts/smc_real_snapshots.py collect first.")
        return 2
    import gzip

    with gzip.open(CORPUS_PATH, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    if args.rows:
        wanted = {item.strip() for item in args.rows.split(",") if item.strip()}
        rows = [
            row for row in rows if f"{row['symbol']}@{row['as_of']}" in wanted
        ]
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        print("BLOCKED: no corpus row selected for replay.")
        return 2

    started = time.perf_counter()
    cases: list[dict[str, Any]] = []
    for row in rows:
        for bars in SEGMENTS:
            case = _segment_case(row, bars)
            case["symbol"] = row["symbol"]
            case["as_of"] = row["as_of"]
            case["snapshot_identity"] = row["snapshot_identity"]
            cases.append(case)
            print(
                f"  {row['symbol']:8s} {row['as_of']} bars={bars:3d} "
                f"route_parity={case['route_parity']} prefix==wide={case['prefix_equals_wide']} "
                f"deterministic={case['deterministic_repeat']} "
                f"after_cutoff={len(case['timestamps_after_cutoff'])}"
            )

    failures = [
        {
            "symbol": case["symbol"],
            "as_of": case["as_of"],
            "bars": case["bars"],
            "route_parity": case["route_parity"],
            "prefix_equals_wide": case["prefix_equals_wide"],
            "deterministic_repeat": case["deterministic_repeat"],
            "timestamps_after_cutoff": case["timestamps_after_cutoff"],
            "stored_verdict_matches": case["stored_verdict_matches"],
        }
        for case in cases
        if not (
            case["route_parity"]
            and case["prefix_equals_wide"]
            and case["deterministic_repeat"]
            and not case["timestamps_after_cutoff"]
            and (case["stored_verdict_matches"] or not case["production_window"])
        )
    ]
    short_segments = [
        {
            "symbol": case["symbol"],
            "as_of": case["as_of"],
            "bars": case["bars"],
            "coverage": case["coverage"],
            "state": case["short_segment_state"],
        }
        for case in cases
        if case["short_segment"]
    ]
    report = {
        "report_version": "smc-replay-parity-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus": str(CORPUS_PATH.relative_to(PROJECT_ROOT)),
        "rows": len(rows),
        "segments": list(SEGMENTS),
        "cases": cases,
        "failures": failures,
        "short_segments": short_segments,
        "no_future_leak": not any(case["timestamps_after_cutoff"] for case in cases),
        "rule_versions": smc_rule_versions(),
        "elapsed_seconds": round(time.perf_counter() - started, 4),
    }
    target = Path(args.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"\ncases={len(cases)} failures={len(failures)} no_future_leak={report['no_future_leak']}")
    print(f"report -> {target}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
