"""Inventory and guard the UI styling debt during style standardization.

This module is deliberately independent from Qt so it can run in CI without
creating a QApplication.  Phase 0 records the current debt as a ceiling:
later phases may reduce the counts, but must not introduce new inline styling
without explicitly updating the reviewed baseline.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "ui"
DEFAULT_BASELINE = ROOT / "docs" / "ui-style-baseline.json"
QSS_FILES = ("styles/base.qss", "styles/dark.qss", "styles/light.qss")
REVIEWED_FOUNDATION_QSS = {"ui/styles/base.qss"}
CENTRAL_STYLE_ALLOWANCE = {
    "ui/theme.py": {
        "hex_color_literals",
    },
    "ui/theme_manager.py": {
        "set_stylesheet_calls",
    },
}

HTML_STYLE_RE = re.compile(r"<[^>]+\bstyle\s*=", re.IGNORECASE)
HEX_COLOR_RE = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
CSS_BLOCK_RE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.DOTALL)


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _set_stylesheet_count(tree: ast.AST) -> int:
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "setStyleSheet"
    )


def _object_name_count(tree: ast.AST) -> int:
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "setObjectName"
    )


def audit_python_file(path: Path) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    return {
        "set_stylesheet_calls": _set_stylesheet_count(tree),
        "html_style_attributes": len(HTML_STYLE_RE.findall(source)),
        "hex_color_literals": len(HEX_COLOR_RE.findall(source)),
        "object_name_calls": _object_name_count(tree),
        "line_count": len(source.splitlines()),
        "sha256": _sha256(path),
    }


def _qss_selector_inventory(source: str) -> tuple[int, int, int]:
    source = CSS_COMMENT_RE.sub("", source)
    selectors: list[str] = []
    for match in CSS_BLOCK_RE.finditer(source):
        selectors.extend(
            " ".join(selector.split())
            for selector in match.group(1).split(",")
            if selector.strip()
        )
    counts = Counter(selectors)
    duplicate_selectors = sum(1 for count in counts.values() if count > 1)
    return len(selectors), len(counts), duplicate_selectors


def audit_qss_file(path: Path) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    selector_refs, unique_selectors, duplicate_selectors = (
        _qss_selector_inventory(source)
    )
    return {
        "line_count": len(source.splitlines()),
        "rule_blocks": source.count("{"),
        "selector_references": selector_refs,
        "unique_selectors": unique_selectors,
        "duplicate_selectors": duplicate_selectors,
        "hex_color_literals": len(HEX_COLOR_RE.findall(source)),
        "sha256": _sha256(path),
    }


def build_inventory() -> dict[str, Any]:
    python_files: dict[str, dict[str, Any]] = {}
    totals: defaultdict[str, int] = defaultdict(int)
    for path in sorted(UI_ROOT.rglob("*.py")):
        metrics = audit_python_file(path)
        python_files[_relative(path)] = metrics
        for key in (
            "set_stylesheet_calls",
            "html_style_attributes",
            "hex_color_literals",
            "object_name_calls",
        ):
            totals[key] += int(metrics[key])

    qss_files = {
        _relative(UI_ROOT / filename): audit_qss_file(UI_ROOT / filename)
        for filename in QSS_FILES
    }
    return {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "scope": "ui/**/*.py plus ui/styles/**/*.qss and theme overlays",
        "policy": {
            "comparison": "current counts must be less than or equal to baseline",
            "new_debt_files": "forbidden",
            "source_hashes": "informational visual-baseline traceability only",
        },
        "totals": dict(totals),
        "python_files": python_files,
        "qss_files": qss_files,
    }


def _debt(metrics: dict[str, Any]) -> tuple[int, int, int]:
    return (
        int(metrics["set_stylesheet_calls"]),
        int(metrics["html_style_attributes"]),
        int(metrics["hex_color_literals"]),
    )


def compare_with_baseline(
    current: dict[str, Any],
    baseline: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    baseline_files = baseline.get("python_files", {})
    current_files = current.get("python_files", {})
    debt_keys = (
        "set_stylesheet_calls",
        "html_style_attributes",
        "hex_color_literals",
    )

    for path, metrics in current_files.items():
        current_debt = _debt(metrics)
        if path not in baseline_files:
            unreviewed = [
                key
                for key in debt_keys
                if int(metrics[key]) > 0
                and key not in CENTRAL_STYLE_ALLOWANCE.get(path, set())
            ]
            if unreviewed:
                errors.append(
                    f"{path}: new UI file introduces unreviewed style debt "
                    f"{', '.join(unreviewed)}"
                )
            continue
        allowed = baseline_files[path]
        for key in debt_keys:
            if key in CENTRAL_STYLE_ALLOWANCE.get(path, set()):
                continue
            if int(metrics[key]) > int(allowed[key]):
                errors.append(
                    f"{path}: {key} increased from {allowed[key]} "
                    f"to {metrics[key]}"
                )

    for path, metrics in current.get("qss_files", {}).items():
        allowed = baseline.get("qss_files", {}).get(path)
        if allowed is None:
            if path in REVIEWED_FOUNDATION_QSS:
                if int(metrics["duplicate_selectors"]) > 0:
                    errors.append(
                        f"{path}: shared foundation contains duplicate selectors"
                    )
                if int(metrics["hex_color_literals"]) > 0:
                    errors.append(
                        f"{path}: shared foundation must not contain theme colors"
                    )
                continue
            errors.append(f"{path}: new shared stylesheet is not reviewed")
            continue
        if int(metrics["duplicate_selectors"]) > int(
            allowed["duplicate_selectors"]
        ):
            errors.append(
                f"{path}: duplicate selectors increased from "
                f"{allowed['duplicate_selectors']} to "
                f"{metrics['duplicate_selectors']}"
            )
    return errors


def load_inventory(path: Path = DEFAULT_BASELINE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_inventory(
    inventory: dict[str, Any],
    path: Path = DEFAULT_BASELINE,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write-baseline",
        type=Path,
        help="Write the reviewed Phase-0 baseline JSON.",
    )
    parser.add_argument(
        "--check",
        type=Path,
        help="Fail when current styling debt exceeds a baseline JSON.",
    )
    args = parser.parse_args()

    current = build_inventory()
    if args.write_baseline:
        write_inventory(current, args.write_baseline)
        print(f"Wrote UI style baseline: {args.write_baseline}")
    if args.check:
        errors = compare_with_baseline(current, load_inventory(args.check))
        if errors:
            print("\n".join(errors))
            return 1
        print(f"UI style debt is within baseline: {args.check}")
    if not args.write_baseline and not args.check:
        print(json.dumps(current, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
