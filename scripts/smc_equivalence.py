"""Canonical-result fingerprint for before/after equivalence proof (task 137).

Run the same command in two trees — one without the reuse optimisation and one
with it — and diff the two JSON files:

    python -X utf8 scripts/smc_equivalence.py --out data/equiv_before.json
    python -X utf8 scripts/smc_equivalence.py --out data/equiv_after.json

The fingerprint is deliberately wider than "the score matches": it records the
canonical identity digest, every decision-relevant field of both sides (state,
zone/setup identity, B/Q/L/C, readiness and its reason codes, lifecycle
confirmation, plan identity and rejection codes), the canonical structure
vocabulary and events of each timeframe, and the documented replay payload of
the frozen snapshot.  A performance change is only allowed to make the same
work cheaper, so every one of those must be byte-identical.

Nothing here is runtime and nothing is written outside the requested path.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.market_models import Candle  # noqa: E402
from core.scanner_live_producers import derive_live_analysis  # noqa: E402
from core.smc_snapshot_cache import smc_snapshot_identity  # noqa: E402
from core.smc_validation import replay_canonical_snapshot  # noqa: E402

CORPUS = PROJECT_ROOT / "reports" / "scanner" / "smc_real_snapshots" / "corpus.jsonl.gz"


def _digest(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _candles(row: Mapping[str, Any], timeframe: str) -> list[Candle]:
    return [
        Candle(
            time=datetime.fromisoformat(item["t"]),
            open=float(item["o"]),
            high=float(item["h"]),
            low=float(item["l"]),
            close=float(item["c"]),
            volume=float(item.get("v") or 0.0),
        )
        for item in row["candles"][timeframe]
    ]


def _jsonable(value: Any) -> Any:
    """Plain JSON for both trees: the fingerprint must not depend on which one ran it."""

    import dataclasses
    from datetime import date

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    return str(value)


# Decision-relevant fields of the finalized selection.  Every one is read with
# ``getattr`` so the tool runs in both trees; a field only one tree has would
# make the comparison meaningless, so the list is kept to what both carry.
_SIDE_FIELDS = (
    "state",
    "selected_candidate_id",
    "selected_zone_id",
    "selected_setup_id",
    "timeframe",
    "family",
    "lifecycle_status",
    "confirmation_state",
    "confirmation_rank",
    "entry_visit_id",
    "confirmation_event_id",
    "quality_raw",
    "quality_score",
    "b",
    "q",
    "l",
    "c",
    "total",
    "plan_available",
    "plan_zone_id",
    "plan_setup_id",
    "zone_low",
    "zone_high",
)


def _side_payload(selection: Any) -> Any:
    from core.smc_scoring_result import smc_selection_of

    final = smc_selection_of(selection)
    if final is None:
        return None
    payload = {name: getattr(final, name, None) for name in _SIDE_FIELDS}
    payload["plan_rejection_codes"] = list(getattr(final, "plan_rejection_codes", ()) or ())
    payload["selection_reason_codes"] = list(
        getattr(final, "selection_reason_codes", ()) or ()
    )
    payload["plan"] = _jsonable(getattr(final, "plan", None))
    return payload


def _structure(analysis: Mapping[str, Any]) -> Any:
    snapshot = analysis["smc_snapshot"]
    context = snapshot.smc if isinstance(snapshot.smc, Mapping) else {}
    out: dict[str, Any] = {}
    for timeframe in ("D1", "H4", "H1"):
        layer = context.get(timeframe) if isinstance(context.get(timeframe), Mapping) else {}
        vocabulary = layer.get("structure")
        out[timeframe] = {
            "structure": (
                vocabulary.get("structure") if isinstance(vocabulary, Mapping) else vocabulary
            ),
            "bos": bool(layer.get("bos")),
            "choch": bool(layer.get("choch")),
            "choch_confirmed": bool(layer.get("choch_confirmed")),
            "displacement": (
                vocabulary.get("displacement") if isinstance(vocabulary, Mapping) else None
            ),
            "bos_strength": (
                vocabulary.get("bos_strength") if isinstance(vocabulary, Mapping) else None
            ),
            "structure_events": [
                {
                    key: event.get(key)
                    for key in (
                        "event_id",
                        "event_type",
                        "time",
                        "occurred_at",
                        "confirmed_at",
                        "invalidated_at",
                        "level",
                        "direction",
                    )
                }
                for event in (layer.get("structure_events") or ())
            ],
            "zone_ids": sorted(
                str(zone.get("zone_id") or "")
                for family in ("demand_zones", "supply_zones", "order_blocks", "fvg")
                for zone in (layer.get(family) or ())
            ),
        }
    return out


def fingerprint_row(row: Mapping[str, Any]) -> dict[str, Any]:
    candles = {tf: _candles(row, tf) for tf in ("D1", "H4", "H1", "M15")}
    analysis = derive_live_analysis(
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
        min_rr=row.get("min_rr"),
    )
    evaluation = analysis["smc_evaluation"]
    snapshot = analysis["smc_snapshot"]
    replay = replay_canonical_snapshot(snapshot, min_rr=row.get("min_rr"))
    raws = analysis["raws"]
    return {
        "symbol": row["symbol"],
        "as_of": row["as_of"],
        "identity": smc_snapshot_identity(
            symbol=row["symbol"],
            as_of=datetime.fromisoformat(row["as_of"]),
            candles_by_timeframe={tf: candles[tf] for tf in ("D1", "H4", "H1", "M15")},
            metadata={
                "tick_size": snapshot.tick_size,
                "tick_size_source": snapshot.tick_size_source,
            },
        ),
        "core_reason_codes": list(snapshot.core_reason_codes),
        "coverage": {tf: len(snapshot.candles.get(tf) or ()) for tf in ("D1", "H4", "H1")},
        "m15_candles": len(snapshot.m15_candles or ()),
        "sides": {
            side: _side_payload(evaluation.result.side(side)) for side in ("buy", "sell")
        },
        "structure": _structure(analysis),
        "replay": _digest(replay),
        "replay_status": replay.get("status"),
        "raws": {
            side: {
                "trend": raws.per_side[side].trend,
                "momentum": raws.per_side[side].momentum,
                "location": raws.per_side[side].location,
                "smc": raws.per_side[side].smc,
            }
            for side in ("buy", "sell")
        },
        "regime": analysis["regime"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="canonical-result fingerprint (task 137)")
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument(
        "--no-reuse",
        action="store_true",
        help="run the pre-optimisation recompute-per-prefix path (the oracle arm)",
    )
    args = parser.parse_args()
    if args.no_reuse:
        import core.smc_structure_window as window_module

        window_module.ENABLED = False
        print("reuse disabled: running the pre-optimisation path")
    if not CORPUS.exists():
        print(f"BLOCKED: no corpus at {CORPUS}")
        return 2
    with gzip.open(CORPUS, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    rows = rows[: args.limit]
    fingerprints: Sequence[dict[str, Any]] = [fingerprint_row(row) for row in rows]
    payload = {
        "reuse_enabled": __import__("core.smc_structure_window", fromlist=["ENABLED"]).ENABLED,
        "rows": len(fingerprints),
        "digest": _digest(fingerprints),
        "fingerprints": fingerprints,
    }
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"rows={len(fingerprints)} digest={payload['digest']}")
    print(f"-> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
