"""Phase 3 contracts for Qt-embedded Matplotlib chart surfaces."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QWidget

from ui.matplotlib_theme import (
    apply_axes_theme,
    apply_figure_theme,
    apply_legend_theme,
)
from ui.screens.backtest_screen import BacktestScreen
from ui.screens.journal_screen import (
    HAS_MATPLOTLIB,
    JournalScreen,
    PerformanceChartWidget,
)
from ui.theme import DARK_PALETTE, LIGHT_PALETTE, chart_palette
from ui.theme_manager import ThemeManager


_APP = QApplication.instance() or QApplication([])


def _hex(color: object) -> str:
    from matplotlib.colors import to_hex

    return to_hex(color, keep_alpha=False).lower()


@pytest.mark.skipif(not HAS_MATPLOTLIB, reason="matplotlib is unavailable")
def test_shared_matplotlib_theme_covers_figure_axes_and_legend() -> None:
    from matplotlib.figure import Figure

    figure = Figure()
    colors = apply_figure_theme(figure, DARK_PALETTE)
    axes = figure.add_subplot(111)
    axes.plot([0, 1], [0, 1], label="Equity")
    axes.set_title("Title")
    axes.set_xlabel("X")
    axes.set_ylabel("Y")
    apply_axes_theme(axes, colors)
    legend = axes.legend()
    apply_legend_theme(legend, colors)

    assert _hex(figure.get_facecolor()) == DARK_PALETTE.background
    assert _hex(axes.get_facecolor()) == DARK_PALETTE.background
    assert _hex(axes.title.get_color()) == DARK_PALETTE.text
    assert _hex(legend.get_frame().get_facecolor()) == DARK_PALETTE.surface
    assert all(_hex(text.get_color()) == DARK_PALETTE.text for text in legend.get_texts())


@pytest.mark.skipif(not HAS_MATPLOTLIB, reason="matplotlib is unavailable")
def test_backtest_chart_is_themed_while_empty_and_after_hot_switch() -> None:
    root = QWidget()
    manager = ThemeManager()
    manager.apply(root, theme="dark")
    screen = BacktestScreen(app=MagicMock())
    try:
        assert _hex(screen._equity_figure.get_facecolor()) == DARK_PALETTE.background
        assert len(screen._equity_figure.axes) == 1
        assert "Chưa có kết quả backtest" in screen._equity_figure.axes[0].texts[0].get_text()

        manager.apply(root, theme="light")
        screen.refresh_theme_styles()

        assert _hex(screen._equity_figure.get_facecolor()) == LIGHT_PALETTE.background
        assert _hex(screen._equity_figure.axes[0].get_facecolor()) == LIGHT_PALETTE.background
        assert _hex(screen._equity_figure.axes[0].texts[0].get_color()) == LIGHT_PALETTE.neutral
    finally:
        screen.close()
        manager.apply(root, theme="dark")
        root.close()


@pytest.mark.skipif(not HAS_MATPLOTLIB, reason="matplotlib is unavailable")
def test_journal_chart_preserves_data_across_hot_theme_switch() -> None:
    root = QWidget()
    manager = ThemeManager()
    manager.apply(root, theme="dark")
    chart = PerformanceChartWidget()
    by_symbol = [{"label": "EUR/USD", "net_amount": 125.0}]
    trades = [
        {
            "symbol": "EUR/USD",
            "closed_at": "2026-07-01T10:00:00",
            "result_amount": 125.0,
        }
    ]
    try:
        assert len(chart.figure.axes) == 2
        assert all(
            _hex(axes.get_facecolor()) == DARK_PALETTE.background
            for axes in chart.figure.axes
        )

        chart.update_charts(by_symbol, trades, selected_symbol="EUR/USD")
        manager.apply(root, theme="light")
        chart.refresh_theme_styles()

        assert chart._last_by_symbol == by_symbol
        assert chart._last_recent_trades == trades
        assert chart._last_selected_symbol == "EUR/USD"
        assert _hex(chart.figure.get_facecolor()) == LIGHT_PALETTE.background
        assert all(
            _hex(axes.get_facecolor()) == LIGHT_PALETTE.background
            for axes in chart.figure.axes
        )
        assert chart.figure.axes[0].patches
        assert chart.figure.axes[1].lines
    finally:
        chart.close()
        manager.apply(root, theme="dark")
        root.close()


def test_journal_screen_forwards_theme_refresh_to_chart() -> None:
    calls: list[bool] = []
    owner = SimpleNamespace(
        performance_chart=SimpleNamespace(
            refresh_theme_styles=lambda: calls.append(True)
        )
    )

    JournalScreen.refresh_theme_styles(owner)

    assert calls == [True]


def test_shared_chart_palette_remains_the_single_color_contract() -> None:
    dark = chart_palette(DARK_PALETTE)
    light = chart_palette(LIGHT_PALETTE)

    assert dark["background"] == DARK_PALETTE.background
    assert dark["grid"] == DARK_PALETTE.chart_grid
    assert light["background"] == LIGHT_PALETTE.background
    assert light["grid"] == LIGHT_PALETTE.chart_grid
