"""Run the Phase-8 Scanner/SMC rollback drill without placing orders."""

from __future__ import annotations

import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.scanner_rollout_service import (  # noqa: E402
    ScannerRolloutMetricsService,
)


def main() -> int:
    report = ScannerRolloutMetricsService().perform_rollback_drill()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
