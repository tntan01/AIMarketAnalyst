from __future__ import annotations

import ast
from pathlib import Path

from tools.ui_density_audit import audit_python_heights


ROOT = Path(__file__).resolve().parents[1]
LAYOUT_SYSTEM = ROOT / "ui" / "layout_system.py"
ALLOWED_HEIGHT_CATEGORIES = {
    "container",
    "multiline",
    "structural",
    "chart",
    "table",
    "progress",
}
HEIGHT_METHODS = {
    "setFixedHeight",
    "setMinimumHeight",
    "setMaximumHeight",
    "setFixedSize",
    "setMinimumSize",
    "setMaximumSize",
}


def _function_calls(function_name: str) -> set[str]:
    tree = ast.parse(LAYOUT_SYSTEM.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return {
                child.func.attr
                for child in ast.walk(node)
                if isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
            }
    raise AssertionError(f"Missing helper {function_name}")


def test_no_python_height_override_remains_on_interactive_controls() -> None:
    entries = audit_python_heights()
    invalid = [
        entry
        for entry in entries
        if entry["category"] in {"interactive", "review"}
    ]
    assert invalid == []
    assert {entry["category"] for entry in entries} <= ALLOWED_HEIGHT_CATEGORIES


def test_layout_helpers_do_not_own_interactive_control_height() -> None:
    for function_name in (
        "configure_control",
        "configure_button",
        "configure_checkbox",
        "configure_help_button",
    ):
        assert _function_calls(function_name).isdisjoint(HEIGHT_METHODS)


def test_removed_interactive_height_tokens_do_not_return() -> None:
    source = LAYOUT_SYSTEM.read_text(encoding="utf-8")
    assert "CONTROL_HEIGHT" not in source
    assert "HELP_SIZE" not in source
