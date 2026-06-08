"""Phase 12.9 tests: detect_ignored_m15 in trade_mistake_detector."""

from __future__ import annotations

from core.trade_mistake_detector import (
    detect_ignored_m15,
    detect_trade_mistakes,
    _has_real_entry,
)


class TestHasRealEntry:
    def test_actual_entry_positive_is_entry(self):
        assert _has_real_entry({"actual_entry": 1.0850}) is True

    def test_actual_entry_string_works(self):
        assert _has_real_entry({"actual_entry": "1.0850"}) is True

    def test_actual_entry_zero_is_not_entry(self):
        assert _has_real_entry({"actual_entry": 0.0}) is False

    def test_opened_at_exists_is_entry(self):
        assert _has_real_entry({"opened_at": "2026-06-04T09:03:00Z"}) is True

    def test_user_action_opened_is_entry(self):
        assert _has_real_entry({"user_action": "opened"}) is True

    def test_user_action_vào_lệnh_is_entry(self):
        assert _has_real_entry({"user_action": "vào lệnh"}) is True

    def test_action_field_works(self):
        assert _has_real_entry({"action": "entered"}) is True

    def test_order_status_filled_is_entry(self):
        assert _has_real_entry({"order_status": "filled"}) is True

    def test_no_signs_is_not_entry(self):
        assert _has_real_entry({}) is False

    def test_none_does_not_crash(self):
        assert _has_real_entry(None) is False


class TestDetectIgnoredM15:
    def test_m15_none_with_entry_triggers(self):
        trade = {"m15_quality": "none", "actual_entry": 1.0850}
        result = detect_ignored_m15(trade)
        assert result["triggered"] is True
        assert "ignored_m15" in result["tags"]

    def test_entry_status_waiting_with_entry_triggers(self):
        trade = {"entry_status": "waiting_confirmation", "user_action": "opened"}
        result = detect_ignored_m15(trade)
        assert result["triggered"] is True

    def test_entry_status_watch_zone_with_entry_triggers(self):
        trade = {"entry_status": "watch_zone", "user_action": "opened"}
        result = detect_ignored_m15(trade)
        assert result["triggered"] is True

    def test_m15_strict_no_trigger(self):
        trade = {"m15_quality": "strict", "actual_entry": 1.0850}
        result = detect_ignored_m15(trade)
        assert result["triggered"] is False

    def test_entry_status_confirmed_no_trigger(self):
        trade = {"entry_status": "confirmed_entry", "actual_entry": 1.0850}
        result = detect_ignored_m15(trade)
        assert result["triggered"] is False

    def test_strict_overrides_entry_status(self):
        trade = {
            "m15_quality": "strict",
            "entry_status": "waiting_confirmation",
            "actual_entry": 1.0850,
        }
        result = detect_ignored_m15(trade)
        assert result["triggered"] is False

    def test_confirmed_entry_overrides_m15_none(self):
        trade = {
            "m15_quality": "none",
            "entry_status": "confirmed_entry",
            "actual_entry": 1.0850,
        }
        result = detect_ignored_m15(trade)
        assert result["triggered"] is False

    def test_m15_none_but_no_entry_no_trigger(self):
        trade = {"m15_quality": "none"}
        result = detect_ignored_m15(trade)
        assert result["triggered"] is False

    def test_waiting_but_no_entry_no_trigger(self):
        trade = {"entry_status": "waiting_confirmation"}
        result = detect_ignored_m15(trade)
        assert result["triggered"] is False

    def test_breakdown_has_required_keys(self):
        trade = {"m15_quality": "none", "actual_entry": 1.0850}
        result = detect_ignored_m15(trade)
        bd = result["breakdown"]["ignored_m15"]
        assert "m15_quality" in bd
        assert "entry_status" in bd
        assert "has_real_entry" in bd
        assert "triggered" in bd

    def test_mistake_code_present(self):
        trade = {"m15_quality": "none", "actual_entry": 1.0850}
        result = detect_ignored_m15(trade)
        assert "MISTAKE_IGNORED_M15" in result["codes"]


class TestDetectIgnoredM15Integrated:
    def test_ignored_m15_in_full_result(self):
        trade = {"m15_quality": "none", "actual_entry": 1.0850}
        result = detect_trade_mistakes(trade)
        assert "ignored_m15" in result["auto_mistake_tags"]
        assert "MISTAKE_IGNORED_M15" in result["mistake_codes"]

    def test_clean_m15_no_tag(self):
        trade = {"m15_quality": "strict", "entry_status": "confirmed_entry", "actual_entry": 1.0850}
        result = detect_trade_mistakes(trade)
        assert "ignored_m15" not in result["auto_mistake_tags"]
