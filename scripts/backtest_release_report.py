"""Build a Phase-7 backtest release report from immutable evidence files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.backtest_golden_replay import run_golden_replay
from core.backtest_migration import LEGACY_RESEARCH, migrate_snapshot_payload
from core.backtest_release import build_release_report
from services.storage_service import JsonStorage


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reconcile a current backtest snapshot with forward-demo "
            "evidence, then build the Phase-7 release report."
        )
    )
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--forward-snapshot", required=True, type=Path)
    parser.add_argument("--demo-trades", required=True, type=Path)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument(
        "--approve", action="store_true",
        help="Confirm that the named reviewer approved the report.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    snapshot = _load_object(args.snapshot)
    migrated_current = migrate_snapshot_payload(
        snapshot, source_path=str(args.snapshot)
    )
    if migrated_current.get("lifecycle", {}).get("status") == LEGACY_RESEARCH:
        parser.error("--snapshot must come from the current backtest engine.")

    demo_payload = JsonStorage(args.demo_trades).load(default=[])
    demo_trades = _trade_rows(demo_payload)
    forward_snapshot = migrate_snapshot_payload(
        _load_object(args.forward_snapshot),
        source_path=str(args.forward_snapshot),
    )
    if forward_snapshot.get("lifecycle", {}).get("status") == LEGACY_RESEARCH:
        parser.error(
            "--forward-snapshot must come from the current backtest engine."
        )
    forward_trades = _trade_rows(forward_snapshot)
    golden = run_golden_replay(
        PROJECT_ROOT / "tests" / "fixtures" / "backtest_phase7_golden.json"
    )
    report = build_release_report(
        migrated_current,
        demo_trades=demo_trades,
        forward_trades=forward_trades,
        golden_report=golden,
        reviewed_by=args.reviewer,
        approved=args.approve,
    )
    migrated_current["release_report"] = report
    migrated_current["lifecycle"] = {
        "status": "RELEASE_READY" if report["ready"] else "REVIEW_REQUIRED",
        "can_publish_config": report["ready"],
        "reasons": list(report["block_codes"]),
    }
    output = args.output or args.snapshot.with_name(
        f"{args.snapshot.stem}-reviewed.json"
    )
    JsonStorage(output).save(migrated_current)
    print(json.dumps({
        "output": str(output.resolve()),
        "ready": report["ready"],
        "block_codes": report["block_codes"],
        "report_fingerprint": report["report_fingerprint"],
    }, ensure_ascii=True, indent=2))
    return 0 if report["ready"] else 2


def _load_object(path: Path) -> dict[str, object]:
    payload = JsonStorage(path).load(default=None)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain one JSON object.")
    return payload


def _trade_rows(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    replay = payload.get("validation_replay")
    source = replay if isinstance(replay, dict) else payload
    rows = source.get("oos_trades")
    if not isinstance(rows, list):
        rows = source.get("trades", [])
    return [dict(row) for row in rows if isinstance(row, dict)]


if __name__ == "__main__":
    raise SystemExit(main())
