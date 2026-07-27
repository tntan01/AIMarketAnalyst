"""Semantic theme helpers shared by Qt-embedded Matplotlib charts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ui.theme import ThemePalette, chart_palette
from ui.theme_manager import current_palette


def apply_figure_theme(
    figure: Any,
    palette: ThemePalette | None = None,
) -> dict[str, str]:
    """Apply the active semantic background to a Matplotlib figure."""

    colors = chart_palette(palette or current_palette())
    figure.set_facecolor(colors["background"])
    if getattr(figure, "patch", None) is not None:
        figure.patch.set_facecolor(colors["background"])
        figure.patch.set_edgecolor(colors["background"])
    return colors


def apply_axes_theme(axes: Any, colors: Mapping[str, str]) -> None:
    """Apply semantic surface/text/border colors to existing axes."""

    axes.set_facecolor(colors["background"])
    axes.tick_params(axis="both", colors=colors["text"])
    axes.title.set_color(colors["text"])
    axes.xaxis.label.set_color(colors["text"])
    axes.yaxis.label.set_color(colors["text"])
    axes.xaxis.get_offset_text().set_color(colors["text"])
    axes.yaxis.get_offset_text().set_color(colors["text"])
    for spine in axes.spines.values():
        spine.set_color(colors["grid"])


def apply_legend_theme(legend: Any, colors: Mapping[str, str]) -> None:
    """Keep legend text/frame consistent with the active chart surface."""

    if legend is None:
        return
    frame = legend.get_frame()
    frame.set_facecolor(colors["surface"])
    frame.set_edgecolor(colors["border"])
    for text in legend.get_texts():
        text.set_color(colors["text"])
