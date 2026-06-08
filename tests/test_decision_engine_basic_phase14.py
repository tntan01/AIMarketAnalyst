"""Phase 14.4 — test make_final_decision() logic layers."""
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
    make_final_decision,
)


# ---------------------------------------------------------------------------
# A. Gate block
# ---------------------------------------------------------------------------


def test_gate_blocked_allowed_false():
    result = make_final_decision(final_score=95, gate_result={"allowed": False})
    assert result["decision"] == TRADE_BLOCKED
    assert not result["allowed"]


def test_gate_blocked_trade_permission():
    result = make_final_decision(
        final_score=95,
        gate_result={"allowed": True},
        trade_permission={"status": "blocked"},
    )
    assert result["decision"] == TRADE_BLOCKED


# ---------------------------------------------------------------------------
# B/C/D. Decision caps
# ---------------------------------------------------------------------------


def test_cap_watch_only():
    result = make_final_decision(
        final_score=95,
        gate_result={"allowed": True, "decision_cap": "WATCH_ONLY"},
        entry_status="confirmed_entry",
    )
    assert result["decision"] == WATCH_ONLY


def test_cap_waiting_confirmation():
    result = make_final_decision(
        final_score=95,
        gate_result={"allowed": True, "decision_cap": "WAITING_CONFIRMATION"},
        entry_status="confirmed_entry",
    )
    assert result["decision"] == WAITING_CONFIRMATION


def test_cap_trade_blocked():
    result = make_final_decision(
        final_score=95,
        gate_result={"allowed": True, "decision_cap": "TRADE_BLOCKED"},
        entry_status="confirmed_entry",
    )
    assert result["decision"] == TRADE_BLOCKED


# ---------------------------------------------------------------------------
# E. Score gap
# ---------------------------------------------------------------------------


def test_score_gap_low():
    result = make_final_decision(
        final_score=90,
        gate_result={"allowed": True},
        entry_status="confirmed_entry",
        score_gap=3,
    )
    assert result["decision"] == WAITING_CONFIRMATION
    # Not READY despite high score


def test_score_gap_ok():
    result = make_final_decision(
        final_score=90,
        gate_result={"allowed": True},
        entry_status="confirmed_entry",
        score_gap=15,
    )
    assert result["decision"] == READY_TO_TRADE


# ---------------------------------------------------------------------------
# F. Entry not confirmed
# ---------------------------------------------------------------------------


def test_entry_waiting_confirmation():
    result = make_final_decision(
        final_score=90,
        gate_result={"allowed": True},
        entry_status="waiting_confirmation",
        score_gap=20,
    )
    assert result["decision"] == WAITING_CONFIRMATION


def test_entry_watch_zone():
    result = make_final_decision(
        final_score=90,
        gate_result={"allowed": True},
        entry_status="watch_zone",
        score_gap=20,
    )
    assert result["decision"] == WATCH_ONLY


def test_entry_invalidated():
    result = make_final_decision(
        final_score=90,
        gate_result={"allowed": True},
        entry_status="invalidated",
    )
    assert result["decision"] == STAND_ASIDE


def test_entry_no_setup():
    result = make_final_decision(
        final_score=90,
        gate_result={"allowed": True},
        entry_status="no_setup",
    )
    assert result["decision"] == STAND_ASIDE


def test_entry_unknown():
    result = make_final_decision(
        final_score=90,
        gate_result={"allowed": True},
        entry_status="unknown",
    )
    assert result["decision"] == WAITING_CONFIRMATION


# ---------------------------------------------------------------------------
# G. Entry confirmed + score tiers
# ---------------------------------------------------------------------------


def test_ready():
    result = make_final_decision(
        final_score=85,
        gate_result={"allowed": True},
        entry_status="confirmed_entry",
    )
    assert result["decision"] == READY_TO_TRADE
    assert result["allowed"]


def test_watch_score():
    result = make_final_decision(
        final_score=70,
        gate_result={"allowed": True},
        entry_status="confirmed_entry",
    )
    assert result["decision"] == WATCH_ONLY


def test_wait_score():
    result = make_final_decision(
        final_score=55,
        gate_result={"allowed": True},
        entry_status="confirmed_entry",
    )
    assert result["decision"] == WAITING_CONFIRMATION


def test_stand_aside_low():
    result = make_final_decision(
        final_score=40,
        gate_result={"allowed": True},
        entry_status="confirmed_entry",
    )
    assert result["decision"] == STAND_ASIDE


# ---------------------------------------------------------------------------
# Dirty data
# ---------------------------------------------------------------------------


def test_dirty_no_crash():
    result = make_final_decision(
        final_score="bad",
        gate_result=None,
        entry_status=None,
    )
    assert result["decision"] in (TRADE_BLOCKED, STAND_ASIDE)
    assert isinstance(result["final_score"], int)


def test_output_has_required_keys():
    result = make_final_decision(final_score=80, gate_result={"allowed": True})
    assert "decision" in result
    assert "final_score" in result
    assert "decision_label" in result
    assert "reason_codes" in result
    assert "warning_codes" in result
    assert "block_codes" in result
    assert "decision_cap" in result
    assert "allowed" in result
    assert "score_breakdown" in result
    assert "reason" in result


def test_score_breakdown_structure():
    result = make_final_decision(
        final_score=80,
        gate_result={"allowed": True},
        entry_status="confirmed_entry",
        score_gap=12,
    )
    bd = result["score_breakdown"]
    assert "entry_status" in bd
    assert "score_gap" in bd
    assert "thresholds" in bd
    assert "gate_allowed" in bd
    assert "applied_rule" in bd


def test_custom_thresholds():
    custom = {"ready": 70, "watch": 55, "wait": 40, "min_score_gap": 8}
    result = make_final_decision(
        final_score=72,
        gate_result={"allowed": True},
        entry_status="confirmed_entry",
        thresholds=custom,
    )
    assert result["decision"] == READY_TO_TRADE
