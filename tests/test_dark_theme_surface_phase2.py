"""Phase 2 contracts for the Scanner Detail WebEngine chart surface."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

import ui.components.chart_view as chart_view_module
from ui.chart_bridge import chart_theme_script
from ui.components.chart_view import AnalysisChartView, chart_bootstrap_html
from ui.theme import DARK_PALETTE, LIGHT_PALETTE, chart_palette


ROOT = Path(__file__).resolve().parents[1]
CHART_HTML = ROOT / "assets" / "chart" / "index.html"
SCANNER_DETAIL = ROOT / "ui" / "screens" / "scanner_detail_screen.py"
_APP = QApplication.instance() or QApplication([])


def test_chart_bootstrap_applies_theme_before_first_paint() -> None:
    source = CHART_HTML.read_text(encoding="utf-8")

    for palette, theme_class in (
        (DARK_PALETTE, "dark-theme"),
        (LIGHT_PALETTE, "light-theme"),
    ):
        html = chart_bootstrap_html(source, palette)
        assert f'<html lang="vi" class="{theme_class}">' in html
        assert f'<body class="{theme_class}">' in html
        assert f"--chart-background:{palette.background};" in html
        assert "background:var(--chart-background)!important" in html


def test_chart_html_has_explicit_surface_and_complete_state_api() -> None:
    html = CHART_HTML.read_text(encoding="utf-8")

    assert "background: transparent !important" not in html
    assert "--chart-background:" in html
    assert "function applyChartTheme(theme, palette)" in html
    assert "function showEmpty()" in html
    assert "function showError(message)" in html
    assert "window.applyChartTheme = applyChartTheme;" in html
    assert "window.showEmpty = showEmpty;" in html
    assert "_chart.applyOptions" in html


def test_webengine_page_background_uses_semantic_palette() -> None:
    class FakePage:
        color: QColor | None = None

        def setBackgroundColor(self, color: QColor) -> None:
            self.color = color

    page = FakePage()
    owner = SimpleNamespace(
        _palette=DARK_PALETTE,
        _webview=SimpleNamespace(page=lambda: page),
    )

    AnalysisChartView._set_page_background(owner)

    assert page.color is not None
    assert page.color.name(QColor.NameFormat.HexRgb) == DARK_PALETTE.background


def test_scripts_queued_before_page_load_are_all_flushed_in_order() -> None:
    executed: list[str] = []
    page = SimpleNamespace(runJavaScript=executed.append)
    owner = SimpleNamespace(
        _page_loaded=False,
        _pending_scripts=[],
        _webview=SimpleNamespace(page=lambda: page),
    )

    AnalysisChartView._run_chart_script(owner, "first();")
    AnalysisChartView._run_chart_script(owner, "second();")
    AnalysisChartView._on_load_finished(owner, True)

    assert executed == ["first();", "second();"]
    assert owner._pending_scripts == []


def test_payload_theme_is_owned_by_chart_view() -> None:
    chart = AnalysisChartView()
    chart._palette = LIGHT_PALETTE

    chart.set_payload({"theme": "dark", "palette": {}, "timeframes": {}})

    assert chart._payload is not None
    assert chart._payload["theme"] == "light"
    assert chart._payload["palette"] == chart_palette(LIGHT_PALETTE)


def test_hot_switch_updates_payload_then_reloads_existing_chart(monkeypatch) -> None:
    scripts: list[str] = []
    background_updates: list[bool] = []
    owner = SimpleNamespace(
        _palette=DARK_PALETTE,
        _payload={"theme": "dark", "palette": chart_palette(DARK_PALETTE)},
        _webview=object(),
        _set_page_background=lambda: background_updates.append(True),
        _run_chart_script=scripts.append,
    )
    monkeypatch.setattr(chart_view_module, "HAS_WEBENGINE", True)

    AnalysisChartView.refresh_theme(owner, LIGHT_PALETTE)

    assert background_updates == [True]
    assert owner._payload["theme"] == "light"
    assert owner._payload["palette"] == chart_palette(LIGHT_PALETTE)
    assert "window.applyChartTheme" in scripts[0]
    assert "window.reloadChart" in scripts[1]


def test_theme_bridge_uses_json_and_scanner_detail_forwards_hot_switch() -> None:
    script = chart_theme_script("dark", chart_palette(DARK_PALETTE))
    scanner_source = SCANNER_DETAIL.read_text(encoding="utf-8")

    assert script.startswith("if(window.applyChartTheme){")
    assert 'window.applyChartTheme("dark",{' in script
    assert "def refresh_theme_styles(self)" in scanner_source
    assert "self.chart.refresh_theme(current_palette())" in scanner_source
