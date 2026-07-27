"""Single entry point for resolving, applying and refreshing UI themes."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Protocol

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QWidget

from ui.theme import ThemePalette, color_for_role, normalize_theme, palette_for


APP_THEME_PROPERTY = "amaTheme"


class _SettingsLoader(Protocol):
    def load(self): ...


def runtime_ui_dir() -> Path:
    """Return the UI resource directory in source and PyInstaller builds."""

    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "ui"
    return Path(__file__).resolve().parent


def resolve_theme(
    *,
    theme: object | None = None,
    settings_service: _SettingsLoader | None = None,
) -> str:
    """Resolve a theme through one normalized precedence chain.

    Explicit input wins, followed by an explicitly supplied settings service,
    the QApplication property, and finally the persisted settings fallback.
    """

    if theme is not None:
        return normalize_theme(theme)

    if settings_service is not None:
        try:
            return normalize_theme(settings_service.load().display.theme)
        except Exception:
            pass

    app = QApplication.instance()
    if app is not None:
        app_theme = app.property(APP_THEME_PROPERTY)
        if app_theme:
            return normalize_theme(app_theme)

    try:
        from services.settings_service import SettingsService

        return normalize_theme(SettingsService().load().display.theme)
    except Exception:
        return "dark"


def current_palette(
    settings_service: _SettingsLoader | None = None,
) -> ThemePalette:
    return palette_for(resolve_theme(settings_service=settings_service))


def is_light_theme(
    settings_service: _SettingsLoader | None = None,
) -> bool:
    return resolve_theme(settings_service=settings_service) == "light"


def semantic_qcolor(
    role: object,
    *,
    settings_service: _SettingsLoader | None = None,
    palette: ThemePalette | None = None,
    alpha: int | None = None,
) -> QColor:
    """Create QColor from a semantic role, optionally as a soft tint."""

    resolved = palette or current_palette(settings_service)
    color = QColor(color_for_role(resolved, role))
    if alpha is not None:
        color.setAlpha(max(0, min(255, int(alpha))))
    return color


def build_qpalette(palette: ThemePalette) -> QPalette:
    """Build the Qt fallback palette from the shared semantic palette.

    QSS remains responsible for component variants. The QPalette covers
    platform-painted viewports, popup internals and unnamed intermediate
    widgets so they never fall back to the operating system's light palette.
    """

    result = QPalette()
    colors = {
        QPalette.ColorRole.Window: palette.background,
        QPalette.ColorRole.WindowText: palette.text,
        QPalette.ColorRole.Base: palette.surface_sunken,
        QPalette.ColorRole.AlternateBase: palette.surface,
        QPalette.ColorRole.ToolTipBase: palette.surface_raised,
        QPalette.ColorRole.ToolTipText: palette.text,
        QPalette.ColorRole.Text: palette.text,
        QPalette.ColorRole.Button: palette.surface_raised,
        QPalette.ColorRole.ButtonText: palette.text,
        QPalette.ColorRole.BrightText: palette.selection_text,
        QPalette.ColorRole.Light: palette.border_strong,
        QPalette.ColorRole.Midlight: palette.border,
        QPalette.ColorRole.Mid: palette.border,
        QPalette.ColorRole.Dark: palette.background,
        QPalette.ColorRole.Shadow: palette.background,
        QPalette.ColorRole.Highlight: palette.accent,
        QPalette.ColorRole.HighlightedText: palette.selection_text,
        QPalette.ColorRole.Link: palette.info,
        QPalette.ColorRole.LinkVisited: palette.accent_hover,
        QPalette.ColorRole.PlaceholderText: palette.text_subtle,
    }
    accent_role = getattr(QPalette.ColorRole, "Accent", None)
    if accent_role is not None:
        colors[accent_role] = palette.accent
    for role, value in colors.items():
        result.setColor(role, QColor(value))

    disabled = QPalette.ColorGroup.Disabled
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.PlaceholderText,
    ):
        result.setColor(disabled, role, QColor(palette.text_subtle))
    result.setColor(disabled, QPalette.ColorRole.Highlight, QColor(palette.border))
    result.setColor(
        disabled,
        QPalette.ColorRole.HighlightedText,
        QColor(palette.text_muted),
    )
    return result


def load_stylesheet(
    theme: object,
    *,
    ui_dir: Path | None = None,
) -> str:
    """Load common structural rules before the selected color overlay."""

    resolved = normalize_theme(theme)
    directory = ui_dir or runtime_ui_dir()
    base_path = directory / "styles" / "base.qss"
    overlay_name = "light.qss" if resolved == "light" else "dark.qss"
    overlay_path = directory / "styles" / overlay_name

    chunks: list[str] = []
    if base_path.exists():
        chunks.append(base_path.read_text(encoding="utf-8").strip())
    if not overlay_path.exists():
        raise FileNotFoundError(f"Theme overlay not found: {overlay_path}")
    chunks.append(overlay_path.read_text(encoding="utf-8").strip())
    return "\n\n".join(chunk for chunk in chunks if chunk) + "\n"


def repolish(widget: QWidget, *, recursive: bool = False) -> None:
    """Re-evaluate QSS selectors after a dynamic property changes."""

    targets = [widget]
    if recursive:
        targets.extend(widget.findChildren(QWidget))
    for target in targets:
        style = target.style()
        if style is not None:
            style.unpolish(target)
            style.polish(target)
        target.update()


def set_dynamic_property(
    widget: QWidget,
    name: str,
    value: object,
    *,
    recursive: bool = False,
) -> None:
    """Set a QSS property and refresh the affected widget consistently."""

    if widget.property(name) == value:
        return
    widget.setProperty(name, value)
    repolish(widget, recursive=recursive)


class ThemeManager:
    """Apply the application stylesheet and expose the active palette."""

    def __init__(self, *, ui_dir: Path | None = None) -> None:
        self.ui_dir = ui_dir or runtime_ui_dir()

    def apply(
        self,
        target: QWidget,
        *,
        theme: object | None = None,
        settings_service: _SettingsLoader | None = None,
    ) -> ThemePalette:
        resolved = resolve_theme(
            theme=theme,
            settings_service=settings_service,
        )
        app = QApplication.instance()
        semantic_palette = palette_for(resolved)
        qt_palette = build_qpalette(semantic_palette)
        if app is not None:
            app.setProperty(APP_THEME_PROPERTY, resolved)
            app.setPalette(qt_palette)
        target.setProperty(APP_THEME_PROPERTY, resolved)
        target.setPalette(qt_palette)
        target.setStyleSheet(
            load_stylesheet(resolved, ui_dir=self.ui_dir)
        )
        return semantic_palette
