"""Phase 11.9: verify journal payload builder."""

from __future__ import annotations

from core.execution_quality_engine import build_execution_quality_journal_payload


class TestPayload:
    def test_clean_trade_payload_score_100(self):
        payload = build_execution_quality_journal_payload(
            {"symbol": "EUR/USD", "result_r": 1.0}
        )
        assert payload["execution_quality_score"] == 100
        assert payload["execution_quality_penalty_codes"] == []
        assert "EXECUTION_DATA_INCOMPLETE" in payload["execution_quality_warning_codes"]

    def test_chased_price_payload(self):
        payload = build_execution_quality_journal_payload({"chased_price": True})
        assert payload["execution_quality_score"] == 75
        assert "EXECUTION_CHASED_PRICE" in payload["execution_quality_penalty_codes"]

    def test_payload_has_required_keys(self):
        payload = build_execution_quality_journal_payload({"symbol": "EUR/USD"})
        for key in ("execution_quality_score", "execution_quality_penalty_codes",
                     "execution_quality_warning_codes", "execution_quality_breakdown"):
            assert key in payload, f"missing {key}"

    def test_payload_breakdown_has_data_complete(self):
        payload = build_execution_quality_journal_payload({"chased_price": True})
        assert payload["execution_quality_breakdown"]["data_complete"] is True

    def test_auto_mistake_tags_string_normalized(self):
        trade = {"auto_mistake_tags": "chased_price, oversized_position"}
        payload = build_execution_quality_journal_payload(trade)
        assert payload["auto_mistake_tags"] == ["chased_price", "oversized_position"]

    def test_manual_mistake_tags_list_preserved(self):
        trade = {"manual_mistake_tags": ["revenge_trade"]}
        payload = build_execution_quality_journal_payload(trade)
        assert payload["manual_mistake_tags"] == ["revenge_trade"]

    def test_no_tags_field_when_empty(self):
        trade = {"symbol": "EUR/USD"}
        payload = build_execution_quality_journal_payload(trade)
        assert "auto_mistake_tags" not in payload
        assert "manual_mistake_tags" not in payload

    def test_none_trade_does_not_crash(self):
        payload = build_execution_quality_journal_payload(None)
        assert payload["execution_quality_score"] == 100
        assert "EXECUTION_DATA_INCOMPLETE" in payload["execution_quality_warning_codes"]
