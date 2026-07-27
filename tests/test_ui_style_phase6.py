"""Phase 6 contracts for rich text, tables and chart palette centralization."""

from __future__ import annotations

import ast
from pathlib import Path
import re

from ui.rich_text import compile_rich_html, empty_state_html
from ui.theme import DARK_PALETTE, LIGHT_PALETTE, chart_palette
from tools.ui_style_audit import build_inventory


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui"


def test_rich_text_compiler_removes_inline_style_attributes() -> None:
    html = (
        "<h2 style='color:#10b981;font-size:15px'>Kết quả</h2>"
        "<table style='border-collapse:collapse'><td style='color:#ef4444'>-1R</td></table>"
    )
    rendered = compile_rich_html(html, palette=DARK_PALETTE)
    assert 'style="' not in rendered
    assert "rt-rule-" in rendered
    assert DARK_PALETTE.success in rendered
    assert DARK_PALETTE.danger in rendered
    assert 'data-ama-rich-text="1"' in rendered


def test_rich_text_compiler_is_idempotent_and_supports_light_palette() -> None:
    rendered = compile_rich_html(
        "<p style='color:#10b981'>Đạt</p>",
        palette=LIGHT_PALETTE,
    )
    assert compile_rich_html(rendered, palette=DARK_PALETTE) == rendered
    assert LIGHT_PALETTE.success in rendered


def test_empty_state_uses_shared_role_classes() -> None:
    rendered = empty_state_html("Thiếu dữ liệu", tone="danger", palette=DARK_PALETTE)
    assert "rt-danger-block" in rendered
    assert 'style=' not in rendered
    assert DARK_PALETTE.danger in rendered


def test_all_widget_stylesheet_calls_are_centralized() -> None:
    inventory = build_inventory()
    assert inventory["totals"]["set_stylesheet_calls"] == 1
    assert inventory["python_files"]["ui/theme_manager.py"]["set_stylesheet_calls"] == 1


def test_chart_palette_contains_shared_semantic_roles() -> None:
    colors = chart_palette(LIGHT_PALETTE)
    assert colors["buy"] == LIGHT_PALETTE.buy
    assert colors["sell"] == LIGHT_PALETTE.sell
    assert colors["equity"] == LIGHT_PALETTE.chart_equity
    assert colors["drawdown"] == LIGHT_PALETTE.chart_drawdown
    assert colors["surfaceRaised"] == LIGHT_PALETTE.surface_raised


def test_phase6_consumers_use_shared_renderer_and_palette() -> None:
    for relative in (
        "ui/screens/backtest_screen.py",
        "ui/screens/dashboard_screen.py",
        "ui/screens/journal_detail_screen.py",
        "ui/screens/scanner_detail_screen.py",
        "ui/components/chart_view.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "set_rich_html" in source or "empty_state_html" in source
    chart_source = (ROOT / "assets/chart/index.html").read_text(encoding="utf-8")
    assert "payload.palette" in chart_source
    assert "--chart-accent" in chart_source
