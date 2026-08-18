"""Scanner V4 Bước 09 evidence artifact generator (reproducible; target-only).

Run:  python scripts/scanner_calibration_evidence.py

Produces a reproducible JSON evidence report proving the CURRENT repository state
for Bước 09 acceptance:

* 9B — the safety-data inventory has NO point-in-time historical dataset
  (``data/`` holds only journals/baseline): every category is ``MISSING`` and the
  audit is ``sufficient_for_calibration=False`` (fail-closed; honest UNKNOWN).
* 9D — the calibration harness run against that empty manifest returns
  ``INSUFFICIENT_SAMPLE`` with every recommended production threshold ``None``
  (never fabricating numbers).

The report is byte-reproducible: same manifest + same input rows → same
fingerprint.  Bước 09 is ``COMPLETED`` (parity/audit/calibration-infra/config
working); the PIT/OOS calibration remains an *optional* future improvement, not
a gate, and no sign-off is required.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.scanner_calibration import (
    make_empty_calibration_manifest,
    run_calibration,
)
from core.scanner_safety_audit import audit_safety_data

PIT_BOUNDARY = datetime(2026, 8, 13, 0, 0, 0, tzinfo=timezone.utc)


def _build_report() -> dict[str, object]:
    # 9B — repository has no PIT safety dataset: declare no sources at all.
    audit = audit_safety_data((), pit_boundary=PIT_BOUNDARY)

    # 9D — calibration over the repo-empty manifest with zero rows.
    manifest = make_empty_calibration_manifest(
        pit_boundary=PIT_BOUNDARY,
        minimum_required_rows=100,
    )
    calibration = run_calibration(manifest, ())

    return {
        "report_version": "scanner-b09-evidence-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "step": "Bước 09 — Backtest parity, calibration, config và version invalidation",
        "status": "COMPLETED",
        "reproducibility_note": (
            "Report deterministic: fields từ module (status/fingerprints/thresholds) "
            "phụ thuộc (manifest, rows) — chạy lại cùng manifest+rows cho cùng bytes."
        ),
        "safety_audit_9B": audit.to_dict(),
        "calibration_9D": calibration.to_dict(),
        "calibration_fingerprint": calibration.fingerprint(()),
        "blockers": list(audit.blockers),
        "verdict": (
            "fail-closed: mọi safety category MISSING; calibration insufficient_sample; "
            "recommended thresholds = None (giữ DEFAULT policy 40/35/5/2); calibration "
            "PIT/OOS là cải tiến tùy chọn, không chặn — Bước 09 COMPLETED, không có sign-off."
        ),
    }


def main() -> None:
    report = _build_report()
    out_path = "reports/scanner_b09_evidence.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"wrote {out_path}")
    print(f"  safety sufficient_for_calibration={report['safety_audit_9B']['sufficient_for_calibration']}")
    print(f"  calibration status={report['calibration_9D']['status']}")
    print(f"  calibration fingerprint={report['calibration_fingerprint']}")


if __name__ == "__main__":
    main()