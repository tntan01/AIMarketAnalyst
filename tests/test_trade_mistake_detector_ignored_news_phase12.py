"""Phase 12.10 tests: detect_ignored_news in trade_mistake_detector."""

from __future__ import annotations

from core.trade_mistake_detector import (
    detect_ignored_news,
    detect_trade_mistakes,
)


class TestDetectIgnoredNews:
    def test_high_impact_boolean_with_entry_triggers(self):
        trade = {"high_impact_news_within_30m": True, "user_action": "opened"}
        result = detect_ignored_news(trade)
        assert result["triggered"] is True
        assert "ignored_news" in result["tags"]

    def test_high_impact_event_boolean_with_entry_triggers(self):
        trade = {"high_impact_event_within_30m": True, "actual_entry": 1.0850}
        result = detect_ignored_news(trade)
        assert result["triggered"] is True

    def test_news_risk_high_with_entry_triggers(self):
        trade = {"news_risk": "high", "actual_entry": 1.0850}
        result = detect_ignored_news(trade)
        assert result["triggered"] is True

    def test_news_risk_blocked_with_entry_triggers(self):
        trade = {"news_risk": "blocked", "actual_entry": 1.0850}
        result = detect_ignored_news(trade)
        assert result["triggered"] is True

    def test_block_codes_contains_high_impact_news_triggers(self):
        trade = {
            "block_codes": ["SPREAD_ABNORMAL", "HIGH_IMPACT_NEWS_NEARBY"],
            "user_action": "opened",
        }
        result = detect_ignored_news(trade)
        assert result["triggered"] is True

    def test_warning_codes_contains_high_impact_news_triggers(self):
        trade = {
            "warning_codes": ["HIGH_IMPACT_NEWS_NEARBY"],
            "actual_entry": 1.0850,
        }
        result = detect_ignored_news(trade)
        assert result["triggered"] is True

    def test_gate_result_block_codes_triggers(self):
        trade = {
            "gate_result": {"block_codes": ["HIGH_IMPACT_NEWS_NEARBY"]},
            "user_action": "opened",
        }
        result = detect_ignored_news(trade)
        assert result["triggered"] is True

    def test_truthy_string_values_work(self):
        trade = {"high_impact_news_within_30m": "1", "actual_entry": 1.0850}
        result = detect_ignored_news(trade)
        assert result["triggered"] is True

    def test_no_entry_no_trigger(self):
        trade = {"high_impact_news_within_30m": True}
        result = detect_ignored_news(trade)
        assert result["triggered"] is False

    def test_entry_but_no_news_risk_no_trigger(self):
        trade = {"user_action": "opened"}
        result = detect_ignored_news(trade)
        assert result["triggered"] is False

    def test_news_risk_normal_no_trigger(self):
        trade = {"news_risk": "normal", "user_action": "opened"}
        result = detect_ignored_news(trade)
        assert result["triggered"] is False

    def test_breakdown_has_required_keys(self):
        trade = {"high_impact_news_within_30m": True, "user_action": "opened"}
        result = detect_ignored_news(trade)
        bd = result["breakdown"]["ignored_news"]
        assert "has_real_entry" in bd
        assert "news_risk_detected" in bd
        assert "triggered" in bd
        assert bd["has_real_entry"] is True
        assert bd["news_risk_detected"] is True

    def test_mistake_code_present(self):
        trade = {"high_impact_news_within_30m": True, "user_action": "opened"}
        result = detect_ignored_news(trade)
        assert "MISTAKE_IGNORED_NEWS" in result["codes"]


class TestDetectIgnoredNewsIntegrated:
    def test_integrated_detection(self):
        trade = {"high_impact_news_within_30m": True, "actual_entry": 1.0850}
        result = detect_trade_mistakes(trade)
        assert "ignored_news" in result["auto_mistake_tags"]
        assert "MISTAKE_IGNORED_NEWS" in result["mistake_codes"]

    def test_no_news_risk_clean(self):
        trade = {"user_action": "opened", "actual_entry": 1.0850}
        result = detect_trade_mistakes(trade)
        assert "ignored_news" not in result["auto_mistake_tags"]
