from __future__ import annotations

import json

from tools.ui_density_audit import (
    DEFAULT_BASELINE,
    DEFAULT_LOCK,
    audit_python_heights,
    audit_qss_heights,
    compare_with_baseline,
)


def _baseline() -> dict[str, object]:
    return json.loads(DEFAULT_BASELINE.read_text(encoding="utf-8"))


def _lock() -> dict[str, object]:
    return json.loads(DEFAULT_LOCK.read_text(encoding="utf-8"))


def test_density_phase0_baseline_is_reviewable() -> None:
    payload = _baseline()
    assert payload["schema_version"] == 1
    assert payload["target_contract"] == {
        "standard_actual_height_px": 24,
        "compact_actual_height_px": 20,
        "multiline_height": "content-driven",
        "style_owner": "ui/styles/base.qss",
        "theme_overlays": ["ui/styles/dark.qss", "ui/styles/light.qss"],
    }
    assert payload["python_height_calls"]
    assert payload["qss_height_rules"]
    assert set(payload["reviewed_groups"]) == {
        "standard_24px",
        "compact_20px",
        "content_or_layout_driven",
    }
    assert set(payload["runtime_measurements"]) == {"dark", "light"}


def test_density_debt_does_not_exceed_reviewed_lock() -> None:
    baseline = _lock()
    current = {
        "python_height_calls": audit_python_heights(),
        "qss_height_rules": audit_qss_heights(),
    }
    errors = compare_with_baseline(current, baseline)
    assert errors == [], "\n".join(errors)


def test_phase0_records_the_existing_height_conflicts() -> None:
    payload = _baseline()
    dark = payload["runtime_measurements"]["dark"]
    light = payload["runtime_measurements"]["light"]
    assert dark["content_tab"]["actual"] == light["content_tab"]["actual"]
    assert dark["filter_line_edit"]["actual"] == light["filter_line_edit"]["actual"]
    assert dark["primary_button"]["actual"] == light["primary_button"]["actual"]
    assert dark["help_button"]["actual"] != light["help_button"]["actual"]
    assert dark["sidebar_toggle"]["actual"] == 33
    assert light["sidebar_toggle"]["actual"] == 33
    assert len(
        {
            dark["content_tab"]["actual"],
            dark["filter_line_edit"]["actual"],
            dark["primary_button"]["actual"],
            dark["configured_button"]["actual"],
        }
    ) > 1
