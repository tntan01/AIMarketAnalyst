"""Phase 18.7 — test upgrade report generation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.phase18_generate_upgrade_report import generate_report


def test_generate_report_with_snapshots(tmp_path):
    # Create fake snapshots
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    (data_dir / "phase18_demo_analysis_snapshot.json").write_text(json.dumps([
        {"symbol": "EUR/USD", "buy_score": 46, "sell_score": 39, "final_score": 55, "decision_engine_decision": "WAITING_CONFIRMATION", "trade_permission": "caution"},
    ]), encoding="utf-8")
    (data_dir / "phase18_demo_scanner_snapshot.json").write_text(json.dumps({
        "rows": [{"symbol": "EUR/USD"}], "summary": {"ready_now_count": 0, "waiting_confirmation_count": 1, "watch_zone_count": 0, "blocked_count": 4}
    }), encoding="utf-8")
    (data_dir / "phase18_demo_journal_report.json").write_text(json.dumps({
        "entries_created": 3, "closed_trades_count": 2, "sample_closed_trade_keys": ["result_r", "planned_entry"]
    }), encoding="utf-8")

    output = tmp_path / "report.md"
    report = generate_report(data_dir, output)

    assert output.is_file()
    content = output.read_text(encoding="utf-8")
    assert "Báo cáo hoàn tất" in content or "HOÀN TẤT" in content
    assert "final_score" in content
    assert "decision_engine" in content
    assert "scanner_ranking" in content
    assert "score" in content  # conclusions mention score


def test_generate_report_no_data_no_crash(tmp_path):
    """No snapshot files → report still generated without crash."""
    empty_dir = tmp_path / "empty_data"
    empty_dir.mkdir()

    output = tmp_path / "report.md"
    report = generate_report(empty_dir, output)
    assert output.is_file()
    assert "Chưa có" in output.read_text(encoding="utf-8")
