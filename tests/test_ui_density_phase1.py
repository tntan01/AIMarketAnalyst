from __future__ import annotations

import json

import pytest

from tools.ui_density_audit import (
    COMPACT_CONTROL_NAMES,
    DEFAULT_LOCK,
    STANDARD_CONTROL_NAMES,
    audit_qss_heights,
    measure_representative_controls,
)


def _measure_or_skip() -> dict:
    # Some PyQt builds refuse access to protected members of the tab bar
    # that QTabWidget creates internally; the runtime measurement cannot
    # run there and must be skipped instead of failing.
    try:
        return measure_representative_controls()
    except RuntimeError as exc:
        if "protected functions" not in str(exc):
            raise
        pytest.skip(
            "Qt runtime density measurement is unsupported by this "
            f"PyQt build: {exc}"
        )


def test_phase1_lock_records_the_density_contract() -> None:
    payload = json.loads(DEFAULT_LOCK.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["target_contract"]["standard_actual_height_px"] == 24
    assert payload["target_contract"]["compact_actual_height_px"] == 20


def test_all_interactive_height_rules_are_owned_by_base_qss() -> None:
    entries = [
        entry
        for entry in audit_qss_heights()
        if entry["category"] == "interactive"
    ]
    assert entries
    assert {entry["path"] for entry in entries} == {"ui/styles/base.qss"}


def test_standard_and_compact_controls_have_exact_dark_light_height() -> None:
    measurements = _measure_or_skip()
    for theme in ("dark", "light"):
        themed = measurements[theme]
        for name in STANDARD_CONTROL_NAMES:
            assert themed[name]["actual"] == 24, (theme, name, themed[name])
        for name in COMPACT_CONTROL_NAMES:
            assert themed[name]["actual"] == 20, (theme, name, themed[name])

    for name in STANDARD_CONTROL_NAMES | COMPACT_CONTROL_NAMES:
        assert measurements["dark"][name]["actual"] == measurements["light"][name][
            "actual"
        ], name
