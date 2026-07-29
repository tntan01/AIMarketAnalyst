"""Phase 5 locks for the final visual baseline and responsive harness."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from tools.capture_ui_style_baseline import (
    SUITE_EXPECTED_PER_THEME,
    SUITE_ROUTES,
    SUITE_SECTIONS,
    _state_gallery,
    _suite_jobs,
)
from ui.theme import DARK_PALETTE, LIGHT_PALETTE
from ui.theme_manager import ThemeManager


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs" / "ui" / "baseline" / "current"
MANIFEST = BASELINE / "screenshot-manifest.json"
DARK_REPORT = ROOT / "docs" / "ui" / "reports" / "dark-surface-report.json"
RESPONSIVE_REPORT = (
    ROOT / "docs" / "ui" / "reports" / "ui-responsive-report.json"
)
_APP = QApplication.instance() or QApplication([])


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_state_gallery_receives_real_dark_and_light_theme() -> None:
    dark = _state_gallery("dark")
    light = _state_gallery("light")
    try:
        assert dark.styleSheet()
        assert light.styleSheet()
        assert (
            dark.palette().color(QPalette.ColorRole.Window).name(
                QColor.NameFormat.HexRgb
            )
            == DARK_PALETTE.background
        )
        assert (
            light.palette().color(QPalette.ColorRole.Window).name(
                QColor.NameFormat.HexRgb
            )
            == LIGHT_PALETTE.background
        )
    finally:
        ThemeManager().apply(dark, theme="dark")
        dark.close()
        light.close()


def test_capture_suite_is_isolated_by_theme_route_and_section() -> None:
    jobs = _suite_jobs()

    assert len(jobs) == 2 * (len(SUITE_ROUTES) + len(SUITE_SECTIONS))
    assert {
        route
        for theme, section, route in jobs
        if theme == "dark" and section == "screens"
    } == set(SUITE_ROUTES)
    assert {
        section
        for theme, section, route in jobs
        if theme == "light" and route is None
    } == set(SUITE_SECTIONS)


def test_final_baseline_is_complete_symmetric_and_checksum_valid() -> None:
    manifest = _json(MANIFEST)
    captures = manifest["captures"]
    dark = [item for item in captures if item["theme"] == "dark"]
    light = [item for item in captures if item["theme"] == "light"]

    assert manifest["failures"] == []
    assert len(captures) == SUITE_EXPECTED_PER_THEME * 2
    assert len(dark) == len(light) == SUITE_EXPECTED_PER_THEME
    assert {item["name"] for item in dark} == {item["name"] for item in light}
    for item in captures:
        path = ROOT / item["path"]
        assert path.is_file(), path
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]


def test_final_dark_baseline_has_no_bright_surface_alerts() -> None:
    report = _json(DARK_REPORT)

    assert report["source_manifest"] == (
        "docs/ui/baseline/current/screenshot-manifest.json"
    )
    assert report["capture_count"] == SUITE_EXPECTED_PER_THEME
    assert report["flagged_count"] == 0
    assert report["flagged_names"] == []
    assert all(not item["flagged"] for item in report["results"])


def test_final_responsive_matrix_is_complete_and_clean() -> None:
    report = _json(RESPONSIVE_REPORT)

    assert report["themes"] == ["dark", "light"]
    assert len(report["routes"]) == len(SUITE_ROUTES)
    assert set(report["dpi_profiles"]) == {"dpi-100", "dpi-125", "dpi-150"}
    assert len(report["results"]) == 288
    assert report["issue_count"] == 0
    assert all(not item["issues"] for item in report["results"])
