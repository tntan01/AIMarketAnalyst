"""Phase 8+9: lock UI Scanner table / order dialog RR semantics.

Tests the display contract at helper/model level (no QWidget instantiation
needed for most tests).  Verifies:
- Scanner table main column shows best-case RR, never base-case.
- Order dialog R:R text/tooltip/note use correct anchors.
- Color coding thresholds match _RR_STRONG / _RR_WEAK.

Phase 9: uses production helpers from ``ui.scanner_rr_formatters`` instead of
replicating formatting logic in test helpers.
"""

from __future__ import annotations

import pytest

import ui.screens.scanner_screen as scanner_screen_module
from ui.screens.scanner_screen import ScannerTableModel
from ui.theme import DARK_PALETTE
from ui.scanner_rr_formatters import (
    format_order_rr_text,
    format_order_rr_tooltip,
    format_order_entry_tooltip,
    enrich_order_note_with_current_rr,
)


def test_scanner_screen_imports_order_dialog_formatters():
    """The order dialog must resolve its production formatter dependencies."""
    assert scanner_screen_module.format_order_entry_tooltip is format_order_entry_tooltip
    assert scanner_screen_module.format_order_rr_text is format_order_rr_text
    assert scanner_screen_module.format_order_rr_tooltip is format_order_rr_tooltip
    assert (
        scanner_screen_module.enrich_order_note_with_current_rr
        is enrich_order_note_with_current_rr
    )


# ---------------------------------------------------------------------------
# Scanner table model — display contract
# ---------------------------------------------------------------------------


class TestScannerTableRRDisplay:
    """Scanner table column 'R:R thuc' (expected_effective_rr) must display
    best-case value, never base-case.  Color coding is also best-case."""

    def _make_model(self) -> ScannerTableModel:
        return ScannerTableModel()

    def test_expected_effective_rr_displays_best_case_not_base(self):
        model = self._make_model()
        row = {
            "expected_effective_rr": 2.5,       # best-case
            "expected_effective_rr_base": 1.1,  # base-case (much lower)
            "analysis_result": {
                "scenarios": [{"type": "buy", "entry_zone_source": "smc"}],
            },
        }
        model.rows = [row]

        display = model._display_value("expected_effective_rr", 2.5, row)
        assert display == "2.5", \
            f"Main column must show best-case 2.5, not base-case 1.1, got: {display}"

    def test_expected_effective_rr_null_displays_dash(self):
        model = self._make_model()
        row = {
            "expected_effective_rr": None,
            "analysis_result": {
                "scenarios": [{"type": "buy", "entry_zone_source": "smc"}],
            },
        }

        display = model._display_value("expected_effective_rr", None, row)
        assert display == "-"

    def test_foreground_color_uses_best_case_thresholds(self):
        """Color coding: >=2.0 green, >=1.3 orange, <1.3 red.  Uses best-case."""
        model = self._make_model()

        # Strong: best=2.5 → green
        green = model._foreground({"expected_effective_rr": 2.5}, "expected_effective_rr")
        assert green is not None
        assert green.name() == DARK_PALETTE.success

        # Weak-but-ok: best=1.5 → orange
        orange = model._foreground({"expected_effective_rr": 1.5}, "expected_effective_rr")
        assert orange is not None
        assert orange.name() == DARK_PALETTE.warning

        # Too low: best=1.0 → red
        red = model._foreground({"expected_effective_rr": 1.0}, "expected_effective_rr")
        assert red is not None
        assert red.name() == DARK_PALETTE.danger

        # Base low but best high → should still be green (uses best-case)
        green2 = model._foreground(
            {"expected_effective_rr": 2.5, "expected_effective_rr_base": 1.1},
            "expected_effective_rr",
        )
        assert green2 is not None
        assert green2.name() == "#10b981", \
            "Color must use best-case (2.5), not base-case (1.1)"

    def test_fallback_row_hides_rr_display(self):
        """Rows with no real plan (fallback) show '--' for RR-related columns."""
        model = self._make_model()
        # A fallback row has no real trade plan
        fallback_row = {
            "expected_effective_rr": 2.0,
            "analysis_result": {
                "scenarios": [
                    {"type": "buy", "entry_zone_source": "fallback"},
                ],
            },
        }
        # The _display_value checks _has_real_plan.  A row with only fallback
        # scenarios should show "--" for expected_effective_rr.
        display = model._display_value("expected_effective_rr", 2.0, fallback_row)
        assert display == "--", \
            f"Fallback row must show '--' for expected_effective_rr, got: {display}"

    def test_none_row_hides_rr_display(self):
        """Rows with zone_origin_class 'none' must show '--' for RR/price."""
        model = self._make_model()
        none_row = {
            "expected_effective_rr": 2.5,
            "zone_origin_class": "none",
        }
        display = model._display_value("expected_effective_rr", 2.5, none_row)
        assert display == "--", \
            f"None row must show '--' for expected_effective_rr, got: {display}"

    def test_none_row_missing_rr_shows_dash(self):
        """None row with missing RR still shows '--' (not '-')."""
        model = self._make_model()
        none_row = {
            "zone_origin_class": "none",
        }
        display = model._display_value("expected_effective_rr", None, none_row)
        assert display == "--", \
            f"None row with missing RR must show '--', got: {display}"

    def test_smc_row_shows_rr_value(self):
        """SMC rows show real RR value, not hidden."""
        model = self._make_model()
        smc_row = {
            "expected_effective_rr": 2.3,
            "zone_origin_class": "smc",
        }
        display = model._display_value("expected_effective_rr", 2.3, smc_row)
        assert display == "2.3", \
            f"SMC row must show real RR value, got: {display}"

    def test_technical_row_shows_rr_value(self):
        """Technical rows show real RR value, not hidden."""
        model = self._make_model()
        tech_row = {
            "expected_effective_rr": 1.8,
            "zone_origin_class": "technical",
        }
        display = model._display_value("expected_effective_rr", 1.8, tech_row)
        assert display == "1.8", \
            f"Technical row must show real RR value, got: {display}"

    def test_zone_origin_display_mapping(self):
        model = self._make_model()
        assert model._display_value("zone_origin_class", "smc", {}) == "SMC thật"
        assert model._display_value("zone_origin_class", "technical", {}) == "Technical"
        assert model._display_value("zone_origin_class", "fallback", {}) == "Fallback"
        assert model._display_value("zone_origin_class", "none", {}) == "--"
        assert model._display_value("zone_origin_class", None, {}) == "--"
        assert model._display_value("zone_origin_class", "bogus", {}) == "--"

    def test_zone_origin_foreground_colors(self):
        model = self._make_model()
        smc_color = model._foreground({"zone_origin_class": "smc"}, "zone_origin_class")
        assert smc_color is not None
        assert smc_color.name() == DARK_PALETTE.success

        tech_color = model._foreground({"zone_origin_class": "technical"}, "zone_origin_class")
        assert tech_color is not None
        assert tech_color.name() == DARK_PALETTE.warning

        fallback_color = model._foreground({"zone_origin_class": "fallback"}, "zone_origin_class")
        assert fallback_color is not None
        assert fallback_color.name() == DARK_PALETTE.text_muted

        none_color = model._foreground({"zone_origin_class": "none"}, "zone_origin_class")
        assert none_color is not None
        assert none_color.name() == DARK_PALETTE.text_subtle

    def test_has_real_plan_all_classes(self):
        model = self._make_model()
        assert model._has_real_plan({"zone_origin_class": "smc"}) is True
        assert model._has_real_plan({"zone_origin_class": "technical"}) is True
        assert model._has_real_plan({"zone_origin_class": "fallback"}) is False
        assert model._has_real_plan({"zone_origin_class": "none"}) is False
        assert model._has_real_plan(None) is False
        assert model._has_real_plan({}) is False

    def test_is_fallback_row_all_classes(self):
        model = self._make_model()
        assert model._is_fallback_row({"zone_origin_class": "smc"}) is False
        assert model._is_fallback_row({"zone_origin_class": "technical"}) is False
        assert model._is_fallback_row({"zone_origin_class": "fallback"}) is True
        assert model._is_fallback_row({"zone_origin_class": "none"}) is False
        assert model._is_fallback_row(None) is False

    def test_entry_zone_display_format(self):
        model = self._make_model()
        assert model._display_value("entry_zone", [1.09700, 1.09900], {}) == "1.09700–1.09900"
        assert model._display_value("entry_zone", None, {}) == "--"

    def test_stop_loss_display_format(self):
        model = self._make_model()
        assert model._display_value("stop_loss", 1.09400, {}) == "1.09400"
        assert model._display_value("stop_loss", None, {}) == "--"

    def test_take_profit_display_format(self):
        model = self._make_model()
        assert model._display_value("take_profit", [1.10500], {}) == "1.10500"
        assert model._display_value("take_profit", [1.10500, 1.11000], {}) == "1.10500"
        assert model._display_value("take_profit", None, {}) == "--"


# ---------------------------------------------------------------------------
# Order dialog — R:R column, tooltip, entry tooltip, note enrichment
# (replicates Phase 5C formatting logic at helper level)
# ---------------------------------------------------------------------------


class TestOrderDialogRRContract:
    """Lock the order dialog contract using production formatters (Phase 9)."""

    # ── R:R column text ────────────────────────────────────────────────

    def test_main_text_is_best_case_not_base(self):
        order = {
            "risk_reward": "1:2.5",
            "risk_reward_range": {"best": 2.5, "base": 1.8, "worst": 1.2},
        }
        text = format_order_rr_text(order)
        assert "2.5" in text
        assert "1.2" in text
        assert "1.8" not in text, "Main text must not show base RR"

    def test_single_best_no_range(self):
        assert format_order_rr_text({"risk_reward": "1:1.8"}) == "1:1.8"

    def test_no_rr_data(self):
        assert format_order_rr_text({}) == "--"

    # ── R:R tooltip ────────────────────────────────────────────────────

    def test_tooltip_has_best_base_current(self):
        order = {
            "risk_reward": "1:2.5",
            "risk_reward_range": {"best": 2.5, "base": 1.8, "worst": 1.2},
            "expected_effective_rr_base": 1.8,
            "current_effective_rr": 1.75,
            "current_entry_price": 1.0985,
            "current_price_in_entry_zone": True,
        }
        tip = format_order_rr_tooltip(order)
        assert "Best: 2.5 (1.2–2.5)" in tip
        assert "Base: 1.8" in tip
        assert "Current @ 1.09850: 1.75 in zone" in tip

    def test_tooltip_without_current(self):
        order = {"risk_reward": "1:2.0", "risk_reward_range": {"best": 2.0, "base": 1.5, "worst": 1.0}}
        tip = format_order_rr_tooltip(order)
        assert "Current" not in tip
        assert "Best" in tip
        assert "Base: 1.5" in tip

    # ── Entry tooltip ──────────────────────────────────────────────────

    def test_entry_tooltip_in_zone(self):
        order = {
            "entry_zone": [1.0970, 1.0990],
            "current_entry_price": 1.0985,
            "current_price_in_entry_zone": True,
        }
        tip = format_order_entry_tooltip(order)
        assert "Execution: [1.09700 - 1.09900]" in tip
        assert "Live: 1.09850 (in zone)" in tip

    def test_entry_tooltip_out_of_zone(self):
        order = {
            "entry_zone": [1.0970, 1.0990],
            "current_entry_price": 1.1010,
            "current_price_in_entry_zone": False,
        }
        tip = format_order_entry_tooltip(order)
        assert "Live: 1.10100 (out of zone)" in tip

    # ── Note column enrichment ─────────────────────────────────────────

    def test_note_enrichment_in_zone(self):
        order = {
            "note": "Sẵn sàng",
            "current_effective_rr": 1.75,
            "current_entry_price": 1.0985,
            "current_price_in_entry_zone": True,
        }
        note = enrich_order_note_with_current_rr(order)
        assert "Live 1.09850 RR=1.75 [in zone]" in note

    def test_note_no_current_rr(self):
        assert enrich_order_note_with_current_rr({"note": "Sẵn sàng"}) == "Sẵn sàng"

    def test_note_dash_fallback(self):
        order = {
            "note": "--",
            "current_effective_rr": 2.1,
            "current_entry_price": 1.0970,
            "current_price_in_entry_zone": True,
        }
        note = enrich_order_note_with_current_rr(order)
        assert note == "Live 1.09700 RR=2.10 [in zone]"


# ---------------------------------------------------------------------------
# Cross-check: scanner model uses best-case, order dialog uses best range
# ---------------------------------------------------------------------------


def test_scanner_main_column_and_order_dialog_use_different_formats():
    """Scanner column shows '2.5', order dialog shows '2.5 (1.2-2.5)'.
    Both are best-case anchored — just formatted differently."""
    row_for_scanner = {
        "expected_effective_rr": 2.5,
        "analysis_result": {
            "scenarios": [{"type": "buy", "entry_zone_source": "smc"}],
        },
    }
    order_for_dialog = {
        "risk_reward": "1:2.5",
        "risk_reward_range": {"best": 2.5, "base": 1.8, "worst": 1.2},
    }

    # Scanner: just the number
    model = ScannerTableModel()
    model.rows = [row_for_scanner]
    scanner_display = model._display_value("expected_effective_rr", 2.5, row_for_scanner)
    assert scanner_display == "2.5"

    # Order dialog: best (worst–best) — use production formatter
    dialog_display = format_order_rr_text(order_for_dialog)
    assert "2.5 (1.2–2.5)" in dialog_display

    # Both use best-case — just different presentation
    assert "2.5" in scanner_display
    assert "2.5" in dialog_display
