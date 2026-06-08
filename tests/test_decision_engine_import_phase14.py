"""Phase 14.2 — test import and basic behaviour of core/decision_engine.py."""
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
    DEFAULT_DECISION_THRESHOLDS,
    DECISION_LABELS,
    default_decision_result,
    make_decision,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_valid_decisions_contains_key_states():
    assert READY_TO_TRADE in VALID_DECISIONS
    assert TRADE_BLOCKED in VALID_DECISIONS
    assert STAND_ASIDE in VALID_DECISIONS
    assert len(VALID_DECISIONS) == 6


def test_default_thresholds():
    assert DEFAULT_DECISION_THRESHOLDS["ready"] == 80
    assert DEFAULT_DECISION_THRESHOLDS["watch"] == 65
    assert DEFAULT_DECISION_THRESHOLDS["wait"] == 50
    assert DEFAULT_DECISION_THRESHOLDS["min_score_gap"] == 10


def test_decision_labels():
    assert DECISION_LABELS[READY_TO_TRADE] == "Sẵn sàng"
    assert DECISION_LABELS[STAND_ASIDE] == "Đứng ngoài"
    assert DECISION_LABELS[TRADE_BLOCKED] == "Bị chặn"


# ---------------------------------------------------------------------------
# default_decision_result
# ---------------------------------------------------------------------------


def test_default_result_decision():
    result = default_decision_result()
    assert result["decision"] == STAND_ASIDE
    assert result["final_score"] == 0
    assert isinstance(result["warning_codes"], list)
    assert len(result["warning_codes"]) >= 1
    assert not result["allowed"]


# ---------------------------------------------------------------------------
# make_decision — safety
# ---------------------------------------------------------------------------


def test_make_decision_none_inputs():
    result = make_decision(None, None, None)
    assert result["decision"] == STAND_ASIDE
    assert not result["allowed"]


def test_make_decision_gate_blocked():
    final = {"final_score": 90}
    gate = {"allowed": False, "decision_cap": "TRADE_BLOCKED", "block_codes": ["SPREAD_ABNORMAL"]}
    result = make_decision(final, gate, "confirmed_entry")
    assert result["decision"] == TRADE_BLOCKED
    assert not result["allowed"]


def test_make_decision_gate_watch_only():
    final = {"final_score": 85}
    gate = {"allowed": True, "decision_cap": "WATCH_ONLY", "warning_codes": ["M15_NOT_CONFIRMED"]}
    result = make_decision(final, gate, "confirmed_entry")
    assert result["decision"] == WATCH_ONLY
    assert result["allowed"]


# ---------------------------------------------------------------------------
# make_decision — ready
# ---------------------------------------------------------------------------


def test_make_decision_ready():
    final = {"final_score": 85}
    gate = {"allowed": True, "decision_cap": None}
    result = make_decision(final, gate, "confirmed_entry")
    assert result["decision"] == READY_TO_TRADE
    assert result["allowed"]


# ---------------------------------------------------------------------------
# make_decision — waiting / watch / stand_aside
# ---------------------------------------------------------------------------


def test_make_decision_confirmed_but_low_score():
    final = {"final_score": 72}
    gate = {"allowed": True, "decision_cap": None}
    result = make_decision(final, gate, "confirmed_entry")
    assert result["decision"] == WAITING_CONFIRMATION


def test_make_decision_watch_range():
    final = {"final_score": 70}
    gate = {"allowed": True, "decision_cap": None}
    result = make_decision(final, gate, "waiting_confirmation")
    assert result["decision"] == WATCH_ONLY


def test_make_decision_stand_aside_low():
    final = {"final_score": 45}
    gate = {"allowed": True, "decision_cap": None}
    result = make_decision(final, gate, "waiting_confirmation")
    assert result["decision"] == STAND_ASIDE


def test_make_decision_aggressive():
    final = {"final_score": 86}
    gate = {"allowed": True, "decision_cap": None}
    result = make_decision(final, gate, "waiting_confirmation")
    assert result["decision"] == AGGRESSIVE_SETUP
    assert result["allowed"]


# ---------------------------------------------------------------------------
# Custom thresholds
# ---------------------------------------------------------------------------


def test_make_decision_custom_thresholds():
    custom = {"ready": 70, "watch": 55, "wait": 40, "min_score_gap": 10}
    final = {"final_score": 75}
    gate = {"allowed": True, "decision_cap": None}
    result = make_decision(final, gate, "confirmed_entry", thresholds=custom)
    assert result["decision"] == READY_TO_TRADE
