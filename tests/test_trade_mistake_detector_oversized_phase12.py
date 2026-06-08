"""Phase 12.4 tests: detect_oversized_position in trade_mistake_detector."""

from __future__ import annotations

from core.trade_mistake_detector import (
    detect_oversized_position,
    detect_trade_mistakes,
)


class TestDetectOversizedPositionDirect:
    def test_triggers_when_actual_exceeds_planned_by_threshold(self):
        trade = {"planned_lot": 0.10, "actual_lot": 0.13}
        result = detect_oversized_position(trade)
        assert result["triggered"] is True
        assert "oversized_position" in result["tags"]

    def test_no_trigger_when_below_threshold(self):
        trade = {"planned_lot": 0.10, "actual_lot": 0.12}
        result = detect_oversized_position(trade)
        assert result["triggered"] is False

    def test_no_trigger_when_equal(self):
        trade = {"planned_lot": 0.10, "actual_lot": 0.10}
        result = detect_oversized_position(trade)
        assert result["triggered"] is False

    def test_no_trigger_when_actual_lower(self):
        trade = {"planned_lot": 0.10, "actual_lot": 0.08}
        result = detect_oversized_position(trade)
        assert result["triggered"] is False

    def test_no_trigger_when_planned_zero(self):
        trade = {"planned_lot": 0.0, "actual_lot": 0.20}
        result = detect_oversized_position(trade)
        assert result["triggered"] is False

    def test_no_trigger_when_actual_zero(self):
        trade = {"planned_lot": 0.10, "actual_lot": 0.0}
        result = detect_oversized_position(trade)
        assert result["triggered"] is False

    def test_no_trigger_when_missing_fields(self):
        result = detect_oversized_position({})
        assert result["triggered"] is False

    def test_custom_threshold(self):
        trade = {"planned_lot": 0.10, "actual_lot": 0.14}
        settings = {"oversized_lot_multiplier": 1.5}
        result = detect_oversized_position(trade, settings)
        # 0.14 > 0.15? No.
        assert result["triggered"] is False

    def test_custom_threshold_triggers(self):
        trade = {"planned_lot": 0.10, "actual_lot": 0.16}
        settings = {"oversized_lot_multiplier": 1.5}
        result = detect_oversized_position(trade, settings)
        # 0.16 > 0.15? Yes.
        assert result["triggered"] is True

    def test_string_inputs_work(self):
        trade = {"planned_lot": "0.10", "actual_lot": "0.13"}
        result = detect_oversized_position(trade)
        assert result["triggered"] is True

    def test_breakdown_has_required_keys(self):
        trade = {"planned_lot": 0.10, "actual_lot": 0.20}
        result = detect_oversized_position(trade)
        bd = result["breakdown"]["oversized_position"]
        assert "planned_lot" in bd
        assert "actual_lot" in bd
        assert "threshold_multiplier" in bd
        assert "triggered" in bd

    def test_mistake_code_present_when_triggered(self):
        trade = {"planned_lot": 0.10, "actual_lot": 0.20}
        result = detect_oversized_position(trade)
        assert "MISTAKE_OVERSIZED_POSITION" in result["codes"]


class TestDetectOversizedPositionIntegrated:
    def test_full_result_has_auto_mistake_tag(self):
        trade = {"planned_lot": 0.10, "actual_lot": 0.14}
        result = detect_trade_mistakes(trade)
        assert "oversized_position" in result["auto_mistake_tags"]

    def test_full_result_has_mistake_code(self):
        trade = {"planned_lot": 0.10, "actual_lot": 0.14}
        result = detect_trade_mistakes(trade)
        assert "MISTAKE_OVERSIZED_POSITION" in result["mistake_codes"]

    def test_full_result_has_breakdown(self):
        trade = {"planned_lot": 0.10, "actual_lot": 0.14}
        result = detect_trade_mistakes(trade)
        assert "oversized_position" in result["score_breakdown"]

    def test_clean_trade_no_mistakes(self):
        trade = {"planned_lot": 0.10, "actual_lot": 0.10}
        result = detect_trade_mistakes(trade)
        assert result["auto_mistake_tags"] == []
        assert result["mistake_codes"] == []

    def test_none_trade_no_crash(self):
        result = detect_trade_mistakes(None)
        assert isinstance(result, dict)
