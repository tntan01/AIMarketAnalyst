"""
Test _format_ai_to_html heading detection — edge cases cho tiếng Việt.
"""
import sys
import unittest
from PyQt6.QtWidgets import QApplication


class TestFormatAiHeadingDetection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    @classmethod
    def _format(cls, raw: str, light: bool = False) -> str:
        from ui.screens.backtest_screen import BacktestScreen
        return BacktestScreen._format_ai_to_html(raw, light)

    # ── Colon heading: true positives ────────────────────────────

    def test_short_colon_label_is_heading(self):
        """Dòng ngắn kết thúc bằng : là heading."""
        html = self._format("Tổng quan:")
        self.assertIn("font-weight:700", html)
        self.assertIn("Tổng quan", html)

    def test_medium_colon_label_is_heading(self):
        """Dòng trung bình kết thúc bằng : là heading."""
        html = self._format("Khuyến nghị và điều chỉnh:")
        self.assertIn("font-weight:700", html)

    def test_label_at_60_chars_is_heading(self):
        """Dòng đúng 60 ký tự kết thúc bằng : vẫn là heading."""
        label = "A" * 59 + ":"
        html = self._format(label)
        self.assertIn("font-weight:700", html)

    # ── Colon heading: false positives (should NOT be heading) ───

    def test_long_line_with_colon_is_not_heading(self):
        """Dòng > 60 ký tự dù kết thúc bằng : cũng không phải heading."""
        long_line = "Đây là một dòng rất dài giải thích chi tiết về kết quả phân tích backtest:"
        self.assertGreater(len(long_line), 60)
        html = self._format(long_line)
        self.assertNotIn("font-weight:700", html)

    def test_sentence_with_colon_at_end_is_not_heading(self):
        """Dòng kết thúc bằng : nhưng > 60 ký tự là text thường."""
        html = self._format(
            "Kết luận: hệ thống có edge tốt nhưng cần điều chỉnh thêm về risk management:"
        )
        self.assertGreater(
            len("Kết luận: hệ thống có edge tốt nhưng cần điều chỉnh thêm về risk management:"),
            60,
        )
        self.assertNotIn("font-weight:700", html)

    def test_colon_in_middle_not_heading(self):
        """Dòng có : ở giữa, không kết thúc bằng : → không phải heading."""
        html = self._format("Lý do: EUR/USD có PF 1.8 với 40 lệnh")
        self.assertNotIn("font-weight:700", html)

    # ── Uppercase heading: Vietnamese diacritics ──────────────────

    def test_vietnamese_all_caps_is_heading(self):
        """Tiếng Việt in hoa có dấu vẫn được nhận diện là heading."""
        html = self._format("ĐÁNH GIÁ CHUNG")
        self.assertIn("font-weight:700", html)

    def test_vietnamese_all_caps_short_is_heading(self):
        """Tiếng Việt in hoa ngắn vẫn là heading."""
        html = self._format("KẾT LUẬN")
        self.assertIn("font-weight:700", html)

    def test_mixed_case_vietnamese_not_heading(self):
        """Tiếng Việt có chữ thường không bị nhận diện sai thành heading."""
        html = self._format("Đánh giá chung về hệ thống")
        self.assertNotIn("font-weight:700", html)

    def test_english_all_caps_is_heading(self):
        """Tiếng Anh in hoa vẫn hoạt động như cũ."""
        html = self._format("IMPORTANT NOTE")
        self.assertIn("font-weight:700", html)

    def test_only_numbers_not_heading(self):
        """Dòng chỉ có số và ký tự không bị coi là heading."""
        html = self._format("12345")
        self.assertNotIn("font-weight:700", html)

    def test_too_short_all_caps_not_heading(self):
        """Dòng in hoa <= 5 ký tự không bị coi là heading."""
        html = self._format("NOTE")
        self.assertNotIn("font-weight:700", html)

    # ── Integration: mixed content ───────────────────────────────

    def test_realistic_ai_response(self):
        """Mô phỏng response thực tế từ AI với cả heading và text."""
        raw = "\n".join([
            "Tổng quan:",
            "- Win rate 45% với 120 lệnh",
            "- Profit factor 1.52",
            "",
            "ĐÁNH GIÁ CHUNG",
            "Hệ thống có edge tốt trên trending regime.",
            "",
            "Lý do: EUR/USD có PF 1.8 với 40 lệnh, win rate 52%",
            "",
            "Khuyến nghị:",
            "1. Chỉ trade BUY trên trending_up",
            "2. Min score nên đặt ở 60",
        ])
        html = self._format(raw)
        # 3 headings: "Tổng quan:", "ĐÁNH GIÁ CHUNG", "Khuyến nghị:"
        self.assertEqual(html.count("font-weight:700"), 3)
        self.assertIn("Lý do: EUR/USD", html)
        # Verify "Lý do: EUR/USD..." is NOT wrapped in a heading div
        import re
        heading_pattern = re.compile(
            r"<div style='font-weight:700[^']*'[^>]*>(.*?)</div>"
        )
        for m in heading_pattern.finditer(html):
            self.assertNotIn("EUR/USD", m.group(1),
                             f"Heading contains unexpected text: {m.group(1)}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
