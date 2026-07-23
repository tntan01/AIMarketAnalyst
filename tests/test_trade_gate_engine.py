"""Tests for Phase 3: trade gate ExpectedRR uses base-case effective RR.

Verifies:
- Base RR passes gate when >= min_rr.
- Base RR fails gate (WATCH_ONLY) even when best-case passes.
- Missing base → fallback to old expected_effective_rr.
- Gate context carries all 3 new fields.
"""

from __future__ import annotations

from typing import Any

import pytest

from core.trade_gate_engine import check_trade_gates
from core.reason_codes import EXPECTED_RR_TOO_LOW


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_context(**overrides) -> dict[str, Any]:
    """Minimal valid gate context that passes all other gates."""
    ctx: dict[str, Any] = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "data_quality_warning": False,
        "high_impact_event_within_30m": False,
        "m15_quality": "strict",
        "score_gap": 20,
        "min_buy_sell_score_gap": 10,
        "zone_broken": False,
        "daily_loss_limit_reached": False,
        "weekly_loss_limit_reached": False,
    }
    ctx.update(overrides)
    return ctx


# ---------------------------------------------------------------------------
# Tests: base RR gate behavior
# ---------------------------------------------------------------------------


class TestBaseRRPassesGate:
    """When base RR >= min_rr, gate should not produce EXPECTED_RR_TOO_LOW."""

    def test_base_rr_above_threshold_no_warning(self):
        ctx = _base_context(
            expected_effective_rr=3.0,            # best-case
            expected_effective_rr_base=2.2,       # base (midpoint)
            expected_effective_rr_for_gate=2.2,
            expected_effective_rr_source="base",
            min_expected_effective_rr=1.3,
            risk_reward="1:3.0",
        )
        result = check_trade_gates(ctx)
        assert result["allowed"] is True
        assert EXPECTED_RR_TOO_LOW not in result["warning_codes"]

    def test_base_rr_exactly_at_threshold_no_warning(self):
        ctx = _base_context(
            expected_effective_rr=2.0,
            expected_effective_rr_base=1.3,
            expected_effective_rr_for_gate=1.3,
            expected_effective_rr_source="base",
            min_expected_effective_rr=1.3,
        )
        result = check_trade_gates(ctx)
        assert EXPECTED_RR_TOO_LOW not in result["warning_codes"]


class TestBaseRRFailsGate:
    """Base RR < min_rr → WATCH_ONLY even if best-case passes."""

    def test_base_rr_below_threshold_adds_warning(self):
        ctx = _base_context(
            expected_effective_rr=2.5,            # best-case: passes
            expected_effective_rr_base=1.1,       # base: fails (< 1.3)
            expected_effective_rr_for_gate=1.1,
            expected_effective_rr_source="base",
            min_expected_effective_rr=1.3,
            risk_reward="1:2.5",
        )
        result = check_trade_gates(ctx)
        assert EXPECTED_RR_TOO_LOW in result["warning_codes"]
        assert result["decision_cap"] == "WATCH_ONLY"

    def test_base_rr_below_threshold_reason_mentions_base(self):
        ctx = _base_context(
            expected_effective_rr=2.5,
            expected_effective_rr_base=1.1,
            expected_effective_rr_for_gate=1.1,
            expected_effective_rr_source="base",
            min_expected_effective_rr=1.3,
            risk_reward="1:2.5",
        )
        result = check_trade_gates(ctx)
        reasons = " ".join(result["reasons"])
        assert "R:R base sau spread" in reasons, \
            f"Reason should mention 'R:R base sau spread', got: {reasons}"


class TestFallbackToBestCase:
    """When base is missing, fall back to old best-case effective RR."""

    def test_missing_base_uses_best_case(self):
        ctx = _base_context(
            expected_effective_rr=1.8,            # best-case only
            expected_effective_rr_base=None,
            expected_effective_rr_for_gate=1.8,   # fallback
            expected_effective_rr_source="best_case_fallback",
            min_expected_effective_rr=1.3,
            risk_reward="1:1.8",
        )
        result = check_trade_gates(ctx)
        assert EXPECTED_RR_TOO_LOW not in result["warning_codes"]

    def test_missing_both_for_gate_and_best_falls_back_to_best(self):
        """When expected_effective_rr_for_gate is None but expected_effective_rr exists."""
        ctx = _base_context(
            expected_effective_rr=1.6,
            expected_effective_rr_base=None,
            expected_effective_rr_for_gate=None,
            expected_effective_rr_source="none",
            min_expected_effective_rr=1.3,
        )
        result = check_trade_gates(ctx)
        # Should fall back to expected_effective_rr=1.6 → passes
        assert EXPECTED_RR_TOO_LOW not in result["warning_codes"]

    def test_missing_both_rr_is_none_triggers_watch_only(self):
        """When both for_gate and best are None → WATCH_ONLY."""
        ctx = _base_context(
            expected_effective_rr=None,
            expected_effective_rr_base=None,
            expected_effective_rr_for_gate=None,
            expected_effective_rr_source="none",
            min_expected_effective_rr=1.3,
        )
        result = check_trade_gates(ctx)
        assert result["decision_cap"] == "WATCH_ONLY"

    def test_fallback_reason_uses_old_label(self):
        """When source is best_case_fallback, reason says 'R:R kỳ vọng sau spread'."""
        ctx = _base_context(
            expected_effective_rr=1.0,
            expected_effective_rr_base=None,
            expected_effective_rr_for_gate=1.0,
            expected_effective_rr_source="best_case_fallback",
            min_expected_effective_rr=1.3,
            risk_reward="1:1.0",
        )
        result = check_trade_gates(ctx)
        reasons = " ".join(result["reasons"])
        assert "R:R kỳ vọng sau spread" in reasons


class TestGateContextFields:
    """New fields are properly passed through the gate context."""

    def test_context_with_base_rr_fields(self):
        ctx = _base_context(
            expected_effective_rr=2.5,
            expected_effective_rr_base=1.8,
            expected_effective_rr_for_gate=1.8,
            expected_effective_rr_source="base",
            min_expected_effective_rr=1.3,
        )
        result = check_trade_gates(ctx)
        # Gate should not modify these context fields
        assert result["allowed"] is True
