"""Phase 14.8 — test legacy action mapping helpers."""
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
    decision_to_legacy_action,
    legacy_action_to_decision,
    make_final_decision,
)


# ---------------------------------------------------------------------------
# decision_to_legacy_action
# ---------------------------------------------------------------------------


def test_decision_to_legacy_ready():
    assert decision_to_legacy_action(READY_TO_TRADE) == "ready"


def test_decision_to_legacy_watch():
    assert decision_to_legacy_action(WATCH_ONLY) == "watch"


def test_decision_to_legacy_waiting():
    assert decision_to_legacy_action(WAITING_CONFIRMATION) == "wait_for_confirmation"


def test_decision_to_legacy_aggressive():
    assert decision_to_legacy_action(AGGRESSIVE_SETUP) == "wait_for_confirmation"


def test_decision_to_legacy_blocked():
    assert decision_to_legacy_action(TRADE_BLOCKED) == "stand_aside"


def test_decision_to_legacy_stand_aside():
    assert decision_to_legacy_action(STAND_ASIDE) == "stand_aside"


def test_decision_to_legacy_unknown():
    assert decision_to_legacy_action("bogus") == "stand_aside"
    assert decision_to_legacy_action(None) == "stand_aside"


# ---------------------------------------------------------------------------
# legacy_action_to_decision
# ---------------------------------------------------------------------------


def test_legacy_to_decision_ready():
    assert legacy_action_to_decision("ready") == READY_TO_TRADE


def test_legacy_to_decision_watch():
    assert legacy_action_to_decision("watch") == WATCH_ONLY


def test_legacy_to_decision_wait():
    assert legacy_action_to_decision("wait") == WAITING_CONFIRMATION


def test_legacy_to_decision_wait_for_confirmation():
    assert legacy_action_to_decision("wait_for_confirmation") == WAITING_CONFIRMATION


def test_legacy_to_decision_stand_aside():
    assert legacy_action_to_decision("stand_aside") == STAND_ASIDE


def test_legacy_to_decision_skip():
    assert legacy_action_to_decision("skip") == STAND_ASIDE


def test_legacy_to_decision_unknown():
    assert legacy_action_to_decision("unknown") == STAND_ASIDE
    assert legacy_action_to_decision(None) == STAND_ASIDE


# ---------------------------------------------------------------------------
# make_final_decision output includes legacy_action
# ---------------------------------------------------------------------------


def test_make_final_decision_ready_has_legacy():
    result = make_final_decision(
        final_score=85,
        gate_result={"allowed": True},
        entry_status="confirmed_entry",
        score_gap=20,
    )
    assert result["decision"] == READY_TO_TRADE
    assert result["legacy_action"] == "ready"


def test_make_final_decision_blocked_has_legacy():
    result = make_final_decision(
        final_score=90,
        gate_result={"allowed": False},
    )
    assert result["decision"] == TRADE_BLOCKED
    assert result["legacy_action"] == "stand_aside"


def test_make_final_decision_watch_has_legacy():
    result = make_final_decision(
        final_score=70,
        gate_result={"allowed": True},
        entry_status="confirmed_entry",
    )
    assert result["decision"] == WATCH_ONLY
    assert result["legacy_action"] == "watch"
