"""Phase 2 contracts for the shared QSS foundation and theme overlays."""

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "ui" / "styles" / "base.qss"
DARK = ROOT / "ui" / "styles" / "dark.qss"
LIGHT = ROOT / "ui" / "styles" / "light.qss"

COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
BLOCK_RE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.DOTALL)
HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def _rules(path: Path) -> dict[str, dict[str, str]]:
    source = COMMENT_RE.sub("", path.read_text(encoding="utf-8"))
    rules: dict[str, dict[str, str]] = {}
    for selector_group, body in BLOCK_RE.findall(source):
        properties: dict[str, str] = {}
        for declaration in body.split(";"):
            if ":" not in declaration:
                continue
            name, value = declaration.split(":", 1)
            properties[name.strip()] = value.strip()
        for selector in selector_group.split(","):
            normalized = " ".join(selector.split())
            if normalized:
                rules.setdefault(normalized, {}).update(properties)
    return rules


def test_base_stylesheet_is_theme_neutral() -> None:
    source = COMMENT_RE.sub("", BASE.read_text(encoding="utf-8"))
    assert not HEX_RE.findall(source)


def test_base_defines_shared_component_contracts() -> None:
    rules = _rules(BASE)
    required = {
        "QLabel",
        "QPushButton",
        "QLineEdit",
        "QTextEdit",
        "QComboBox",
        "QCheckBox",
        "QRadioButton",
        "QTabWidget::pane",
        "QTabBar::tab",
        "QTableWidget#EconTable::item",
        "QFrame#InfoCard",
        "QLabel#InfoCardLabel",
        "QLabel#InfoCardValue",
        "QLabel#InfoCardDetail",
        "QTextEdit#BacktestResultText",
        "QLabel#BacktestVerdict",
        "QLabel#MarketBadge",
        "QDialog#BacktestAnalysisDialog QTextEdit#BacktestAnalysisText",
    }
    assert required <= set(rules)


def test_theme_overlays_have_matching_component_contracts() -> None:
    required = {
        "QFrame#InfoCard",
        "QFrame#InfoCard:hover",
        "QLabel#InfoCardLabel",
        "QLabel#InfoCardValue",
        "QLabel#InfoCardDetail",
        "QTextEdit#BacktestResultText",
        "QLabel#MarketBadge",
        "QDialog#BacktestAnalysisDialog",
        "QDialog#BacktestAnalysisDialog QTextEdit#BacktestAnalysisText",
        "QDialog#BacktestConfigDialog",
    }
    dark_rules = _rules(DARK)
    light_rules = _rules(LIGHT)
    assert required <= set(dark_rules)
    assert required <= set(light_rules)
    assert set(dark_rules) == set(light_rules)


def test_structural_declarations_are_removed_from_color_overlays() -> None:
    structural = {
        "QLabel": {"font-size", "font-family"},
        "QPushButton": {
            "border-radius",
            "padding",
            "font-size",
            "font-family",
        },
        "QPushButton#NavButton": {
            "text-align",
            "padding",
            "border-radius",
            "font-weight",
        },
        "QLineEdit": {"border-radius", "padding", "font-size"},
        "QTextEdit": {
            "border-radius",
            "padding",
            "font-size",
            "font-family",
        },
        "QComboBox": {"border-radius", "padding", "font-size"},
        "QCheckBox": {"spacing", "font-size", "font-family"},
        "QRadioButton": {"font-size", "font-family"},
        "QTabWidget::pane": {"border-radius", "margin-top", "padding"},
        "QTabBar::tab": {
            "border-radius",
            "font-size",
            "font-weight",
            "min-width",
            "padding",
            "margin-right",
        },
        "QTableWidget#EconTable::item": {
            "font-size",
            "padding",
            "border",
        },
    }
    for path in (DARK, LIGHT):
        rules = _rules(path)
        for selector, properties in structural.items():
            assert properties.isdisjoint(rules.get(selector, {})), (
                path.name,
                selector,
                properties & set(rules.get(selector, {})),
            )
