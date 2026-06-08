"""Phase 18 — test scanner ranking decision priority.

Verify that legacy scanner_action="skip" does NOT override decision-engine
results (WATCH_ONLY, WAITING_CONFIRMATION) in classify_scanner_group() and
its callers (calculate_opportunity_score, enrich_scanner_row_with_ranking).

These tests currently FAIL because of the bug described in:
docs/Upgrade/score_and_gate_upgrade/UNFINISH - phase_18_fix_scanner_ranking_promts.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scanner_ranking_engine import (
    classify_scanner_group,
    calculate_opportunity_score,
    enrich_scanner_row_with_ranking,
    READY_NOW,
    WATCH_ZONE,
    WAITING_CONFIRMATION,
    BLOCKED,
)


# ---------------------------------------------------------------------------
# Test case 1 — WATCH_ONLY + skip → WATCH_ZONE
# ---------------------------------------------------------------------------


def test_watch_only_decision_not_blocked_by_legacy_skip_action():
    """Decision engine says WATCH_ONLY, gate not blocked — legacy skip
    must NOT push the row into blocked."""
    result = classify_scanner_group(
        decision="WATCH_ONLY",
        scanner_action="skip",
        trade_permission="caution",
        entry_status="waiting_confirmation",
        ready_to_trade=False,
    )
    assert result == WATCH_ZONE, (
        f"Expected WATCH_ZONE but got {result}. "
        f"Decision WATCH_ONLY must win over legacy scanner_action='skip'."
    )


# ---------------------------------------------------------------------------
# Test case 2 — WAITING_CONFIRMATION + skip → WAITING_CONFIRMATION
# ---------------------------------------------------------------------------


def test_waiting_confirmation_decision_not_blocked_by_legacy_skip_action():
    """Decision engine says WAITING_CONFIRMATION — legacy skip must NOT
    push the row into blocked."""
    result = classify_scanner_group(
        decision="WAITING_CONFIRMATION",
        scanner_action="skip",
        trade_permission="caution",
        entry_status="waiting_confirmation",
        ready_to_trade=False,
    )
    assert result == WAITING_CONFIRMATION, (
        f"Expected WAITING_CONFIRMATION but got {result}. "
        f"Decision WAITING_CONFIRMATION must win over legacy scanner_action='skip'."
    )


# ---------------------------------------------------------------------------
# Test case 3 — TRADE_BLOCKED + skip → BLOCKED (gate still wins)
# ---------------------------------------------------------------------------


def test_trade_blocked_decision_still_blocked_even_with_skip():
    """TRADE_BLOCKED from decision engine must remain BLOCKED regardless
    of scanner_action."""
    result = classify_scanner_group(
        decision="TRADE_BLOCKED",
        scanner_action="skip",
        trade_permission="caution",
        entry_status="waiting_confirmation",
    )
    assert result == BLOCKED, (
        f"Expected BLOCKED but got {result}. "
        f"TRADE_BLOCKED decision must always result in BLOCKED."
    )


# ---------------------------------------------------------------------------
# Test case 4 — trade_permission blocked wins over WATCH_ONLY decision
# ---------------------------------------------------------------------------


def test_trade_permission_blocked_still_blocked_even_if_watch_only():
    """trade_permission=blocked is a hard gate — must stay BLOCKED even
    when decision engine says WATCH_ONLY."""
    result = classify_scanner_group(
        decision="WATCH_ONLY",
        scanner_action="skip",
        trade_permission="blocked",
        entry_status="waiting_confirmation",
    )
    assert result == BLOCKED, (
        f"Expected BLOCKED but got {result}. "
        f"trade_permission='blocked' must win over WATCH_ONLY decision."
    )


# ---------------------------------------------------------------------------
# Test case 5 — calculate_opportunity_score with WATCH_ONLY + skip
# ---------------------------------------------------------------------------


def test_opportunity_score_watch_only_skip_is_watch_zone_not_blocked():
    """Row with decision=WATCH_ONLY and legacy scanner_action='skip' must
    be classified as WATCH_ZONE with opportunity_score > 20."""
    row = {
        "final_score": 62,
        "scanner_decision": "WATCH_ONLY",
        "scanner_action": "skip",
        "trade_permission": "caution",
        "entry_status": "waiting_confirmation",
        "price_vs_zone": "in_zone",
        "risk_reward": "1:1.7",
    }
    result = calculate_opportunity_score(row)

    assert result["scanner_group"] == WATCH_ZONE, (
        f"Expected WATCH_ZONE but got {result['scanner_group']}. "
        f"WATCH_ONLY decision must prevent blocked classification."
    )
    assert result["opportunity_score"] > 20, (
        f"Expected opportunity_score > 20 but got {result['opportunity_score']}. "
        f"Non-blocked rows must not be capped at 20."
    )
    # Must NOT contain the blocked group reason code
    assert "SCANNER_RANKING_BLOCKED" not in result["reason_codes"], (
        f"Reason codes must not contain SCANNER_RANKING_BLOCKED: {result['reason_codes']}"
    )


# ---------------------------------------------------------------------------
# Test case 6 — enrich_scanner_row_with_ranking with WATCH_ONLY + skip
# ---------------------------------------------------------------------------


def test_enrich_scanner_row_watch_only_skip_is_watch_zone_not_blocked():
    """enrich_scanner_row_with_ranking must propagate the corrected group
    and must NOT mutate the original row."""
    row = {
        "final_score": 62,
        "scanner_decision": "WATCH_ONLY",
        "scanner_action": "skip",
        "trade_permission": "caution",
        "entry_status": "waiting_confirmation",
        "price_vs_zone": "in_zone",
        "risk_reward": "1:1.7",
    }
    original_keys = set(row.keys())

    enriched = enrich_scanner_row_with_ranking(row)

    # Original row must not be mutated
    assert set(row.keys()) == original_keys, (
        f"Original row was mutated. Original keys: {original_keys}, "
        f"current keys: {set(row.keys())}"
    )

    assert enriched["scanner_group"] == WATCH_ZONE, (
        f"Expected WATCH_ZONE but got {enriched['scanner_group']}. "
        f"WATCH_ONLY decision must prevent blocked classification."
    )
    assert enriched["opportunity_score"] > 20, (
        f"Expected opportunity_score > 20 but got {enriched['opportunity_score']}. "
        f"Non-blocked rows must not be capped at 20."
    )


# ===========================================================================
# Realistic scenario tests — verify calculate_opportunity_score with
# production-like data after classify_scanner_group fix.
# ===========================================================================


# ---------------------------------------------------------------------------
# Scenario A — WATCH_ONLY due to low expected effective R:R
# ---------------------------------------------------------------------------


def test_realistic_scenario_a_watch_only_low_effective_rr():
    """WATCH_ONLY from decision engine (e.g. expected RR too low).
    Legacy scanner_action='skip' must not override to BLOCKED."""
    row = {
        "symbol": "XAU/USD",
        "final_score": 62,
        "scanner_decision": "WATCH_ONLY",
        "scanner_action": "skip",
        "trade_permission": "caution",
        "entry_status": "waiting_confirmation",
        "price_vs_zone": "in_zone",
        "risk_reward": "1:1.7",
        "expected_effective_rr": 0.8,
        "spread_status": "normal",
        "high_impact_event_within_30m": False,
    }
    result = calculate_opportunity_score(row)

    assert result["scanner_group"] == WATCH_ZONE, (
        f"Scenario A: expected WATCH_ZONE but got {result['scanner_group']}"
    )
    assert result["opportunity_score"] > 20, (
        f"Scenario A: expected opportunity_score > 20 but got {result['opportunity_score']}"
    )
    assert "SCANNER_RANKING_BLOCKED" not in result["reason_codes"], (
        f"Scenario A: must not contain SCANNER_RANKING_BLOCKED: {result['reason_codes']}"
    )


# ---------------------------------------------------------------------------
# Scenario B — WAITING_CONFIRMATION due to low score gap
# ---------------------------------------------------------------------------


def test_realistic_scenario_b_waiting_confirmation_low_score_gap():
    """WAITING_CONFIRMATION from decision engine (e.g. score gap too low).
    Legacy scanner_action='skip' must not override to BLOCKED."""
    row = {
        "symbol": "AUD/USD",
        "final_score": 60,
        "scanner_decision": "WAITING_CONFIRMATION",
        "scanner_action": "skip",
        "trade_permission": "caution",
        "entry_status": "waiting_confirmation",
        "price_vs_zone": "near_zone",
        "risk_reward": "1:2.1",
        "score_gap": 5,
        "spread_status": "normal",
    }
    result = calculate_opportunity_score(row)

    assert result["scanner_group"] == WAITING_CONFIRMATION, (
        f"Scenario B: expected WAITING_CONFIRMATION but got {result['scanner_group']}"
    )
    assert result["opportunity_score"] > 20, (
        f"Scenario B: expected opportunity_score > 20 but got {result['opportunity_score']}"
    )


# ---------------------------------------------------------------------------
# Scenario C — TRADE_BLOCKED due to spread abnormal
# ---------------------------------------------------------------------------


def test_realistic_scenario_c_trade_blocked_spread_abnormal():
    """TRADE_BLOCKED from decision engine due to abnormal spread.
    Must be BLOCKED with capped opportunity_score <= 20."""
    row = {
        "symbol": "EUR/USD",
        "final_score": 88,
        "scanner_decision": "TRADE_BLOCKED",
        "scanner_action": "ready",
        "trade_permission": "blocked",
        "entry_status": "confirmed_entry",
        "price_vs_zone": "in_zone",
        "risk_reward": "1:2.4",
        "spread_status": "abnormal",
    }
    result = calculate_opportunity_score(row)

    assert result["scanner_group"] == BLOCKED, (
        f"Scenario C: expected BLOCKED but got {result['scanner_group']}"
    )
    assert result["opportunity_score"] <= 20, (
        f"Scenario C: expected opportunity_score <= 20 but got {result['opportunity_score']}"
    )


# ---------------------------------------------------------------------------
# Scenario D — READY_TO_TRADE not damaged by legacy action
# ---------------------------------------------------------------------------


def test_realistic_scenario_d_ready_to_trade_not_damaged_by_legacy_action():
    """READY_TO_TRADE from decision engine must remain READY_NOW even when
    legacy scanner_action is 'watch'. Opportunity score must exceed final_score
    due to readiness + proximity + RR bonuses."""
    row = {
        "symbol": "GBP/JPY",
        "final_score": 84,
        "scanner_decision": "READY_TO_TRADE",
        "scanner_action": "watch",
        "trade_permission": "allowed",
        "entry_status": "confirmed_entry",
        "ready_to_trade": True,
        "price_vs_zone": "in_zone",
        "risk_reward": "1:2.0",
        "spread_status": "normal",
    }
    result = calculate_opportunity_score(row)

    assert result["scanner_group"] == READY_NOW, (
        f"Scenario D: expected READY_NOW but got {result['scanner_group']}"
    )
    assert result["opportunity_score"] > row["final_score"], (
        f"Scenario D: expected opportunity_score ({result['opportunity_score']}) "
        f"> final_score ({row['final_score']}) due to readiness/proximity/RR bonuses"
    )
