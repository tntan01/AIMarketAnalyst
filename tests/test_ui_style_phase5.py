"""Phase 5 contracts for screen-cluster stylesheet migration."""

from __future__ import annotations

import ast
from pathlib import Path

from tools.ui_style_audit import build_inventory


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui"


def _stylesheet_calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "setStyleSheet"
    ]


def test_completed_screen_clusters_have_no_local_stylesheets() -> None:
    migrated = (
        UI / "main_window.py",
        UI / "components" / "chart_view.py",
        UI / "screens" / "dashboard_screen.py",
        UI / "screens" / "orders_screen.py",
        UI / "screens" / "journal_screen.py",
        UI / "screens" / "journal_detail_screen.py",
        UI / "screens" / "backtest_screen.py",
    )
    assert {
        path.relative_to(ROOT).as_posix(): len(_stylesheet_calls(path))
        for path in migrated
    } == {
        path.relative_to(ROOT).as_posix(): 0
        for path in migrated
    }


def test_scanner_residual_styles_have_migrated_to_phase6_contracts() -> None:
    assert len(_stylesheet_calls(UI / "screens" / "scanner_screen.py")) == 0
    assert len(_stylesheet_calls(UI / "screens" / "scanner_detail_screen.py")) == 0


def test_phase5_shared_component_selectors_exist_in_both_themes() -> None:
    required = (
        'QLabel#StatusIcon[state="warning"]',
        'QPushButton#DialogAiButton',
        'QLabel#BacktestVerdict[verdictState="success"]',
        'QLabel#OrderDirectionPill[direction="buy"]',
        'QLabel#ScannerDetailHero[candidateState="ready"]',
        'QLabel#ScannerPanelValue[metricTone="success"]',
        'QLabel#ScannerChecklistText[checkState="fail"]',
    )
    dark = (UI / "styles" / "dark.qss").read_text(encoding="utf-8")
    light = (UI / "styles" / "light.qss").read_text(encoding="utf-8")
    for selector in required:
        assert selector in dark
        assert selector in light


def test_scanner_detail_hero_uses_bold_typography() -> None:
    base = (UI / "styles" / "base.qss").read_text(encoding="utf-8")
    hero_rule = base.split("QLabel#ScannerDetailHero {", 1)[1].split("}", 1)[0]

    assert "font-weight: 700;" in hero_rule


def test_phase5_inline_stylesheet_debt_is_frozen() -> None:
    inventory = build_inventory()
    assert inventory["totals"]["set_stylesheet_calls"] <= 4
