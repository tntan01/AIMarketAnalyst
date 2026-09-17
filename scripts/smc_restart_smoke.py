"""Restart / history / cache smoke on a temporary runtime root (task 134).

Run:
    python -X utf8 scripts/smc_restart_smoke.py --report reports/scanner/smc_real_snapshots/restart_smoke.json

The smoke drives the REAL producers — the production Order-Analysis caller
(``AnalysisPipeline.execute``) on the real candles of the task-131 corpus, the
real Scanner document writer (``core.scanner_observability.build_analysis_document``)
and the real persistence/cache services — against a **temporary** runtime root.
Nothing under the operational data directory is read or written, and no order is
ever sent.

It then answers, for each stored case:

1. **Scan a list, restart, open history.**  Several symbols are evaluated and
   persisted, then a *new* service instance — which carries nothing except the
   bytes on disk — reads them back and reports the same verdict the live run
   reported.
2. **Missing / corrupt / incompatible fails closed.**  A stored payload whose
   block is gone, whose identity was tampered with, whose contract version is
   unknown, or whose file is unreadable must NOT come back as live/current.  Each
   one is stored as an observation of what the reader actually returned.
3. **Cache reload.**  A record written under its snapshot identity is a real hit
   for a new instance; a record that lost its identity, its snapshot binding or
   its bytes is a miss that carries a reason and no record.
4. **Nothing else moved.**  The digest of the journal and open-order files is
   compared before and after, so "we only touched the temp root" is checkable.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.analysis_pipeline import AnalysisPipeline  # noqa: E402
from core.market_models import Candle  # noqa: E402
from core.scanner_observability import build_analysis_document  # noqa: E402
from core.smc_persistence import classify_persisted_smc  # noqa: E402
from services.scanner_persistence_service import (  # noqa: E402
    ScannerPersistenceService,
    analysis_document_path,
    atomic_json_save,
)

OUTPUT_DIR = PROJECT_ROOT / "reports" / "scanner" / "smc_real_snapshots"
CORPUS_PATH = OUTPUT_DIR / "corpus.jsonl.gz"
DEFAULT_REPORT = OUTPUT_DIR / "restart_smoke.json"

# Operational storage the smoke must not touch.  ``data/`` is the real runtime
# root in this repository; the smoke only ever writes to its own temp root.
OPERATIONAL_PATHS = (
    PROJECT_ROOT / "data" / "event_assessment_journal.jsonl",
    PROJECT_ROOT / "data" / "macro_verdict_journal.jsonl",
    PROJECT_ROOT / "data" / "shadow_records.jsonl",
)

# The owner R:R floor and gate thresholds used by the production caller's tests.
THRESHOLDS = {"min_rr": 2.0, "ready": 65, "wait": 55}


def _operational_digest() -> dict[str, str]:
    digests: dict[str, str] = {}
    for path in OPERATIONAL_PATHS:
        if not path.exists():
            digests[path.name] = "absent"
            continue
        digests[path.name] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def _correlation_context() -> dict[str, Any]:
    """The macro correlation context the production caller receives."""

    import importlib

    helper = importlib.import_module("tests.test_analysis_pipeline_integration")
    return helper._correlation_context(
        {"dxy_candles", "vix_candles", "us10y_candles", "us2y_candles"}
    )


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


def _run_analysis(row: Mapping[str, Any]) -> tuple[dict[str, Any], AnalysisPipeline]:
    """The real Analyze caller on the real candles of one corpus row."""

    from core.analysis_pipeline import AnalysisInput

    pipeline = AnalysisPipeline()
    cutoff = datetime.fromisoformat(row["as_of"])
    result = pipeline.execute(
        AnalysisInput(
            symbol=row["symbol"],
            broker_symbol=row["broker_symbol"],
            account_balance=10_000.0,
            risk_percent=1.0,
        ),
        {
            "D1": _candles(row, "D1"),
            "H4": _candles(row, "H4"),
            "H1": _candles(row, "H1"),
        },
        m15_candles=_candles(row, "M15"),
        m15_as_of=cutoff,
        snapshot_as_of=cutoff,
        tick_size=row["tick_size"],
        tick_size_source=row["tick_size_source"],
        macro_alignment={"buy": 30, "sell": 0},
        macro_confidence=1.0,
        correlation_context=_correlation_context(),
        thresholds=dict(THRESHOLDS),
    )
    return result, pipeline


def _verdict_of(evaluation: Any) -> dict[str, Any]:
    verdict: dict[str, Any] = {}
    for side in ("buy", "sell"):
        selection = evaluation.selection(side)
        if selection is None:
            verdict[side] = None
            continue
        readiness = getattr(selection, "readiness", None)
        verdict[side] = {
            "state": selection.state,
            "zone_id": selection.selected_zone_id,
            "setup_id": selection.selected_setup_id,
            "quality_raw": selection.selected_quality_raw,
            "plan_available": bool(selection.plan_available),
            "readiness_status": getattr(readiness, "status", None),
            "smc_state": getattr(readiness, "smc_state", None),
        }
    return verdict


def _stored_verdict(document: Mapping[str, Any]) -> dict[str, Any]:
    """The verdict the STORED bytes carry, read through the stored selection.

    The writer keeps two projections: a scoring projection (``block["sides"]``)
    and the consumer selection the readers certify (``consumer_contract``).  The
    comparison uses the consumer selection, because that is the one the UI,
    the chart and the revalidation gate read.
    """

    from core.smc_persistence import consumer_sides_of, smc_block_of

    block = smc_block_of(document)
    consumer_sides = consumer_sides_of(block)
    scoring_sides = block.get("sides") if isinstance(block.get("sides"), Mapping) else {}
    verdict: dict[str, Any] = {}
    for side in ("buy", "sell"):
        item = consumer_sides.get(side)
        selection = item.get("selection") if isinstance(item, Mapping) else None
        scoring = scoring_sides.get(side) if isinstance(scoring_sides, Mapping) else None
        if not isinstance(selection, Mapping):
            verdict[side] = None
            continue
        readiness = selection.get("readiness")
        readiness_payload = readiness if isinstance(readiness, Mapping) else {}
        verdict[side] = {
            "state": selection.get("state"),
            "zone_id": selection.get("selected_zone_id"),
            "setup_id": selection.get("selected_setup_id"),
            "quality_raw": selection.get("quality_raw"),
            "plan_available": bool(selection.get("plan_available")),
            "readiness_status": selection.get("readiness_status")
            or readiness_payload.get("status"),
            "smc_state": selection.get("smc_state") or readiness_payload.get("smc_state"),
            "scoring_projection_zone_id": (
                scoring.get("selected_zone_id") if isinstance(scoring, Mapping) else None
            ),
        }
    return verdict


def _verdicts_match(live: Mapping[str, Any], stored: Mapping[str, Any]) -> bool:
    """The stored verdict equals the live one, field by field, per side."""

    for side in ("buy", "sell"):
        left = live.get(side)
        right = stored.get(side)
        if left is None or right is None:
            if left is not None or right is not None:
                return False
            continue
        for key in (
            "state",
            "zone_id",
            "setup_id",
            "quality_raw",
            "plan_available",
            "readiness_status",
            "smc_state",
        ):
            if left.get(key) != right.get(key):
                return False
        # The two stored projections must also agree with each other: a payload
        # whose consumer selection names a different zone than its scoring
        # projection is a broken record, not a verdict.
        projection = right.get("scoring_projection_zone_id")
        if projection is not None and projection != right.get("zone_id"):
            return False
    return True


def _document(row: Mapping[str, Any], result: Mapping[str, Any], scan_id: str) -> dict[str, Any]:
    return build_analysis_document(
        {
            "symbol": row["symbol"],
            "row_id": f"{scan_id}:{row['symbol']}",
            "analysis_result": result,
        },
        {
            "scan_id": scan_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "settings_hash": "a" * 64,
        },
    )


def _tamper_missing_block(document: dict[str, Any]) -> dict[str, Any]:
    """Remove the block the way a payload written by older code would lack it."""

    mutated = json.loads(json.dumps(document))
    for container in (mutated.get("analysis_result"), mutated):
        if isinstance(container, dict):
            container.pop("smc_scoring", None)
    return mutated


def _tamper_identity(document: dict[str, Any]) -> dict[str, Any]:
    mutated = json.loads(json.dumps(document))
    block = _find_block(mutated)
    if block is not None:
        identity = block.get("persistence_identity")
        if isinstance(identity, dict):
            identity["cache_identity_version"] = "tampered"
    return mutated


def _tamper_contract(document: dict[str, Any]) -> dict[str, Any]:
    mutated = json.loads(json.dumps(document))
    block = _find_block(mutated)
    if block is not None:
        block["contract_version"] = "smc-consumer-contract-v999"
    return mutated


def _tamper_selection(document: dict[str, Any]) -> dict[str, Any]:
    """Break the recorded selection's own final invariant.

    The mutation lands on the CONSUMER selection — the payload the readers
    certify — not on the scoring projection beside it.  The test suite asserts
    the same shape (``test_a_recorded_selection_that_breaks_its_own_invariant_is_
    incompatible``): a selected setup with an accepted plan must name its zone.
    """

    mutated = json.loads(json.dumps(document))
    block = _find_block(mutated)
    if block is not None:
        consumer = block.get("consumer_contract")
        sides = consumer.get("sides") if isinstance(consumer, Mapping) else None
        if isinstance(sides, Mapping):
            for side in ("buy", "sell"):
                item = sides.get(side)
                selection = item.get("selection") if isinstance(item, Mapping) else None
                if isinstance(selection, dict) and selection.get("selected_zone_id"):
                    selection["selected_zone_id"] = None
                    break
    return mutated


def _find_block(document: Mapping[str, Any]) -> dict[str, Any] | None:
    """The live nested block (not a copy), so a tamper actually lands on disk."""

    from core.smc_persistence import smc_block_of

    block = smc_block_of(document)
    return block if isinstance(block, dict) and block else None


def _write_document(root: Path, scan_id: str, symbol: str, document: Mapping[str, Any]) -> Path:
    path = analysis_document_path(root, scan_id, symbol)
    atomic_json_save(path, document, indent=None)
    return path


def run_smoke(rows: Sequence[Mapping[str, Any]], limit: int) -> dict[str, Any]:
    selected = list(rows[:limit]) if limit else list(rows)
    before = _operational_digest()
    scan_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-smcsmoke"
    cases: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="smc_restart_smoke_") as temporary:
        root = Path(temporary)
        writer = ScannerPersistenceService(root)
        for row in selected:
            case: dict[str, Any] = {
                "symbol": row["symbol"],
                "as_of": row["as_of"],
                "snapshot_identity": row["snapshot_identity"],
            }
            try:
                result, pipeline = _run_analysis(row)
            except Exception as exc:
                case["status"] = "BLOCKED"
                case["error"] = f"{type(exc).__name__}: {exc}"
                cases.append(case)
                continue
            live = _verdict_of(pipeline._smc_evaluation)
            document = _document(row, result, scan_id)
            path = _write_document(root, scan_id, row["symbol"], document)

            # ---- restart: a brand-new instance reads the bytes on disk ------
            reader = ScannerPersistenceService(root)
            loaded = reader.load_analysis(scan_id, row["symbol"])
            compat = reader.classify_analysis(scan_id, row["symbol"])
            stored = _stored_verdict(loaded)
            case.update(
                {
                    "status": "OK",
                    "live_verdict": live,
                    "stored_verdict": stored,
                    "verdict_matches": _verdicts_match(live, stored),
                    "restart_classification": compat.status,
                    "restart_usable_as_current": bool(compat.usable_as_current),
                    "restart_reason_codes": list(compat.reason_codes),
                    "document_bytes": path.stat().st_size,
                }
            )

            # ---- fail-closed variants, each on its own temp root ------------
            case["closed_cases"] = _closed_cases(root, scan_id, row, document)

            # ---- cache reload ----------------------------------------------
            case["cache"] = _cache_case(root, row, compat)
            cases.append(case)

    after = _operational_digest()
    return {
        "report_version": "smc-restart-smoke-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cases": cases,
        "operational_storage_untouched": before == after,
        "operational_storage_digest": after,
    }


def _closed_cases(
    root: Path,
    scan_id: str,
    row: Mapping[str, Any],
    document: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Every way a stored payload may be unusable must stay unusable."""

    variants = (
        ("block_removed", _tamper_missing_block(dict(document))),
        ("identity_tampered", _tamper_identity(dict(document))),
        ("contract_unknown", _tamper_contract(dict(document))),
        ("selection_invariant_broken", _tamper_selection(dict(document))),
    )
    results: list[dict[str, Any]] = []
    for name, mutated in variants:
        with tempfile.TemporaryDirectory(prefix=f"smc_restart_{name}_") as temporary:
            scratch = Path(temporary)
            _write_document(scratch, scan_id, row["symbol"], mutated)
            reader = ScannerPersistenceService(scratch)
            loaded = reader.load_analysis(scan_id, row["symbol"])
            compat = classify_persisted_smc(loaded)
            results.append(
                {
                    "variant": name,
                    "classification": compat.status,
                    "usable_as_current": bool(compat.usable_as_current),
                    "reason_codes": list(compat.reason_codes),
                    "readable": bool(compat.readable),
                    "fail_closed": not bool(compat.usable_as_current),
                }
            )
    with tempfile.TemporaryDirectory(prefix="smc_restart_corrupt_") as temporary:
        scratch = Path(temporary)
        path = _write_document(scratch, scan_id, row["symbol"], document)
        path.write_bytes(b"not a gzip stream")
        reader = ScannerPersistenceService(scratch)
        # The documented contract is that unreadable bytes are *refused*, not
        # read as an empty document (``test_an_unreadable_artifact_is_refused_
        # instead_of_read_as_empty``).  Refusing by raising is still fail-closed,
        # so the smoke records which refusal it actually got.
        raised: str | None = None
        loaded: dict[str, Any] = {}
        try:
            loaded = reader.load_analysis(scan_id, row["symbol"])
        except Exception as exc:
            raised = f"{type(exc).__name__}: {exc}"
        compat = classify_persisted_smc(loaded)
        results.append(
            {
                "variant": "file_unreadable",
                "refused_by": raised,
                "loaded_is_empty": loaded == {} and raised is not None,
                "classification": compat.status,
                "usable_as_current": bool(compat.usable_as_current),
                "reason_codes": list(compat.reason_codes),
                "fail_closed": raised is not None and not bool(compat.usable_as_current),
            }
        )
    with tempfile.TemporaryDirectory(prefix="smc_restart_absent_") as temporary:
        scratch = Path(temporary)
        reader = ScannerPersistenceService(scratch)
        # A payload that was never written is refused, not read as an empty
        # current result.
        raised: str | None = None
        loaded: dict[str, Any] = {}
        try:
            loaded = reader.load_analysis(scan_id, row["symbol"])
        except Exception as exc:
            raised = f"{type(exc).__name__}: {exc}"
        compat = classify_persisted_smc(loaded)
        results.append(
            {
                "variant": "never_written",
                "refused_by": raised,
                "classification": compat.status,
                "usable_as_current": bool(compat.usable_as_current),
                "reason_codes": list(compat.reason_codes),
                "fail_closed": raised is not None
                and not bool(compat.usable_as_current),
            }
        )
    return results


def _cache_case(root: Path, row: Mapping[str, Any], compat: Any) -> dict[str, Any]:
    """Write a record under the snapshot identity and read it after a restart.

    The stored record is the canonical block itself — the shape the cache read
    requires to be usable — so a hit proves the real record round-trips, not a
    hand-made stand-in.
    """

    identity = row["snapshot_identity"]
    record = json.loads(json.dumps(dict(compat.block), default=str))
    writer = ScannerPersistenceService(root)
    writer.write_smc_cache_record(snapshot_identity=identity, record=record)
    reader = ScannerPersistenceService(root)
    hit = reader.read_smc_cache_record(snapshot_identity=identity)
    miss = reader.read_smc_cache_record(snapshot_identity=identity + ":other")
    other_root = Path(tempfile.mkdtemp(prefix="smc_restart_cache_"))
    try:
        fresh = ScannerPersistenceService(other_root)
        cold = fresh.read_smc_cache_record(snapshot_identity=identity)
        tampered = fresh.read_smc_cache_record(snapshot_identity="not-the-same-input")
    finally:
        shutil.rmtree(other_root, ignore_errors=True)
    return {
        "hit": hit.hit,
        "hit_usable": hit.usable,
        "hit_reason_codes": list(hit.reason_codes),
        "miss_for_other_input": {
            "hit": miss.hit,
            "reason_codes": list(miss.reason_codes),
        },
        "cold_reader_on_other_root": {
            "hit": cold.hit,
            "reason_codes": list(cold.reason_codes),
        },
        "unrelated_identity": {
            "hit": tampered.hit,
            "reason_codes": list(tampered.reason_codes),
        },
    }


def _corpus_rows() -> list[dict[str, Any]]:
    with gzip.open(CORPUS_PATH, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Restart/history/cache smoke (task 134)")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--limit", type=int, default=6)
    args = parser.parse_args()
    if not CORPUS_PATH.exists():
        print(f"BLOCKED: no corpus at {CORPUS_PATH}; run scripts/smc_real_snapshots.py collect first.")
        return 2

    started = time.perf_counter()
    rows = _corpus_rows()
    smoke = run_smoke(rows, args.limit)
    failures: list[str] = []
    for case in smoke["cases"]:
        if case.get("status") == "BLOCKED":
            failures.append(f"{case['symbol']}@{case['as_of']}: analysis failed")
            continue
        if not case.get("verdict_matches"):
            failures.append(f"{case['symbol']}@{case['as_of']}: verdict changed across restart")
        if not case.get("restart_usable_as_current"):
            failures.append(f"{case['symbol']}@{case['as_of']}: stored payload not current")
        for closed in case.get("closed_cases") or []:
            if not closed.get("fail_closed"):
                failures.append(
                    f"{case['symbol']}@{case['as_of']}: {closed['variant']} did NOT fail closed"
                )
        if not (case.get("cache") or {}).get("hit"):
            failures.append(f"{case['symbol']}@{case['as_of']}: cache record did not hit")
    if not smoke["operational_storage_untouched"]:
        failures.append("operational storage changed during the smoke")

    report = {
        **smoke,
        "rows_available": len(rows),
        "cases_run": len(smoke["cases"]),
        "failures": failures,
        "elapsed_seconds": round(time.perf_counter() - started, 4),
    }
    target = Path(args.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for case in smoke["cases"]:
        print(
            f"  {case['symbol']:8s} {case['as_of']} status={case.get('status')} "
            f"matches={case.get('verdict_matches')} class={case.get('restart_classification')} "
            f"closed={[c['fail_closed'] for c in case.get('closed_cases') or []]}"
        )
    print(f"\ncases={len(smoke['cases'])} failures={len(failures)}")
    print(f"report -> {target}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
