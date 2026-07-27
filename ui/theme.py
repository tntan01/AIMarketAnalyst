from __future__ import annotations

from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True, slots=True)
class ThemePalette:
    """Semantic colors shared by Qt widgets, rich text and charts."""

    name: str
    background: str
    surface: str
    surface_raised: str
    surface_sunken: str
    text: str
    text_muted: str
    text_subtle: str
    border: str
    border_strong: str
    accent: str
    accent_hover: str
    accent_soft: str
    success: str
    warning: str
    danger: str
    info: str
    buy: str
    sell: str
    neutral: str
    focus: str
    selection_text: str
    chart_grid: str
    chart_equity: str
    chart_drawdown: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


DARK_PALETTE = ThemePalette(
    name="dark",
    background="#0f1216",
    surface="#171c24",
    surface_raised="#1f2937",
    surface_sunken="#0f172a",
    text="#e5e7eb",
    text_muted="#9ca3af",
    text_subtle="#64748b",
    border="#334155",
    border_strong="#475569",
    accent="#0f766e",
    accent_hover="#14b8a6",
    accent_soft="#12352f",
    success="#10b981",
    warning="#f59e0b",
    danger="#ef4444",
    info="#38bdf8",
    buy="#10b981",
    sell="#f43f5e",
    neutral="#94a3b8",
    focus="#5eead4",
    selection_text="#ffffff",
    chart_grid="#1e2227",
    chart_equity="#2196f3",
    chart_drawdown="#f44336",
)

LIGHT_PALETTE = ThemePalette(
    name="light",
    background="#f4f1ea",
    surface="#faf9f5",
    surface_raised="#eae6df",
    surface_sunken="#ffffff",
    text="#111827",
    text_muted="#736b60",
    text_subtle="#78716c",
    border="#d6d2c8",
    border_strong="#a19b90",
    accent="#d94625",
    accent_hover="#e0533c",
    accent_soft="#fce8e5",
    success="#059669",
    warning="#d97706",
    danger="#e11d48",
    info="#0284c7",
    buy="#059669",
    sell="#b91c1c",
    neutral="#78716c",
    focus="#d94625",
    selection_text="#ffffff",
    chart_grid="#e5e7eb",
    chart_equity="#1976d2",
    chart_drawdown="#d32f2f",
)

PALETTES: Mapping[str, ThemePalette] = MappingProxyType(
    {
        "dark": DARK_PALETTE,
        "light": LIGHT_PALETTE,
    }
)


def normalize_theme(theme: object) -> str:
    """Return a supported theme name, defaulting safely to dark."""

    value = str(theme or "").strip().lower()
    return value if value in PALETTES else "dark"


def palette_for(theme: object) -> ThemePalette:
    """Return the immutable semantic palette for *theme*."""

    return PALETTES[normalize_theme(theme)]


_SEMANTIC_COLOR_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        "#00c853": "success",
        "#059669": "success",
        "#10b981": "success",
        "#22c55e": "success",
        "#d32f2f": "danger",
        "#b91c1c": "danger",
        "#e11d48": "danger",
        "#ef4444": "danger",
        "#f43f5e": "danger",
        "#f87171": "danger",
        "#d97706": "warning",
        "#ea580c": "warning",
        "#f59e0b": "warning",
        "#fbbf24": "warning",
        "#fb923c": "warning",
        "#0284c7": "info",
        "#1976d2": "info",
        "#2196f3": "info",
        "#38bdf8": "info",
        "#3b82f6": "info",
        "#0d9488": "accent",
        "#0f766e": "accent",
        "#14b8a6": "accent",
        "#d94625": "accent",
        "#e0533c": "accent",
        "#5eead4": "focus",
        "#64748b": "muted",
        "#6b7280": "muted",
        "#736b60": "muted",
        "#78716c": "muted",
        "#94a3b8": "muted",
        "#9ca3af": "muted",
        "#cbd5e1": "text",
        "#d1d5db": "text",
        "#e5e7eb": "text",
        "#f3f4f6": "text",
        "#f8fafc": "text",
        "#111827": "text",
        "#1f2937": "text",
    }
)


def semantic_role_for_color(color: object, *, default: str = "neutral") -> str:
    """Map legacy/runtime colors to a stable semantic role.

    This adapter lets data-producing code keep its backward-compatible return
    contract while widgets and rich-text renderers consume semantic roles.
    """

    value = str(color or "").strip().lower()
    return _SEMANTIC_COLOR_ALIASES.get(value, default)


def color_for_role(
    palette: ThemePalette,
    role: object,
    *,
    default: str = "neutral",
) -> str:
    """Resolve a semantic role against *palette* without exposing literals."""

    normalized = str(role or default).strip().lower()
    aliases = {
        "positive": "success",
        "negative": "danger",
        "error": "danger",
        "risk": "danger",
        "caution": "warning",
        "primary": "accent",
        "secondary": "muted",
        "muted": "text_muted",
        "subtle": "text_subtle",
    }
    attribute = aliases.get(normalized, normalized)
    return str(getattr(palette, attribute, getattr(palette, default)))


def chart_palette(palette: ThemePalette) -> dict[str, str]:
    """Return the shared WebEngine/Matplotlib chart color contract."""

    return {
        "background": palette.background,
        "surface": palette.surface,
        "surfaceRaised": palette.surface_raised,
        "text": palette.text,
        "grid": palette.chart_grid,
        "border": palette.border,
        "accent": palette.accent,
        "selectionText": palette.selection_text,
        "equity": palette.chart_equity,
        "drawdown": palette.chart_drawdown,
        "buy": palette.buy,
        "sell": palette.sell,
        "neutral": palette.neutral,
        "warning": palette.warning,
        "info": palette.info,
    }
