from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DARK_QSS = ROOT / "ui" / "styles" / "dark.qss"
LIGHT_QSS = ROOT / "ui" / "styles" / "light.qss"
COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
BLOCK_RE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.DOTALL)


def _rules(path: Path) -> dict[str, list[dict[str, str]]]:
    source = COMMENT_RE.sub("", path.read_text(encoding="utf-8"))
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    for match in BLOCK_RE.finditer(source):
        declarations: dict[str, str] = {}
        for declaration in match.group(2).split(";"):
            if ":" not in declaration:
                continue
            name, value = declaration.split(":", 1)
            declarations[name.strip()] = value.strip()
        for selector in match.group(1).split(","):
            normalized = " ".join(selector.split())
            if normalized:
                result[normalized].append(declarations)
    return dict(result)


def _value(
    rules: dict[str, list[dict[str, str]]],
    selector: str,
    property_name: str,
) -> str:
    for declarations in reversed(rules.get(selector, [])):
        if property_name in declarations:
            return declarations[property_name]
    raise AssertionError(f"Missing {property_name} for {selector}")


THEMES = (
    (
        DARK_QSS,
        {
            "normal": "1px solid #475569",
            "hover": "1px solid #64748b",
            "focus": "1px solid #38bdf8",
            "disabled": "1px solid #334155",
            "invalid": "1px solid #f43f5e",
            "invalid_focus": "1px solid #fb7185",
            "drop_normal": "#475569",
            "drop_hover": "#64748b",
            "drop_focus": "#38bdf8",
            "drop_disabled": "#334155",
            "drop_invalid": "#f43f5e",
        },
    ),
    (
        LIGHT_QSS,
        {
            "normal": "1px solid #B5B0A6",
            "hover": "1px solid #A19B90",
            "focus": "1px solid #0284C7",
            "disabled": "1px solid #CCC7BD",
            "invalid": "1px solid #DC2626",
            "invalid_focus": "1px solid #EF4444",
            "drop_normal": "#B5B0A6",
            "drop_hover": "#A19B90",
            "drop_focus": "#0284C7",
            "drop_disabled": "#CCC7BD",
            "drop_invalid": "#DC2626",
        },
    ),
)


def test_single_line_controls_have_complete_theme_border_states() -> None:
    field_types = (
        "QLineEdit",
        "QDoubleSpinBox",
        "QSpinBox",
        "QDateEdit",
        "QDateTimeEdit",
        "QTimeEdit",
        "QComboBox",
    )
    for path, colors in THEMES:
        rules = _rules(path)
        for field_type in field_types:
            assert _value(rules, field_type, "border") == colors["normal"]
            assert _value(rules, f"{field_type}:hover", "border") == colors["hover"]
            assert _value(rules, f"{field_type}:focus", "border") == colors["focus"]
            assert _value(rules, f"{field_type}:disabled", "border") == colors[
                "disabled"
            ]
            assert _value(
                rules,
                f'{field_type}[validationState="invalid"]',
                "border",
            ) == colors["invalid"]
            assert _value(
                rules,
                f'{field_type}[validationState="invalid"]:focus',
                "border",
            ) == colors["invalid_focus"]
            assert _value(
                rules,
                f'{field_type}[validationState="invalid"]:disabled',
                "border",
            ) == colors["disabled"]


def test_filter_fields_use_the_same_semantic_border_scale() -> None:
    field_types = (
        "QLineEdit",
        "QDoubleSpinBox",
        "QSpinBox",
        "QDateEdit",
        "QDateTimeEdit",
        "QTimeEdit",
        "QComboBox",
    )
    for path, colors in THEMES:
        rules = _rules(path)
        for field_type in field_types:
            selector = f"{field_type}#FilterField"
            assert _value(rules, selector, "border") == colors["normal"]
            assert _value(rules, f"{selector}:hover", "border") == colors["hover"]
            assert _value(rules, f"{selector}:focus", "border") == colors["focus"]
            assert _value(rules, f"{selector}:disabled", "border") == colors[
                "disabled"
            ]
            assert _value(
                rules,
                f'{selector}[validationState="invalid"]',
                "border",
            ) == colors["invalid"]
            assert _value(
                rules,
                f'{selector}[validationState="invalid"]:focus',
                "border",
            ) == colors["invalid_focus"]
            assert _value(
                rules,
                f'{selector}[validationState="invalid"]:disabled',
                "border",
            ) == colors["disabled"]


def test_drop_down_divider_tracks_control_state_in_both_themes() -> None:
    drop_types = ("QComboBox", "QDateEdit", "QDateTimeEdit", "QTimeEdit")
    for path, colors in THEMES:
        rules = _rules(path)
        for field_type in drop_types:
            assert _value(
                rules,
                f"{field_type}::drop-down",
                "border-left",
            ) == f"1px solid {colors['drop_normal']}"
            assert _value(
                rules,
                f"{field_type}::drop-down:hover",
                "border-left-color",
            ) == colors["drop_hover"]
            assert _value(
                rules,
                f"{field_type}:focus::drop-down",
                "border-left-color",
            ) == colors["drop_focus"]
            assert _value(
                rules,
                f"{field_type}:disabled::drop-down",
                "border-left-color",
            ) == colors["drop_disabled"]
            assert _value(
                rules,
                f'{field_type}[validationState="invalid"]::drop-down',
                "border-left-color",
            ) == colors["drop_invalid"]

            filter_selector = f"{field_type}#FilterField"
            assert _value(
                rules,
                f"{filter_selector}::drop-down",
                "border-left",
            ) == f"1px solid {colors['drop_normal']}"
            assert _value(
                rules,
                f"{filter_selector}:focus::drop-down",
                "border-left-color",
            ) == colors["drop_focus"]
            assert _value(
                rules,
                f"{filter_selector}:disabled::drop-down",
                "border-left-color",
            ) == colors["drop_disabled"]
            assert _value(
                rules,
                f'{filter_selector}[validationState="invalid"]::drop-down',
                "border-left-color",
            ) == colors["drop_invalid"]


def test_compact_table_editors_have_hover_focus_disabled_and_invalid_borders() -> None:
    suffixes = (
        "QLineEdit#Mt5MinScoreInput",
        "QDoubleSpinBox#Mt5MinRrInput",
        "QComboBox",
    )
    prefix = 'QTableWidget#DataTable[tableRole="mt5Symbols"] '
    for path, colors in THEMES:
        rules = _rules(path)
        for suffix in suffixes:
            selector = prefix + suffix
            assert _value(rules, selector, "border") == colors["normal"]
            assert _value(rules, f"{selector}:hover", "border") == colors["hover"]
            assert _value(rules, f"{selector}:focus", "border") == colors["focus"]
            assert _value(rules, f"{selector}:disabled", "border") == colors[
                "disabled"
            ]
            assert _value(
                rules,
                f'{selector}[validationState="invalid"]',
                "border",
            ) == colors["invalid"]
