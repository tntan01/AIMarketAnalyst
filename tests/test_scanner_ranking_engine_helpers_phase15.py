"""Phase 15.3 — test helper functions in scanner_ranking_engine."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scanner_ranking_engine import (
    clamp_score,
    safe_float,
    parse_risk_reward,
    normalize_price_vs_zone,
    normalize_entry_status,
    normalize_decision,
    merge_unique_codes,
)


# ---------------------------------------------------------------------------
# clamp_score
# ---------------------------------------------------------------------------


def test_clamp_score_valid():
    assert clamp_score("85") == 85
    assert clamp_score(50) == 50
    assert clamp_score(0) == 0
    assert clamp_score(100) == 100


def test_clamp_score_bad():
    assert clamp_score("abc", default=50) == 50
    assert clamp_score(None, default=50) == 50
    assert clamp_score("", default=50) == 50
    assert clamp_score(float("nan"), default=50) == 50


def test_clamp_score_bounds():
    assert clamp_score(150) == 100
    assert clamp_score(-10) == 0


# ---------------------------------------------------------------------------
# safe_float
# ---------------------------------------------------------------------------


def test_safe_float_valid():
    assert safe_float("1.25") == 1.25
    assert safe_float(3.14) == 3.14
    assert safe_float("0") == 0.0


def test_safe_float_bad():
    assert safe_float("abc", default=5.0) == 5.0
    assert safe_float(None, default=5.0) == 5.0
    assert safe_float("", default=5.0) == 5.0


# ---------------------------------------------------------------------------
# parse_risk_reward
# ---------------------------------------------------------------------------


def test_parse_rr_colon():
    assert parse_risk_reward("1:1.8") == 1.8
    assert parse_risk_reward("1:2") == 2.0


def test_parse_rr_raw_float():
    assert parse_risk_reward("2.5") == 2.5


def test_parse_rr_none():
    assert parse_risk_reward(None) == 0.0


def test_parse_rr_bad():
    assert parse_risk_reward("abc") == 0.0


# ---------------------------------------------------------------------------
# normalize_price_vs_zone
# ---------------------------------------------------------------------------


def test_price_vs_zone_exact():
    assert normalize_price_vs_zone("in_zone") == "in_zone"
    assert normalize_price_vs_zone("near_zone") == "near_zone"
    assert normalize_price_vs_zone("far") == "far"


def test_price_vs_zone_aliases():
    assert normalize_price_vs_zone("inside") == "in_zone"
    assert normalize_price_vs_zone("near") == "near_zone"
    assert normalize_price_vs_zone("far_zone") == "far"


def test_price_vs_zone_unknown():
    assert normalize_price_vs_zone(None) == "unknown"
    assert normalize_price_vs_zone("bogus") == "unknown"


def test_price_vs_zone_boolean_true_maps_to_in_zone():
    assert normalize_price_vs_zone(True) == "in_zone"


def test_price_vs_zone_boolean_false_maps_to_far():
    assert normalize_price_vs_zone(False) == "far"


# ---------------------------------------------------------------------------
# normalize_entry_status
# ---------------------------------------------------------------------------


def test_entry_status_valid():
    assert normalize_entry_status("confirmed_entry") == "confirmed_entry"
    assert normalize_entry_status("waiting_confirmation") == "waiting_confirmation"


def test_entry_status_unknown():
    assert normalize_entry_status(None) == "unknown"
    assert normalize_entry_status("bogus") == "unknown"


# ---------------------------------------------------------------------------
# normalize_decision
# ---------------------------------------------------------------------------


def test_normalize_decision_legacy():
    assert normalize_decision("ready") == "READY_TO_TRADE"
    assert normalize_decision("watch") == "WATCH_ONLY"
    assert normalize_decision("wait") == "WAITING_CONFIRMATION"
    assert normalize_decision("blocked") == "TRADE_BLOCKED"
    assert normalize_decision("stand_aside") == "STAND_ASIDE"


def test_normalize_decision_engine_constants():
    assert normalize_decision("WATCH_ONLY") == "WATCH_ONLY"
    assert normalize_decision("READY_TO_TRADE") == "READY_TO_TRADE"


def test_normalize_decision_unknown():
    assert normalize_decision("bogus") == ""
    assert normalize_decision(None) == ""


# ---------------------------------------------------------------------------
# merge_unique_codes
# ---------------------------------------------------------------------------


def test_merge_unique():
    assert merge_unique_codes(["A", "B"], ["B", "C"]) == ["A", "B", "C"]


def test_merge_none():
    assert merge_unique_codes(None, ["A"]) == ["A"]


def test_merge_empty():
    assert merge_unique_codes([], []) == []
