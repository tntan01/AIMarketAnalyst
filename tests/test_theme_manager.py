from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QWidget

from ui.theme import (
    DARK_PALETTE,
    LIGHT_PALETTE,
    PALETTES,
    normalize_theme,
    palette_for,
)
from ui.theme_manager import (
    APP_THEME_PROPERTY,
    ThemeManager,
    is_light_theme,
    load_stylesheet,
    repolish,
    resolve_theme,
    set_dynamic_property,
)

_QT_APP = QApplication.instance() or QApplication([])


def _application() -> QApplication:
    return _QT_APP


def _settings_service(theme: str):
    service = MagicMock()
    service.load.return_value = SimpleNamespace(
        display=SimpleNamespace(theme=theme)
    )
    return service


def test_semantic_palettes_cover_required_roles() -> None:
    required = {
        "background",
        "surface",
        "text",
        "text_muted",
        "border",
        "accent",
        "success",
        "warning",
        "danger",
        "info",
        "buy",
        "sell",
        "neutral",
    }
    assert set(PALETTES) == {"dark", "light"}
    assert required <= set(DARK_PALETTE.to_dict())
    assert required <= set(LIGHT_PALETTE.to_dict())
    assert DARK_PALETTE.background != LIGHT_PALETTE.background
    assert DARK_PALETTE.text != LIGHT_PALETTE.text


def test_theme_names_are_normalized_safely() -> None:
    assert normalize_theme("LIGHT") == "light"
    assert normalize_theme(" dark ") == "dark"
    assert normalize_theme("unsupported") == "dark"
    assert palette_for(None) is DARK_PALETTE
    assert palette_for("light") is LIGHT_PALETTE


def test_theme_resolution_uses_central_precedence() -> None:
    app = _application()
    app.setProperty(APP_THEME_PROPERTY, "dark")
    assert resolve_theme(theme="light") == "light"
    assert resolve_theme(settings_service=_settings_service("light")) == "light"
    assert resolve_theme() == "dark"
    assert is_light_theme(_settings_service("light")) is True


def test_stylesheet_pipeline_loads_base_then_theme_overlay() -> None:
    ui_dir = Path(__file__).resolve().parents[1] / "ui"
    base_marker = "Shared visual foundation for both themes"
    dark = load_stylesheet("dark", ui_dir=ui_dir)
    light = load_stylesheet("light", ui_dir=ui_dir)
    assert base_marker in dark
    assert base_marker in light
    assert "QMainWindow" in dark
    assert "QMainWindow" in light
    assert dark != light


def test_theme_manager_applies_theme_and_exposes_it_to_children() -> None:
    app = _application()
    target = QWidget()
    child = QWidget(target)
    palette = ThemeManager().apply(target, theme="light")
    assert palette is LIGHT_PALETTE
    assert app.property(APP_THEME_PROPERTY) == "light"
    assert target.property(APP_THEME_PROPERTY) == "light"
    assert "QMainWindow" in target.styleSheet()
    assert child.parentWidget() is target


def test_dynamic_property_helper_sets_and_repolishes() -> None:
    _application()
    widget = QWidget()
    set_dynamic_property(widget, "state", "warning")
    assert widget.property("state") == "warning"
    repolish(widget, recursive=True)
