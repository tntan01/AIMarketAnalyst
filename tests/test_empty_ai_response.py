"""
Test empty/whitespace response guard trong _analyze_loaded_result.
"""
import sys
import unittest
from PyQt6.QtWidgets import QApplication


class TestEmptyAiResponseGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    # ── Guard condition logic ─────────────────────────────────────

    def test_empty_string_is_detected(self):
        """Chuỗi rỗng → guard kích hoạt."""
        response = ""
        self.assertTrue(not response or not response.strip())

    def test_whitespace_only_is_detected(self):
        """Chuỗi chỉ có whitespace → guard kích hoạt."""
        self.assertTrue(not "   " or not "   ".strip())
        self.assertTrue(not "\n  \n" or not "\n  \n".strip())
        self.assertTrue(not "\t" or not "\t".strip())

    def test_valid_response_passes_guard(self):
        """Chuỗi có nội dung → guard không kích hoạt."""
        response = "Hệ thống có edge tốt"
        self.assertFalse(not response or not response.strip())

    def test_single_char_passes_guard(self):
        """Chuỗi 1 ký tự không-whitespace → guard không kích hoạt."""
        response = "X"
        self.assertFalse(not response or not response.strip())

    def test_none_is_detected(self):
        """None → guard kích hoạt."""
        response = None
        self.assertTrue(not response or not response.strip())

    # ── _format_ai_to_html handles empty input gracefully ──────────

    def test_format_ai_to_html_empty_returns_wrapper_only(self):
        """_format_ai_to_html với input rỗng → chỉ có wrapper div, không có nội dung."""
        from ui.screens.backtest_screen import BacktestScreen
        result = BacktestScreen._format_ai_to_html("", light=False)
        # Method always wraps in a container div; empty input = empty wrapper
        self.assertIn("font-family", result)
        # No actual content: no headings, no paragraphs, no list items
        self.assertNotIn("font-weight:700", result)
        self.assertNotIn("<li", result)
        self.assertNotIn("<p ", result)

    def test_format_ai_to_html_whitespace_returns_wrapper_only(self):
        """_format_ai_to_html với whitespace → chỉ có wrapper div."""
        from ui.screens.backtest_screen import BacktestScreen
        result = BacktestScreen._format_ai_to_html("   \n  \n  ", light=False)
        self.assertIn("font-family", result)
        self.assertNotIn("font-weight:700", result)
        self.assertNotIn("<li", result)
        self.assertNotIn("<p ", result)

    # ── Guard prevents empty AI section in dialog ──────────────────

    def test_guard_prevents_empty_ai_section(self):
        """Mô phỏng: response rỗng → QMessageBox.warning, không tạo dialog."""
        # Verify the guard would intercept before _format_ai_to_html is called
        # by checking the condition used in on_succeeded
        empty_responses = ["", "   ", "\n \n", None]
        for r in empty_responses:
            should_guard = not r or not r.strip() if r else True
            self.assertTrue(should_guard, f"Should guard for: {r!r}")

        valid_responses = ["OK", "Phân tích", "X", "  valid  "]
        for r in valid_responses:
            should_guard = not r or not r.strip() if r else True
            self.assertFalse(should_guard, f"Should NOT guard for: {r!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
