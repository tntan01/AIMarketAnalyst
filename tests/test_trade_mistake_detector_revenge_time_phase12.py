"""Phase 12.6 tests: detect_revenge_trade_time in trade_mistake_detector."""

from __future__ import annotations

from core.trade_mistake_detector import (
    detect_revenge_trade_time,
    detect_trade_mistakes,
    find_previous_closed_trade,
    is_loss_trade,
)


class TestIsLossTrade:
    def test_negative_result_r_is_loss(self):
        assert is_loss_trade({"result_r": -1.0}) is True

    def test_positive_result_r_is_not_loss(self):
        assert is_loss_trade({"result_r": 1.5}) is False

    def test_negative_result_pct_is_loss(self):
        assert is_loss_trade({"result_pct": -0.5}) is True

    def test_positive_result_pct_is_not_loss(self):
        assert is_loss_trade({"result_pct": 0.8}) is False

    def test_zero_result_r_is_not_loss(self):
        assert is_loss_trade({"result_r": 0.0}) is False

    def test_result_label_loss_is_loss(self):
        assert is_loss_trade({"result": "loss"}) is True

    def test_result_label_thua_is_loss(self):
        assert is_loss_trade({"result": "thua"}) is True

    def test_no_data_is_not_loss(self):
        assert is_loss_trade({}) is False

    def test_none_is_not_loss(self):
        assert is_loss_trade(None) is False

    def test_result_r_string_works(self):
        assert is_loss_trade({"result_r": "-0.8"}) is True


class TestFindPreviousClosedTrade:
    def test_finds_most_recent_before_open(self):
        prev = [
            {"symbol": "EUR/USD", "closed_at": "2026-06-04T08:00:00Z", "result_r": -1.0},
            {"symbol": "EUR/USD", "closed_at": "2026-06-04T09:00:00Z", "result_r": -1.0},
        ]
        current = {"symbol": "GBP/JPY", "opened_at": "2026-06-04T09:03:00Z"}
        found = find_previous_closed_trade(current, prev)
        assert found is not None
        assert found["closed_at"] == "2026-06-04T09:00:00Z"

    def test_skips_closed_after_open(self):
        prev = [
            {"symbol": "EUR/USD", "closed_at": "2026-06-04T09:10:00Z", "result_r": -1.0},
        ]
        current = {"symbol": "GBP/JPY", "opened_at": "2026-06-04T09:03:00Z"}
        found = find_previous_closed_trade(current, prev)
        assert found is None

    def test_uses_entry_time_fallback(self):
        prev = [
            {"symbol": "EUR/USD", "closed_at": "2026-06-04T08:00:00Z", "result_r": -1.0},
        ]
        current = {"symbol": "GBP/JPY", "entry_time": "2026-06-04T09:03:00Z"}
        found = find_previous_closed_trade(current, prev)
        assert found is not None

    def test_uses_timestamp_fallback(self):
        prev = [
            {"symbol": "EUR/USD", "closed_at": "2026-06-04T08:00:00Z", "result_r": -1.0},
        ]
        current = {"symbol": "GBP/JPY", "timestamp": "2026-06-04T09:03:00Z"}
        found = find_previous_closed_trade(current, prev)
        assert found is not None

    def test_no_open_time_returns_none(self):
        prev = [{"closed_at": "2026-06-04T09:00:00Z"}]
        current = {"symbol": "GBP/JPY"}
        found = find_previous_closed_trade(current, prev)
        assert found is None

    def test_none_previous_returns_none(self):
        current = {"symbol": "GBP/JPY", "opened_at": "2026-06-04T09:03:00Z"}
        found = find_previous_closed_trade(current, None)
        assert found is None

    def test_empty_previous_returns_none(self):
        current = {"symbol": "GBP/JPY", "opened_at": "2026-06-04T09:03:00Z"}
        found = find_previous_closed_trade(current, [])
        assert found is None


class TestDetectRevengeTradeTime:
    def test_loss_then_quick_open_triggers(self):
        trade = {"symbol": "GBP/JPY", "opened_at": "2026-06-04T09:03:00Z"}
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": -1.0,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_revenge_trade_time(trade, prev)
        assert result["triggered"] is True
        assert "revenge_trade_warning" in result["tags"]

    def test_loss_but_long_gap_no_trigger(self):
        trade = {"symbol": "GBP/JPY", "opened_at": "2026-06-04T09:10:00Z"}
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": -1.0,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_revenge_trade_time(trade, prev)
        assert result["triggered"] is False

    def test_win_then_quick_open_no_trigger(self):
        trade = {"symbol": "GBP/JPY", "opened_at": "2026-06-04T09:03:00Z"}
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": 1.5,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_revenge_trade_time(trade, prev)
        assert result["triggered"] is False

    def test_no_prev_trades_no_trigger(self):
        trade = {"symbol": "GBP/JPY", "opened_at": "2026-06-04T09:03:00Z"}
        result = detect_revenge_trade_time(trade, None)
        assert result["triggered"] is False

    def test_empty_prev_trades_no_trigger(self):
        trade = {"symbol": "GBP/JPY", "opened_at": "2026-06-04T09:03:00Z"}
        result = detect_revenge_trade_time(trade, [])
        assert result["triggered"] is False

    def test_custom_threshold_triggers(self):
        trade = {"symbol": "GBP/JPY", "opened_at": "2026-06-04T09:10:00Z"}
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": -1.0,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        settings = {"revenge_trade_minutes": 15}
        result = detect_revenge_trade_time(trade, prev, settings)
        assert result["triggered"] is True

    def test_breakdown_has_required_keys(self):
        trade = {"symbol": "GBP/JPY", "opened_at": "2026-06-04T09:03:00Z"}
        prev = [{"result_r": -1.0, "closed_at": "2026-06-04T09:00:00Z"}]
        result = detect_revenge_trade_time(trade, prev)
        bd = result["breakdown"]["revenge_trade_time"]
        assert "triggered" in bd

    def test_mistake_code_present_when_triggered(self):
        trade = {"symbol": "GBP/JPY", "opened_at": "2026-06-04T09:03:00Z"}
        prev = [{"result_r": -1.0, "closed_at": "2026-06-04T09:00:00Z"}]
        result = detect_revenge_trade_time(trade, prev)
        assert "MISTAKE_REVENGE_TRADE_WARNING" in result["codes"]

    def test_result_pct_loss_triggers(self):
        trade = {"symbol": "GBP/JPY", "opened_at": "2026-06-04T09:03:00Z"}
        prev = [
            {
                "symbol": "EUR/USD",
                "result_pct": -0.8,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_revenge_trade_time(trade, prev)
        assert result["triggered"] is True


class TestDetectRevengeTradeTimeIntegrated:
    def test_integrated_detection(self):
        trade = {"symbol": "GBP/JPY", "opened_at": "2026-06-04T09:03:00Z"}
        prev = [{"result_r": -1.0, "closed_at": "2026-06-04T09:00:00Z"}]
        result = detect_trade_mistakes(trade, prev)
        assert "revenge_trade_warning" in result["auto_mistake_tags"]
        assert "MISTAKE_REVENGE_TRADE_WARNING" in result["mistake_codes"]

    def test_no_revenge_clean_result(self):
        trade = {"symbol": "GBP/JPY", "opened_at": "2026-06-04T09:10:00Z"}
        prev = [{"result_r": -1.0, "closed_at": "2026-06-04T09:00:00Z"}]
        result = detect_trade_mistakes(trade, prev)
        assert "revenge_trade_warning" not in result["auto_mistake_tags"]

    def test_previous_trades_is_none_no_crash(self):
        trade = {"symbol": "EUR/USD", "opened_at": "2026-06-04T09:03:00Z"}
        result = detect_trade_mistakes(trade, None)
        assert isinstance(result, dict)
