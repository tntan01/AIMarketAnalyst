"""Phase 12.16 tests: compat between trade_mistake_detector and execution_quality_engine."""

from __future__ import annotations

from core.execution_quality_engine import calculate_execution_quality
from core.trade_mistake_detector import (
    apply_detected_mistakes_to_trade,
    detect_trade_mistakes,
)


class TestApplyDetectedMistakesToTrade:
    def test_does_not_mutate_original(self):
        trade = {"symbol": "EUR/USD", "planned_lot": 0.10, "actual_lot": 0.20}
        detection = detect_trade_mistakes(trade)
        original = dict(trade)
        _ = apply_detected_mistakes_to_trade(trade, detection)
        assert trade == original

    def test_injects_auto_mistake_tags(self):
        trade = {"planned_lot": 0.10, "actual_lot": 0.20}
        detection = detect_trade_mistakes(trade)
        enriched = apply_detected_mistakes_to_trade(trade, detection)
        assert "oversized_position" in enriched["auto_mistake_tags"]

    def test_injects_all_mistake_tags(self):
        trade = {"planned_lot": 0.10, "actual_lot": 0.20}
        detection = detect_trade_mistakes(trade)
        enriched = apply_detected_mistakes_to_trade(trade, detection)
        assert "oversized_position" in enriched["all_mistake_tags"]

    def test_preserves_existing_fields(self):
        trade = {"symbol": "EUR/USD", "closed_at": "2026-06-04T10:00:00Z", "result_r": -1.0}
        detection = detect_trade_mistakes(trade)
        enriched = apply_detected_mistakes_to_trade(trade, detection)
        assert enriched["symbol"] == "EUR/USD"
        assert enriched["closed_at"] == "2026-06-04T10:00:00Z"
        assert enriched["result_r"] == -1.0


class TestExecutionQualityCompat:
    def test_execution_quality_reads_detected_oversized(self):
        trade = {
            "planned_lot": 0.10,
            "actual_lot": 0.20,
            "closed_at": "2026-06-04T10:00:00Z",
        }
        detection = detect_trade_mistakes(trade)
        enriched = apply_detected_mistakes_to_trade(trade, detection)

        # Execution quality engine should detect "oversized_position" from auto_mistake_tags
        quality = calculate_execution_quality(enriched, use_existing_score=False)
        assert quality["execution_quality_score"] <= 70  # oversized = -30
        assert "EXECUTION_OVERSIZED" in quality["penalty_codes"]

    def test_execution_quality_reads_detected_chased(self):
        trade = {
            "direction": "buy",
            "planned_entry": 1.1000,
            "actual_entry": 1.1020,
            "closed_at": "2026-06-04T10:00:00Z",
        }
        detection = detect_trade_mistakes(trade)
        enriched = apply_detected_mistakes_to_trade(trade, detection)

        quality = calculate_execution_quality(enriched, use_existing_score=False)
        assert quality["execution_quality_score"] <= 75  # chased = -25
        assert "EXECUTION_CHASED_PRICE" in quality["penalty_codes"]

    def test_execution_quality_reads_detected_moved_sl(self):
        trade = {
            "direction": "buy",
            "planned_sl": 1.0800,
            "actual_sl": 1.0780,
            "closed_at": "2026-06-04T10:00:00Z",
        }
        detection = detect_trade_mistakes(trade)
        enriched = apply_detected_mistakes_to_trade(trade, detection)

        quality = calculate_execution_quality(enriched, use_existing_score=False)
        assert quality["execution_quality_score"] <= 70  # moved_sl = -30
        assert "EXECUTION_MOVED_SL_FURTHER" in quality["penalty_codes"]

    def test_execution_quality_reads_detected_revenge(self):
        trade = {
            "actual_lot": 0.20,
            "opened_at": "2026-06-04T09:03:00Z",
            "closed_at": "2026-06-04T10:00:00Z",
        }
        prev = [
            {
                "result_r": -1.0,
                "actual_lot": 0.10,
                "closed_at": "2026-06-04T09:00:00Z",
            }
        ]
        detection = detect_trade_mistakes(trade, prev)
        enriched = apply_detected_mistakes_to_trade(trade, detection)

        quality = calculate_execution_quality(enriched, use_existing_score=False)
        assert quality["execution_quality_score"] <= 65  # revenge_confirmed = -35
        assert "EXECUTION_REVENGE_CONFIRMED" in quality["penalty_codes"]

    def test_clean_trade_full_score(self):
        trade = {"symbol": "EUR/USD", "closed_at": "2026-06-04T10:00:00Z"}
        detection = detect_trade_mistakes(trade)
        enriched = apply_detected_mistakes_to_trade(trade, detection)

        quality = calculate_execution_quality(enriched, use_existing_score=False)
        assert quality["execution_quality_score"] == 100
