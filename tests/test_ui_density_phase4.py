from __future__ import annotations

from pathlib import Path
import re

from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication, QCheckBox, QDialog, QRadioButton, QVBoxLayout

from tools.ui_density_audit import ROOT, UI_ROOT, audit_python_heights
from ui.theme_manager import APP_THEME_PROPERTY, load_stylesheet


SCREEN_CLUSTER_FILES = {
    "ui/screens/journal_screen.py",
    "ui/screens/journal_detail_screen.py",
    "ui/screens/backtest_screen.py",
    "ui/screens/settings_screen.py",
    "ui/screens/scanner_screen.py",
    "ui/screens/scanner_detail_screen.py",
    "ui/screens/orders_screen.py",
    "ui/screens/dashboard_screen.py",
    "ui/screens/shared.py",
}
THEME_FILES = (
    ROOT / "ui" / "styles" / "dark.qss",
    ROOT / "ui" / "styles" / "light.qss",
)
INTERACTIVE_SELECTOR_TOKENS = (
    "QPushButton",
    "QToolButton",
    "QLineEdit",
    "QComboBox",
    "QSpinBox",
    "QDoubleSpinBox",
    "QDateEdit",
    "QDateTimeEdit",
    "QTimeEdit",
    "QCheckBox",
    "QRadioButton",
    "QTabBar::tab",
)
PRESENTATION_PROPERTIES = {
    "padding",
    "padding-left",
    "padding-right",
    "padding-top",
    "padding-bottom",
    "margin",
    "margin-left",
    "margin-right",
    "margin-top",
    "margin-bottom",
    "font-size",
    "font-weight",
    "font-family",
    "min-height",
    "max-height",
    "height",
    "min-width",
    "max-width",
    "width",
    "spacing",
    "border-radius",
    "text-align",
}
BLOCK_RE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.DOTALL)
COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def _interactive_presentation_declarations(path: Path) -> list[str]:
    source = COMMENT_RE.sub("", path.read_text(encoding="utf-8"))
    found: list[str] = []
    for match in BLOCK_RE.finditer(source):
        selector = " ".join(match.group(1).split())
        if not any(token in selector for token in INTERACTIVE_SELECTOR_TOKENS):
            continue
        for declaration in match.group(2).split(";"):
            if ":" not in declaration:
                continue
            name, _value = declaration.split(":", 1)
            if name.strip() in PRESENTATION_PROPERTIES:
                found.append(f"{selector}: {name.strip()}")
    return found


def test_all_screen_clusters_delegate_interactive_height_to_shared_qss() -> None:
    entries = [
        entry
        for entry in audit_python_heights()
        if entry["path"] in SCREEN_CLUSTER_FILES
    ]
    assert not [
        entry
        for entry in entries
        if entry["category"] in {"interactive", "review"}
    ]
    for relative_path in SCREEN_CLUSTER_FILES:
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert ".setStyleSheet(" not in source, relative_path


def test_theme_overlays_only_own_interactive_colors_and_states() -> None:
    for path in THEME_FILES:
        assert _interactive_presentation_declarations(path) == [], path


def test_scanner_dialog_controls_keep_24px_contract_in_both_themes() -> None:
    app = QApplication.instance() or QApplication([])
    original_stylesheet = app.styleSheet()
    original_palette = QPalette(app.palette())
    original_theme = app.property(APP_THEME_PROPERTY)
    try:
        for theme in ("dark", "light"):
            app.setStyleSheet(load_stylesheet(theme, ui_dir=UI_ROOT))
            dialog = QDialog()
            dialog.setObjectName("ScannerHelpDialog")
            layout = QVBoxLayout(dialog)
            radio = QRadioButton("Chế độ giải thích")
            symbol = QCheckBox("EUR/USD")
            symbol.setObjectName("ScannerSymbolCheck")
            layout.addWidget(radio)
            layout.addWidget(symbol)
            dialog.show()
            app.processEvents()
            assert radio.height() == 24, (theme, radio.height())
            assert radio.sizeHint().height() == 24, (theme, radio.sizeHint().height())
            assert symbol.height() == 24, (theme, symbol.height())
            assert symbol.sizeHint().height() == 24, (
                theme,
                symbol.sizeHint().height(),
            )
            dialog.close()
            dialog.deleteLater()
            app.processEvents()
    finally:
        app.setStyleSheet(original_stylesheet)
        app.setPalette(original_palette)
        app.setProperty(APP_THEME_PROPERTY, original_theme)
        app.processEvents()
