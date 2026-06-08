"""Phase 12.2 tests: verify trade_mistake_detector module import and basic API."""

from __future__ import annotations

from core.trade_mistake_detector import (
    default_mistake_detection_result,
    detect_trade_mistakes,
)


class TestImport:
    def test_import_module(self):
        import core.trade_mistake_detector as tmd
        assert tmd is not None


class TestDefaultResult:
    def test_returns_dict(self):
        result = default_mistake_detection_result()
        assert isinstance(result, dict)

    def test_auto_mistake_tags_is_empty_list(self):
        result = default_mistake_detection_result()
        assert result["auto_mistake_tags"] == []

    def test_manual_mistake_tags_is_empty_list(self):
        result = default_mistake_detection_result()
        assert result["manual_mistake_tags"] == []

    def test_mistake_codes_is_empty_list(self):
        result = default_mistake_detection_result()
        assert result["mistake_codes"] == []

    def test_has_required_keys(self):
        result = default_mistake_detection_result()
        required = {
            "auto_mistake_tags", "manual_mistake_tags",
            "mistake_codes", "warning_codes",
            "reason_codes", "score_breakdown", "reason",
        }
        assert required.issubset(result.keys())

    def test_custom_reason(self):
        result = default_mistake_detection_result(reason="test_reason")
        assert result["reason"] == "test_reason"


class TestDetectTradeMistakes:
    def test_empty_dict_returns_result(self):
        result = detect_trade_mistakes({})
        assert isinstance(result, dict)
        assert "auto_mistake_tags" in result

    def test_none_trade_does_not_crash(self):
        result = detect_trade_mistakes(None)
        assert isinstance(result, dict)

    def test_none_trade_has_warning(self):
        result = detect_trade_mistakes(None)
        assert len(result["warning_codes"]) > 0

    def test_none_previous_trades_does_not_crash(self):
        result = detect_trade_mistakes({"symbol": "EUR/USD"}, previous_trades=None)
        assert isinstance(result, dict)

    def test_none_settings_does_not_crash(self):
        result = detect_trade_mistakes({"symbol": "EUR/USD"}, settings=None)
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        result = detect_trade_mistakes({"symbol": "EUR/USD"})
        required = {
            "auto_mistake_tags", "manual_mistake_tags",
            "mistake_codes", "warning_codes",
            "reason_codes", "score_breakdown", "reason",
        }
        assert required.issubset(result.keys())
