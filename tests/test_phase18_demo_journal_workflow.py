"""Phase 18.6 — test demo journal workflow."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.phase18_demo_journal_workflow import run_demo_journal_workflow


def test_journal_workflow(tmp_path):
    db = tmp_path / "demo_journal.db"
    output = tmp_path / "report.json"
    report = run_demo_journal_workflow(db_path=db, output_path=output)

    assert report["entries_created"] >= 2
    assert report["closed_trades_count"] >= 1
    assert "result_r" in report["sample_closed_trade_keys"]
    # Phase 17 fields
    keys = set(report["sample_closed_trade_keys"])
    assert "planned_entry" in keys or "actual_entry" in keys, f"Missing Phase 17 fields in keys: {report['sample_closed_trade_keys']}"

    assert output.is_file()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["entries_created"] >= 2


def test_script_runnable():
    from scripts.phase18_demo_journal_workflow import main
    main()
    report_path = Path(__file__).resolve().parent.parent / "data" / "phase18_demo_journal_report.json"
    assert report_path.is_file()
