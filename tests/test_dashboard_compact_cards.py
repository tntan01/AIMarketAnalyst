import sys
import pytest
from PyQt6.QtWidgets import QApplication, QLabel
from ui.screens.dashboard_screen import DashboardScreen

# Khởi tạo QApplication (nếu chưa có)
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)


def test_dashboard_compact_cards():
    # Khởi tạo DashboardScreen
    screen = DashboardScreen(None, app=None)
    
    # 1. Kiểm tra 4 card trạng thái tồn tại
    assert len(screen.status_cards) == 4, "Should have exactly 4 status cards"
    for key in ["Kết nối", "Broker", "AI", "Nguồn dữ liệu"]:
        assert key in screen.status_cards, f"Missing status card: {key}"
        
    # 2. Mỗi card có chiều cao trong khoảng 56–64px (cố định, đều nhau)
    for title, (frame, value_lbl, detail_lbl) in screen.status_cards.items():
        assert 56 <= frame.minimumHeight() <= 64, f"Card '{title}' min height {frame.minimumHeight()} outside 56-64px"
        assert 56 <= frame.maximumHeight() <= 64, f"Card '{title}' max height {frame.maximumHeight()} outside 56-64px"
        
    # 3. Dòng subtitle đã bị xóa khỏi header
    found_subtitle = False
    for child in screen.findChildren(QLabel):
        if "Kiểm tra trạng thái hệ thống và bắt đầu phân tích" in child.text():
            found_subtitle = True
            break
    assert not found_subtitle, "Subtitle still present in UI"
    
    # 4. Card hiển thị 2 dòng: dòng detail phải hiện và nằm trong layout
    for title, (frame, value_lbl, detail_lbl) in screen.status_cards.items():
        assert not detail_lbl.isHidden(), f"Detail label for '{title}' should be visible"

        # Kiểm tra xem detail_lbl có nằm trong layout hiển thị của frame hay không
        layout = frame.layout()
        found_detail_in_layout = False
        for i in range(layout.count()):
            item = layout.itemAt(i)
            widget = item.widget()
            if widget == detail_lbl:
                found_detail_in_layout = True
                break
            # Kiểm tra layout con (text VBox chứa cả hai dòng) qua QLayoutItem
            nested_layout = item.layout()
            if nested_layout:
                for j in range(nested_layout.count()):
                    if nested_layout.itemAt(j).widget() == detail_lbl:
                        found_detail_in_layout = True
                        break
            if found_detail_in_layout:
                break
            # Nếu widget con có layout riêng (như right_widget) ta cũng kiểm tra
            if widget:
                sub_layout = widget.layout()
                if sub_layout:
                    for j in range(sub_layout.count()):
                        if sub_layout.itemAt(j).widget() == detail_lbl:
                            found_detail_in_layout = True
                            break
        assert found_detail_in_layout, f"Detail label for '{title}' should be in the layout hierarchy"
