"""Phase 4 contracts for semantic component and runtime states."""

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


def test_journal_and_orders_runtime_states_use_properties() -> None:
    assert _stylesheet_calls(UI / "screens" / "journal_screen.py") == []
    assert _stylesheet_calls(UI / "screens" / "orders_screen.py") == []
    journal_source = (UI / "screens" / "journal_screen.py").read_text(
        encoding="utf-8"
    )
    orders_source = (UI / "screens" / "orders_screen.py").read_text(
        encoding="utf-8"
    )
    assert 'set_dynamic_property(self, "kpiState"' in journal_source
    assert 'set_dynamic_property(self, "state"' in journal_source
    assert '"metricTone"' in orders_source
    assert '"statusTone"' in orders_source


def test_phase4_semantic_selectors_are_shared_by_both_themes() -> None:
    required = (
        'QFrame#PerformanceKPICard[kpiState="positive"]',
        'QLabel#KPICardValue[kpiState="negative"]',
        'QFrame#MissingRBanner[state="warning"]',
        'QLabel#MiniStatValue[metricTone="positive"]',
        'QLabel#CardDetail[statusTone="warning"]',
    )
    dark = (UI / "styles.qss").read_text(encoding="utf-8")
    light = (UI / "styles_light.qss").read_text(encoding="utf-8")
    for selector in required:
        assert selector in dark
        assert selector in light


def test_phase4_inline_stylesheet_debt_is_frozen() -> None:
    inventory = build_inventory()
    assert inventory["totals"]["set_stylesheet_calls"] <= 57
