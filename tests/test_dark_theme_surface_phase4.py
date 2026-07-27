"""Phase 4 guards for residual dark controls and application dialogs."""

from __future__ import annotations

import os
import re
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QFileDialog, QPushButton, QVBoxLayout, QWidget

from ui.screens.backtest_screen import BacktestScreen
from ui.theme_manager import ThemeManager


ROOT = Path(__file__).resolve().parents[1]
DARK_QSS = ROOT / "ui" / "styles.qss"
LIGHT_QSS = ROOT / "ui" / "styles_light.qss"
BACKTEST = ROOT / "ui" / "screens" / "backtest_screen.py"
_APP = QApplication.instance() or QApplication([])


def _selector_block(source: str, selector: str) -> str:
    match = re.search(
        rf"{re.escape(selector)}\s*\{{(?P<body>.*?)\}}",
        source,
        flags=re.DOTALL,
    )
    assert match is not None, selector
    return match.group("body")


def test_help_button_uses_theme_specific_surface_instead_of_light_fill() -> None:
    dark = _selector_block(DARK_QSS.read_text(encoding="utf-8"), "QPushButton#HelpButton")
    light = _selector_block(LIGHT_QSS.read_text(encoding="utf-8"), "QPushButton#HelpButton")

    assert "background: #1f2937;" in dark
    assert "color: #cbd5e1;" in dark
    assert "border: 1px solid #475569;" in dark
    assert "background: #e2e8f0;" in light


def test_dark_overlay_has_no_neutral_bright_background_literal() -> None:
    source = DARK_QSS.read_text(encoding="utf-8")
    declarations = re.findall(
        r"background(?:-color)?\s*:\s*(#[0-9a-fA-F]{3,6})\s*;",
        source,
    )
    offenders: list[str] = []
    for value in declarations:
        raw = value.lstrip("#")
        if len(raw) == 3:
            raw = "".join(channel * 2 for channel in raw)
        red, green, blue = (
            int(raw[index:index + 2], 16) for index in (0, 2, 4)
        )
        if min(red, green, blue) >= 215 and max(red, green, blue) - min(red, green, blue) <= 30:
            offenders.append(value)

    assert offenders == []


def test_backtest_file_picker_uses_qt_dialog_for_theme_consistency() -> None:
    source = BACKTEST.read_text(encoding="utf-8")

    assert "options=QFileDialog.Option.DontUseNativeDialog" in source
    assert QFileDialog.Option.DontUseNativeDialog.value != 0


def test_backtest_file_picker_passes_non_native_option(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_open(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return "", ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", fake_open)

    BacktestScreen._load_backtest_file(SimpleNamespace())

    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["options"] == QFileDialog.Option.DontUseNativeDialog


def test_help_button_renders_dark_after_theme_application() -> None:
    root = QWidget()
    layout = QVBoxLayout(root)
    button = QPushButton("?")
    button.setObjectName("HelpButton")
    layout.addWidget(button)
    manager = ThemeManager()
    try:
        manager.apply(root, theme="dark")
        root.show()
        _APP.processEvents()
        image = button.grab().toImage()
        background = DARK_QSS.read_text(encoding="utf-8")
        assert "background: #1f2937;" in background
        expected = "#1f2937"
        matching_pixels = sum(
            QColor.fromRgba(image.pixel(x, y)).name().lower() == expected
            for y in range(image.height())
            for x in range(image.width())
        )
        assert matching_pixels > 20
    finally:
        root.close()


def test_popup_and_messagebox_contracts_exist_in_both_themes() -> None:
    required = (
        "QDialog,",
        "QMenu,",
        "QCalendarWidget,",
        "QToolTip {",
        "QMessageBox {",
        "QMessageBox QLabel {",
        "QMessageBox QPushButton {",
    )
    for path in (DARK_QSS, LIGHT_QSS):
        source = path.read_text(encoding="utf-8")
        for selector in required:
            assert selector in source, (path.name, selector)
