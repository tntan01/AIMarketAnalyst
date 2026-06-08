"""Phase 11.11: verify execution quality engine works with current journal output."""

from __future__ import annotations

from core.execution_quality_engine import (
    calculate_execution_quality,
    calculate_execution_quality_batch,
    summarize_execution_quality,
)

# Mimics current JournalService.list_closed_trades_for_account_guard() output
_JOURNAL_TRADES = [
    {
        "symbol": "EUR/USD",
        "direction": "buy",
        "result_r": 1.4,
        "result_pct": 1.2,
        "closed_at": "2026-06-04T10:30:00+07:00",
        "exit_reason": "take_profit",
        "actual_lot": 0.10,
        "planned_lot": 0.10,
    },
    {
        "symbol": "GBP/JPY",
        "direction": "sell",
        "result_r": -1.0,
        "result_pct": -0.9,
        "closed_at": "2026-06-04T11:15:00+07:00",
        "exit_reason": "stop_loss",
        "actual_lot": 0.20,
        "planned_lot": 0.10,
    },
]


class TestJournalCompatibility:

    def test_batch_does_not_crash(self):
        results = calculate_execution_quality_batch(_JOURNAL_TRADES)
        assert len(results) == 2

    def test_each_result_has_score(self):
        results = calculate_execution_quality_batch(_JOURNAL_TRADES)
        for r in results:
            assert "execution_quality_score" in r
            assert isinstance(r["execution_quality_score"], int)

    def test_no_execution_data_scores_100(self):
        """Journal entries without mistake tags must score 100 (not penalized)."""
        results = calculate_execution_quality_batch(_JOURNAL_TRADES)
        for r in results:
            assert r["execution_quality_score"] == 100

    def test_no_execution_data_has_warning(self):
        """Entries without execution data must warn about incompleteness."""
        results = calculate_execution_quality_batch(_JOURNAL_TRADES)
        for r in results:
            assert "EXECUTION_DATA_INCOMPLETE" in r["warning_codes"]

    def test_summary_works(self):
        batch = calculate_execution_quality_batch(_JOURNAL_TRADES)
        summary = summarize_execution_quality(batch)
        assert summary["sample_size"] == 2
        assert summary["average_execution_quality_score"] == 100.0

    def test_single_trade_preserves_identity(self):
        result = calculate_execution_quality(_JOURNAL_TRADES[0])
        assert result["execution_quality_score"] == 100

    def test_actual_lot_discrepancy_not_auto_detected(self):
        """Phase 11 does NOT auto-detect oversized from actual_lot > planned_lot.

        That belongs to Phase 12 (trade_mistake_detector)."""
        trade = dict(_JOURNAL_TRADES[1])  # actual_lot=0.20, planned_lot=0.10
        result = calculate_execution_quality(trade)
        assert result["execution_quality_score"] == 100
        assert "EXECUTION_OVERSIZED" not in result["penalty_codes"]
