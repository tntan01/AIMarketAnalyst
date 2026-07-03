"""
Test strip markdown (*) trong list items của _format_ai_to_html.
"""
import sys
import unittest
from PyQt6.QtWidgets import QApplication


class TestStripMarkdownInListItems(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    @classmethod
    def _format(cls, raw: str, light: bool = False) -> str:
        from ui.screens.backtest_screen import BacktestScreen
        return BacktestScreen._format_ai_to_html(raw, light)

    # ── Bullet list items: strip * ────────────────────────────────

    def test_bullet_item_strips_surrounding_asterisks(self):
        """*text quan trọng* trong bullet → * bị strip."""
        html = self._format("- Đây là *điểm quan trọng* cần lưu ý")
        self.assertNotIn("*điểm quan trọng*", html)
        self.assertIn("điểm quan trọng", html)

    def test_bullet_item_strips_leading_asterisks(self):
        """*text* ở đầu bullet → * bị strip."""
        html = self._format("- *Khuyến nghị:* nên trade BUY")
        self.assertNotIn("*Khuyến nghị:*", html)
        self.assertIn("Khuyến nghị:", html)

    def test_bullet_item_preserves_non_markdown_text(self):
        """Bullet không có markdown → giữ nguyên nội dung (số được highlight)."""
        html = self._format("- Win rate 45% với 120 lệnh")
        self.assertIn("Win rate", html)
        self.assertIn("45%", html)

    def test_multiple_bullet_items_all_stripped(self):
        """Nhiều bullet items → tất cả đều strip markdown."""
        html = self._format(
            "- *Ưu điểm:* PF 1.8\n"
            "- *Nhược điểm:* drawdown 15%\n"
            "- Kết luận chung"
        )
        self.assertNotIn("*Ưu điểm:*", html)
        self.assertNotIn("*Nhược điểm:*", html)
        self.assertIn("Ưu điểm:", html)
        self.assertIn("Nhược điểm:", html)
        self.assertIn("Kết luận chung", html)

    # ── Numbered list items: strip * ──────────────────────────────

    def test_numbered_item_strips_asterisks(self):
        """*text* trong numbered list → * bị strip."""
        html = self._format("1. Chỉ trade *BUY* trên trending_up")
        self.assertNotIn("*BUY*", html)
        self.assertIn("BUY", html)

    def test_numbered_item_without_markdown_unchanged(self):
        """Numbered list không markdown → giữ nguyên."""
        html = self._format("1. Min score nên đặt ở 60")
        self.assertIn("Min score nên đặt ở 60", html)

    # ── Regular text: strip * (vẫn hoạt động như cũ) ─────────────

    def test_regular_text_still_strips_asterisks(self):
        """Text thường vẫn strip * như trước (không regression)."""
        html = self._format("Đây là *text quan trọng* trong phân tích")
        self.assertNotIn("*text quan trọng*", html)
        self.assertIn("text quan trọng", html)

    # ── Heading: strip * (vẫn hoạt động như cũ) ──────────────────

    def test_heading_still_strips_asterisks(self):
        """Heading vẫn strip * như trước."""
        html = self._format("*Tổng quan:*")
        self.assertNotIn("*Tổng quan:*", html)
        self.assertIn("Tổng quan:", html)

    # ── Edge cases ────────────────────────────────────────────────

    def test_empty_asterisks_only(self):
        """Bullet chỉ có ** → strip thành rỗng."""
        html = self._format("- **")
        self.assertIn("<li", html)
        self.assertNotIn("*", html.replace("</li>", "").split("<li")[-1])

    def test_nested_asterisks_in_mixed_list(self):
        """Kết hợp bullet, numbered, text thường → tất cả strip *."""
        raw = (
            "- *Ưu điểm:* PF cao\n"
            "1. *Khuyến nghị:* tăng min_score\n"
            "Đây là *kết luận* cuối cùng\n"
        )
        html = self._format(raw)
        self.assertNotIn("*Ưu điểm:*", html)
        self.assertNotIn("*Khuyến nghị:*", html)
        self.assertNotIn("*kết luận*", html)
        self.assertIn("Ưu điểm:", html)
        self.assertIn("Khuyến nghị:", html)
        self.assertIn("kết luận", html)

    def test_realistic_ai_bullet_response(self):
        """Mô phỏng response AI thực tế với markdown trong bullet."""
        raw = (
            "Khuyến nghị:\n"
            "- *Regime tốt nhất:* trending_up với PF *1.8* và win rate *52%*\n"
            "- *Regime tệ nhất:* ranging với PF *0.7*\n"
            "- Nên *chỉ trade BUY* trên trending_up\n"
            "- *Min score* tối ưu: *60-65*\n"
        )
        html = self._format(raw)
        # Tất cả dấu * bao quanh text phải bị strip
        self.assertNotIn("*Regime tốt nhất:*", html)
        self.assertNotIn("*Regime tệ nhất:*", html)
        self.assertNotIn("*chỉ trade BUY*", html)
        self.assertNotIn("*Min score*", html)
        self.assertNotIn("*60-65*", html)
        # Nội dung thật vẫn hiển thị (underscores bị _esc strip)
        self.assertIn("Regime tốt nhất:", html)
        self.assertIn("trending", html)
        self.assertIn("Min score", html)
        # Số trong _highlight_numbers vẫn hoạt động (1.8, 52%, 0.7 được highlight)
        self.assertIn("1.8", html)
        self.assertIn("52%", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
