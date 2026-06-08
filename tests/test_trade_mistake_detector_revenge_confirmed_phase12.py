"""Phase 12.8 tests: detect_revenge_trade_confirmed in trade_mistake_detector."""

from __future__ import annotations

from core.trade_mistake_detector import (
    detect_revenge_trade_confirmed,
    detect_trade_mistakes,
)


class TestDetectRevengeTradeConfirmed:
    def test_both_time_and_lot_triggers_confirmed(self):
        trade = {
            "symbol": "GBP/JPY",
            "actual_lot": 0.20,
            "opened_at": "2026-06-04T09:03:00Z",
        }
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": -1.0,
                "actual_lot": 0.10,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_revenge_trade_confirmed(trade, prev)
        assert result["triggered"] is True
        assert "revenge_trade_confirmed" in result["tags"]
        assert "MISTAKE_REVENGE_TRADE_CONFIRMED" in result["codes"]

    def test_time_only_no_confirmed(self):
        trade = {
            "symbol": "GBP/JPY",
            "actual_lot": 0.12,
            "opened_at": "2026-06-04T09:03:00Z",
        }
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": -1.0,
                "actual_lot": 0.10,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_revenge_trade_confirmed(trade, prev)
        assert result["triggered"] is False
        bd = result["breakdown"]["revenge_trade_confirmed"]
        assert bd["time_condition"] is True
        assert bd["lot_condition"] is False

    def test_lot_only_no_confirmed(self):
        trade = {
            "symbol": "GBP/JPY",
            "actual_lot": 0.20,
            "opened_at": "2026-06-04T09:10:00Z",
        }
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": -1.0,
                "actual_lot": 0.10,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_revenge_trade_confirmed(trade, prev)
        assert result["triggered"] is False
        bd = result["breakdown"]["revenge_trade_confirmed"]
        assert bd["time_condition"] is False
        assert bd["lot_condition"] is True

    def test_previous_win_no_trigger(self):
        trade = {
            "symbol": "GBP/JPY",
            "actual_lot": 0.20,
            "opened_at": "2026-06-04T09:03:00Z",
        }
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": 1.5,
                "actual_lot": 0.10,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_revenge_trade_confirmed(trade, prev)
        assert result["triggered"] is False

    def test_no_prev_trades_no_trigger(self):
        trade = {
            "symbol": "GBP/JPY",
            "actual_lot": 0.20,
            "opened_at": "2026-06-04T09:03:00Z",
        }
        result = detect_revenge_trade_confirmed(trade, None)
        assert result["triggered"] is False

    def test_breakdown_keys(self):
        trade = {
            "symbol": "GBP/JPY",
            "actual_lot": 0.20,
            "opened_at": "2026-06-04T09:03:00Z",
        }
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": -1.0,
                "actual_lot": 0.10,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_revenge_trade_confirmed(trade, prev)
        bd = result["breakdown"]["revenge_trade_confirmed"]
        assert "time_condition" in bd
        assert "lot_condition" in bd
        assert "triggered" in bd
        assert bd["time_condition"] is True
        assert bd["lot_condition"] is True
        assert bd["triggered"] is True


class TestDetectRevengeTradeConfirmedIntegrated:
    def test_both_conditions_confirmed_tag_present(self):
        trade = {
            "symbol": "GBP/JPY",
            "actual_lot": 0.20,
            "opened_at": "2026-06-04T09:03:00Z",
        }
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": -1.0,
                "actual_lot": 0.10,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_trade_mistakes(trade, prev)
        assert "revenge_trade_warning" in result["auto_mistake_tags"]
        assert "revenge_trade_confirmed" in result["auto_mistake_tags"]
        assert "MISTAKE_REVENGE_TRADE_CONFIRMED" in result["mistake_codes"]

    def test_time_only_warning_not_confirmed(self):
        trade = {
            "symbol": "GBP/JPY",
            "actual_lot": 0.12,
            "opened_at": "2026-06-04T09:03:00Z",
        }
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": -1.0,
                "actual_lot": 0.10,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_trade_mistakes(trade, prev)
        assert "revenge_trade_warning" in result["auto_mistake_tags"]
        assert "revenge_trade_confirmed" not in result["auto_mistake_tags"]

    def test_lot_only_warning_not_confirmed(self):
        trade = {
            "symbol": "GBP/JPY",
            "actual_lot": 0.20,
            "opened_at": "2026-06-04T09:10:00Z",
        }
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": -1.0,
                "actual_lot": 0.10,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_trade_mistakes(trade, prev)
        assert "revenge_trade_warning" in result["auto_mistake_tags"]
        assert "revenge_trade_confirmed" not in result["auto_mistake_tags"]

    def test_no_duplicate_warning_tag(self):
        trade = {
            "symbol": "GBP/JPY",
            "actual_lot": 0.20,
            "opened_at": "2026-06-04T09:03:00Z",
        }
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": -1.0,
                "actual_lot": 0.10,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_trade_mistakes(trade, prev)
        # warning triggered by time, lot, AND confirmed rule →
        # add_unique keeps it to 1
        assert result["auto_mistake_tags"].count("revenge_trade_warning") == 1

    def test_breakdown_in_full_result(self):
        trade = {
            "symbol": "GBP/JPY",
            "actual_lot": 0.20,
            "opened_at": "2026-06-04T09:03:00Z",
        }
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": -1.0,
                "actual_lot": 0.10,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_trade_mistakes(trade, prev)
        assert "revenge_trade_confirmed" in result["score_breakdown"]
