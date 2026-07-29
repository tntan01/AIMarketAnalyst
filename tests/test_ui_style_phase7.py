"""Phase 7 architecture locks for UI styling and responsive coverage."""

from __future__ import annotations

import json
from pathlib import Path

from tools.ui_style_audit import (
    build_inventory,
    compare_with_baseline,
    load_inventory,
)


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
EXPECTED_ROUTES = {
    "dashboard",
    "scanner",
    "scanner_detail",
    "orders",
    "backtest",
    "journal",
    "journal_detail",
    "settings",
}
EXPECTED_PROFILES = {
    "laptop-14",
    "laptop-15-6",
    "laptop-16",
    "desktop-24",
    "desktop-27",
    "desktop-32",
}
EXPECTED_STATES = {
    "state-default",
    "state-focus",
    "state-hover",
    "state-pressed",
    "state-disabled",
    "state-checked",
    "state-validation",
}


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_current_ui_debt_does_not_exceed_phase7_lock() -> None:
    current = build_inventory()
    lock = load_inventory(DOCS / "ui" / "style" / "ui-style-lock.json")
    assert compare_with_baseline(current, lock) == []


def test_stylesheet_application_remains_centralized() -> None:
    inventory = build_inventory()
    assert inventory["totals"]["set_stylesheet_calls"] == 1
    assert (
        inventory["python_files"]["ui/theme_manager.py"][
            "set_stylesheet_calls"
        ]
        == 1
    )
    for path, metrics in inventory["python_files"].items():
        if path.startswith("ui/screens/"):
            assert metrics["set_stylesheet_calls"] == 0, path


def test_responsive_matrix_is_complete_and_clean() -> None:
    report = _json(DOCS / "ui" / "reports" / "ui-responsive-report.json")
    assert report["issue_count"] == 0
    assert set(report["routes"]) == EXPECTED_ROUTES
    assert set(report["profiles"]) == EXPECTED_PROFILES
    assert set(report["dpi_profiles"]) == {"dpi-100", "dpi-125", "dpi-150"}
    assert report["themes"] == ["dark", "light"]
    assert len(report["results"]) == 288
    assert all(not result["issues"] for result in report["results"])


def test_visual_baseline_covers_both_themes_and_interaction_states() -> None:
    manifest = _json(
        DOCS
        / "ui"
        / "baseline"
        / "current"
        / "screenshot-manifest.json"
    )
    assert manifest["failures"] == []
    captures = manifest["captures"]
    assert len(captures) == 80
    for theme in ("dark", "light"):
        themed = [item for item in captures if item["theme"] == theme]
        assert len(themed) == 40
        assert {
            item["name"] for item in themed if item["name"].startswith("state-")
        } == EXPECTED_STATES
        for item in themed:
            assert (ROOT / item["path"]).is_file()


def test_phase7_allowlist_contains_only_reviewed_dispositions() -> None:
    allowlist = _json(DOCS / "ui" / "style" / "ui-style-allowlist.json")
    assert allowlist["status"] == "phase-7-reviewed"
    assert {
        item["disposition"] for item in allowlist["exceptions"]
    } <= {"permanent", "centralized"}
