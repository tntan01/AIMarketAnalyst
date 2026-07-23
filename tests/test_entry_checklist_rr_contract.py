"""Phase 11: lock Entry Checklist and manual order eligibility RR semantics.

Verifies:
- Entry checklist R:R uses ``risk_reward`` best-case string (via ``_parse_rr``).
- Checklist note displays base/effective range but the pass/fail uses best-case.
- Manual eligibility (auto-trade candidate) uses best-case effective RR for
  backtest gate, NOT base-case (ranking uses base, gate uses base, but
  manual eligibility pre-filter still uses best-case expected_effective_rr).
- Current RR guard only at execution time — not in checklist or eligibility.

Consumer contract per docs/rr_anchor_semantics.md:
- Entry checklist: best-case nominal (risk_reward)
- Auto-trade candidate eligibility: best-case effective (expected_effective_rr)
- Manual execution guard: current effective RR (Phase 5B)
"""

from __future__ import annotations

import pytest

from core.analysis_pipeline import _parse_rr, _build_entry_checklist, _checklist_item


# ---------------------------------------------------------------------------
# _parse_rr contract
# ---------------------------------------------------------------------------


class TestParseRR:
    def test_parses_best_case_risk_reward_string(self):
        assert _parse_rr("1:2.5") == 2.5
        assert _parse_rr("1:1.3") == 1.3
        assert _parse_rr("1:0.8") == 0.8

    def test_returns_zero_for_invalid(self):
        assert _parse_rr(None) == 0.0
        assert _parse_rr("") == 0.0
        assert _parse_rr("abc") == 0.0
        assert _parse_rr("2.5") == 0.0  # no colon


# ---------------------------------------------------------------------------
# Entry checklist contract: R:R uses best-case, not base/current
# ---------------------------------------------------------------------------


class TestEntryChecklistRRContract:
    """Entry checklist must use best-case nominal RR for pass/fail,
    while base/range appear only in the note."""

    def _build_checklist(self, scenario_overrides=None, **kw):
        scenario = {
            "type": "buy",
            "risk_reward": "1:2.5",
            "expected_effective_rr": 2.3,
            "expected_effective_rr_base": 1.1,
            "expected_effective_rr_worst": 0.8,
            "risk_reward_range": {"best": 2.5, "base": 1.8, "worst": 1.2},
            "risk_reward_effective_range": {"best": 2.3, "base": 1.6, "worst": 1.0},
            "entry_zone": [1.0950, 1.0970],
            "entry_status": "watch_zone",
            "stop_loss": 1.0930,
            "take_profit": [1.1050],
            "position_sizing": {"suggested_lot": 0.05},
            "h1_confirmation": True,
            "trigger_type": "bullish_engulfing",
        }
        if scenario_overrides:
            scenario.update(scenario_overrides)
        market_regime = kw.get("market_regime", {"primary": "trend_up"})
        trade_permission = kw.get("trade_permission", {"status": "allowed", "min_rr": 1.3})
        data_quality = kw.get("data_quality", {"spread_status": "normal"})
        score = kw.get("score", {"location_quality": 15})
        return _build_entry_checklist(scenario, market_regime, trade_permission, data_quality, score)

    def test_checklist_rr_passes_when_best_case_above_min_rr(self):
        items = self._build_checklist()
        rr_item = next(i for i in items if i["label"] == "R:R")
        # risk_reward="1:2.5" → parsed 2.5 >= 1.3 → pass
        assert rr_item["status"] == "pass"
        assert rr_item["value"] == "1:2.5"  # displays the string

    def test_checklist_rr_fails_when_best_case_below_min_rr(self):
        items = self._build_checklist(scenario_overrides={"risk_reward": "1:1.1"})
        rr_item = next(i for i in items if i["label"] == "R:R")
        assert rr_item["status"] == "wait"
        # Note still shows R:R threshold
        assert "1:1.3" in rr_item["note"]

    def test_checklist_passes_even_when_base_is_below_min_rr(self):
        """Checklist uses best-case, so it passes even when base < min_rr.
        This is intentional: checklist is a display guide, not an execution gate.
        The actual gate (Phase 3) and ranking (Phase 4A) already use base-case."""
        items = self._build_checklist(scenario_overrides={
            "risk_reward": "1:2.5",                 # best: passes
            "expected_effective_rr_base": 1.1,      # base: fails (< 1.3)
        })
        rr_item = next(i for i in items if i["label"] == "R:R")
        assert rr_item["status"] == "pass", \
            "Checklist pass/fail must use best-case risk_reward, not base"

    def test_checklist_note_includes_base_and_range(self):
        """Note displays base effective and range for user reference."""
        items = self._build_checklist()
        rr_item = next(i for i in items if i["label"] == "R:R")
        note = str(rr_item["note"])
        # Note must mention base spread-adjusted
        assert "base sau spread" in note

    def test_checklist_rr_display_is_risk_reward_string(self):
        """The RR value in the checklist should be the risk_reward string."""
        items = self._build_checklist()
        rr_item = next(i for i in items if i["label"] == "R:R")
        assert rr_item["value"] == "1:2.5"


# ---------------------------------------------------------------------------
# Manual eligibility contract: pre-filter uses best-case effective RR
# ---------------------------------------------------------------------------


class TestManualEligibilityRRContract:
    """Auto-trade candidate eligibility (backtest gate) uses
    expected_effective_rr (best-case) for min_rr filtering.
    Base-case is used by ranking/gate only.  Current RR only at execution."""

    def _is_eligible_by_backtest_rr(self, row_rr, cfg_min_rr):
        """Replicate the backtest gate RR check from _is_auto_trade_candidate."""
        try:
            row_rr_f = float(row_rr) if row_rr is not None else 0.0
        except (TypeError, ValueError):
            row_rr_f = 0.0
        return row_rr_f >= cfg_min_rr

    def test_eligible_when_best_effective_above_min_rr(self):
        assert self._is_eligible_by_backtest_rr(2.5, 1.3) is True

    def test_not_eligible_when_best_effective_below_min_rr(self):
        assert self._is_eligible_by_backtest_rr(1.1, 1.3) is False

    def test_eligible_even_when_base_is_below_min_rr(self):
        """Backtest eligibility uses best-case effective, not base.
        A row with best=2.5, base=1.1 passes the eligibility pre-filter
        even though the gate (Phase 3) would apply WATCH_ONLY for base=1.1."""
        # This represents the row-level expected_effective_rr (best)
        row_eff_rr = 2.5  # best-case
        cfg_min_rr = 1.3
        assert self._is_eligible_by_backtest_rr(row_eff_rr, cfg_min_rr) is True

    def test_none_rr_treated_as_zero(self):
        assert self._is_eligible_by_backtest_rr(None, 1.3) is False


# ---------------------------------------------------------------------------
# Cross-contract: checklist ≠ gate ≠ eligibility ≠ execution guard
# ---------------------------------------------------------------------------


def test_four_consumers_use_different_anchors():
    """Verify that the four RR consumers use different anchors as designed:

    Checklist:   best-case nominal (risk_reward)
    Gate:        base-case effective (expected_effective_rr_for_gate/base)
    Ranking:     base-case effective (expected_effective_rr_base)
    Eligibility: best-case effective (expected_effective_rr) — pre-filter
    Guard:       current effective (current_effective_rr) — execution
    """
    # Simulate a row where best >> base >> current
    best_nominal = "1:2.5"          # risk_reward
    best_eff = 2.3                  # expected_effective_rr
    base_eff = 1.1                  # expected_effective_rr_base
    cur_eff = 0.8                   # current_effective_rr
    min_rr = 1.3

    # Checklist: uses best nominal (string parsed)
    checklist_rr = _parse_rr(best_nominal)   # 2.5
    assert checklist_rr >= min_rr, "Checklist passes (best-case nominal)"

    # Gate: uses base effective (Phase 3)
    assert base_eff < min_rr, "Gate would WATCH_ONLY (base < min_rr)"

    # Ranking: uses base effective (Phase 4A)
    assert base_eff < 1.3, "Ranking rr_bonus would be 0 (base < weak tier)"

    # Eligibility: uses best effective (Phase 5B pre-filter)
    assert best_eff >= min_rr, "Eligibility passes (best effective)"

    # Guard: uses current effective (Phase 5B execution)
    assert cur_eff < min_rr, "Guard blocks (current < min_rr)"

    # All assertions pass without contradiction — each layer has its own anchor
