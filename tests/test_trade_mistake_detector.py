"""Tests for trade_mistake_detector — individual mistake detectors."""

from __future__ import annotations

from datetime import datetime, timezone

from core.trade_mistake_detector import (
    detect_chased_price,
    detect_closed_too_early,
    detect_entered_too_early,
    detect_oversized_position,
    is_loss_trade,
)


class TestIsLossTrade:
    def test_win(self):
        assert not is_loss_trade({"result": "win"})

    def test_loss(self):
        assert is_loss_trade({"result": "loss"})

    def test_breakeven_is_not_loss(self):
        assert not is_loss_trade({"result": "breakeven"})

    def test_empty_is_not_loss(self):
        assert not is_loss_trade({})


class TestDetectOversizedPosition:
    def test_within_plan(self):
        trade = {
            "planned_lot": 0.10,
            "actual_lot": 0.10,
            "risk_percent": 2.0,
        }
        result = detect_oversized_position(trade)
        assert result["triggered"] is False

    def test_exceeds_plan(self):
        trade = {
            "planned_lot": 0.10,
            "actual_lot": 0.20,  # 100% over plan
            "risk_percent": 2.0,
        }
        result = detect_oversized_position(trade)
        assert result["triggered"] is True

    def test_missing_planned_skips(self):
        trade = {"planned_lot": None, "actual_lot": 0.20}
        result = detect_oversized_position(trade)
        assert result["triggered"] is False


class TestDetectChasedPrice:
    def test_no_chase_when_entered_in_zone(self):
        trade = {
            "planned_entry": 1.1000,
            "actual_entry": 1.1005,
            "entry_zone": "[1.0990, 1.1010]",
            "selected_scenario": "buy",
        }
        result = detect_chased_price(trade)
        assert result["triggered"] is False

    def test_chase_detected_outside_zone(self):
        trade = {
            "planned_entry": 1.1000,
            "actual_entry": 1.1050,  # way above buy zone
            "entry_zone": "[1.0990, 1.1010]",
            "selected_scenario": "buy",
        }
        result = detect_chased_price(trade)
        assert result["triggered"] is True

    def test_missing_data_skips(self):
        trade = {"planned_entry": None}
        result = detect_chased_price(trade)
        assert result["triggered"] is False


class TestDetectEnteredTooEarly:
    def test_no_entry_skips(self):
        trade = {
            "timestamp_utc": "2026-06-15T10:00:00Z",
            "opened_at": None,  # never opened
            "selected_scenario": "buy",
        }
        result = detect_entered_too_early(trade)
        assert result["triggered"] is False

    def test_missing_entry_status_flagged(self):
        """Entry opened without confirmed_entry status → early entry."""
        trade = {
            "timestamp_utc": "2026-06-15T10:00:00Z",
            "opened_at": "2026-06-15T10:00:00Z",
            "selected_scenario": "buy",
            "entry_status": "watch_zone",  # Not confirmed yet
            "planned_entry": 1.1000,
            "actual_entry": 1.1000,
        }
        result = detect_entered_too_early(trade)
        assert result["triggered"] is True


class TestDetectClosedTooEarly:
    def test_not_closed_skips(self):
        trade = {
            "trade_status": "opened",
            "selected_scenario": "buy",
        }
        result = detect_closed_too_early(trade)
        assert result["triggered"] is False

    def test_missing_exit_price_skips(self):
        trade = {
            "trade_status": "closed",
            "selected_scenario": "buy",
            "actual_entry": 1.1000,
            "actual_exit": None,
            "planned_tp": 1.1050,
        }
        result = detect_closed_too_early(trade)
        assert result["triggered"] is False

    def test_closed_with_small_profit_flagged(self):
        """Small positive R below threshold triggers early close."""
        trade = {
            "trade_status": "closed",
            "selected_scenario": "buy",
            "actual_entry": 1.1000,
            "actual_exit": 1.1008,
            "planned_tp": 1.1050,
            "actual_sl": 1.0980,
            "closed_at": "2026-06-15T14:00:00Z",
            "planned_entry": 1.1000,
            "planned_sl": 1.0980,
            # risk = 0.0020, reward = 0.0008 → result_r = 0.4
            "result_r": 0.4,
        }
        result = detect_closed_too_early(trade)
        # result_r (0.4) > 0 and < threshold (0.5) → triggered
        assert result["triggered"] is True
