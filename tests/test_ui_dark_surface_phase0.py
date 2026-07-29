"""Phase 0 contracts for repeatable dark-surface inventory."""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QRect
from PyQt6.QtGui import QColor, QImage, QPainter

from tools.ui_dark_surface_audit import analyze_image


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "ui" / "reports" / "dark-surface-report.json"
MANIFEST = (
    ROOT
    / "docs"
    / "ui"
    / "baseline"
    / "current"
    / "screenshot-manifest.json"
)


def _save_surface(path: Path, *, with_large_surface: bool) -> None:
    image = QImage(400, 240, QImage.Format.Format_RGB888)
    image.fill(QColor("#101214"))
    painter = QPainter(image)
    # Small disconnected bright marks model normal text/icon strokes without
    # requiring a GUI font engine in this non-QApplication unit test.
    for index in range(12):
        painter.fillRect(
            QRect(20 + index * 10, 24, 5, 8),
            QColor("#f3f4f6"),
        )
    if with_large_surface:
        painter.fillRect(QRect(80, 60, 240, 140), QColor("#ffffff"))
    painter.end()
    assert image.save(str(path), "PNG")


def test_dark_surface_detector_flags_large_bright_region(tmp_path: Path) -> None:
    screenshot = tmp_path / "bright-region.png"
    _save_surface(screenshot, with_large_surface=True)
    result = analyze_image(screenshot)
    assert result["flagged"] is True
    assert result["largest_component_ratio"] > 0.25


def test_dark_surface_detector_ignores_normal_bright_text(tmp_path: Path) -> None:
    screenshot = tmp_path / "dark-with-text.png"
    _save_surface(screenshot, with_large_surface=False)
    result = analyze_image(screenshot)
    assert result["flagged"] is False


def test_committed_report_covers_every_dark_baseline_capture() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    dark_captures = [
        item for item in manifest["captures"] if item["theme"] == "dark"
    ]
    assert report["schema_version"] == 1
    assert report["theme"] == "dark"
    assert report["capture_count"] == len(dark_captures)
    assert {item["name"] for item in report["results"]} == {
        item["name"] for item in dark_captures
    }
