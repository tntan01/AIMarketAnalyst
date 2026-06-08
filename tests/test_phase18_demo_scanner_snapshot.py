"""Phase 18.4 — test demo scanner snapshot generation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.phase18_run_demo_scanner import run_demo_scanner


def test_demo_scanner_5_symbols(tmp_path):
    output_file = tmp_path / "scanner_snapshot.json"
    snapshot = run_demo_scanner(output_file)

    assert snapshot["symbols_scanned"] == 5
    rows = snapshot["rows"]
    assert len(rows) == 5

    for i, row in enumerate(rows, start=1):
        assert row["rank"] == i, f"Row {i} rank mismatch"
        assert isinstance(row["symbol"], str)
        assert isinstance(row["opportunity_score"], int)
        assert isinstance(row["scanner_group"], str)
        assert row["scanner_group"] in ("ready_now", "waiting_confirmation", "watch_zone", "blocked")
        assert isinstance(row["final_score"], int)
        assert isinstance(row["best_score"], int)

    # Summary has new group counts
    summary = snapshot["summary"]
    assert "ready_now_count" in summary
    assert "blocked_count" in summary

    # JSON file valid
    assert output_file.is_file()
    data = json.loads(output_file.read_text(encoding="utf-8"))
    assert len(data["rows"]) == 5


def test_scanner_script_runnable():
    from scripts.phase18_run_demo_scanner import main
    main()
    snapshot = Path(__file__).resolve().parent.parent / "data" / "phase18_demo_scanner_snapshot.json"
    assert snapshot.is_file()
