"""Phase 18.11 — verify prompt file status is correct."""
from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "docs" / "Upgrade" / "score_and_gate_upgrade"


def test_phases_0_to_17_are_finish():
    for phase in range(0, 18):
        expected = f"FINISH - phase_{phase}"
        files = list(PROMPTS_DIR.glob(f"FINISH - phase_{phase}*"))
        assert len(files) >= 1, f"Phase {phase} FINISH file missing"


def test_phase_18_is_unfinish():
    files = list(PROMPTS_DIR.glob("UNFINISH - phase_18*"))
    assert len(files) >= 1, "Phase 18 should still be UNFINISH"
    finish_files = list(PROMPTS_DIR.glob("FINISH - phase_18*"))
    assert len(finish_files) == 0, "Phase 18 should NOT be FINISH yet"


def test_phase_16_is_finish():
    files = list(PROMPTS_DIR.glob("FINISH - phase_16*"))
    assert len(files) == 1
    assert files[0].suffix == ".txt"
