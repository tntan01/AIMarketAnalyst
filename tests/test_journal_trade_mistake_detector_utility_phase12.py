"""Phase 12.17: utility test — detector on journal-style dict trade, no migration.

This test demonstrates that the trade_mistake_detector works on dict trades
structured like journal entries without requiring database schema changes.
"""

from __future__ import annotations

from core.trade_mistake_detector import detect_trade_mistakes


def _journal_style_trade(
    symbol: str = "EUR/USD",
    direction: str = "buy",
    planned_lot: float = 0.10,
    actual_lot: float = 0.10,
    planned_sl: float | None = None,
    actual_sl: float | None = None,
    planned_entry: float | None = None,
    actual_entry: float | None = None,
    entry_status: str | None = None,
    m15_quality: str | None = None,
    opened_at: str | None = None,
    closed_at: str | None = None,
    result_r: float | None = None,
    exit_reason: str | None = None,
    risk_reward: str | None = None,
    high_impact_news_within_30m: bool = False,
    manual_mistake_tags: object = None,
) -> dict[str, object]:
    """Build a dict resembling a journal row / closed-trade entry."""
    trade: dict[str, object] = {
        "symbol": symbol,
        "direction": direction,
        "planned_lot": planned_lot,
        "actual_lot": actual_lot,
    }
    if planned_sl is not None:
        trade["planned_sl"] = planned_sl
    if actual_sl is not None:
        trade["actual_sl"] = actual_sl
    if planned_entry is not None:
        trade["planned_entry"] = planned_entry
    if actual_entry is not None:
        trade["actual_entry"] = actual_entry
    if entry_status is not None:
        trade["entry_status"] = entry_status
    if m15_quality is not None:
        trade["m15_quality"] = m15_quality
    if opened_at is not None:
        trade["opened_at"] = opened_at
    if closed_at is not None:
        trade["closed_at"] = closed_at
    if result_r is not None:
        trade["result_r"] = result_r
    if exit_reason is not None:
        trade["exit_reason"] = exit_reason
    if risk_reward is not None:
        trade["risk_reward"] = risk_reward
    if high_impact_news_within_30m:
        trade["high_impact_news_within_30m"] = True
    if manual_mistake_tags is not None:
        trade["manual_mistake_tags"] = manual_mistake_tags
    return trade


_MOCK_PREVIOUS = [
    {
        "symbol": "GBP/JPY",
        "result_r": -1.0,
        "result_pct": -1.2,
        "actual_lot": 0.10,
        "closed_at": "2026-06-04T09:00:00Z",
    }
]


class TestJournalStyleTradeDetection:
    def test_clean_journal_entry_no_mistakes(self):
        trade = _journal_style_trade()
        result = detect_trade_mistakes(trade)
        assert result["auto_mistake_tags"] == []
        assert "Không phát hiện" in result["summary"]

    def test_oversized_from_journal_style(self):
        trade = _journal_style_trade(planned_lot=0.10, actual_lot=0.14)
        result = detect_trade_mistakes(trade)
        assert "oversized_position" in result["auto_mistake_tags"]

    def test_moved_sl_from_journal_style(self):
        trade = _journal_style_trade(
            planned_sl=1.0800,
            actual_sl=1.0780,
        )
        result = detect_trade_mistakes(trade)
        assert "moved_stop_loss" in result["auto_mistake_tags"]

    def test_chased_price_from_journal_style(self):
        trade = _journal_style_trade(
            planned_entry=1.1000,
            actual_entry=1.1020,
        )
        result = detect_trade_mistakes(trade)
        assert "chased_price" in result["auto_mistake_tags"]

    def test_ignored_m15_from_journal_style(self):
        trade = _journal_style_trade(
            m15_quality="none",
            actual_entry=1.0850,
        )
        result = detect_trade_mistakes(trade)
        assert "ignored_m15" in result["auto_mistake_tags"]

    def test_ignored_news_from_journal_style(self):
        trade = _journal_style_trade(
            high_impact_news_within_30m=True,
            actual_entry=1.0850,
        )
        result = detect_trade_mistakes(trade)
        assert "ignored_news" in result["auto_mistake_tags"]

    def test_entered_too_early_from_journal_style(self):
        trade = _journal_style_trade(
            entry_status="waiting_confirmation",
            actual_entry=1.0850,
        )
        result = detect_trade_mistakes(trade)
        assert "entered_too_early" in result["auto_mistake_tags"]

    def test_closed_too_early_from_journal_style(self):
        trade = _journal_style_trade(
            closed_at="2026-06-04T09:30:00Z",
            result_r=0.25,
            risk_reward="1:2.0",
            exit_reason="manual_close",
        )
        result = detect_trade_mistakes(trade)
        assert "closed_too_early" in result["auto_mistake_tags"]

    def test_revenge_trade_from_journal_style(self):
        trade = _journal_style_trade(
            actual_lot=0.20,
            opened_at="2026-06-04T09:03:00Z",
        )
        result = detect_trade_mistakes(trade, previous_trades=_MOCK_PREVIOUS)
        assert "revenge_trade_warning" in result["auto_mistake_tags"]
        assert "revenge_trade_confirmed" in result["auto_mistake_tags"]

    def test_manual_tags_preserved_in_journal_style(self):
        trade = _journal_style_trade(
            manual_mistake_tags=["ignored_m15", "chased_price"],
        )
        result = detect_trade_mistakes(trade)
        assert "ignored_m15" in result["manual_mistake_tags"]
        assert "chased_price" in result["manual_mistake_tags"]

    def test_multi_mistake_journal_style_does_not_crash(self):
        trade = _journal_style_trade(
            planned_lot=0.10,
            actual_lot=0.20,
            planned_sl=1.0800,
            actual_sl=1.0780,
            planned_entry=1.1000,
            actual_entry=1.1020,
            m15_quality="none",
            entry_status="watch_zone",
            high_impact_news_within_30m=True,
            closed_at="2026-06-04T09:30:00Z",
            result_r=0.3,
            risk_reward="1:2.0",
            exit_reason="manual_close",
            opened_at="2026-06-04T09:03:00Z",
        )
        result = detect_trade_mistakes(trade, previous_trades=_MOCK_PREVIOUS)
        assert isinstance(result, dict)
        assert "summary" in result
        assert "all_mistake_tags" in result
        # no duplicates
        assert len(result["all_mistake_tags"]) == len(set(result["all_mistake_tags"]))
