from __future__ import annotations

import ast
from pathlib import Path

from core.decision_engine import (
    READY_TO_TRADE,
    TRADE_BLOCKED,
    WAITING_CONFIRMATION,
    WATCH_ONLY,
    make_decision,
    make_final_decision,
)
from core.reason_codes import (
    DECISION_ENTRY_NOT_CONFIRMED,
    DECISION_FINAL_SCORE_STRONG,
    DECISION_GATE_BLOCKED,
    DECISION_GATE_CAPPED,
    DECISION_READY_TO_TRADE,
    DECISION_SCORE_GAP_LOW,
    DECISION_TRADE_BLOCKED,
    DECISION_WAITING_CONFIRMATION,
    DECISION_WATCH_ONLY,
)


def _allowed_gate(**extra):
    return {"allowed": True, **extra}


def test_gate_block_has_priority_over_high_score_and_confirmed_entry():
    result = make_final_decision(
        final_score=95,
        gate_result={"allowed": False, "block_codes": ["SPREAD_BLOCKED"]},
        entry_status="confirmed_entry",
        score_gap=30,
    )

    assert result["decision"] == TRADE_BLOCKED
    assert result["allowed"] is False
    assert DECISION_TRADE_BLOCKED in result["reason_codes"]
    assert DECISION_GATE_BLOCKED in result["block_codes"]
    assert "SPREAD_BLOCKED" in result["block_codes"]


def test_decision_cap_watch_only_overrides_ready_conditions():
    result = make_final_decision(
        final_score=95,
        gate_result=_allowed_gate(decision_cap="WATCH_ONLY"),
        entry_status="confirmed_entry",
        score_gap=30,
    )

    assert result["decision"] == WATCH_ONLY
    assert result["allowed"] is True
    assert result["decision_cap"] == "WATCH_ONLY"
    assert DECISION_GATE_CAPPED in result["warning_codes"]
    assert DECISION_WATCH_ONLY in result["reason_codes"]


def test_low_score_gap_waits_even_when_entry_is_confirmed():
    result = make_final_decision(
        final_score=90,
        gate_result=_allowed_gate(),
        entry_status="confirmed_entry",
        score_gap=4,
    )

    assert result["decision"] == WAITING_CONFIRMATION
    assert DECISION_SCORE_GAP_LOW in result["warning_codes"]
    assert DECISION_WAITING_CONFIRMATION in result["reason_codes"]


def test_missing_entry_confirmation_waits_and_marks_warning():
    result = make_final_decision(
        final_score=90,
        gate_result=_allowed_gate(),
        entry_status="waiting_confirmation",
        score_gap=20,
    )

    assert result["decision"] == WAITING_CONFIRMATION
    assert DECISION_ENTRY_NOT_CONFIRMED in result["warning_codes"]
    assert result["allowed"] is True


def test_confirmed_entry_and_strong_score_are_ready_to_trade():
    result = make_final_decision(
        final_score=88,
        gate_result=_allowed_gate(),
        entry_status="confirmed_entry",
        score_gap=20,
    )

    assert result["decision"] == READY_TO_TRADE
    assert result["allowed"] is True
    assert DECISION_READY_TO_TRADE in result["reason_codes"]
    assert DECISION_FINAL_SCORE_STRONG in result["reason_codes"]


def test_compat_make_decision_delegates_to_final_decision_shape():
    result = make_decision(
        {"final_score": 88},
        _allowed_gate(),
        "confirmed_entry",
    )

    assert result["decision"] == READY_TO_TRADE
    assert result["legacy_action"] == "ready"
    assert result["allowed"] is True


def test_decision_engine_has_no_duplicate_literal_dict_keys():
    source = Path("core/decision_engine.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    duplicates: list[tuple[str, int, int]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        seen: dict[str, int] = {}
        for key in node.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                if key.value in seen:
                    duplicates.append((key.value, seen[key.value], key.lineno))
                else:
                    seen[key.value] = key.lineno

    assert duplicates == []
