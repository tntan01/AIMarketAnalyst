from __future__ import annotations

NAV_ITEMS = [
    ("dashboard", "Bảng điều khiển"),
    ("scanner", "Quét thị trường"),
    ("orders", "Quản lý lệnh"),
    ("backtest", "Backtest"),
    ("journal", "Nhật ký"),
    ("settings", "Cài đặt"),
]

# Glyph flat cho icon rail (ui/icons.py) — mỗi key trỏ tới tên glyph.
NAV_ICONS = {
    "dashboard": "bar-chart",
    "scanner": "search",
    "orders": "clipboard",
    "backtest": "flask",
    "journal": "book-open",
    "settings": "gear",
}
