"""Restart button styling is owned by shared QSS, not MainWindow."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
BASE = (ROOT / "ui" / "styles" / "base.qss").read_text(encoding="utf-8")
DARK = (ROOT / "ui" / "styles" / "dark.qss").read_text(encoding="utf-8")
LIGHT = (ROOT / "ui" / "styles" / "light.qss").read_text(encoding="utf-8")


def test_restart_button_uses_shared_selector() -> None:
    start = MAIN.index('QPushButton("🔄 Khởi động lại")')
    end = MAIN.index("restart_btn.clicked.connect", start)
    block = MAIN[start:end]
    assert 'setObjectName("RestartButton")' in block
    assert "setStyleSheet" not in block


def test_restart_button_base_contract_is_transparent_and_compact() -> None:
    assert "QPushButton#RestartButton {" in BASE
    assert "background: transparent;" in BASE
    assert "border: none;" in BASE
    assert "font-size: 11px;" in BASE
    assert "padding: 4px 8px;" in BASE
    assert "margin-top: 12px;" in BASE
    assert "text-decoration: underline;" in BASE


def test_restart_button_has_dark_and_light_colors() -> None:
    assert "QPushButton#RestartButton {" in DARK
    assert "color: #0d9488;" in DARK
    assert "color: #2dd4bf;" in DARK
    assert "QPushButton#RestartButton {" in LIGHT
    assert "color: #D94625;" in LIGHT
    assert "color: #E0533C;" in LIGHT
