"""Phase 12.5 tests: detect_moved_stop_loss in trade_mistake_detector."""

from __future__ import annotations

from core.trade_mistake_detector import (
    detect_moved_stop_loss,
    detect_trade_mistakes,
)


class TestDetectMovedStopLossDirect:
    def test_buy_sl_moved_lower_triggers(self):
        trade = {
            "direction": "buy",
            "planned_sl": 1.0800,
            "actual_sl": 1.0780,
        }
        result = detect_moved_stop_loss(trade)
        assert result["triggered"] is True
        assert "moved_stop_loss" in result["tags"]

    def test_buy_sl_moved_higher_no_trigger(self):
        trade = {
            "direction": "buy",
            "planned_sl": 1.0800,
            "actual_sl": 1.0810,
        }
        result = detect_moved_stop_loss(trade)
        assert result["triggered"] is False

    def test_buy_sl_unchanged_no_trigger(self):
        trade = {
            "direction": "buy",
            "planned_sl": 1.0800,
            "actual_sl": 1.0800,
        }
        result = detect_moved_stop_loss(trade)
        assert result["triggered"] is False

    def test_sell_sl_moved_higher_triggers(self):
        trade = {
            "direction": "sell",
            "planned_sl": 1.0950,
            "actual_sl": 1.0980,
        }
        result = detect_moved_stop_loss(trade)
        assert result["triggered"] is True
        assert "moved_stop_loss" in result["tags"]

    def test_sell_sl_moved_lower_no_trigger(self):
        trade = {
            "direction": "sell",
            "planned_sl": 1.0950,
            "actual_sl": 1.0930,
        }
        result = detect_moved_stop_loss(trade)
        assert result["triggered"] is False

    def test_sell_sl_unchanged_no_trigger(self):
        trade = {
            "direction": "sell",
            "planned_sl": 1.0950,
            "actual_sl": 1.0950,
        }
        result = detect_moved_stop_loss(trade)
        assert result["triggered"] is False

    # ---- direction aliases ----

    def test_buy_uppercase_triggers(self):
        trade = {
            "direction": "BUY",
            "planned_sl": 1.0800,
            "actual_sl": 1.0780,
        }
        result = detect_moved_stop_loss(trade)
        assert result["triggered"] is True

    def test_long_alias_triggers(self):
        trade = {
            "direction": "long",
            "planned_sl": 1.0800,
            "actual_sl": 1.0780,
        }
        result = detect_moved_stop_loss(trade)
        assert result["triggered"] is True

    def test_short_alias_triggers(self):
        trade = {
            "direction": "short",
            "planned_sl": 1.0950,
            "actual_sl": 1.0980,
        }
        result = detect_moved_stop_loss(trade)
        assert result["triggered"] is True

    def test_selected_scenario_field_works(self):
        trade = {
            "selected_scenario": "buy",
            "planned_sl": 1.0800,
            "actual_sl": 1.0780,
        }
        result = detect_moved_stop_loss(trade)
        assert result["triggered"] is True

    # ---- missing data ----

    def test_missing_direction_no_trigger(self):
        trade = {
            "planned_sl": 1.0800,
            "actual_sl": 1.0780,
        }
        result = detect_moved_stop_loss(trade)
        assert result["triggered"] is False

    def test_missing_actual_sl_no_trigger(self):
        trade = {
            "direction": "buy",
            "planned_sl": 1.0800,
        }
        result = detect_moved_stop_loss(trade)
        assert result["triggered"] is False

    def test_missing_planned_sl_no_trigger(self):
        trade = {
            "direction": "buy",
            "actual_sl": 1.0780,
        }
        result = detect_moved_stop_loss(trade)
        assert result["triggered"] is False

    def test_empty_trade_no_crash(self):
        result = detect_moved_stop_loss({})
        assert result["triggered"] is False

    def test_none_values_no_crash(self):
        trade = {
            "direction": None,
            "planned_sl": None,
            "actual_sl": None,
        }
        result = detect_moved_stop_loss(trade)
        assert result["triggered"] is False

    # ---- string inputs ----

    def test_string_values_work(self):
        trade = {
            "direction": "BUY",
            "planned_sl": "1.0800",
            "actual_sl": "1.0780",
        }
        result = detect_moved_stop_loss(trade)
        assert result["triggered"] is True

    # ---- breakdown ----

    def test_breakdown_has_required_keys(self):
        trade = {
            "direction": "buy",
            "planned_sl": 1.0800,
            "actual_sl": 1.0780,
        }
        result = detect_moved_stop_loss(trade)
        bd = result["breakdown"]["moved_stop_loss"]
        assert "direction" in bd
        assert "planned_sl" in bd
        assert "actual_sl" in bd
        assert "triggered" in bd

    def test_mistake_code_present_when_triggered(self):
        trade = {
            "direction": "buy",
            "planned_sl": 1.0800,
            "actual_sl": 1.0780,
        }
        result = detect_moved_stop_loss(trade)
        assert "MISTAKE_MOVED_STOP_LOSS" in result["codes"]

    def test_stop_loss_key_alias_works(self):
        trade = {
            "direction": "buy",
            "stop_loss": 1.0800,
            "actual_sl": 1.0780,
        }
        result = detect_moved_stop_loss(trade)
        assert result["triggered"] is True


class TestDetectMovedStopLossIntegrated:
    def test_full_result_has_auto_mistake_tag(self):
        trade = {
            "direction": "sell",
            "planned_sl": 1.0950,
            "actual_sl": 1.0980,
        }
        result = detect_trade_mistakes(trade)
        assert "moved_stop_loss" in result["auto_mistake_tags"]

    def test_full_result_has_mistake_code(self):
        trade = {
            "direction": "sell",
            "planned_sl": 1.0950,
            "actual_sl": 1.0980,
        }
        result = detect_trade_mistakes(trade)
        assert "MISTAKE_MOVED_STOP_LOSS" in result["mistake_codes"]

    def test_full_result_has_breakdown(self):
        trade = {
            "direction": "sell",
            "planned_sl": 1.0950,
            "actual_sl": 1.0980,
        }
        result = detect_trade_mistakes(trade)
        assert "moved_stop_loss" in result["score_breakdown"]

    def test_clean_trade_no_mistakes(self):
        trade = {
            "direction": "buy",
            "planned_sl": 1.0800,
            "actual_sl": 1.0810,
        }
        result = detect_trade_mistakes(trade)
        assert result["auto_mistake_tags"] == []
