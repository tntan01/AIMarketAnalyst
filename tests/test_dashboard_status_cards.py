import sys
import pytest
from PyQt6.QtWidgets import QApplication, QLabel, QFrame
from PyQt6.QtCore import QEvent
from ui.screens.dashboard_screen import DashboardScreen

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
    
    # 1. 4 card tồn tại và có chiều cao 44px
    assert len(screen.status_cards) == 4, "Should have exactly 4 status cards"
    for key, (frame, value_lbl, detail_lbl) in screen.status_cards.items():
        # Kiểm tra chiều cao cố định 44px
        assert frame.height() == 44 or frame.maximumHeight() == 44 or frame.minimumHeight() == 44, \
            f"Card '{key}' height should be fixed to 44px"
        
        # 2. Card có border 1px solid, border-radius 6px, background transparent
        style = frame.styleSheet()
        assert "border: 1px solid" in style, f"Card '{key}' should have border styling"
        assert "border-radius: 6px" in style, f"Card '{key}' border-radius should be 6px"
        assert "background: transparent" in style, f"Card '{key}' background should be transparent"
        
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
            
            # Đọc stylesheet mới sau khi thay đổi state
            dot_style = dot.styleSheet()
            frame_style = frame.styleSheet()
            
            assert expected_color in dot_style, \
                f"Dot color for state '{test_state}' should be '{expected_color}' but got '{dot_style}'"
            assert f"border: 1px solid {expected_color}" in frame_style, \
                f"Frame border color for state '{test_state}' should match '{expected_color}'"
