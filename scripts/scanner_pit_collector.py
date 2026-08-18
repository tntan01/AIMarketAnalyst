"""Scanner V4 PIT dataset collector CLI (Bước 09; target-only, standalone).

Purpose: gather/validate a historical point-in-time dataset for Bước 09
calibration.  It is a *tool*, not runtime — nothing here is wired into the live
scanner, it does not emit orders, and it never fabricates data or self-sets
production thresholds.

Run:
    python scripts/scanner_pit_collector.py --schema
    python scripts/scanner_pit_collector.py --dataset DATA.jsonl \\
        --out reports/scanner/pit_evidence.json \\
        --pit-boundary 2026-08-13T00:00:00Z --minimum-rows 100

``--dataset`` is a JSONL corpus (one PIT snapshot per line) matching the schema
printed by ``--schema``.  The tool writes an evidence artifact containing the
validation issues, the 9B safety audit, the 9D calibration report, and the
SHA-256 digest of the canonical corpus payload.

With today's repo (no PIT dataset), the audit reports every category MISSING and
the calibration report is INSUFFICIENT_SAMPLE with all threshold recommendations
``None`` — fail-closed, which is the expected evidence: Bước 09 calibration infra
works, PIT/OOS calibration stays an optional future improvement, and the DEFAULT
policy remains in place.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.scanner_pit_dataset import (
    ForwardCollectorConfig,
    append_forward_snapshot,
    forward_status,
    init_forward_collector,
    load_pit_dataset_jsonl,
    requested_schema,
    run_pit_evidence,
)


def _collector_config(args) -> ForwardCollectorConfig:
    boundary = datetime.fromisoformat(args.pit_boundary)
    if boundary.utcoffset() is None:
        boundary = boundary.replace(tzinfo=timezone.utc)
    return ForwardCollectorConfig(
        corpus_path=args.corpus,
        minimum_required_rows=args.minimum_rows,
        target_coverage_days=args.coverage_days,
        pit_boundary=boundary,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Scanner V4 PIT dataset collector")
    parser.add_argument("--schema", action="store_true", help="print the required row schema")

    parser.add_argument("--dataset", metavar="DATA.jsonl", help="one-shot: validate an existing PIT corpus")
    parser.add_argument("--out", metavar="ARTIFACT.json", help="output evidence artifact path for --dataset")

    parser.add_argument("--corpus", metavar="CORPUS.jsonl", help="forward-collection corpus path")
    parser.add_argument("--init", action="store_true", help="create the forward corpus (empty)")
    parser.add_argument("--append", metavar="SNAPSHOT.json", help="validate + append one snapshot")
    parser.add_argument("--status", action="store_true", help="report forward-corpus state vs owner bars")

    parser.add_argument("--pit-boundary", default="2026-08-13T00:00:00Z", help="train/OOS boundary (ISO)")
    parser.add_argument("--minimum-rows", type=int, default=100, help="explicit evidence bar (owner-set)")
    parser.add_argument("--coverage-days", type=int, default=0, help="target minimum per-category coverage days (owner-set)")
    args = parser.parse_args()

    if args.schema:
        print(json.dumps(requested_schema(), indent=2, sort_keys=True, ensure_ascii=False))
        return

    # Forward collection modes.
    if args.corpus:
        cfg = _collector_config(args)
        if args.init:
            init_forward_collector(cfg)
            print(f"[collector] initialised forward corpus: {cfg.corpus_path}")
            print(json.dumps(forward_status(cfg).to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
            return
        if args.append:
            raw = json.loads(args.append)
            ok, issues, report = append_forward_snapshot(cfg, raw)
            print(json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
            if not ok:
                print(f"[collector] REJECTED ({len(issues)} issues) — corpus unchanged", file=sys.stderr)
                for issue in issues[:20]:
                    print(f"  - {issue}", file=sys.stderr)
                sys.exit(3)
            return
        if args.status:
            print(json.dumps(forward_status(cfg).to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
            return

    if not args.dataset or not args.out:
        parser.error("dùng --schema | --dataset+--out | --corpus (+--init/--append/--status)")

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"[collector] dataset không tồn tại: {dataset_path}", file=sys.stderr)
        sys.exit(2)

    rows = load_pit_dataset_jsonl(dataset_path)
    pit_boundary = datetime.fromisoformat(args.pit_boundary)
    if pit_boundary.utcoffset() is None:
        pit_boundary = pit_boundary.replace(tzinfo=timezone.utc)
    coverage = {"spread": args.coverage_days} if args.coverage_days else None

    evidence = run_pit_evidence(
        rows,
        pit_boundary=pit_boundary,
        minimum_required_rows=args.minimum_rows,
        minimum_coverage_days=coverage,
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(evidence.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"dataset:  {dataset_path} ({len(rows)} rows)")
    print(f"sha256:   {evidence.sha256}")
    print(f"audit:    sufficient_for_calibration={evidence.audit.sufficient_for_calibration}")
    for item in evidence.audit.items:
        print(f"          {item.category}: {item.status}")
    print(f"calib:    {evidence.calibration.status} n={evidence.calibration.summary.n} "
          f"oos_n={evidence.calibration.summary.oos_n}")
    print(f"verify:   validation.clean={evidence.validation.clean} "
          f"issues={len(evidence.validation.issues)}")
    print(f"wrote:    {out}")


if __name__ == "__main__":
    main()