"""Phase 12.15 tests: build_mistake_summary in trade_mistake_detector."""

from __future__ import annotations

from core.trade_mistake_detector import build_mistake_summary, detect_trade_mistakes


class TestBuildMistakeSummary:
    def test_no_tags_default_message(self):
        result = {
            "auto_mistake_tags": [],
            "manual_mistake_tags": [],
        }
        msg = build_mistake_summary(result)
        assert "Không phát hiện" in msg

    def test_auto_tags_translated(self):
        result = {
            "auto_mistake_tags": ["oversized_position", "ignored_m15"],
            "manual_mistake_tags": [],
        }
        msg = build_mistake_summary(result)
        assert "vào khối lượng lớn hơn kế hoạch" in msg
        assert "bỏ qua xác nhận M15" in msg

    def test_manual_only_mentions_journal(self):
        result = {
            "auto_mistake_tags": [],
            "manual_mistake_tags": ["chased_price"],
        }
        msg = build_mistake_summary(result)
        assert "tag thủ công" in msg

    def test_both_auto_and_manual(self):
        result = {
            "auto_mistake_tags": ["chased_price"],
            "manual_mistake_tags": ["ignored_news"],
        }
        msg = build_mistake_summary(result)
        assert "đuổi giá" in msg
        assert "tag thủ công" in msg

    def test_all_tags_have_translations(self):
        result = {
            "auto_mistake_tags": [
                "oversized_position", "moved_stop_loss",
                "revenge_trade_warning", "revenge_trade_confirmed",
                "ignored_m15", "ignored_news",
                "chased_price", "entered_too_early", "closed_too_early",
            ],
            "manual_mistake_tags": [],
        }
        msg = build_mistake_summary(result)
        assert len(msg) > 30  # plenty of content


class TestSummaryInFullResult:
    def test_no_mistakes_has_summary(self):
        trade = {"symbol": "EUR/USD"}
        result = detect_trade_mistakes(trade)
        assert "summary" in result
        assert "Không phát hiện" in result["summary"]

    def test_mistakes_have_summary(self):
        trade = {
            "planned_lot": 0.10,
            "actual_lot": 0.20,
            "direction": "buy",
            "planned_sl": 1.0800,
            "actual_sl": 1.0780,
        }
        result = detect_trade_mistakes(trade)
        assert "summary" in result
        assert "khối lượng" in result["summary"].lower()
        assert "stop loss" in result["summary"].lower()

    def test_none_trade_has_summary(self):
        result = detect_trade_mistakes(None)
        assert "summary" in result
        assert "Không đủ dữ liệu" in result["summary"]
