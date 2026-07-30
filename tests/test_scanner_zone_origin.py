"""Unit tests for core/scanner_zone_origin.py — contract and classification."""

from __future__ import annotations

import copy

import pytest

from core.scanner_zone_origin import (
    VALID_ZONE_ORIGIN_CLASSES,
    ZONE_ORIGIN_FALLBACK,
    ZONE_ORIGIN_NONE,
    ZONE_ORIGIN_SMC,
    ZONE_ORIGIN_TECHNICAL,
    classify_entry_zone_source,
    zone_origin_from_row,
)


# ---------------------------------------------------------------------------
# classify_entry_zone_source — raw source → class
#
# Matrix is HARD-CODED, not generated from production allowlists, so tests
# do not silently pass when an allowlist is accidentally changed.
# ---------------------------------------------------------------------------

CLASSIFY_CASES = [
    # SMC sources (must match SMC_ENTRY_ZONE_SOURCES in production)
    ("smc", ZONE_ORIGIN_SMC),
    ("smc_selected", ZONE_ORIGIN_SMC),
    ("smc_active_selected", ZONE_ORIGIN_SMC),
    ("smc_v2_selected", ZONE_ORIGIN_SMC),
    ("smc_distant", ZONE_ORIGIN_SMC),
    # Technical
    ("technical", ZONE_ORIGIN_TECHNICAL),
    # Fallback
    ("fallback", ZONE_ORIGIN_FALLBACK),
    # None / edge
    (None, ZONE_ORIGIN_NONE),
    ("", ZONE_ORIGIN_NONE),
    ("   ", ZONE_ORIGIN_NONE),
    ("keyword_fallback", ZONE_ORIGIN_NONE),
    ("smc_future_unknown", ZONE_ORIGIN_NONE),
    ("random_string", ZONE_ORIGIN_NONE),
    # Case-insensitive
    ("SMC", ZONE_ORIGIN_SMC),
    ("SMC_SELECTED", ZONE_ORIGIN_SMC),
    ("SMC_DISTANT", ZONE_ORIGIN_SMC),
    ("FALLBACK", ZONE_ORIGIN_FALLBACK),
    ("TECHNICAL", ZONE_ORIGIN_TECHNICAL),
    # Whitespace-trimmed
    ("  smc_v2_selected  ", ZONE_ORIGIN_SMC),
    ("\t fallback \n", ZONE_ORIGIN_FALLBACK),
    # Non-string types
    (123, ZONE_ORIGIN_NONE),
    (0, ZONE_ORIGIN_NONE),
    (True, ZONE_ORIGIN_NONE),
    (3.14, ZONE_ORIGIN_NONE),
]


@pytest.mark.parametrize("source,expected", CLASSIFY_CASES)
def test_classify_entry_zone_source(source, expected):
    assert classify_entry_zone_source(source) == expected


def test_valid_classes_contains_all_four():
    assert VALID_ZONE_ORIGIN_CLASSES == frozenset({
        ZONE_ORIGIN_SMC,
        ZONE_ORIGIN_TECHNICAL,
        ZONE_ORIGIN_FALLBACK,
        ZONE_ORIGIN_NONE,
    })


# ---------------------------------------------------------------------------
# zone_origin_from_row — row-level extraction
# ---------------------------------------------------------------------------

def test_zone_origin_from_row_not_dict_returns_none():
    assert zone_origin_from_row(None) == ZONE_ORIGIN_NONE
    assert zone_origin_from_row("string") == ZONE_ORIGIN_NONE
    assert zone_origin_from_row(42) == ZONE_ORIGIN_NONE
    assert zone_origin_from_row([]) == ZONE_ORIGIN_NONE


# --- Priority 1: stamped zone_origin_class ---

def test_zone_origin_from_row_prioritizes_stamped_field():
    row = {
        "zone_origin_class": "technical",
        "entry_zone_source": "smc_v2_selected",
    }
    assert zone_origin_from_row(row) == ZONE_ORIGIN_TECHNICAL


def test_zone_origin_from_row_invalid_stamped_field_falls_back():
    row = {
        "zone_origin_class": "bogus_value",
        "entry_zone_source": "fallback",
    }
    assert zone_origin_from_row(row) == ZONE_ORIGIN_FALLBACK


# --- Priority 2: entry_zone_source key EXISTS → classify directly ---

def test_zone_origin_from_row_reads_entry_zone_source():
    row = {"entry_zone_source": "fallback"}
    assert zone_origin_from_row(row) == ZONE_ORIGIN_FALLBACK

    row = {"entry_zone_source": "technical"}
    assert zone_origin_from_row(row) == ZONE_ORIGIN_TECHNICAL

    row = {"entry_zone_source": "smc_distant"}
    assert zone_origin_from_row(row) == ZONE_ORIGIN_SMC


def test_zone_origin_from_row_entry_zone_source_none_direct_classify():
    """Key exists with None → classify directly as 'none', do NOT fall to nested."""
    row = {
        "entry_zone_source": None,
        "selected_side": "buy",
        "analysis_result": {
            "scenarios": [
                {"type": "buy", "entry_zone_source": "technical"},
            ]
        },
    }
    assert zone_origin_from_row(row) == ZONE_ORIGIN_NONE


def test_zone_origin_from_row_entry_zone_source_empty_direct_classify():
    """Key exists with '' → classify directly as 'none', do NOT fall to nested."""
    row = {
        "entry_zone_source": "",
        "selected_side": "buy",
        "analysis_result": {
            "scenarios": [
                {"type": "buy", "entry_zone_source": "technical"},
            ]
        },
    }
    assert zone_origin_from_row(row) == ZONE_ORIGIN_NONE


# --- Priority 3: key ABSENT → nested scenario fallback (legacy payload) ---

def test_zone_origin_from_row_key_missing_falls_to_nested():
    """Row truly lacks entry_zone_source key → read nested scenarios."""
    row = {
        "selected_side": "buy",
        "analysis_result": {
            "scenarios": [
                {"type": "buy", "entry_zone_source": "technical"},
            ]
        },
    }
    # key "entry_zone_source" not in row → nested fallback
    assert zone_origin_from_row(row) == ZONE_ORIGIN_TECHNICAL


def test_zone_origin_from_row_key_missing_no_scenarios_returns_none():
    row: dict = {}
    assert zone_origin_from_row(row) == ZONE_ORIGIN_NONE

    row = {"analysis_result": {}}
    assert zone_origin_from_row(row) == ZONE_ORIGIN_NONE

    row = {"analysis_result": {"scenarios": []}}
    assert zone_origin_from_row(row) == ZONE_ORIGIN_NONE


# --- Nested scenario selection ---

def test_zone_origin_from_row_selected_side_scenario():
    row = {
        "selected_side": "sell",
        "analysis_result": {
            "scenarios": [
                {"type": "buy", "entry_zone_source": "smc"},
                {"type": "sell", "entry_zone_source": "technical"},
            ]
        },
    }
    assert zone_origin_from_row(row) == ZONE_ORIGIN_TECHNICAL


def test_zone_origin_from_row_falls_back_to_best_side():
    row = {
        "best_side": "buy",
        "analysis_result": {
            "scenarios": [
                {"type": "buy", "entry_zone_source": "smc_v2_selected"},
                {"type": "sell", "entry_zone_source": "fallback"},
            ]
        },
    }
    assert zone_origin_from_row(row) == ZONE_ORIGIN_SMC


def test_zone_origin_from_row_single_directional_scenario():
    row = {
        "analysis_result": {
            "scenarios": [
                {"side": "buy", "entry_zone_source": "fallback"},
            ]
        },
    }
    assert zone_origin_from_row(row) == ZONE_ORIGIN_FALLBACK


def test_zone_origin_from_row_multiple_scenarios_no_side_returns_none():
    """When there are multiple directional scenarios but no selected_side,
    best_side, or other hint, return none — do NOT pick the first."""
    row = {
        "analysis_result": {
            "scenarios": [
                {"type": "buy", "entry_zone_source": "smc"},
                {"type": "sell", "entry_zone_source": "fallback"},
            ]
        },
    }
    assert zone_origin_from_row(row) == ZONE_ORIGIN_NONE


# --- Independent type/side check ---

def test_zone_origin_from_row_type_primary_side_buy_is_directional():
    """type='primary' is not buy/sell BUT side='buy' is → scenario IS directional."""
    row = {
        "selected_side": "buy",
        "analysis_result": {
            "scenarios": [
                {"type": "primary", "side": "buy", "entry_zone_source": "smc"},
            ]
        },
    }
    assert zone_origin_from_row(row) == ZONE_ORIGIN_SMC


def test_zone_origin_from_row_type_buy_side_empty_is_directional():
    """type='buy' even without side → directional."""
    row = {
        "selected_side": "buy",
        "analysis_result": {
            "scenarios": [
                {"type": "buy", "entry_zone_source": "technical"},
            ]
        },
    }
    assert zone_origin_from_row(row) == ZONE_ORIGIN_TECHNICAL


def test_zone_origin_from_row_type_none_side_sell_is_directional():
    """type=None, side='sell' → directional."""
    row = {
        "selected_side": "sell",
        "analysis_result": {
            "scenarios": [
                {"type": None, "side": "sell", "entry_zone_source": "smc"},
            ]
        },
    }
    assert zone_origin_from_row(row) == ZONE_ORIGIN_SMC


def test_zone_origin_from_row_neither_type_nor_side_directional():
    """Neither type nor side is buy/sell → NOT directional."""
    row = {
        "analysis_result": {
            "scenarios": [
                {"type": "neutral", "side": "watch", "entry_zone_source": "smc"},
            ]
        },
    }
    assert zone_origin_from_row(row) == ZONE_ORIGIN_NONE


# PO-required matrix of 3 specific cases
def test_po_required_three_cases():
    """Contract: type='primary'/side='buy' → none; type='buy' → none;
    type='buy'/side='buy' → smc (all with no selected_side, multiple scenarios)."""
    # Case 1: type="primary", side="buy" → directional recognized, but
    # multiple scenarios with no selected_side/best_side → none
    row1 = {
        "analysis_result": {
            "scenarios": [
                {"type": "primary", "side": "buy", "entry_zone_source": "technical"},
                {"type": "primary", "side": "sell", "entry_zone_source": "smc"},
            ]
        },
    }
    assert zone_origin_from_row(row1) == ZONE_ORIGIN_NONE

    # Case 2: type="buy" only → directional recognized, but
    # multiple scenarios with no selected_side/best_side → none
    row2 = {
        "analysis_result": {
            "scenarios": [
                {"type": "buy", "entry_zone_source": "technical"},
                {"type": "sell", "entry_zone_source": "smc"},
            ]
        },
    }
    assert zone_origin_from_row(row2) == ZONE_ORIGIN_NONE

    # Case 3: exactly one directional scenario → smc
    row3 = {
        "analysis_result": {
            "scenarios": [
                {"type": "buy", "side": "buy", "entry_zone_source": "smc"},
            ]
        },
    }
    assert zone_origin_from_row(row3) == ZONE_ORIGIN_SMC


# --- Matching selected_side/best_side via type OR side independently ---

def test_zone_origin_from_row_matches_selected_side_via_side_field():
    """selected_side='buy' matches scenario with type='primary', side='buy'."""
    row = {
        "selected_side": "buy",
        "analysis_result": {
            "scenarios": [
                {"type": "primary", "side": "buy", "entry_zone_source": "smc_v2_selected"},
                {"type": "primary", "side": "sell", "entry_zone_source": "fallback"},
            ]
        },
    }
    assert zone_origin_from_row(row) == ZONE_ORIGIN_SMC


def test_zone_origin_from_row_matches_best_side_via_side_field():
    """best_side='sell' matches scenario with type='primary', side='sell'."""
    row = {
        "best_side": "sell",
        "analysis_result": {
            "scenarios": [
                {"type": "primary", "side": "buy", "entry_zone_source": "smc"},
                {"type": "primary", "side": "sell", "entry_zone_source": "technical"},
            ]
        },
    }
    assert zone_origin_from_row(row) == ZONE_ORIGIN_TECHNICAL


# --- Immutability ---

def test_classify_does_not_mutate():
    row = {
        "entry_zone_source": "fallback",
        "analysis_result": {"scenarios": [{"type": "buy", "entry_zone_source": "smc"}]},
    }
    original = copy.deepcopy(row)
    zone_origin_from_row(row)
    assert row == original


def test_zone_origin_from_row_handles_malformed_scenarios():
    row = {
        "selected_side": "buy",
        "analysis_result": {"scenarios": [None, 123, "string", {"type": "buy", "entry_zone_source": "smc"}]},
    }
    assert zone_origin_from_row(row) == ZONE_ORIGIN_SMC


def test_zone_origin_from_row_side_via_field():
    """Scenarios that use 'side' instead of 'type' are recognized."""
    row = {
        "best_side": "sell",
        "analysis_result": {
            "scenarios": [
                {"side": "sell", "entry_zone_source": "smc_active_selected"},
            ]
        },
    }
    assert zone_origin_from_row(row) == ZONE_ORIGIN_SMC


# ---------------------------------------------------------------------------
# Integration: scanner_row_from_analysis populates zone_origin_class
# ---------------------------------------------------------------------------


def _make_result(symbol="EUR/USD", plan=None, side="buy"):
    """Build a minimal analysis result for scanner_row_from_analysis."""
    scenarios = [plan] if plan else []
    return {
        "symbol": symbol,
        "scenario_scores": {
            "buy": {"signal_score": 80, "macro_alignment": 15, "macro_confidence": 1.0},
            "sell": {"signal_score": 40, "macro_alignment": 15, "macro_confidence": 1.0},
        },
        "trade_permission": {"status": "allowed"},
        "scenarios": scenarios,
        "technical": {"price": 1.1000, "atr_h4": 0.0020},
        "decision_engine": {"legacy_action": "buy"},
        "direction_bias": {"best_side": "buy"},
    }


def _make_plan(entry_zone_source, side="buy"):
    return {
        "type": side,
        "risk_reward": "1:2.4",
        "entry_zone": [1.095, 1.097],
        "entry_status": "watch_zone",
        "stop_loss": 1.093,
        "take_profit": [1.105],
        "entry_zone_source": entry_zone_source,
    }


def test_row_from_analysis_smc_v2_selected():
    from core.scanner import scanner_row_from_analysis

    plan = _make_plan("smc_v2_selected")
    row = scanner_row_from_analysis(_make_result(plan=plan))
    assert row["entry_zone_source"] == "smc_v2_selected"
    assert row["zone_origin_class"] == ZONE_ORIGIN_SMC


def test_row_from_analysis_smc_distant():
    from core.scanner import scanner_row_from_analysis

    plan = _make_plan("smc_distant")
    row = scanner_row_from_analysis(_make_result(plan=plan))
    assert row["entry_zone_source"] == "smc_distant"
    assert row["zone_origin_class"] == ZONE_ORIGIN_SMC


def test_row_from_analysis_technical():
    from core.scanner import scanner_row_from_analysis

    plan = _make_plan("technical")
    row = scanner_row_from_analysis(_make_result(plan=plan))
    assert row["entry_zone_source"] == "technical"
    assert row["zone_origin_class"] == ZONE_ORIGIN_TECHNICAL


def test_row_from_analysis_fallback():
    from core.scanner import scanner_row_from_analysis

    plan = _make_plan("fallback")
    row = scanner_row_from_analysis(_make_result(plan=plan))
    assert row["entry_zone_source"] == "fallback"
    assert row["zone_origin_class"] == ZONE_ORIGIN_FALLBACK


def test_row_from_analysis_no_best_plan_is_none():
    from core.scanner import scanner_row_from_analysis

    row = scanner_row_from_analysis(_make_result(plan=None))
    assert row["zone_origin_class"] == ZONE_ORIGIN_NONE


def test_blocked_row_is_none():
    from core.scanner import blocked_scanner_row

    row = blocked_scanner_row("EUR/USD", "DATA_UNAVAILABLE")
    assert row["entry_zone_source"] is None
    assert row["zone_origin_class"] == ZONE_ORIGIN_NONE
