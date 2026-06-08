"""Phase 16.12 — test that the test manifest file exists with required content."""
from __future__ import annotations

from pathlib import Path

MANIFEST_PATH = Path(__file__).resolve().parent.parent / "docs" / "Upgrade" / "score_and_gate_upgrade" / "phase16_test_manifest.txt"


def test_manifest_exists():
    assert MANIFEST_PATH.is_file(), f"Manifest not found at {MANIFEST_PATH}"


def test_manifest_mentions_phase16():
    content = MANIFEST_PATH.read_text(encoding="utf-8")
    assert "Phase 16" in content


def test_manifest_has_phase16_test_command():
    content = MANIFEST_PATH.read_text(encoding="utf-8")
    assert "python -m pytest tests/test_phase16_*.py -q" in content


def test_manifest_mentions_env_issues():
    content = MANIFEST_PATH.read_text(encoding="utf-8")
    assert "MT5" in content or "PyQt6" in content, "Manifest must mention known env issues"
