"""Phase 12.11 tests: detect_chased_price in trade_mistake_detector."""

from __future__ import annotations

from core.trade_mistake_detector import detect_chased_price, detect_trade_mistakes


class TestDetectChasedPrice:
    def test_buy_worse_entry_triggers(self):
        trade = {
            "direction": "buy",
            "planned_entry": 1.1000,
            "actual_entry": 1.1020,
        }
        result = detect_chased_price(trade)
        assert result["triggered"] is True
        assert "chased_price" in result["tags"]

    def test_buy_barely_over_no_trigger(self):
        trade = {
            "direction": "buy",
            "planned_entry": 1.1000,
            "actual_entry": 1.1005,
        }
        result = detect_chased_price(trade)
        assert result["triggered"] is False

    def test_buy_better_entry_no_trigger(self):
        trade = {
            "direction": "buy",
            "planned_entry": 1.1000,
            "actual_entry": 1.0990,
        }
        result = detect_chased_price(trade)
        assert result["triggered"] is False

    def test_sell_worse_entry_triggers(self):
        trade = {
            "direction": "sell",
            "planned_entry": 1.1000,
            "actual_entry": 1.0980,
        }
        result = detect_chased_price(trade)
        assert result["triggered"] is True
        assert "chased_price" in result["tags"]

    def test_sell_barely_under_no_trigger(self):
        trade = {
            "direction": "sell",
            "planned_entry": 1.1000,
            "actual_entry": 1.0995,
        }
        result = detect_chased_price(trade)
        assert result["triggered"] is False

    def test_sell_better_entry_no_trigger(self):
        trade = {
            "direction": "sell",
            "planned_entry": 1.1000,
            "actual_entry": 1.1010,
        }
        result = detect_chased_price(trade)
        assert result["triggered"] is False

    def test_missing_direction_no_trigger(self):
        trade = {
            "planned_entry": 1.1000,
            "actual_entry": 1.1020,
        }
        result = detect_chased_price(trade)
        assert result["triggered"] is False

    def test_missing_planned_entry_no_trigger(self):
        trade = {
            "direction": "buy",
            "actual_entry": 1.1020,
        }
        result = detect_chased_price(trade)
        assert result["triggered"] is False

    def test_missing_actual_entry_no_trigger(self):
        trade = {
            "direction": "buy",
            "planned_entry": 1.1000,
        }
        result = detect_chased_price(trade)
        assert result["triggered"] is False

    def test_empty_trade_no_crash(self):
        result = detect_chased_price({})
        assert result["triggered"] is False

    def test_uses_selected_scenario_for_direction(self):
        trade = {
            "selected_scenario": "sell",
            "planned_entry": 1.1000,
            "actual_entry": 1.0980,
        }
        result = detect_chased_price(trade)
        assert result["triggered"] is True

    def test_uses_entry_alias(self):
        trade = {
            "direction": "buy",
            "entry": 1.1000,
            "actual_entry": 1.1020,
        }
        result = detect_chased_price(trade)
        assert result["triggered"] is True

    def test_custom_tolerance(self):
        trade = {
            "direction": "buy",
            "planned_entry": 1.1000,
            "actual_entry": 1.1015,
        }
        settings = {"chased_price_tolerance_pct": 0.20}
        result = detect_chased_price(trade, settings)
        # 1.1015 > 1.1000 * (1 + 0.20/100) = 1.1000 * 1.002 = 1.1022? No.
        # Actually 0.20% = 0.002 as fraction. 1.1000 * 1.002 = 1.1022.
        # 1.1015 < 1.1022, so no trigger.
        assert result["triggered"] is False

    def test_custom_tolerance_triggers(self):
        trade = {
            "direction": "buy",
            "planned_entry": 1.1000,
            "actual_entry": 1.1030,
        }
        settings = {"chased_price_tolerance_pct": 0.10}
        result = detect_chased_price(trade, settings)
        # 1.1030 > 1.1000 * 1.001 = 1.1011 => trigger
        assert result["triggered"] is True

    def test_breakdown_has_required_keys(self):
        trade = {
            "direction": "buy",
            "planned_entry": 1.1000,
            "actual_entry": 1.1020,
        }
        result = detect_chased_price(trade)
        bd = result["breakdown"]["chased_price"]
        assert "direction" in bd
        assert "planned_entry" in bd
        assert "actual_entry" in bd
        assert "tolerance_pct" in bd
        assert "triggered" in bd

    def test_mistake_code_present(self):
        trade = {
            "direction": "buy",
            "planned_entry": 1.1000,
            "actual_entry": 1.1020,
        }
        result = detect_chased_price(trade)
        assert "MISTAKE_CHASED_PRICE" in result["codes"]


class TestDetectChasedPriceIntegrated:
    def test_integrated_detection(self):
        trade = {
            "direction": "buy",
            "planned_entry": 1.1000,
            "actual_entry": 1.1020,
        }
        result = detect_trade_mistakes(trade)
        assert "chased_price" in result["auto_mistake_tags"]
        assert "MISTAKE_CHASED_PRICE" in result["mistake_codes"]

    def test_clean_entry_no_tag(self):
        trade = {
            "direction": "buy",
            "planned_entry": 1.1000,
            "actual_entry": 1.1005,
        }
        result = detect_trade_mistakes(trade)
        assert "chased_price" not in result["auto_mistake_tags"]
