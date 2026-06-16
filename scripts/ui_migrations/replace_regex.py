import re
import sys

def process_dashboard():
    with open('ui/screens/dashboard_screen.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Thử lại MT5
    content = re.sub(
        r'retry\s*=\s*QPushButton\([^)]+\)\s+retry\.setObjectName\("PrimaryButton"\)\s+retry\.setCursor\(Qt\.CursorShape\.PointingHandCursor\)',
        'retry = action_button("🔄 Thử lại MT5", primary=True, color="info")',
        content
    )

    # 2. Giải thích chỉ số
    content = re.sub(
        r'help_btn\s*=\s*QPushButton\("Giải thích chỉ số"\)\s+help_btn\.setObjectName\("MarketHelpBtn"\)\s+help_btn\.setCursor\(Qt\.CursorShape\.PointingHandCursor\)',
        'help_btn = action_button("❓ Giải thích chỉ số", primary=True, color="info")',
        content
    )

    # 3. Làm mới
    content = re.sub(
        r'self\.econ_refresh_button\s*=\s*QPushButton\("[^"]+"\)\s+self\.econ_refresh_button\.setObjectName\("PrimaryButton"\)\s+self\.econ_refresh_button\.setProperty\("dashboardRefresh", True\)\s+self\.econ_refresh_button\.setCursor\(Qt\.CursorShape\.PointingHandCursor\)\s+self\.econ_refresh_button\.setToolTip\("[^"]+"\)\s+self\.econ_refresh_button\.setIcon\([^)]+\)\s+self\.econ_refresh_button\.setFixedHeight\(28\)\s+self\.econ_refresh_button\.setMinimumWidth\(76\)\s+self\.econ_refresh_button\.setMaximumWidth\(92\)\s+self\.econ_refresh_button\.setIconSize\(QSize\(12, 12\)\)',
        'self.econ_refresh_button = action_button("🔄 Làm mới", primary=True, color="info")\n        self.econ_refresh_button.setProperty("dashboardRefresh", True)\n        self.econ_refresh_button.setToolTip("Tải lại toàn bộ lịch kinh tế")',
        content
    )
    
    content = re.sub(
        r'refresh_button\.setText\("L\\u00e0m m\\u1edbi"\)',
        'refresh_button.setText("🔄 Làm mới")',
        content
    )

    # 4. Xem tác động
    content = re.sub(
        r'ai_btn\s*=\s*QPushButton\([^)]+\)\s+ai_btn\.setObjectName\("AIImpactBtn"\)\s+ai_btn\.setCursor\(Qt\.CursorShape\.PointingHandCursor\)\s+ai_btn\.setStyleSheet\([^)]+\)',
        'ai_btn = action_button("🤖 Xem tác động", primary=True, color="info")',
        content
    )

    # 5. Đóng (2 chỗ)
    content = re.sub(
        r'close_btn\s*=\s*QPushButton\("Đóng"\)\s+close_btn\.setObjectName\("PrimaryButton"\)\s+close_btn\.setCursor\(Qt\.CursorShape\.PointingHandCursor\)',
        'close_btn = action_button("❌ Đóng", primary=True, color="danger")',
        content
    )

    with open('ui/screens/dashboard_screen.py', 'w', encoding='utf-8') as f:
        f.write(content)

def process_backtest():
    with open('ui/screens/backtest_screen.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Chọn mã
    content = re.sub(
        r'self\.symbol_button\s*=\s*QPushButton\("Chọn mã"\)\s+self\.symbol_button\.setObjectName\("InlineHelpButton"\)\s+self\.symbol_button\.setFixedHeight\(34\)',
        'self.symbol_button = action_button("🔍 Chọn mã", primary=True, color="info")',
        content
    )

    # 2. Xem lại kết quả backtest
    content = re.sub(
        r'load_btn\s*=\s*QPushButton\("📂 Xem lại kết quả backtest"\)\s+load_btn\.setObjectName\("LoadFileButton"\)\s+load_btn\.setCursor\(Qt\.CursorShape\.PointingHandCursor\)\s+load_btn\.setFixedHeight\(22\)',
        'load_btn = action_button("📂 Xem lại kết quả", primary=True, color="success")',
        content
    )

    # 3. Phân tích
    content = re.sub(
        r'analyze_btn\s*=\s*QPushButton\("🤖 Phân tích"\)\s+analyze_btn\.setObjectName\("AnalyzeFileButton"\)\s+analyze_btn\.setCursor\(Qt\.CursorShape\.PointingHandCursor\)\s+analyze_btn\.setFixedHeight\(22\)',
        'analyze_btn = action_button("🤖 Phân tích", primary=True, color="info")',
        content
    )

    # 4. Xóa setStyleSheet cho load_btn, analyze_btn
    content = re.sub(
        r'for btn in \(load_btn, analyze_btn\):\s*btn\.setStyleSheet\([^)]+\)',
        '',
        content
    )

    # 5. Đóng
    content = re.sub(
        r'close_btn\s*=\s*QPushButton\("Đóng"\)\s+close_btn\.setObjectName\("PrimaryButton"\)',
        'close_btn = action_button("❌ Đóng", primary=True, color="danger")',
        content
    )

    # 6. Dialog buttons
    content = re.sub(
        r'self\.select_all_button\s*=\s*QPushButton\("Chọn tất cả"\)\s+self\.clear_button\s*=\s*QPushButton\("Bỏ chọn"\)\s+self\.forex_button\s*=\s*QPushButton\("Forex"\)\s+self\.metal_crypto_button\s*=\s*QPushButton\("Kim loại/Crypto"\)\s+for button in \(\s*self\.select_all_button,\s*self\.clear_button,\s*self\.forex_button,\s*self\.metal_crypto_button,\s*\):\s*button\.setObjectName\("InlineHelpButton"\)\s*button\.setCursor\(Qt\.CursorShape\.PointingHandCursor\)',
        'self.select_all_button = action_button("✅ Chọn tất cả", primary=True, color="success")\n        self.clear_button = action_button("❌ Bỏ chọn", primary=True, color="danger")\n        self.forex_button = action_button("💱 Forex", primary=True, color="info")\n        self.metal_crypto_button = action_button("🪙 Kim loại/Crypto", primary=True, color="info")',
        content
    )

    with open('ui/screens/backtest_screen.py', 'w', encoding='utf-8') as f:
        f.write(content)

process_dashboard()
process_backtest()
print("Success")
