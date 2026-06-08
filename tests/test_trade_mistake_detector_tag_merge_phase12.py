"""Phase 12.14 tests: manual tag merge in trade_mistake_detector output."""

from __future__ import annotations

from core.trade_mistake_detector import detect_trade_mistakes


class TestManualTagMerge:
    def test_manual_tags_from_json_list(self):
        trade = {
            "manual_mistake_tags": '["ignored_m15", "oversized_position"]',
            "actual_entry": 1.0850,
            "m15_quality": "strict",
            "planned_lot": 0.10,
            "actual_lot": 0.10,
        }
        result = detect_trade_mistakes(trade)
        assert result["manual_mistake_tags"] == ["ignored_m15", "oversized_position"]

    def test_manual_tags_from_comma_string(self):
        trade = {
            "manual_mistake_tags": "ignored_m15, oversized_position",
        }
        result = detect_trade_mistakes(trade)
        assert "ignored_m15" in result["manual_mistake_tags"]
        assert "oversized_position" in result["manual_mistake_tags"]

    def test_manual_tags_from_mistake_tags_key(self):
        trade = {
            "mistake_tags": "chased_price, moved_stop_loss",
        }
        result = detect_trade_mistakes(trade)
        assert result["manual_mistake_tags"] == ["chased_price", "moved_stop_loss"]

    def test_manual_tags_from_user_mistake_tags(self):
        trade = {
            "user_mistake_tags": "revenge_trade_warning",
        }
        result = detect_trade_mistakes(trade)
        assert "revenge_trade_warning" in result["manual_mistake_tags"]

    def test_no_manual_tags_result_is_empty(self):
        trade = {"symbol": "EUR/USD"}
        result = detect_trade_mistakes(trade)
        assert result["manual_mistake_tags"] == []

    def test_all_mistake_tags_contains_manual(self):
        trade = {
            "manual_mistake_tags": '["ignored_m15", "chased_price"]',
        }
        result = detect_trade_mistakes(trade)
        assert "ignored_m15" in result["all_mistake_tags"]
        assert "chased_price" in result["all_mistake_tags"]

    def test_all_mistake_tags_no_duplicates_when_overlap(self):
        trade = {
            "manual_mistake_tags": '["oversized_position", "ignored_m15"]',
            "planned_lot": 0.10,
            "actual_lot": 0.20,
            "direction": "buy",
            "planned_sl": 1.0800,
            "actual_sl": 1.0780,
            "m15_quality": "none",
            "actual_entry": 1.0850,
        }
        result = detect_trade_mistakes(trade)
        # auto detects: oversized, moved_sl, ignored_m15
        assert "oversized_position" in result["auto_mistake_tags"]
        # manual has: oversized_position, ignored_m15 (overlap with auto)
        assert "oversized_position" in result["manual_mistake_tags"]
        assert "ignored_m15" in result["manual_mistake_tags"]
        # all_mistake_tags should not have duplicates
        all_tags = result["all_mistake_tags"]
        assert len(all_tags) == len(set(all_tags))
        assert "oversized_position" in all_tags
        assert "ignored_m15" in all_tags
        assert "moved_stop_loss" in all_tags
        # no duplicate
        assert all_tags.count("oversized_position") == 1

    def test_auto_and_manual_separate(self):
        trade = {
            "manual_mistake_tags": '["ignored_news"]',
            "planned_lot": 0.10,
            "actual_lot": 0.20,
        }
        result = detect_trade_mistakes(trade)
        # auto detects oversized
        assert "oversized_position" in result["auto_mistake_tags"]
        assert "ignored_news" not in result["auto_mistake_tags"]
        # manual preserved
        assert "ignored_news" in result["manual_mistake_tags"]
        # both in all
        assert "oversized_position" in result["all_mistake_tags"]
        assert "ignored_news" in result["all_mistake_tags"]

    def test_none_trade_has_empty_tags(self):
        result = detect_trade_mistakes(None)
        assert result["manual_mistake_tags"] == []
        assert result["all_mistake_tags"] == []

    def test_manual_tags_not_in_mistake_codes(self):
        trade = {
            "manual_mistake_tags": '["entered_too_early"]',
        }
        result = detect_trade_mistakes(trade)
        # manual tags do NOT auto-create mistake_codes
        assert "MISTAKE_ENTERED_TOO_EARLY" not in result["mistake_codes"]
        assert result["manual_mistake_tags"] == ["entered_too_early"]
