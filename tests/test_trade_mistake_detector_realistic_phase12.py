"""Phase 12.18: realistic integration tests for trade_mistake_detector."""

from __future__ import annotations

from core.trade_mistake_detector import detect_trade_mistakes


class TestBadTradeManyMistakes:
    def test_all_nine_mistakes_detected(self):
        trade = {
            "symbol": "EURUSD",
            "direction": "buy",
            "planned_lot": 0.10,
            "actual_lot": 0.20,
            "planned_sl": 1.0800,
            "actual_sl": 1.0780,
            "planned_entry": 1.0850,
            "actual_entry": 1.0880,
            "opened_at": "2026-06-04T09:03:00Z",
            "entry_status": "waiting_confirmation",
            "m15_quality": "none",
            "high_impact_news_within_30m": True,
            "closed_at": "2026-06-04T09:25:00Z",
            "result_r": 0.25,
            "risk_reward": "1:2.0",
            "exit_reason": "manual_close",
        }
        previous = [
            {
                "symbol": "GBPJPY",
                "result_r": -1.0,
                "result_pct": -1.2,
                "closed_at": "2026-06-04T09:00:00Z",
                "actual_lot": 0.10,
            }
        ]

        result = detect_trade_mistakes(trade, previous_trades=previous)

        auto = result["auto_mistake_tags"]
        assert "oversized_position" in auto
        assert "moved_stop_loss" in auto
        assert "chased_price" in auto
        assert "ignored_m15" in auto
        assert "ignored_news" in auto
        assert "entered_too_early" in auto
        assert "closed_too_early" in auto
        assert "revenge_trade_warning" in auto
        assert "revenge_trade_confirmed" in auto

    def test_no_duplicate_tags(self):
        trade = {
            "symbol": "EURUSD",
            "direction": "buy",
            "planned_lot": 0.10,
            "actual_lot": 0.20,
            "planned_sl": 1.0800,
            "actual_sl": 1.0780,
            "planned_entry": 1.0850,
            "actual_entry": 1.0880,
            "opened_at": "2026-06-04T09:03:00Z",
            "entry_status": "waiting_confirmation",
            "m15_quality": "none",
            "high_impact_news_within_30m": True,
            "closed_at": "2026-06-04T09:25:00Z",
            "result_r": 0.25,
            "risk_reward": "1:2.0",
            "exit_reason": "manual_close",
        }
        previous = [
            {
                "symbol": "GBPJPY",
                "result_r": -1.0,
                "closed_at": "2026-06-04T09:00:00Z",
                "actual_lot": 0.10,
            }
        ]

        result = detect_trade_mistakes(trade, previous_trades=previous)

        assert len(result["auto_mistake_tags"]) == len(set(result["auto_mistake_tags"]))
        assert len(result["all_mistake_tags"]) == len(set(result["all_mistake_tags"]))
        assert len(result["mistake_codes"]) == len(set(result["mistake_codes"]))

    def test_summary_not_empty(self):
        trade = {
            "symbol": "EURUSD",
            "direction": "buy",
            "planned_lot": 0.10,
            "actual_lot": 0.20,
            "planned_sl": 1.0800,
            "actual_sl": 1.0780,
            "planned_entry": 1.0850,
            "actual_entry": 1.0880,
            "opened_at": "2026-06-04T09:03:00Z",
            "entry_status": "waiting_confirmation",
            "m15_quality": "none",
            "high_impact_news_within_30m": True,
            "closed_at": "2026-06-04T09:25:00Z",
            "result_r": 0.25,
            "risk_reward": "1:2.0",
            "exit_reason": "manual_close",
        }
        previous = [
            {
                "symbol": "GBPJPY",
                "result_r": -1.0,
                "closed_at": "2026-06-04T09:00:00Z",
                "actual_lot": 0.10,
            }
        ]

        result = detect_trade_mistakes(trade, previous_trades=previous)
        assert len(result["summary"]) > 20


class TestCleanTradeNoMistakes:
    def test_perfect_trade_no_auto_tags(self):
        trade = {
            "symbol": "EURUSD",
            "direction": "buy",
            "planned_lot": 0.10,
            "actual_lot": 0.10,
            "planned_sl": 1.0800,
            "actual_sl": 1.0810,
            "planned_entry": 1.0850,
            "actual_entry": 1.0852,
            "opened_at": "2026-06-04T10:05:00Z",
            "entry_status": "confirmed_entry",
            "m15_quality": "strict",
            "closed_at": "2026-06-04T13:00:00Z",
            "result_r": 1.8,
            "risk_reward": "1:2.0",
            "exit_reason": "tp_hit",
        }
        previous = [
            {
                "symbol": "GBPJPY",
                "result_r": 1.5,
                "closed_at": "2026-06-04T08:00:00Z",
                "actual_lot": 0.10,
            }
        ]

        result = detect_trade_mistakes(trade, previous_trades=previous)
        assert result["auto_mistake_tags"] == []
        assert result["mistake_codes"] == []
        assert "Không phát hiện" in result["summary"]

    def test_clean_trade_has_all_required_keys(self):
        trade = {"symbol": "EURUSD"}
        result = detect_trade_mistakes(trade)
        for key in (
            "auto_mistake_tags", "manual_mistake_tags", "all_mistake_tags",
            "mistake_codes", "warning_codes", "reason_codes",
            "score_breakdown", "summary", "reason",
        ):
            assert key in result


class TestDirtyDataNoCrash:
    def test_empty_dict(self):
        result = detect_trade_mistakes({})
        assert isinstance(result, dict)

    def test_none_trade(self):
        result = detect_trade_mistakes(None)
        assert isinstance(result, dict)

    def test_string_values_in_numeric_fields(self):
        trade = {
            "planned_lot": "abc",
            "actual_lot": "xyz",
            "planned_sl": "",
            "actual_sl": None,
            "direction": 123,
            "planned_entry": "nan",
            "actual_entry": float("nan"),
        }
        result = detect_trade_mistakes(trade)
        assert result["auto_mistake_tags"] == []

    def test_missing_all_keys(self):
        trade = {"unknown_field": "garbage"}
        result = detect_trade_mistakes(trade)
        assert result["auto_mistake_tags"] == []
        assert "Không phát hiện" in result["summary"]

    def test_partial_data_no_crash(self):
        trade = {
            "symbol": "EURUSD",
            "direction": "buy",
            "closed_at": "2026-06-04T10:00:00Z",
            "result_r": 0.3,
            "exit_reason": "manual_close",
        }
        result = detect_trade_mistakes(trade)
        assert isinstance(result, dict)
