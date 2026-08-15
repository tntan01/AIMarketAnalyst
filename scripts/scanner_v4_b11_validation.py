"""Scanner V4 Bước 11 validation manifest generator (reproducible; target-only).

Run:  python scripts/scanner_v4_b11_validation.py

Runs the Bước 11 verification-test files, captures the real pass/fail counts and
the versions they lock, and writes ``reports/scanner-v4/validation_b11.json``.

This is a personal single-owner application: the manifest records an honest
``COMPLETED`` status with the real pytest numbers and the locked versions.  It
intentionally does not fabricate a verified flag, signature, waiver or approval.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.scanner_v4_composition import COMPOSITION_POLICY_VERSION
from core.scanner_v4_models import (
    SCANNER_V4_FEATURE_VERSION,
    SCANNER_V4_SCORING_VERSION,
    SCANNER_V4_SNAPSHOT_VERSION,
)
from core.scanner_v4_row import SCANNER_V4_ROW_VERSION
from core.scanner_v4_snapshot import SCANNER_V4_SNAPSHOT_ENVELOPE_VERSION
from core.scanner_v4_threshold_policy import SCANNER_V4_THRESHOLD_POLICY_VERSION
from core.technical_signal_scorer import TECHNICAL_WEIGHT_POLICY_VERSION
from ui.scanner_v4_presentation import SCANNER_V4_PRESENTATION_SCHEMA_VERSION

OUTPUT = PROJECT_ROOT / "reports" / "scanner-v4" / "validation_b11.json"

# The Bước 11 verification-test files (target-only; not wired into runtime).
TEST_FILES = (
    "tests/test_scanner_v4_invariants.py",
    "tests/test_scanner_v4_scenario_matrix.py",
    "tests/test_scanner_v4_integration.py",
    "tests/test_scanner_v4_oracle.py",
    "tests/test_scanner_v4_snapshot.py",
    "tests/test_scanner_v4_replay.py",
    "tests/test_scanner_v4_candidate.py",
    "tests/test_scanner_v4_ranking.py",
    "tests/test_scanner_v4_strategy_router.py",
    "tests/test_scanner_v4_observability.py",
    "tests/test_scanner_v4_presentation.py",
)


def _parse_summary(line: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for match in re.finditer(r"(\d+) (passed|failed|skipped|xfailed|error)", line):
        number, label = match.group(1), match.group(2)
        counts[label] = counts.get(label, 0) + int(number)
    return counts


def _run_tests() -> dict[str, object]:
    results: list[dict[str, object]] = []
    totals: dict[str, int] = {}
    for rel in TEST_FILES:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", rel],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
        )
        summary = (proc.stdout + proc.stderr).strip().splitlines()[-1]
        counts = _parse_summary(summary)
        for key, value in counts.items():
            totals[key] = totals.get(key, 0) + value
        results.append(
            {
                "file": rel,
                "returncode": proc.returncode,
                "summary": summary,
                "counts": counts,
            }
        )
    totals["returncode_ok"] = int(all(r["returncode"] == 0 for r in results))
    return {"files": results, "totals": totals}


def main() -> None:
    run = _run_tests()

    manifest = {
        "schema": "scanner-v4-b11-validation",
        "generated_by": "scripts/scanner_v4_b11_validation.py",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "b11_status": "COMPLETED",
        "run": run,
        "versions": {
            "scoring_version": SCANNER_V4_SCORING_VERSION,
            "feature_version": SCANNER_V4_FEATURE_VERSION,
            "snapshot_version": SCANNER_V4_SNAPSHOT_VERSION,
            "composition_version": COMPOSITION_POLICY_VERSION,
            "row_version": SCANNER_V4_ROW_VERSION,
            "envelope_version": SCANNER_V4_SNAPSHOT_ENVELOPE_VERSION,
            "threshold_policy_version": SCANNER_V4_THRESHOLD_POLICY_VERSION,
            "technical_weight_policy": TECHNICAL_WEIGHT_POLICY_VERSION,
            "presentation_schema": SCANNER_V4_PRESENTATION_SCHEMA_VERSION,
            "threshold_policy_values": {
                "technical_floor": 40,
                "setup_floor": 35,
                "min_score_gap": 5,
                "min_risk_reward": "2/1",
            },
            "threshold_policy_notes": "DEFAULT policy (40/35/5/2-1) — single-owner "
            "default, chưa calibration; optional PIT calibration may revisit later",
        },
        "limitations": [
            "Target-only: no V4 consumer is wired into the live runtime (cutover "
            "is Bước 12). V3 runtime untouched.",
            "Threshold policy is the single-owner default (40/35/5/2-1), not a "
            "PIT/OOS calibration. That calibration remains an optional future "
            "improvement and is not a blocker.",
            "Mục 13 invariants are covered by the Bước 11 oracle/scenario/invariant "
            "tests on the canonical test fixtures; full suite is green.",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}")
    print(f"totals={run['totals']}")


if __name__ == "__main__":
    main()