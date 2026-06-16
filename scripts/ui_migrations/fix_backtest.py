import re

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

    # 4. Xóa setStyleSheet
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

process_backtest()
print("Backtest fixed.")
