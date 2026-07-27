from __future__ import annotations

import json
from pathlib import Path

from tools.ui_style_audit import (
    DEFAULT_BASELINE,
    ROOT,
    build_inventory,
    compare_with_baseline,
    load_inventory,
)


ALLOWLIST = ROOT / "docs" / "ui-style-allowlist.json"
SCREENSHOT_MANIFEST = (
    ROOT
    / "docs"
    / "ui-baseline"
    / "current"
    / "screenshot-manifest.json"
)


def test_ui_style_debt_does_not_exceed_phase0_baseline() -> None:
    baseline = load_inventory(DEFAULT_BASELINE)
    errors = compare_with_baseline(build_inventory(), baseline)
    assert errors == [], "\n".join(errors)


def test_ui_style_allowlist_is_reviewable() -> None:
    payload = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    exceptions = payload["exceptions"]
    assert payload["status"].startswith("phase-")
    assert payload["status"].endswith("-reviewed")
    assert exceptions
    for item in exceptions:
        assert item["path"].startswith("ui/")
        assert item["category"]
        assert item["disposition"] in {
            "permanent",
            "temporary",
            "mixed",
            "centralized",
        }
        assert len(item["reason"].strip()) >= 20


def test_ui_baseline_screenshots_match_manifest() -> None:
    payload = json.loads(SCREENSHOT_MANIFEST.read_text(encoding="utf-8"))
    captures = payload["captures"]
    assert payload["schema_version"] == 1
    assert {"dark", "light"} <= set(payload["themes"])
    assert len(captures) >= 30
    for capture in captures:
        path = ROOT / capture["path"]
        assert path.is_file(), capture["path"]
        assert path.stat().st_size > 0
        assert capture["width"] > 0
        assert capture["height"] > 0
