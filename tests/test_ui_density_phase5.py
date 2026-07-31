from __future__ import annotations

from pathlib import Path

from tools.ui_density_audit import (
    COMPACT_CONTROL_NAMES,
    STANDARD_CONTROL_NAMES,
    measure_representative_controls,
    validate_runtime_contract,
)


ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "ui"


def test_runtime_density_contract_has_no_height_parity_or_clipping_errors() -> None:
    measurements = measure_representative_controls()
    assert validate_runtime_contract(measurements) == []


def test_runtime_contract_covers_every_declared_representative_control() -> None:
    measurements = measure_representative_controls()
    expected = STANDARD_CONTROL_NAMES | COMPACT_CONTROL_NAMES
    assert expected <= set(measurements["dark"])
    assert expected <= set(measurements["light"])


def test_local_stylesheet_calls_are_restricted_to_the_central_theme_loader() -> None:
    occurrences: list[str] = []
    for path in sorted(UI_ROOT.rglob("*.py")):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if ".setStyleSheet(" in line:
                occurrences.append(
                    f"{path.relative_to(ROOT).as_posix()}:{line_number}"
                )
    assert len(occurrences) == 1
    assert occurrences[0].startswith("ui/theme_manager.py:")
