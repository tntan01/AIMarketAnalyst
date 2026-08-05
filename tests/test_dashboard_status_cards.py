import sys
from pathlib import Path
import pytest
from PyQt6.QtWidgets import QApplication, QLabel, QFrame
from PyQt6.QtCore import QEvent
from ui.screens.dashboard_screen import DashboardScreen

ROOT = Path(__file__).resolve().parents[1]
BASE_QSS = (ROOT / "ui" / "styles" / "base.qss").read_text(encoding="utf-8")
DARK_QSS = (ROOT / "ui" / "styles" / "dark.qss").read_text(encoding="utf-8")

# Khởi tạo QApplication (nếu chưa có)
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)


class MockEvent(QEvent):
    def __init__(self):
        super().__init__(QEvent.Type.DynamicPropertyChange)

    def propertyName(self):
        return b"state"


def test_dashboard_status_cards():
    screen = DashboardScreen(None, app=None)
    
    # 1. 4 card tồn tại và có chiều cao cố định trong khoảng 56–64px
    assert len(screen.status_cards) == 4, "Should have exactly 4 status cards"
    for key, (frame, value_lbl, detail_lbl) in screen.status_cards.items():
        # Kiểm tra chiều cao cố định trong khoảng 56–64px
        assert 56 <= frame.minimumHeight() <= 64, \
            f"Card '{key}' min height {frame.minimumHeight()} outside 56-64px"
        assert 56 <= frame.maximumHeight() <= 64, \
            f"Card '{key}' max height {frame.maximumHeight()} outside 56-64px"
        
        # 2. Card dùng contract QSS chung, không còn stylesheet cục bộ.
        assert frame.styleSheet() == ""
        assert "QFrame#StatusCard {" in BASE_QSS
        assert "border-radius: 6px" in BASE_QSS
        assert "background: transparent" in BASE_QSS
        
        # 3. Mỗi card có chấm tròn màu (không dùng emoji)
        dots = [child for child in frame.findChildren(QFrame) if child.objectName() == "StatusDot"]
        assert len(dots) == 1, f"Card '{key}' should have exactly one StatusDot frame"
        dot = dots[0]
        assert dot.maximumWidth() == 8 or dot.width() == 8, f"Dot for '{key}' width should be 8px"
        assert dot.maximumHeight() == 8 or dot.height() == 8, f"Dot for '{key}' height should be 8px"
        
        # Kiểm tra xem không có emoji trạng thái cũ
        for label in frame.findChildren(QLabel):
            text = label.text()
            assert "✅" not in text, f"Card '{key}' should not contain success emoji ✅"
            assert "❌" not in text, f"Card '{key}' should not contain error emoji ❌"
            assert "🟡" not in text, f"Card '{key}' should not contain warning emoji 🟡"
            
        # 4. Màu chấm và border đúng theo state khi trạng thái thay đổi
        for test_state, expected_color in [("ok", "#10b981"), ("danger", "#ef4444"), ("warning", "#f59e0b")]:
            frame.setProperty("state", test_state)
            
            # Gửi DynamicPropertyChange event thủ công bằng cách tìm filter trong children
            for child in frame.children():
                if child.__class__.__name__ == "StatusCardEventFilter":
                    # Gửi MockEvent kế thừa từ QEvent
                    child.eventFilter(frame, MockEvent())
            
            assert dot.property("state") == test_state
            assert f'QFrame#StatusDot[state="{test_state}"]' in DARK_QSS
            assert expected_color in DARK_QSS
