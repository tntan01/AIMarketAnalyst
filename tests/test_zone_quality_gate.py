"""Tests for _gate_zone_quality in trade_gate_engine."""

import pytest


def _run_gate(zone_score):
    from core.trade_gate_engine import _gate_zone_quality, _resolve_cap, MIN_ZONE_SCORE_FOR_ENTRY

    context = {"zone_score": zone_score}
    result = {"warning_codes": [], "decision_cap": None, "reasons": []}
    _gate_zone_quality(context, result)
    return result


def test_low_zone_score_caps_to_watch_only():
    result = _run_gate(20)
    assert "ZONE_QUALITY_LOW" in result["warning_codes"]
    assert result["decision_cap"] == "WATCH_ONLY"
    assert any("dưới ngưỡng" in r for r in result["reasons"])


def test_good_zone_score_not_affected():
    result = _run_gate(70)
    assert "ZONE_QUALITY_LOW" not in result["warning_codes"]
    assert result["decision_cap"] is None


def test_missing_zone_score_not_blocked():
    result = _run_gate(None)
    assert "ZONE_QUALITY_LOW" not in result["warning_codes"]
    assert result["decision_cap"] is None


def test_boundary_at_threshold():
    from core.trade_gate_engine import MIN_ZONE_SCORE_FOR_ENTRY

    result_below = _run_gate(MIN_ZONE_SCORE_FOR_ENTRY - 1)
    assert "ZONE_QUALITY_LOW" in result_below["warning_codes"]

    result_at = _run_gate(MIN_ZONE_SCORE_FOR_ENTRY)
    assert "ZONE_QUALITY_LOW" not in result_at["warning_codes"]
