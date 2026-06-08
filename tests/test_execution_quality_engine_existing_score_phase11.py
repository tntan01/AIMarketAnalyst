"""Phase 11.10: verify use_existing_score parameter."""

from __future__ import annotations

from core.execution_quality_engine import calculate_execution_quality


class TestUseExistingScore:

    def test_existing_score_returned_as_is(self):
        trade = {"execution_quality_score": 88}
        result = calculate_execution_quality(trade, use_existing_score=True)
        assert result["execution_quality_score"] == 88
        assert result["score_breakdown"]["used_existing_score"] is True

    def test_existing_score_ignored_when_false(self):
        trade = {"execution_quality_score": 88, "chased_price": True}
        result = calculate_execution_quality(trade, use_existing_score=False)
        assert result["execution_quality_score"] == 75  # computed from flags
        assert result["score_breakdown"].get("used_existing_score") is not True

    def test_existing_score_used_when_true_even_with_penalties(self):
        trade = {"execution_quality_score": 88, "chased_price": True}
        result = calculate_execution_quality(trade, use_existing_score=True)
        assert result["execution_quality_score"] == 88

    def test_existing_score_defaults_to_true(self):
        trade = {"execution_quality_score": 72}
        result = calculate_execution_quality(trade)
        assert result["execution_quality_score"] == 72

    def test_score_above_100_clamped(self):
        trade = {"execution_quality_score": 999}
        result = calculate_execution_quality(trade)
        assert result["execution_quality_score"] == 100

    def test_score_below_0_clamped(self):
        trade = {"execution_quality_score": -50}
        result = calculate_execution_quality(trade)
        assert result["execution_quality_score"] == 0

    def test_garbage_score_recalculated(self):
        """Bogus score → fall through to normal calculation."""
        trade = {"execution_quality_score": "abc", "chased_price": True}
        result = calculate_execution_quality(trade)
        assert result["execution_quality_score"] == 75  # computed normally
        assert result["score_breakdown"].get("used_existing_score") is not True

    def test_existing_100_has_quality_ok(self):
        trade = {"execution_quality_score": 100}
        result = calculate_execution_quality(trade)
        assert "EXECUTION_QUALITY_OK" in result["reason_codes"]

    def test_all_existing_tests_still_pass(self):
        """Verify that existing test scenarios are unaffected."""
        # Clean trade
        r1 = calculate_execution_quality({"symbol": "EUR/USD"})
        assert r1["execution_quality_score"] == 100
        # Chased
        r2 = calculate_execution_quality({"chased_price": True})
        assert r2["execution_quality_score"] == 75
        # All 4
        r3 = calculate_execution_quality({
            "chased_price": True, "oversized_position": True,
            "moved_sl_further": True, "revenge_trade": True,
        })
        assert r3["execution_quality_score"] == 0
