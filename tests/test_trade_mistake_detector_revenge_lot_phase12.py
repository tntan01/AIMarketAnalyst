"""Phase 12.7 tests: detect_revenge_trade_lot in trade_mistake_detector."""

from __future__ import annotations

from core.trade_mistake_detector import (
    detect_revenge_trade_lot,
    detect_trade_mistakes,
)


class TestDetectRevengeTradeLot:
    def test_loss_then_double_lot_triggers(self):
        trade = {
            "symbol": "GBP/JPY",
            "actual_lot": 0.20,
            "opened_at": "2026-06-04T09:05:00Z",
        }
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": -1.0,
                "actual_lot": 0.10,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_revenge_trade_lot(trade, prev)
        assert result["triggered"] is True
        assert "revenge_trade_warning" in result["tags"]

    def test_loss_but_small_lot_increase_no_trigger(self):
        trade = {
            "symbol": "GBP/JPY",
            "actual_lot": 0.14,
            "opened_at": "2026-06-04T09:05:00Z",
        }
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": -1.0,
                "actual_lot": 0.10,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_revenge_trade_lot(trade, prev)
        assert result["triggered"] is False

    def test_loss_same_lot_no_trigger(self):
        trade = {
            "symbol": "GBP/JPY",
            "actual_lot": 0.10,
            "opened_at": "2026-06-04T09:05:00Z",
        }
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": -1.0,
                "actual_lot": 0.10,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_revenge_trade_lot(trade, prev)
        assert result["triggered"] is False

    def test_win_then_big_lot_no_trigger(self):
        trade = {
            "symbol": "GBP/JPY",
            "actual_lot": 0.20,
            "opened_at": "2026-06-04T09:05:00Z",
        }
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": 1.5,
                "actual_lot": 0.10,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_revenge_trade_lot(trade, prev)
        assert result["triggered"] is False

    def test_no_prev_trades_no_trigger(self):
        trade = {
            "symbol": "GBP/JPY",
            "actual_lot": 0.20,
            "opened_at": "2026-06-04T09:05:00Z",
        }
        result = detect_revenge_trade_lot(trade, None)
        assert result["triggered"] is False

    def test_empty_prev_trades_no_trigger(self):
        trade = {
            "symbol": "GBP/JPY",
            "actual_lot": 0.20,
            "opened_at": "2026-06-04T09:05:00Z",
        }
        result = detect_revenge_trade_lot(trade, [])
        assert result["triggered"] is False

    def test_uses_planned_lot_fallback(self):
        trade = {
            "symbol": "GBP/JPY",
            "planned_lot": 0.20,
            "opened_at": "2026-06-04T09:05:00Z",
        }
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": -1.0,
                "actual_lot": 0.10,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_revenge_trade_lot(trade, prev)
        assert result["triggered"] is True

    def test_custom_multiplier_triggers(self):
        trade = {
            "symbol": "GBP/JPY",
            "actual_lot": 0.15,
            "opened_at": "2026-06-04T09:05:00Z",
        }
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": -1.0,
                "actual_lot": 0.10,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        settings = {"revenge_lot_multiplier": 1.3}
        result = detect_revenge_trade_lot(trade, prev, settings)
        # 0.15 > 0.10 * 1.3 = 0.13 => yes
        assert result["triggered"] is True

    def test_previous_lot_zero_no_trigger(self):
        trade = {
            "symbol": "GBP/JPY",
            "actual_lot": 0.20,
            "opened_at": "2026-06-04T09:05:00Z",
        }
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": -1.0,
                "actual_lot": 0.0,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_revenge_trade_lot(trade, prev)
        assert result["triggered"] is False

    def test_current_lot_zero_no_trigger(self):
        trade = {
            "symbol": "GBP/JPY",
            "actual_lot": 0.0,
            "opened_at": "2026-06-04T09:05:00Z",
        }
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": -1.0,
                "actual_lot": 0.10,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_revenge_trade_lot(trade, prev)
        assert result["triggered"] is False

    def test_breakdown_has_required_keys(self):
        trade = {
            "symbol": "GBP/JPY",
            "actual_lot": 0.20,
            "opened_at": "2026-06-04T09:05:00Z",
        }
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": -1.0,
                "actual_lot": 0.10,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_revenge_trade_lot(trade, prev)
        bd = result["breakdown"]["revenge_trade_lot"]
        assert "previous_lot" in bd
        assert "current_lot" in bd
        assert "threshold_multiplier" in bd
        assert "triggered" in bd

    def test_mistake_code_present_when_triggered(self):
        trade = {
            "symbol": "GBP/JPY",
            "actual_lot": 0.20,
            "opened_at": "2026-06-04T09:05:00Z",
        }
        prev = [
            {
                "symbol": "EUR/USD",
                "result_r": -1.0,
                "actual_lot": 0.10,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        result = detect_revenge_trade_lot(trade, prev)
        assert "MISTAKE_REVENGE_TRADE_WARNING" in result["codes"]


class TestDetectRevengeTradeLotIntegrated:
    def test_no_duplicate_tag_when_both_time_and_lot_trigger(self):
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
        # both time (3 min) and lot (2x) trigger, but tag should appear once
        count = result["auto_mistake_tags"].count("revenge_trade_warning")
        assert count == 1

    def test_lot_only_trigger_integrated(self):
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
        # time gap 10 min > 5 → time doesn't trigger
        # lot 0.20 > 0.10*1.5 → lot triggers
        assert "revenge_trade_warning" in result["auto_mistake_tags"]
        assert "revenge_trade_lot" in result["score_breakdown"]
