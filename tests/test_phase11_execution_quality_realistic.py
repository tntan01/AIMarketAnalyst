"""Phase 11.12: realistic execution quality test with 6 journal-like trades."""

from __future__ import annotations

from core.execution_quality_engine import (
    calculate_execution_quality,
    calculate_execution_quality_batch,
    summarize_execution_quality,
)

# 6 closed trades with varied mistake scenarios
_TRADES: list[dict] = [
    # a. Clean EUR/USD buy win, manual_mistake_tags=[] → score 100
    {
        "symbol": "EUR/USD", "direction": "buy", "result_r": 1.4, "result_pct": 1.2,
        "closed_at": "2026-06-04T10:30:00+07:00", "exit_reason": "take_profit",
        "actual_lot": 0.10, "planned_lot": 0.10,
        "manual_mistake_tags": [],
    },
    # b. GBP/JPY sell loss, chased_price=True → score 75
    {
        "symbol": "GBP/JPY", "direction": "sell", "result_r": -1.0, "result_pct": -0.9,
        "closed_at": "2026-06-04T11:15:00+07:00", "exit_reason": "stop_loss",
        "actual_lot": 0.10, "planned_lot": 0.10,
        "chased_price": True,
    },
    # c. XAU/USD buy loss, auto_mistake_tags with oversized+moved_sl → score 40
    {
        "symbol": "XAU/USD", "direction": "buy", "result_r": -2.0, "result_pct": -1.5,
        "closed_at": "2026-06-04T12:00:00+07:00", "exit_reason": "stop_loss",
        "actual_lot": 0.30, "planned_lot": 0.10,
        "auto_mistake_tags": "oversized_position, moved_sl_further",
    },
    # d. USD/JPY sell loss, revenge + manual penalty → 100-35-10 = 55
    {
        "symbol": "USD/JPY", "direction": "sell", "result_r": -0.8, "result_pct": -0.5,
        "closed_at": "2026-06-04T13:00:00+07:00", "exit_reason": "stop_loss",
        "actual_lot": 0.50, "planned_lot": 0.10,
        "manual_mistake_tags": ["revenge_trade_confirmed"],
        "manual_penalty_points": 10,
    },
    # e. AUD/USD buy breakeven, no execution data → score 100 + warning
    {
        "symbol": "AUD/USD", "direction": "buy", "result_r": 0.0, "result_pct": 0.0,
        "closed_at": "2026-06-04T14:00:00+07:00", "exit_reason": "breakeven",
        "actual_lot": 0.10, "planned_lot": 0.10,
    },
    # f. EUR/USD sell with pre-existing execution_quality_score=82
    {
        "symbol": "EUR/USD", "direction": "sell", "result_r": -0.5, "result_pct": -0.3,
        "closed_at": "2026-06-04T15:00:00+07:00", "exit_reason": "stop_loss",
        "actual_lot": 0.10, "planned_lot": 0.10,
        "execution_quality_score": 82,
    },
]

_DIRTY_EXTRAS: list[dict] = [
    {
        "symbol": "NZD/USD", "direction": "buy", "result_r": 0.5,
        "closed_at": "2026-06-04T16:00:00+07:00",
        "manual_mistake_tags": None,
        "auto_mistake_tags": "not-json [",
        "manual_penalty_points": "abc",
    },
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRealisticBatch:
    def test_batch_returns_6_results(self):
        results = calculate_execution_quality_batch(_TRADES)
        assert len(results) == 6

    def test_scores_match_expected(self):
        results = calculate_execution_quality_batch(_TRADES)
        expected = [100, 75, 40, 55, 100, 82]
        actual = [r["execution_quality_score"] for r in results]
        assert actual == expected, f"got {actual}"

    def test_summary_average(self):
        batch = calculate_execution_quality_batch(_TRADES)
        summary = summarize_execution_quality(batch)
        # (100+75+40+55+100+82) / 6 = 452/6 = 75.33
        assert summary["average_execution_quality_score"] == 75.33
        assert summary["min_execution_quality_score"] == 40
        assert summary["max_execution_quality_score"] == 100

    def test_penalty_code_counts(self):
        batch = calculate_execution_quality_batch(_TRADES)
        summary = summarize_execution_quality(batch)
        counts = summary["penalty_code_counts"]
        assert counts.get("EXECUTION_CHASED_PRICE") == 1
        assert counts.get("EXECUTION_OVERSIZED") == 1
        assert counts.get("EXECUTION_MOVED_SL_FURTHER") == 1
        assert counts.get("EXECUTION_REVENGE_CONFIRMED") == 1
        assert counts.get("EXECUTION_MANUAL_PENALTY") == 1

    def test_warning_counts(self):
        batch = calculate_execution_quality_batch(_TRADES)
        summary = summarize_execution_quality(batch)
        counts = summary["warning_code_counts"]
        # Trade e has EXECUTION_DATA_INCOMPLETE
        assert counts.get("EXECUTION_DATA_INCOMPLETE") == 1


class TestDirtyData:
    def test_dirty_extras_do_not_crash_batch(self):
        all_trades = [*_TRADES, *_DIRTY_EXTRAS]
        results = calculate_execution_quality_batch(all_trades)
        assert len(results) == 7

    def test_dirty_manual_tags_none_no_crash(self):
        result = calculate_execution_quality(_DIRTY_EXTRAS[0])
        assert result["execution_quality_score"] == 100

    def test_dirty_auto_tags_broken_json_no_crash(self):
        result = calculate_execution_quality(_DIRTY_EXTRAS[0])
        # "not-json [" → treated as comma-separated → ["not-json", "["] — no crash
        assert result["execution_quality_score"] == 100

    def test_dirty_manual_penalty_points_string_no_crash(self):
        result = calculate_execution_quality(_DIRTY_EXTRAS[0])
        # "abc" is not numeric → manual penalty = 0, score stays 100
        assert result["execution_quality_score"] == 100
