"""Phase 1 contracts for Qt fallback surfaces and popup/view styling."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QListWidget,
    QScrollArea,
    QSplitter,
    QWidget,
)

from ui.theme import DARK_PALETTE, LIGHT_PALETTE
from ui.theme_manager import ThemeManager, build_qpalette


ROOT = Path(__file__).resolve().parents[1]
DARK_QSS = ROOT / "ui" / "styles" / "dark.qss"
LIGHT_QSS = ROOT / "ui" / "styles" / "light.qss"
_APP = QApplication.instance() or QApplication([])


def _hex(palette: QPalette, role: QPalette.ColorRole) -> str:
    return palette.color(role).name(QColor.NameFormat.HexRgb)


def test_semantic_qpalette_maps_dark_and_light_fallback_roles() -> None:
    dark = build_qpalette(DARK_PALETTE)
    light = build_qpalette(LIGHT_PALETTE)
    assert _hex(dark, QPalette.ColorRole.Window) == DARK_PALETTE.background
    assert _hex(dark, QPalette.ColorRole.Base) == DARK_PALETTE.surface_sunken
    assert _hex(dark, QPalette.ColorRole.Text) == DARK_PALETTE.text
    assert _hex(dark, QPalette.ColorRole.Highlight) == DARK_PALETTE.accent
    assert _hex(light, QPalette.ColorRole.Window) == LIGHT_PALETTE.background
    assert _hex(light, QPalette.ColorRole.Base) == LIGHT_PALETTE.surface_sunken
    assert _hex(light, QPalette.ColorRole.Text) == LIGHT_PALETTE.text


def test_theme_manager_updates_application_and_descendant_fallback_palette() -> None:
    root = QWidget()
    scroll = QScrollArea(root)
    scroll.setWidget(QWidget())
    item_view = QListWidget(root)
    splitter = QSplitter(root)

    ThemeManager().apply(root, theme="dark")
    for widget in (root, scroll, scroll.viewport(), item_view, splitter):
        assert (
            _hex(widget.palette(), QPalette.ColorRole.Window)
            == DARK_PALETTE.background
        )
    assert (
        _hex(item_view.palette(), QPalette.ColorRole.Base)
        == DARK_PALETTE.surface_sunken
    )

    ThemeManager().apply(root, theme="light")
    assert _hex(_APP.palette(), QPalette.ColorRole.Window) == LIGHT_PALETTE.background
    assert _hex(root.palette(), QPalette.ColorRole.Window) == LIGHT_PALETTE.background
    assert _hex(item_view.palette(), QPalette.ColorRole.Base) == LIGHT_PALETTE.surface_sunken


def test_theme_overlays_cover_default_surface_families_symmetrically() -> None:
    dark = DARK_QSS.read_text(encoding="utf-8")
    light = LIGHT_QSS.read_text(encoding="utf-8")
    required = (
        "QAbstractScrollArea",
        "QWidget#qt_scrollarea_viewport",
        "QAbstractItemView",
        "QScrollBar:horizontal",
        "QScrollBar:vertical",
        "QSplitter::handle",
        "QMenu::item:selected",
        "QMenu::item:disabled",
    )
    for selector in required:
        assert selector in dark
        assert selector in light


def test_phase1_does_not_add_local_widget_stylesheets() -> None:
    for path in (ROOT / "ui" / "screens").glob("*.py"):
        assert ".setStyleSheet(" not in path.read_text(encoding="utf-8"), path
