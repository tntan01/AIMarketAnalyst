"""Phase 12.13 tests: detect_closed_too_early in trade_mistake_detector."""

from __future__ import annotations

from core.trade_mistake_detector import detect_closed_too_early, detect_trade_mistakes


class TestDetectClosedTooEarly:
    def test_small_win_with_manual_close_triggers(self):
        trade = {
            "closed_at": "2026-06-04T09:30:00Z",
            "result_r": 0.25,
            "risk_reward": "1:2.0",
            "exit_reason": "manual_close",
        }
        result = detect_closed_too_early(trade)
        assert result["triggered"] is True
        assert "closed_too_early" in result["tags"]

    def test_small_win_with_valid_exit_reason_no_trigger(self):
        trade = {
            "closed_at": "2026-06-04T09:30:00Z",
            "result_r": 0.25,
            "risk_reward": "1:2.0",
            "exit_reason": "news_exit",
        }
        result = detect_closed_too_early(trade)
        assert result["triggered"] is False

    def test_big_win_no_trigger(self):
        trade = {
            "closed_at": "2026-06-04T09:30:00Z",
            "result_r": 1.2,
            "risk_reward": "1:2.0",
            "exit_reason": "manual_close",
        }
        result = detect_closed_too_early(trade)
        assert result["triggered"] is False

    def test_loss_no_trigger(self):
        trade = {
            "closed_at": "2026-06-04T09:30:00Z",
            "result_r": -1.0,
            "risk_reward": "1:2.0",
            "exit_reason": "manual_close",
        }
        result = detect_closed_too_early(trade)
        assert result["triggered"] is False

    def test_not_closed_no_trigger(self):
        trade = {
            "result_r": 0.25,
            "risk_reward": "1:2.0",
            "exit_reason": "manual_close",
        }
        result = detect_closed_too_early(trade)
        assert result["triggered"] is False

    def test_explicit_early_close_with_small_r_triggers(self):
        trade = {
            "closed_at": "2026-06-04T09:30:00Z",
            "result_r": 0.3,
            "risk_reward": "1:2.0",
            "exit_reason": "chốt non",
        }
        result = detect_closed_too_early(trade)
        assert result["triggered"] is True

    def test_tp_hit_no_trigger(self):
        trade = {
            "closed_at": "2026-06-04T09:30:00Z",
            "result_r": 0.3,
            "risk_reward": "1:2.0",
            "exit_reason": "tp_hit",
        }
        result = detect_closed_too_early(trade)
        assert result["triggered"] is False

    def test_sl_hit_no_trigger(self):
        trade = {
            "closed_at": "2026-06-04T09:30:00Z",
            "result_r": 0.3,
            "risk_reward": "1:2.0",
            "exit_reason": "sl_hit",
        }
        result = detect_closed_too_early(trade)
        assert result["triggered"] is False

    def test_breakeven_no_trigger(self):
        trade = {
            "closed_at": "2026-06-04T09:30:00Z",
            "result_r": 0.3,
            "risk_reward": "1:2.0",
            "exit_reason": "breakeven",
        }
        result = detect_closed_too_early(trade)
        assert result["triggered"] is False

    def test_closed_via_actual_exit(self):
        trade = {
            "actual_exit": 1.0850,
            "result_r": 0.3,
            "risk_reward": "1:2.0",
            "exit_reason": "manual_close",
        }
        result = detect_closed_too_early(trade)
        assert result["triggered"] is True

    def test_empty_trade_no_crash(self):
        result = detect_closed_too_early({})
        assert result["triggered"] is False

    def test_breakdown_keys(self):
        trade = {
            "closed_at": "2026-06-04T09:30:00Z",
            "result_r": 0.25,
            "risk_reward": "1:2.0",
            "exit_reason": "manual_close",
        }
        result = detect_closed_too_early(trade)
        bd = result["breakdown"]["closed_too_early"]
        assert "result_r" in bd
        assert "risk_reward" in bd
        assert "exit_reason" in bd
        assert "triggered" in bd

    def test_mistake_code_present(self):
        trade = {
            "closed_at": "2026-06-04T09:30:00Z",
            "result_r": 0.25,
            "risk_reward": "1:2.0",
            "exit_reason": "manual_close",
        }
        result = detect_closed_too_early(trade)
        assert "MISTAKE_CLOSED_TOO_EARLY" in result["codes"]


class TestDetectClosedTooEarlyIntegrated:
    def test_integrated_detection(self):
        trade = {
            "closed_at": "2026-06-04T09:30:00Z",
            "result_r": 0.25,
            "risk_reward": "1:2.0",
            "exit_reason": "manual_close",
        }
        result = detect_trade_mistakes(trade)
        assert "closed_too_early" in result["auto_mistake_tags"]

    def test_clean_close_no_tag(self):
        trade = {
            "closed_at": "2026-06-04T09:30:00Z",
            "result_r": 1.5,
            "risk_reward": "1:1.5",
            "exit_reason": "tp_hit",
        }
        result = detect_trade_mistakes(trade)
        assert "closed_too_early" not in result["auto_mistake_tags"]
