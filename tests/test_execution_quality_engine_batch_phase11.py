"""Phase 11.8: verify batch processing and summary functions."""

from __future__ import annotations

from core.execution_quality_engine import (
    calculate_execution_quality_batch,
    summarize_execution_quality,
)

_TRADES = [
    {"symbol": "EUR/USD", "direction": "buy", "result_r": 1.0, "closed_at": "2026-06-01T10:00:00"},
    {"symbol": "GBP/JPY", "direction": "sell", "result_r": -1.0, "closed_at": "2026-06-01T11:00:00", "chased_price": True},
    {"symbol": "XAU/USD", "direction": "buy", "result_r": 2.0, "closed_at": "2026-06-01T12:00:00", "oversized_position": True, "moved_sl_further": True},
]


class TestBatch:
    def test_batch_returns_three_results(self):
        results = calculate_execution_quality_batch(_TRADES)
        assert len(results) == 3

    def test_batch_preserves_identity_fields(self):
        results = calculate_execution_quality_batch(_TRADES)
        assert results[0]["symbol"] == "EUR/USD"
        assert results[0]["direction"] == "buy"
        assert results[1]["symbol"] == "GBP/JPY"
        assert results[2]["symbol"] == "XAU/USD"

    def test_batch_does_not_mutate_originals(self):
        original = dict(_TRADES[0])
        calculate_execution_quality_batch(_TRADES)
        assert _TRADES[0] == original

    def test_batch_none_returns_empty(self):
        assert calculate_execution_quality_batch(None) == []

    def test_batch_not_a_list_returns_empty(self):
        assert calculate_execution_quality_batch("nope") == []  # type: ignore[arg-type]

    def test_batch_scores_correct(self):
        results = calculate_execution_quality_batch(_TRADES)
        assert results[0]["execution_quality_score"] == 100  # clean
        assert results[1]["execution_quality_score"] == 75   # chased
        assert results[2]["execution_quality_score"] == 40   # 100-30-30


class TestSummary:
    def test_summary_sample_size(self):
        batch = calculate_execution_quality_batch(_TRADES)
        summary = summarize_execution_quality(batch)
        assert summary["sample_size"] == 3

    def test_summary_average(self):
        batch = calculate_execution_quality_batch(_TRADES)
        summary = summarize_execution_quality(batch)
        # (100 + 75 + 40) / 3 = 71.67
        assert summary["average_execution_quality_score"] == 71.67

    def test_summary_min_max(self):
        batch = calculate_execution_quality_batch(_TRADES)
        summary = summarize_execution_quality(batch)
        assert summary["min_execution_quality_score"] == 40
        assert summary["max_execution_quality_score"] == 100

    def test_summary_penalty_counts(self):
        batch = calculate_execution_quality_batch(_TRADES)
        summary = summarize_execution_quality(batch)
        counts = summary["penalty_code_counts"]
        assert counts.get("EXECUTION_CHASED_PRICE") == 1
        assert counts.get("EXECUTION_OVERSIZED") == 1
        assert counts.get("EXECUTION_MOVED_SL_FURTHER") == 1

    def test_summary_none_returns_empty(self):
        s = summarize_execution_quality(None)
        assert s["sample_size"] == 0
        assert s["average_execution_quality_score"] is None

    def test_summary_empty_list(self):
        s = summarize_execution_quality([])
        assert s["sample_size"] == 0

    def test_summary_skips_dirty_items(self):
        batch = calculate_execution_quality_batch(_TRADES)
        batch.append("not_a_dict")  # type: ignore[arg-type]
        batch.append({"execution_quality_score": "abc"})  # type: ignore[arg-type]
        summary = summarize_execution_quality(batch)
        # Only the 3 valid results counted
        assert summary["sample_size"] == 3

    @staticmethod
    def test_batch_skips_non_dict_trades():
        trades: list = [*_TRADES, None, "bad"]
        results = calculate_execution_quality_batch(trades)  # type: ignore[arg-type]
        assert len(results) == 3
