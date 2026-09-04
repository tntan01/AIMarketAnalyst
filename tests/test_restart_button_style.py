"""Restart button styling is owned by shared QSS, not MainWindow."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
BASE = (ROOT / "ui" / "styles" / "base.qss").read_text(encoding="utf-8")
DARK = (ROOT / "ui" / "styles" / "dark.qss").read_text(encoding="utf-8")
LIGHT = (ROOT / "ui" / "styles" / "light.qss").read_text(encoding="utf-8")


def test_restart_button_uses_shared_selector() -> None:
    start = MAIN.index('setToolTip("Khởi động lại")')
    end = MAIN.index("restart_btn.clicked.connect", start)
    block = MAIN[start:end]
    assert 'setObjectName("RestartButton")' in block
    assert "setStyleSheet" not in block
    assert "flat_icon(" not in block or "_NavIconFilter" in MAIN
    assert "setIconSize" in block
    assert ".setText(" not in block


def test_restart_button_base_contract_is_transparent_and_square() -> None:
    assert "QPushButton#RestartButton {" in BASE
    restart_block = BASE[
        BASE.index("QPushButton#RestartButton {"):
        BASE.index("QPushButton#RestartButton:hover,")
    ]
    hover_block = BASE[
        BASE.index("QPushButton#RestartButton:hover,"):
        BASE.index("QWidget#AnalysisChartSurface,")
    ]
    block = restart_block + hover_block
    assert "background: transparent;" in block
    assert "border: 1px solid transparent;" in block
    assert "@QSS_BUTTON@" in block
    assert "margin: 0;" in block
    # Ô vuông 40×40 (content 38 + border 1px×2), bo góc 10 — đồng bộ NavButton
    assert "min-width: 38px;" in block
    assert "max-width: 38px;" in block
    assert "min-height: 38px;" in block
    assert "max-height: 38px;" in block
    assert "border-radius: 10px;" in block
    assert "padding: 4px 8px;" not in block
    assert "underline" not in block


def test_restart_button_has_dark_and_light_colors() -> None:
    assert "QPushButton#RestartButton {" in DARK
    assert "color: #0d9488;" in DARK
    assert "color: #2dd4bf;" in DARK
    assert "QPushButton#RestartButton {" in LIGHT
    assert "color: #D94625;" in LIGHT
    assert "color: #E0533C;" in LIGHT
