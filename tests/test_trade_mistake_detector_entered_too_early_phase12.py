"""Phase 12.12 tests: detect_entered_too_early in trade_mistake_detector."""

from __future__ import annotations

from core.trade_mistake_detector import detect_entered_too_early, detect_trade_mistakes


class TestDetectEnteredTooEarly:
    def test_waiting_confirmation_with_entry_triggers(self):
        trade = {
            "entry_status": "waiting_confirmation",
            "user_action": "opened",
        }
        result = detect_entered_too_early(trade)
        assert result["triggered"] is True
        assert "entered_too_early" in result["tags"]

    def test_watch_zone_with_entry_triggers(self):
        trade = {
            "entry_status": "watch_zone",
            "actual_entry": 1.0850,
        }
        result = detect_entered_too_early(trade)
        assert result["triggered"] is True

    def test_not_in_entry_zone_triggers(self):
        trade = {
            "in_entry_zone": False,
            "user_action": "opened",
        }
        result = detect_entered_too_early(trade)
        assert result["triggered"] is True

    def test_price_in_entry_zone_false_triggers(self):
        trade = {
            "price_in_entry_zone": False,
            "actual_entry": 1.0850,
        }
        result = detect_entered_too_early(trade)
        assert result["triggered"] is True

    def test_confirmed_entry_no_trigger(self):
        trade = {
            "entry_status": "confirmed_entry",
            "in_entry_zone": True,
            "user_action": "opened",
        }
        result = detect_entered_too_early(trade)
        assert result["triggered"] is False

    def test_in_zone_true_no_trigger(self):
        trade = {
            "in_entry_zone": True,
            "user_action": "opened",
        }
        result = detect_entered_too_early(trade)
        assert result["triggered"] is False

    def test_no_entry_signs_no_trigger(self):
        trade = {"entry_status": "waiting_confirmation"}
        result = detect_entered_too_early(trade)
        assert result["triggered"] is False

    def test_no_data_no_trigger(self):
        result = detect_entered_too_early({})
        assert result["triggered"] is False

    def test_breakdown_keys(self):
        trade = {"entry_status": "watch_zone", "user_action": "opened"}
        result = detect_entered_too_early(trade)
        bd = result["breakdown"]["entered_too_early"]
        assert "has_real_entry" in bd
        assert "entry_status" in bd
        assert "in_entry_zone" in bd
        assert "triggered" in bd

    def test_mistake_code_present(self):
        trade = {"entry_status": "waiting_confirmation", "user_action": "opened"}
        result = detect_entered_too_early(trade)
        assert "MISTAKE_ENTERED_TOO_EARLY" in result["codes"]


class TestDetectEnteredTooEarlyIntegrated:
    def test_integrated_detection(self):
        trade = {"entry_status": "waiting_confirmation", "user_action": "opened"}
        result = detect_trade_mistakes(trade)
        assert "entered_too_early" in result["auto_mistake_tags"]
        assert "MISTAKE_ENTERED_TOO_EARLY" in result["mistake_codes"]

    def test_confirmed_clean(self):
        trade = {
            "entry_status": "confirmed_entry",
            "in_entry_zone": True,
            "user_action": "opened",
        }
        result = detect_trade_mistakes(trade)
        assert "entered_too_early" not in result["auto_mistake_tags"]
