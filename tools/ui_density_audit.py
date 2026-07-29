"""Inventory UI control-height ownership before density standardization.

The audit is intentionally read-only.  It records Python-side geometry calls,
QSS height declarations and representative Qt runtime measurements for both
themes.  Later density phases can remove reviewed debt while the Phase-0
baseline prevents new per-widget height rules from appearing unnoticed.
"""

from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Any


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "ui"
DEFAULT_BASELINE = ROOT / "docs" / "ui" / "density" / "ui-density-baseline.json"
DEFAULT_LOCK = ROOT / "docs" / "ui" / "density" / "ui-density-lock.json"

STANDARD_CONTROL_NAMES = {
    "content_tab",
    "generic_line_edit",
    "generic_combo_box",
    "generic_spin_box",
    "generic_double_spin_box",
    "generic_date_edit",
    "generic_date_time_edit",
    "generic_time_edit",
    "filter_line_edit",
    "filter_combo_box",
    "filter_spin_box",
    "filter_double_spin_box",
    "filter_date_edit",
    "filter_date_time_edit",
    "filter_time_edit",
    "generic_button",
    "generic_checkbox",
    "generic_radio_button",
    "scanner_symbol_check",
    "scanner_help_radio",
    "primary_button",
    "secondary_button",
    "nav_button",
    "dialog_ai_button",
    "restart_button",
    "scanner_detail_button",
    "inline_help_button",
    "market_help_button",
    "auto_trade_toggle",
    "pill_tab",
    "configured_button",
    "configured_control",
}

COMPACT_CONTROL_NAMES = {
    "help_button",
    "sidebar_toggle",
    "news_link_button",
    "news_icon_button",
    "tag_chip",
    "result_tab_arrow",
    "table_line_edit",
    "table_spin_box",
    "table_combo_box",
    "lifecycle_line_edit",
    "lifecycle_spin_box",
    "lifecycle_date_time_edit",
    "lifecycle_combo_box",
    "content_tab_scroller",
}

HEIGHT_METHODS = {
    "setFixedHeight",
    "setMinimumHeight",
    "setMaximumHeight",
    "setFixedSize",
    "setMinimumSize",
    "setMaximumSize",
}
QSS_FILES = (
    UI_ROOT / "styles" / "base.qss",
    UI_ROOT / "styles" / "dark.qss",
    UI_ROOT / "styles" / "light.qss",
)
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
CSS_BLOCK_RE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.DOTALL)
HEIGHT_DECL_RE = re.compile(
    r"(?m)^\s*((?:min-|max-)?height)\s*:\s*([^;]+);"
)


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _classify_python_height(
    path: Path,
    receiver: str,
    method: str,
) -> str:
    text = f"{path.as_posix()} {receiver} {method}".lower()
    if any(token in text for token in ("text", "txt", "note", "response")):
        return "multiline"
    if any(token in text for token in ("canvas", "chart", "webview")):
        return "chart"
    if "progress" in text:
        return "progress"
    if any(token in text for token in ("table", "header", " horizontal")):
        return "table"
    if any(
        token in text
        for token in (
            "button",
            "btn",
            "input",
            "combo",
            "spin",
            "date",
            "check",
            "symbol_summary",
            "screens/shared.py self",
            "layout_system.py widget",
        )
    ):
        return "interactive"
    if any(
        token in text
        for token in ("dialog", " dlg", "main_window.py", "screen.py self")
    ):
        return "container"
    if any(token in text for token in ("card", "frame", "label", "bar", "dot")):
        return "structural"
    return "review"


def audit_python_heights() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(UI_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in HEIGHT_METHODS:
                continue
            receiver = ast.unparse(node.func.value)
            arguments = [ast.unparse(argument) for argument in node.args]
            entries.append(
                {
                    "path": _relative(path),
                    "line": node.lineno,
                    "method": node.func.attr,
                    "receiver": receiver,
                    "arguments": arguments,
                    "category": _classify_python_height(
                        path,
                        receiver,
                        node.func.attr,
                    ),
                }
            )
    return sorted(
        entries,
        key=lambda item: (item["path"], item["line"], item["method"]),
    )


def _strip_css_comments_preserving_lines(source: str) -> str:
    return CSS_COMMENT_RE.sub(
        lambda match: "\n" * match.group(0).count("\n"),
        source,
    )


def _classify_qss_height(selector: str) -> str:
    lowered = selector.lower()
    if any(token in lowered for token in ("scrollbar", "::indicator", "::arrow")):
        return "subcontrol"
    if any(
        token in lowered
        for token in (
            "qlineedit",
            "qcombobox",
            "qdoublespinbox",
            "qspinbox",
            "qdateedit",
            "qtimeedit",
            "qpushbutton",
            "qtoolbutton",
            "qtabbar::tab",
            "qcheckbox",
            "qradiobutton",
        )
    ):
        return "interactive"
    if any(token in lowered for token in ("qtextedit", "chart")):
        return "multiline_or_chart"
    return "structural"


def audit_qss_heights() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in QSS_FILES:
        original = path.read_text(encoding="utf-8")
        source = _strip_css_comments_preserving_lines(original)
        for match in CSS_BLOCK_RE.finditer(source):
            declarations = [
                {"property": name, "value": value.strip()}
                for name, value in HEIGHT_DECL_RE.findall(match.group(2))
            ]
            if not declarations:
                continue
            selector = " ".join(match.group(1).split())
            entries.append(
                {
                    "path": _relative(path),
                    "line": source.count("\n", 0, match.start()) + 1,
                    "selector": selector,
                    "declarations": declarations,
                    "category": _classify_qss_height(selector),
                }
            )
    return entries


def measure_representative_controls() -> dict[str, dict[str, dict[str, int]]]:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from PyQt6.QtGui import QPalette
    from PyQt6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDateEdit,
        QDateTimeEdit,
        QDialog,
        QDoubleSpinBox,
        QHBoxLayout,
        QLineEdit,
        QPushButton,
        QRadioButton,
        QSizePolicy,
        QSpinBox,
        QTableWidget,
        QTabWidget,
        QTimeEdit,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )

    from ui.layout_system import configure_button, configure_control
    from ui.theme_manager import APP_THEME_PROPERTY, load_stylesheet

    app = QApplication.instance() or QApplication([])
    original_stylesheet = app.styleSheet()
    original_palette = QPalette(app.palette())
    original_theme = app.property(APP_THEME_PROPERTY)
    measurements: dict[str, dict[str, dict[str, int]]] = {}

    for theme in ("dark", "light"):
        app.setStyleSheet(load_stylesheet(theme, ui_dir=UI_ROOT))
        host = QWidget()
        layout = QVBoxLayout(host)
        widgets: dict[str, QWidget] = {}

        tabs = QTabWidget()
        tabs.setObjectName("ContentTabs")
        tabs.addTab(QWidget(), "Nhật ký Phân tích")
        tabs.addTab(QWidget(), "Thống kê Hiệu suất")
        layout.addWidget(tabs)

        control_types = (
            ("line_edit", QLineEdit),
            ("combo_box", QComboBox),
            ("spin_box", QSpinBox),
            ("double_spin_box", QDoubleSpinBox),
            ("date_edit", QDateEdit),
            ("date_time_edit", QDateTimeEdit),
            ("time_edit", QTimeEdit),
        )
        for name, control_type in control_types:
            widget = control_type()
            widget.setSizePolicy(
                QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Fixed,
            )
            widgets[f"generic_{name}"] = widget
            layout.addWidget(widget)

        for name, control_type in control_types:
            widget = control_type()
            widget.setObjectName("FilterField")
            widget.setSizePolicy(
                QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Fixed,
            )
            widgets[f"filter_{name}"] = widget
            layout.addWidget(widget)

        for name, object_name in (
            ("generic_button", ""),
            ("primary_button", "PrimaryButton"),
            ("secondary_button", "SecondaryButton"),
            ("help_button", "HelpButton"),
            ("sidebar_toggle", "SidebarToggleButton"),
            ("nav_button", "NavButton"),
            ("news_link_button", "NewsLinkButton"),
            ("news_icon_button", "NewsIconButton"),
            ("dialog_ai_button", "DialogAiButton"),
            ("restart_button", "RestartButton"),
            ("scanner_detail_button", "ScannerDetailFullButton"),
            ("tag_chip", "TagChip"),
            ("inline_help_button", "InlineHelpButton"),
            ("market_help_button", "MarketHelpBtn"),
            ("auto_trade_toggle", "AutoTradeToggle"),
            ("result_tab_arrow", "ResultTabArrow"),
        ):
            button = QPushButton(name)
            if object_name:
                button.setObjectName(object_name)
            widgets[name] = button
            layout.addWidget(button)

        generic_checkbox = QCheckBox("generic_checkbox")
        widgets["generic_checkbox"] = generic_checkbox
        layout.addWidget(generic_checkbox)

        scanner_symbol_check = QCheckBox("EUR/USD — đã kiểm thử")
        scanner_symbol_check.setObjectName("ScannerSymbolCheck")
        widgets["scanner_symbol_check"] = scanner_symbol_check
        layout.addWidget(scanner_symbol_check)

        generic_radio_button = QRadioButton("generic_radio_button")
        widgets["generic_radio_button"] = generic_radio_button
        layout.addWidget(generic_radio_button)

        scanner_help_dialog = QDialog()
        scanner_help_dialog.setObjectName("ScannerHelpDialog")
        scanner_help_layout = QVBoxLayout(scanner_help_dialog)
        scanner_help_radio = QRadioButton("Hiển thị thông tin kỹ thuật")
        scanner_help_layout.addWidget(scanner_help_radio)
        widgets["scanner_help_radio"] = scanner_help_radio
        layout.addWidget(scanner_help_dialog)

        pill_tab = QPushButton("pill_tab")
        pill_tab.setProperty("tabStyle", "PillTab")
        widgets["pill_tab"] = pill_tab
        layout.addWidget(pill_tab)

        configured_button = QPushButton("configured_button")
        configure_button(configured_button)
        widgets["configured_button"] = configured_button
        layout.addWidget(configured_button)

        configured_control = QLineEdit()
        configure_control(configured_control)
        widgets["configured_control"] = configured_control
        layout.addWidget(configured_control)

        symbol_table = QTableWidget(1, 3)
        symbol_table.setObjectName("EconTable")
        symbol_table.setProperty("tableRole", "mt5Symbols")
        symbol_table.setFixedHeight(56)
        table_line_edit = QLineEdit()
        table_line_edit.setObjectName("Mt5MinScoreInput")
        table_spin_box = QDoubleSpinBox()
        table_spin_box.setObjectName("Mt5MinRrInput")
        table_combo_box = QComboBox()
        for column, (name, widget) in enumerate(
            (
                ("table_line_edit", table_line_edit),
                ("table_spin_box", table_spin_box),
                ("table_combo_box", table_combo_box),
            )
        ):
            symbol_table.setCellWidget(0, column, widget)
            widgets[name] = widget
        layout.addWidget(symbol_table)

        lifecycle = QWidget()
        lifecycle.setObjectName("LifecycleScrollWidget")
        lifecycle_layout = QHBoxLayout(lifecycle)
        lifecycle_widgets = (
            ("lifecycle_line_edit", QLineEdit()),
            ("lifecycle_spin_box", QDoubleSpinBox()),
            ("lifecycle_date_time_edit", QDateTimeEdit()),
            ("lifecycle_combo_box", QComboBox()),
        )
        for name, widget in lifecycle_widgets:
            lifecycle_layout.addWidget(widget)
            widgets[name] = widget
        layout.addWidget(lifecycle)

        scroll_tabs = QTabWidget()
        scroll_tabs.setObjectName("ContentTabs")
        scroll_tabs.setUsesScrollButtons(True)
        scroll_tabs.setFixedWidth(320)
        for index in range(20):
            scroll_tabs.addTab(QWidget(), f"Tab dài {index}")
        layout.addWidget(scroll_tabs)

        layout.addStretch(1)
        host.resize(960, 1400)
        host.show()
        app.processEvents()

        theme_measurements: dict[str, dict[str, int]] = {
            "content_tab": {
                "actual": tabs.tabBar().tabRect(0).height(),
                "size_hint": tabs.tabBar().tabSizeHint(0).height(),
                "minimum": tabs.tabBar().minimumHeight(),
                "maximum": tabs.tabBar().maximumHeight(),
                "content_height": tabs.tabBar().fontMetrics().height(),
            }
        }
        for name, widget in widgets.items():
            content_height = widget.fontMetrics().height()
            icon_getter = getattr(widget, "icon", None)
            icon_size_getter = getattr(widget, "iconSize", None)
            if callable(icon_getter) and callable(icon_size_getter):
                icon = icon_getter()
                if not icon.isNull():
                    content_height = max(
                        content_height,
                        icon_size_getter().height(),
                    )
            theme_measurements[name] = {
                "actual": widget.height(),
                "size_hint": widget.sizeHint().height(),
                "minimum": widget.minimumHeight(),
                "maximum": widget.maximumHeight(),
                "content_height": content_height,
            }
        scrollers = scroll_tabs.tabBar().findChildren(QToolButton)
        if scrollers:
            scroller = scrollers[0]
            theme_measurements["content_tab_scroller"] = {
                "actual": scroller.height(),
                "size_hint": scroller.sizeHint().height(),
                "minimum": scroller.minimumHeight(),
                "maximum": scroller.maximumHeight(),
                "content_height": scroller.fontMetrics().height(),
            }
        measurements[theme] = theme_measurements
        host.close()
        host.deleteLater()
        app.processEvents()

    app.setStyleSheet(original_stylesheet)
    app.setPalette(original_palette)
    app.setProperty(APP_THEME_PROPERTY, original_theme)
    return measurements


def validate_runtime_contract(
    measurements: dict[str, dict[str, dict[str, int]]] | None = None,
) -> list[str]:
    """Validate exact density, theme parity and vertical content clearance."""
    measured = measurements or measure_representative_controls()
    errors: list[str] = []
    contracts = (
        (STANDARD_CONTROL_NAMES, 24, 4),
        (COMPACT_CONTROL_NAMES, 20, 2),
    )
    for theme in ("dark", "light"):
        themed = measured.get(theme, {})
        for names, expected_height, minimum_clearance in contracts:
            for name in sorted(names):
                value = themed.get(name)
                if value is None:
                    errors.append(f"{theme}/{name}: missing runtime measurement")
                    continue
                actual = value["actual"]
                if actual != expected_height:
                    errors.append(
                        f"{theme}/{name}: actual height {actual} != "
                        f"{expected_height}"
                    )
                clearance = actual - value["content_height"]
                if clearance < minimum_clearance:
                    errors.append(
                        f"{theme}/{name}: vertical content clearance "
                        f"{clearance} < {minimum_clearance}"
                    )

    dark = measured.get("dark", {})
    light = measured.get("light", {})
    for name in sorted(STANDARD_CONTROL_NAMES | COMPACT_CONTROL_NAMES):
        if name not in dark or name not in light:
            continue
        for field in ("actual", "content_height"):
            if dark[name][field] != light[name][field]:
                errors.append(
                    f"{name}: dark/light {field} mismatch "
                    f"{dark[name][field]} != {light[name][field]}"
                )
    return errors


def _category_counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        category = str(entry["category"])
        counts[category] = counts.get(category, 0) + 1
    return dict(sorted(counts.items()))


def build_inventory(*, include_runtime: bool = True) -> dict[str, Any]:
    python_entries = audit_python_heights()
    qss_entries = audit_qss_heights()
    result: dict[str, Any] = {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "target_contract": {
            "standard_actual_height_px": 24,
            "compact_actual_height_px": 20,
            "multiline_height": "content-driven",
            "style_owner": "ui/styles/base.qss",
            "theme_overlays": ["ui/styles/dark.qss", "ui/styles/light.qss"],
        },
        "reviewed_groups": {
            "standard_24px": [
                "QLineEdit",
                "QComboBox",
                "QSpinBox",
                "QDoubleSpinBox",
                "QDateEdit",
                "QDateTimeEdit",
                "QTimeEdit",
                "QCheckBox",
                "QRadioButton",
                "standard action QPushButton",
                "standard QTabBar::tab",
            ],
            "compact_20px": [
                "table-embedded editor",
                "HelpButton",
                "icon-only button",
                "compact chip or badge",
                "dense toolbar control",
            ],
            "content_or_layout_driven": [
                "QTextEdit and note fields",
                "chart and WebEngine canvas",
                "progress indicator",
                "table and header",
                "scrollbar subcontrol",
                "card, dialog and window container",
            ],
        },
        "python_height_calls": python_entries,
        "python_category_counts": _category_counts(python_entries),
        "qss_height_rules": qss_entries,
        "qss_category_counts": _category_counts(qss_entries),
    }
    if include_runtime:
        result["runtime_measurements"] = measure_representative_controls()
    return result


def _python_signature(entry: dict[str, Any]) -> tuple[Any, ...]:
    return (
        entry["path"],
        entry["method"],
        entry["receiver"],
        tuple(entry["arguments"]),
    )


def _qss_signature(entry: dict[str, Any]) -> tuple[Any, ...]:
    return (
        entry["path"],
        entry["selector"],
        tuple(
            (item["property"], item["value"])
            for item in entry["declarations"]
        ),
    )


def compare_with_baseline(
    current: dict[str, Any],
    baseline: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    baseline_python = {
        _python_signature(entry) for entry in baseline["python_height_calls"]
    }
    for entry in current["python_height_calls"]:
        if _python_signature(entry) not in baseline_python:
            errors.append(
                f"{entry['path']}:{entry['line']}: new unreviewed "
                f"{entry['method']}({', '.join(entry['arguments'])})"
            )

    baseline_qss = {
        _qss_signature(entry) for entry in baseline["qss_height_rules"]
    }
    for entry in current["qss_height_rules"]:
        if _qss_signature(entry) not in baseline_qss:
            errors.append(
                f"{entry['path']}:{entry['line']}: new or changed "
                f"height declaration for {entry['selector']}"
            )
    return errors


def write_inventory(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write",
        type=Path,
        help="Write the complete Phase-0 density inventory.",
    )
    parser.add_argument(
        "--check",
        type=Path,
        help="Reject new Python/QSS height declarations not in the baseline.",
    )
    parser.add_argument(
        "--no-runtime",
        action="store_true",
        help="Skip representative Qt runtime measurements.",
    )
    parser.add_argument(
        "--validate-contract",
        action="store_true",
        help="Validate 24/20 px, theme parity and vertical content clearance.",
    )
    args = parser.parse_args()

    payload = build_inventory(include_runtime=not args.no_runtime)
    if args.write:
        write_inventory(payload, args.write)
        print(f"Wrote UI density inventory: {args.write}")
    if args.check:
        baseline = json.loads(args.check.read_text(encoding="utf-8"))
        errors = compare_with_baseline(payload, baseline)
        if errors:
            print("\n".join(errors))
            return 1
        print(f"UI density debt is within baseline: {args.check}")
    if args.validate_contract:
        if args.no_runtime:
            print("--validate-contract cannot be used with --no-runtime")
            return 2
        errors = validate_runtime_contract(payload["runtime_measurements"])
        if errors:
            print("\n".join(errors))
            return 1
        print("UI density runtime contract is valid")
    if not args.write and not args.check and not args.validate_contract:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
