"""Phase 14.3 — test helper functions in core/decision_engine.py."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.decision_engine import (
    READY_TO_TRADE,
    WAITING_CONFIRMATION,
    WATCH_ONLY,
    TRADE_BLOCKED,
    STAND_ASIDE,
    clamp_score,
    normalize_decision_cap,
    normalize_entry_status,
    gate_allows_trade,
    merge_unique_codes,
)


# ---------------------------------------------------------------------------
# clamp_score
# ---------------------------------------------------------------------------


def test_clamp_score_valid():
    assert clamp_score("82") == 82
    assert clamp_score(50) == 50
    assert clamp_score(0) == 0
    assert clamp_score(100) == 100


def test_clamp_score_bad_returns_default():
    assert clamp_score("abc", default=50) == 50
    assert clamp_score("", default=50) == 50
    assert clamp_score(None, default=50) == 50
    assert clamp_score(float("nan"), default=50) == 50


def test_clamp_score_out_of_bounds():
    assert clamp_score(150) == 100
    assert clamp_score(-10) == 0


def test_clamp_score_default_clamped():
    assert clamp_score(None, default=150) == 100


# ---------------------------------------------------------------------------
# normalize_decision_cap
# ---------------------------------------------------------------------------


def test_normalize_cap_exact():
    assert normalize_decision_cap("TRADE_BLOCKED") == TRADE_BLOCKED
    assert normalize_decision_cap("WATCH_ONLY") == WATCH_ONLY
    assert normalize_decision_cap("WAITING_CONFIRMATION") == WAITING_CONFIRMATION
    assert normalize_decision_cap("READY_TO_TRADE") == READY_TO_TRADE
    assert normalize_decision_cap(STAND_ASIDE) == STAND_ASIDE


def test_normalize_cap_aliases():
    assert normalize_decision_cap("blocked") == TRADE_BLOCKED
    assert normalize_decision_cap("watch") == WATCH_ONLY
    assert normalize_decision_cap("wait") == WAITING_CONFIRMATION
    assert normalize_decision_cap("ready") == READY_TO_TRADE
    assert normalize_decision_cap("stand_aside") == STAND_ASIDE


def test_normalize_cap_case_insensitive():
    assert normalize_decision_cap("trade_blocked") == TRADE_BLOCKED
    assert normalize_decision_cap("watch_only") == WATCH_ONLY


def test_normalize_cap_unknown():
    assert normalize_decision_cap("bad") is None
    assert normalize_decision_cap("junk") is None


def test_normalize_cap_none_empty():
    assert normalize_decision_cap(None) is None
    assert normalize_decision_cap("") is None
    assert normalize_decision_cap("none") is None


# ---------------------------------------------------------------------------
# normalize_entry_status
# ---------------------------------------------------------------------------


def test_normalize_entry_status_valid():
    assert normalize_entry_status("confirmed_entry") == "confirmed_entry"
    assert normalize_entry_status("waiting_confirmation") == "waiting_confirmation"
    assert normalize_entry_status("watch_zone") == "watch_zone"
    assert normalize_entry_status("invalidated") == "invalidated"
    assert normalize_entry_status("no_setup") == "no_setup"


def test_normalize_entry_status_unknown():
    assert normalize_entry_status(None) == "unknown"
    assert normalize_entry_status("") == "unknown"
    assert normalize_entry_status("bogus") == "unknown"


# ---------------------------------------------------------------------------
# gate_allows_trade
# ---------------------------------------------------------------------------


def test_gate_allows_true():
    assert gate_allows_trade({"allowed": True}) is True


def test_gate_allows_false():
    assert gate_allows_trade({"allowed": False}) is False


def test_gate_permission_blocked():
    assert gate_allows_trade(None, {"status": "blocked"}) is False


def test_gate_permission_allowed_but_no_gate():
    # No gate_result → defaults to False for safety
    assert gate_allows_trade(None, {"status": "allowed"}) is False


def test_gate_no_data():
    assert gate_allows_trade(None) is False


# ---------------------------------------------------------------------------
# merge_unique_codes
# ---------------------------------------------------------------------------


def test_merge_unique_basic():
    assert merge_unique_codes(["A", "B"], ["B", "C"]) == ["A", "B", "C"]


def test_merge_unique_none():
    assert merge_unique_codes(None, ["A"]) == ["A"]


def test_merge_unique_empty():
    assert merge_unique_codes([], []) == []


def test_merge_unique_skips_empty_strings():
    assert merge_unique_codes(["A", "", "B"]) == ["A", "B"]


def test_merge_unique_preserves_order():
    assert merge_unique_codes(["C", "A"], ["B", "A"]) == ["C", "A", "B"]


def test_merge_unique_all_none():
    assert merge_unique_codes(None, None) == []
