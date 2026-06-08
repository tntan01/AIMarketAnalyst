"""Phase 18.5 — test before/after comparison script."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from scripts.phase18_compare_before_after import compare_snapshots


def test_compare_with_delta(tmp_path):
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    output = tmp_path / "report.json"

    before.write_text(json.dumps([
        {"symbol": "EUR/USD", "best_score": 70, "decision_action": "watch"},
        {"symbol": "GBP/JPY", "best_score": 65, "decision_action": "wait"},
    ]), encoding="utf-8")
    after.write_text(json.dumps([
        {"symbol": "EUR/USD", "best_score": 80, "final_score": 75, "opportunity_score": 90, "scanner_group": "ready_now"},
        {"symbol": "GBP/JPY", "best_score": 70, "final_score": 68, "opportunity_score": 82, "scanner_group": "waiting_confirmation"},
    ]), encoding="utf-8")

    report = compare_snapshots(before, after, output)
    assert report["baseline_available"] is True
    comparisons = report["comparisons"]
    assert len(comparisons) == 2

    eur = next(c for c in comparisons if c["symbol"] == "EUR/USD")
    assert eur["score_delta"] == 10
    assert eur["before_best_score"] == 70
    assert eur["after_best_score"] == 80

    assert output.is_file()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["baseline_available"] is True


def test_missing_before_no_crash(tmp_path):
    before = tmp_path / "no_exist.json"
    after = tmp_path / "after.json"
    after.write_text(json.dumps([
        {"symbol": "EUR/USD", "best_score": 80}
    ]), encoding="utf-8")

    report = compare_snapshots(before, after)
    assert report["baseline_available"] is False
    assert report["after_count"] == 1


def test_missing_after_raises(tmp_path):
    before = tmp_path / "before.json"
    before.write_text(json.dumps([{"symbol": "EUR/USD", "best_score": 70}]), encoding="utf-8")
    after = tmp_path / "no_exist.json"

    with pytest.raises(FileNotFoundError):
        compare_snapshots(before, after)


def test_none_before_no_crash(tmp_path):
    after = tmp_path / "after.json"
    after.write_text(json.dumps([{"symbol": "EUR/USD"}]), encoding="utf-8")

    report = compare_snapshots(None, after)
    assert report["baseline_available"] is False


def test_dict_rows_format(tmp_path):
    """Snapshot with dict wrapper {'rows': [...]} is supported."""
    after = tmp_path / "after_dict.json"
    after.write_text(json.dumps({
        "rows": [{"symbol": "EUR/USD", "best_score": 82}],
        "summary": {},
    }), encoding="utf-8")

    report = compare_snapshots(None, after)
    assert report["after_count"] == 1
