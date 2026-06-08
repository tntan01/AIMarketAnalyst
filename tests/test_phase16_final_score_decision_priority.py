"""Phase 16.8 — verify final_score + decision_engine priority: gate > gap > entry > score."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.final_score_engine import calculate_final_score
from core.decision_engine import make_final_decision


# ---------------------------------------------------------------------------
# Case 1: High final_score but gate blocks
# ---------------------------------------------------------------------------


def test_gate_block_overrides_high_final_score():
    final = calculate_final_score(signal_score=95, evidence_score=80, execution_quality_score=100)
    decision = make_final_decision(
        final_score=final["final_score"],
        gate_result={"allowed": False, "decision_cap": "TRADE_BLOCKED"},
        entry_status="confirmed_entry",
        score_gap=30,
    )
    assert decision["decision"] == "TRADE_BLOCKED"


# ---------------------------------------------------------------------------
# Case 2: High final_score but score_gap too low
# ---------------------------------------------------------------------------


def test_score_gap_overrides_high_final_score():
    final = calculate_final_score(signal_score=90, evidence_score=75, execution_quality_score=100)
    decision = make_final_decision(
        final_score=final["final_score"],
        gate_result={"allowed": True},
        entry_status="confirmed_entry",
        score_gap=4,
    )
    assert decision["decision"] == "WAITING_CONFIRMATION"
    assert decision["decision"] != "READY_TO_TRADE"


# ---------------------------------------------------------------------------
# Case 3: High final_score but entry waiting
# ---------------------------------------------------------------------------


def test_entry_waiting_blocks_ready():
    final = calculate_final_score(signal_score=88, evidence_score=70, execution_quality_score=100)
    decision = make_final_decision(
        final_score=final["final_score"],
        gate_result={"allowed": True},
        entry_status="waiting_confirmation",
        score_gap=20,
    )
    # Default aggressive=False → should be WAITING_CONFIRMATION
    assert decision["decision"] == "WAITING_CONFIRMATION"


# ---------------------------------------------------------------------------
# Case 4: Moderate final_score → WATCH
# ---------------------------------------------------------------------------


def test_moderate_score_watch():
    final = calculate_final_score(signal_score=70, evidence_score=50, execution_quality_score=100)
    decision = make_final_decision(
        final_score=final["final_score"],
        gate_result={"allowed": True},
        entry_status="confirmed_entry",
        score_gap=20,
    )
    assert decision["decision"] == "WATCH_ONLY"


# ---------------------------------------------------------------------------
# Case 5: Weak final_score → STAND_ASIDE
# ---------------------------------------------------------------------------


def test_weak_score_stand_aside():
    final = calculate_final_score(signal_score=40, evidence_score=30, execution_quality_score=50)
    decision = make_final_decision(
        final_score=final["final_score"],
        gate_result={"allowed": True},
        entry_status="confirmed_entry",
        score_gap=20,
    )
    assert decision["decision"] == "STAND_ASIDE"


# ---------------------------------------------------------------------------
# Case 6: Perfect setup → READY
# ---------------------------------------------------------------------------


def test_perfect_setup_ready():
    final = calculate_final_score(signal_score=90, evidence_score=80, execution_quality_score=95)
    decision = make_final_decision(
        final_score=final["final_score"],
        gate_result={"allowed": True},
        entry_status="confirmed_entry",
        score_gap=20,
    )
    assert decision["decision"] == "READY_TO_TRADE"
    assert decision["allowed"] is True


# ---------------------------------------------------------------------------
# Case 7: Aggressive opt-in with waiting entry
# ---------------------------------------------------------------------------


def test_aggressive_opt_in():
    final = calculate_final_score(signal_score=88, evidence_score=75, execution_quality_score=100)
    decision = make_final_decision(
        final_score=final["final_score"],
        gate_result={"allowed": True},
        entry_status="waiting_confirmation",
        score_gap=20,
        allow_aggressive_setup=True,
    )
    assert decision["decision"] == "AGGRESSIVE_SETUP"
    assert decision["allowed"] is True


# ---------------------------------------------------------------------------
# Verify all results have standard keys
# ---------------------------------------------------------------------------


def test_all_decisions_have_required_keys():
    cases = [
        (calculate_final_score(90, 80, 95), {"allowed": True}, "confirmed_entry", 20),
        (calculate_final_score(95, 80, 100), {"allowed": False}, "confirmed_entry", 30),
        (calculate_final_score(40, 30, 50), {"allowed": True}, "confirmed_entry", 20),
    ]
    for final, gate, entry, gap in cases:
        decision = make_final_decision(
            final_score=final["final_score"],
            gate_result=gate,
            entry_status=entry,
            score_gap=gap,
        )
        for key in ("decision", "final_score", "decision_label", "legacy_action",
                     "reason_codes", "warning_codes", "block_codes", "allowed"):
            assert key in decision, f"Missing key '{key}' in decision"
