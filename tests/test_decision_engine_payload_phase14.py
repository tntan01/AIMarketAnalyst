"""Phase 14.6 — test calculate_decision_from_payload() and pick_* helpers."""
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
    pick_final_score,
    pick_gate_result,
    pick_entry_status,
    pick_score_gap,
    calculate_decision_from_payload,
)


# ---------------------------------------------------------------------------
# pick_final_score
# ---------------------------------------------------------------------------


def test_pick_final_score_direct():
    assert pick_final_score({"final_score": 85}) == 85


def test_pick_final_score_from_detail():
    assert pick_final_score({"final_score_detail": {"final_score": 77}}) == 77


def test_pick_final_score_fallback_best_score():
    assert pick_final_score({"decision_summary": {"best_score": 78}}) == 78


def test_pick_final_score_none():
    assert pick_final_score(None) == 0


def test_pick_final_score_empty():
    assert pick_final_score({}) == 0


# ---------------------------------------------------------------------------
# pick_gate_result
# ---------------------------------------------------------------------------


def test_pick_gate_trade_gate():
    gate = {"allowed": True}
    assert pick_gate_result({"trade_gate": gate}) == gate


def test_pick_gate_gate_key():
    gate = {"allowed": False}
    assert pick_gate_result({"gate": gate}) == gate


def test_pick_gate_none():
    assert pick_gate_result(None) is None


# ---------------------------------------------------------------------------
# pick_entry_status
# ---------------------------------------------------------------------------


def test_pick_entry_from_scenario():
    payload = {
        "scenarios": [
            {"type": "sell", "entry_status": "watch_zone"},
            {"type": "buy", "entry_status": "confirmed_entry"},
        ]
    }
    assert pick_entry_status(payload) == "watch_zone"


def test_pick_entry_fallback_key():
    assert pick_entry_status({"entry_status": "invalidated"}) == "invalidated"


def test_pick_entry_none():
    assert pick_entry_status(None) == "unknown"


# ---------------------------------------------------------------------------
# pick_score_gap
# ---------------------------------------------------------------------------


def test_pick_score_gap_decision_summary():
    assert pick_score_gap({"decision_summary": {"score_gap": 15}}) == 15


def test_pick_score_gap_direction_bias():
    assert pick_score_gap({"direction_bias": {"score_gap": 8}}) == 8


def test_pick_score_gap_top_level():
    assert pick_score_gap({"score_gap": 12}) == 12


def test_pick_score_gap_none():
    assert pick_score_gap(None) is None


# ---------------------------------------------------------------------------
# calculate_decision_from_payload
# ---------------------------------------------------------------------------


def test_payload_ready():
    payload = {
        "final_score": 85,
        "trade_gate": {"allowed": True, "decision_cap": None},
        "scenarios": [{"type": "buy", "entry_status": "confirmed_entry"}],
        "decision_summary": {"score_gap": 20},
    }
    result = calculate_decision_from_payload(payload)
    assert result["decision"] == READY_TO_TRADE


def test_payload_gate_blocked():
    payload = {
        "final_score": 95,
        "trade_gate": {"allowed": False, "block_codes": ["SPREAD_ABNORMAL"]},
        "scenarios": [{"type": "buy", "entry_status": "confirmed_entry"}],
        "decision_summary": {"score_gap": 20},
    }
    result = calculate_decision_from_payload(payload)
    assert result["decision"] == TRADE_BLOCKED


def test_payload_waiting_entry():
    payload = {
        "final_score": 90,
        "trade_gate": {"allowed": True, "decision_cap": None},
        "scenarios": [{"type": "buy", "entry_status": "waiting_confirmation"}],
        "decision_summary": {"score_gap": 20},
    }
    result = calculate_decision_from_payload(payload)
    assert result["decision"] == WAITING_CONFIRMATION


def test_payload_score_gap_low():
    payload = {
        "final_score": 90,
        "trade_gate": {"allowed": True, "decision_cap": None},
        "scenarios": [{"type": "buy", "entry_status": "confirmed_entry"}],
        "decision_summary": {"score_gap": 5},
    }
    result = calculate_decision_from_payload(payload)
    assert result["decision"] == WAITING_CONFIRMATION


def test_payload_none_no_crash():
    result = calculate_decision_from_payload(None)
    assert isinstance(result["decision"], str)
    assert result["allowed"] is False


def test_payload_does_not_mutate():
    original = {
        "final_score": 85,
        "trade_gate": {"allowed": True},
        "scenarios": [{"type": "buy", "entry_status": "confirmed_entry"}],
    }
    copy = {
        "final_score": 85,
        "trade_gate": {"allowed": True},
        "scenarios": [{"type": "buy", "entry_status": "confirmed_entry"}],
    }
    calculate_decision_from_payload(original)
    assert original == copy


def test_payload_source_in_breakdown():
    payload = {
        "final_score": 85,
        "trade_gate": {"allowed": True, "decision_cap": None},
        "scenarios": [{"type": "buy", "entry_status": "confirmed_entry"}],
        "decision_summary": {"score_gap": 20},
    }
    result = calculate_decision_from_payload(payload)
    assert result["score_breakdown"]["source"] == "payload"
