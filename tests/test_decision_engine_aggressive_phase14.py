"""Phase 14.5 — test AGGRESSIVE_SETUP behaviour in make_final_decision."""
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
    make_final_decision,
    DECISION_ENTRY_NOT_CONFIRMED,
    DECISION_AGGRESSIVE_SETUP,
)


# ---------------------------------------------------------------------------
# Default: allow_aggressive_setup=False
# ---------------------------------------------------------------------------


def test_default_no_aggressive():
    """Without allow_aggressive_setup, waiting_confirmation stays waiting."""
    result = make_final_decision(
        final_score=90,
        gate_result={"allowed": True},
        entry_status="waiting_confirmation",
        score_gap=20,
    )
    assert result["decision"] == WAITING_CONFIRMATION


# ---------------------------------------------------------------------------
# allow_aggressive_setup=True — basic
# ---------------------------------------------------------------------------


def test_aggressive_allowed():
    """When allowed, waiting_confirmation + high score → AGGRESSIVE."""
    result = make_final_decision(
        final_score=90,
        gate_result={"allowed": True},
        entry_status="waiting_confirmation",
        score_gap=20,
        allow_aggressive_setup=True,
    )
    assert result["decision"] == AGGRESSIVE_SETUP
    assert result["allowed"]
    assert DECISION_AGGRESSIVE_SETUP in result["reason_codes"]
    assert DECISION_ENTRY_NOT_CONFIRMED in result["warning_codes"]


# ---------------------------------------------------------------------------
# AGGRESSIVE_SETUP must NOT override gates
# ---------------------------------------------------------------------------


def test_aggressive_blocked_by_gate():
    """Gate blocked → TRADE_BLOCKED even with allow_aggressive_setup."""
    result = make_final_decision(
        final_score=90,
        gate_result={"allowed": False},
        entry_status="waiting_confirmation",
        score_gap=20,
        allow_aggressive_setup=True,
    )
    assert result["decision"] == TRADE_BLOCKED


def test_aggressive_blocked_by_cap():
    """Decision cap WATCH_ONLY → WATCH_ONLY even with allow_aggressive_setup."""
    result = make_final_decision(
        final_score=90,
        gate_result={"allowed": True, "decision_cap": "WATCH_ONLY"},
        entry_status="waiting_confirmation",
        score_gap=20,
        allow_aggressive_setup=True,
    )
    assert result["decision"] == WATCH_ONLY


# ---------------------------------------------------------------------------
# AGGRESSIVE_SETUP must NOT override score gap
# ---------------------------------------------------------------------------


def test_aggressive_score_gap_low():
    """Score gap too low → WAITING_CONFIRMATION even with aggressive allowed."""
    result = make_final_decision(
        final_score=90,
        gate_result={"allowed": True},
        entry_status="waiting_confirmation",
        score_gap=3,
        allow_aggressive_setup=True,
    )
    # Score gap check (E) runs before aggressive setup (E2) in Make-Order logic flow
    assert result["decision"] == WAITING_CONFIRMATION


# ---------------------------------------------------------------------------
# AGGRESSIVE_SETUP must NOT trigger for other entry statuses
# ---------------------------------------------------------------------------


def test_aggressive_not_for_confirmed_entry():
    """confirmed_entry → READY (not aggressive) even when allowed."""
    result = make_final_decision(
        final_score=85,
        gate_result={"allowed": True},
        entry_status="confirmed_entry",
        score_gap=20,
        allow_aggressive_setup=True,
    )
    assert result["decision"] == READY_TO_TRADE


def test_aggressive_not_for_watch_zone():
    """watch_zone → WATCH_ONLY even when aggressive allowed."""
    result = make_final_decision(
        final_score=90,
        gate_result={"allowed": True},
        entry_status="watch_zone",
        score_gap=20,
        allow_aggressive_setup=True,
    )
    assert result["decision"] == WATCH_ONLY


def test_aggressive_not_for_invalidated():
    """invalidated → STAND_ASIDE even when aggressive allowed."""
    result = make_final_decision(
        final_score=90,
        gate_result={"allowed": True},
        entry_status="invalidated",
        allow_aggressive_setup=True,
    )
    assert result["decision"] == STAND_ASIDE


# ---------------------------------------------------------------------------
# Score threshold
# ---------------------------------------------------------------------------


def test_aggressive_needs_high_score():
    """Score below ready threshold → WAITING_CONFIRMATION not aggressive."""
    result = make_final_decision(
        final_score=70,
        gate_result={"allowed": True},
        entry_status="waiting_confirmation",
        score_gap=20,
        allow_aggressive_setup=True,
    )
    # Score 70 < ready(80) → falls through to waiting_confirmation in F
    assert result["decision"] == WAITING_CONFIRMATION
