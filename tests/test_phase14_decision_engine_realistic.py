"""Phase 14.10 — realistic scenarios for decision_engine."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.decision_engine import (
    READY_TO_TRADE,
    WAITING_CONFIRMATION,
    AGGRESSIVE_SETUP,
    WATCH_ONLY,
    TRADE_BLOCKED,
    STAND_ASIDE,
    VALID_DECISIONS,
    make_final_decision,
    DECISION_GATE_BLOCKED,
    DECISION_GATE_CAPPED,
    DECISION_ENTRY_NOT_CONFIRMED,
    DECISION_FINAL_SCORE_STRONG,
    DECISION_FINAL_SCORE_MODERATE,
    DECISION_FINAL_SCORE_WEAK,
    DECISION_SCORE_GAP_LOW,
    DECISION_AGGRESSIVE_SETUP,
)


def _no_duplicates(result: dict) -> None:
    """Assert no duplicate codes in any list."""
    for key in ("reason_codes", "warning_codes", "block_codes"):
        codes = result.get(key, [])
        assert len(codes) == len(set(codes)), f"Duplicates in {key}: {codes}"


def _valid_structure(result: dict) -> None:
    assert result["decision"] in VALID_DECISIONS
    assert isinstance(result["legacy_action"], str)
    assert isinstance(result["final_score"], int)
    assert isinstance(result["decision_label"], str)


# ---------------------------------------------------------------------------
# Case 1 — Clean setup → READY_TO_TRADE
# ---------------------------------------------------------------------------


def test_case1_ready():
    result = make_final_decision(
        final_score=86,
        gate_result={"allowed": True, "decision_cap": None},
        entry_status="confirmed_entry",
        score_gap=22,
    )
    assert result["decision"] == READY_TO_TRADE
    assert result["allowed"]
    assert DECISION_FINAL_SCORE_STRONG in result["reason_codes"]
    assert result["legacy_action"] == "ready"
    _no_duplicates(result)
    _valid_structure(result)


# ---------------------------------------------------------------------------
# Case 2 — Gate block overrides high score
# ---------------------------------------------------------------------------


def test_case2_gate_blocked():
    result = make_final_decision(
        final_score=92,
        gate_result={
            "allowed": False,
            "decision_cap": "TRADE_BLOCKED",
            "block_codes": ["HIGH_IMPACT_NEWS_NEARBY"],
        },
        entry_status="confirmed_entry",
        score_gap=25,
    )
    assert result["decision"] == TRADE_BLOCKED
    assert not result["allowed"]
    assert DECISION_GATE_BLOCKED in result["block_codes"]
    assert "HIGH_IMPACT_NEWS_NEARBY" in result["block_codes"]
    assert result["legacy_action"] == "stand_aside"
    _no_duplicates(result)
    _valid_structure(result)


# ---------------------------------------------------------------------------
# Case 3 — High score but M15 not confirmed
# ---------------------------------------------------------------------------


def test_case3_waiting_default():
    """Without aggressive opt-in, waiting_confirmation stays WAITING."""
    result = make_final_decision(
        final_score=88,
        gate_result={"allowed": True},
        entry_status="waiting_confirmation",
        score_gap=18,
    )
    assert result["decision"] == WAITING_CONFIRMATION
    assert DECISION_ENTRY_NOT_CONFIRMED in result["warning_codes"]
    _no_duplicates(result)


def test_case3_aggressive_opt_in():
    """With aggressive opt-in, waiting_confirmation + high score → AGGRESSIVE."""
    result = make_final_decision(
        final_score=88,
        gate_result={"allowed": True},
        entry_status="waiting_confirmation",
        score_gap=18,
        allow_aggressive_setup=True,
    )
    assert result["decision"] == AGGRESSIVE_SETUP
    assert DECISION_AGGRESSIVE_SETUP in result["reason_codes"]
    assert DECISION_ENTRY_NOT_CONFIRMED in result["warning_codes"]
    assert result["legacy_action"] == "wait_for_confirmation"
    _no_duplicates(result)


# ---------------------------------------------------------------------------
# Case 4 — Low score gap
# ---------------------------------------------------------------------------


def test_case4_score_gap_low():
    result = make_final_decision(
        final_score=90,
        gate_result={"allowed": True},
        entry_status="confirmed_entry",
        score_gap=4,
    )
    assert result["decision"] == WAITING_CONFIRMATION
    assert DECISION_SCORE_GAP_LOW in result["warning_codes"]
    _no_duplicates(result)


# ---------------------------------------------------------------------------
# Case 5 — Moderate final score
# ---------------------------------------------------------------------------


def test_case5_watch():
    result = make_final_decision(
        final_score=70,
        gate_result={"allowed": True},
        entry_status="confirmed_entry",
        score_gap=15,
    )
    assert result["decision"] == WATCH_ONLY
    assert DECISION_FINAL_SCORE_MODERATE in result["reason_codes"]
    assert result["legacy_action"] == "watch"
    _no_duplicates(result)
    _valid_structure(result)


# ---------------------------------------------------------------------------
# Case 6 — Weak final score
# ---------------------------------------------------------------------------


def test_case6_stand_aside():
    result = make_final_decision(
        final_score=42,
        gate_result={"allowed": True},
        entry_status="confirmed_entry",
        score_gap=15,
    )
    assert result["decision"] == STAND_ASIDE
    assert DECISION_FINAL_SCORE_WEAK in result["reason_codes"]
    assert result["legacy_action"] == "stand_aside"
    _no_duplicates(result)
    _valid_structure(result)


# ---------------------------------------------------------------------------
# Case 7 — Dirty data
# ---------------------------------------------------------------------------


def test_case7_dirty_data():
    result = make_final_decision(
        final_score="bad",
        gate_result=None,
        entry_status=None,
        score_gap="bad",
    )
    assert result["decision"] in VALID_DECISIONS
    assert result["final_score"] == 0  # "bad" → clamp to 0
    assert not result["allowed"]
    _no_duplicates(result)
    _valid_structure(result)


# ---------------------------------------------------------------------------
# Case 8 — WATCH_ONLY cap
# ---------------------------------------------------------------------------


def test_case8_watch_cap():
    result = make_final_decision(
        final_score=88,
        gate_result={"allowed": True, "decision_cap": "WATCH_ONLY"},
        entry_status="confirmed_entry",
        score_gap=20,
    )
    assert result["decision"] == WATCH_ONLY
    assert DECISION_GATE_CAPPED in result["warning_codes"]
    _no_duplicates(result)


# ---------------------------------------------------------------------------
# Case 9 — WAITING_CONFIRMATION cap
# ---------------------------------------------------------------------------


def test_case9_waiting_cap():
    result = make_final_decision(
        final_score=88,
        gate_result={"allowed": True, "decision_cap": "WAITING_CONFIRMATION"},
        entry_status="confirmed_entry",
        score_gap=20,
    )
    assert result["decision"] == WAITING_CONFIRMATION
    assert DECISION_GATE_CAPPED in result["warning_codes"]
    _no_duplicates(result)


# ---------------------------------------------------------------------------
# Case 10 — Trade permission blocked
# ---------------------------------------------------------------------------


def test_case10_tp_blocked():
    result = make_final_decision(
        final_score=88,
        gate_result={"allowed": True},
        trade_permission={"status": "blocked"},
        entry_status="confirmed_entry",
    )
    assert result["decision"] == TRADE_BLOCKED
    assert not result["allowed"]
    _no_duplicates(result)
