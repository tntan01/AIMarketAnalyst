"""Synthetic tests for the SD-C4 report helpers (no files, no MT5)."""

from __future__ import annotations

import pytest

from scripts.smc_demote_report import (
    fmt_num,
    fmt_pct,
    hashes_match,
    mechanical_conclusion,
    q4_width_estimate,
)


def test_mechanical_conclusion_combinations() -> None:
    assert mechanical_conclusion(False, False).startswith("Không đạt điều kiện (1)")
    assert mechanical_conclusion(False, True).startswith("Không đạt điều kiện (1)")
    assert mechanical_conclusion(True, False).startswith("Đạt (1), không đạt (2)")
    assert mechanical_conclusion(True, True) == "Đạt cả hai điều kiện → chọn A."


def test_q4_width_estimate() -> None:
    estimate = q4_width_estimate(0.0, -0.09, 0.09)
    assert estimate["half_width"] == pytest.approx(0.09)
    assert estimate["need"] == pytest.approx(0.05)
    assert estimate["factor"] == pytest.approx(3.24)
    assert "3.2 lần" in estimate["text"]

    below = q4_width_estimate(-0.06, -0.12, -0.01)
    assert below["factor"] is None
    assert below["text"] == "Ước lượng điểm đã dưới ngưỡng \u22120,05."


def test_formatting() -> None:
    assert fmt_num(None) == "\u2014"
    assert fmt_num(0.12345) == "0.123"
    assert fmt_pct(0.3333) == "33.3%"
    assert fmt_pct(None) == "\u2014"


def test_hashes_match() -> None:
    assert hashes_match({"inputs": {"rows_sha256": "x"}}, {"rows_sha256": "x"}) is True
    assert hashes_match({"inputs": {"rows_sha256": "x"}}, {"rows_sha256": "y"}) is False
