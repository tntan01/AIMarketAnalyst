"""Phase 3 guardrails for migration away from static inline QSS."""

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


def test_no_literal_static_stylesheet_calls_remain() -> None:
    offenders: list[str] = []
    for path in sorted(UI.rglob("*.py")):
        for call in _stylesheet_calls(path):
            argument = call.args[0] if call.args else None
            if isinstance(argument, ast.Constant) and isinstance(
                argument.value, str
            ):
                offenders.append(f"{path.relative_to(ROOT)}:{call.lineno}")
    assert offenders == []


def test_phase3_components_have_no_local_stylesheets() -> None:
    migrated = (
        UI / "main_window.py",
        UI / "components" / "chart_view.py",
        UI / "components" / "info_card.py",
        UI / "screens" / "journal_detail_screen.py",
    )
    assert {path.name: len(_stylesheet_calls(path)) for path in migrated} == {
        "main_window.py": 0,
        "chart_view.py": 0,
        "info_card.py": 0,
        "journal_detail_screen.py": 0,
    }


def test_inline_stylesheet_debt_is_reduced_and_frozen() -> None:
    inventory = build_inventory()
    assert inventory["totals"]["set_stylesheet_calls"] <= 72


def test_phase3_shared_selectors_exist() -> None:
    base = (UI / "styles" / "base.qss").read_text(encoding="utf-8")
    required = {
        "QPushButton#RestartButton",
        "QWidget#AnalysisChartSurface",
        "QFrame#InfoCard",
        "QTextEdit#BacktestResultText",
        "QDialog#MarketBriefDialog",
        "QTextEdit#ScannerDetailText",
        "QFrame#HeroSummaryCard",
        "QPushButton#TagChip",
    }
    assert all(selector in base for selector in required)
