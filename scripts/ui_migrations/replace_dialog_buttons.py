import re
import sys

def process_file(filepath, replacements, add_import=False):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    for old_pattern, new_pattern in replacements:
        content, count = re.subn(old_pattern, new_pattern, content)
        if count == 0:
            print(f"Warning: pattern not found in {filepath}: {old_pattern[:50]}")
            
    if add_import and 'action_button' not in content:
        content = re.sub(
            r'(from PyQt6\.QtWidgets import [^\n]+)',
            r'\1\nfrom ui.screens.shared import action_button',
            content,
            count=1
        )
            
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

backtest_repls = [
    (
        r'self\.select_all_button\s*=\s*QPushButton\("Chọn tất cả"\)\s+self\.clear_button\s*=\s*QPushButton\("Bỏ chọn"\)\s+self\.forex_button\s*=\s*QPushButton\("Forex"\)\s+self\.metal_crypto_button\s*=\s*QPushButton\("Kim loại/Crypto"\)\s+for button in \(self\.select_all_button, self\.clear_button, self\.forex_button, self\.metal_crypto_button\):\s+button\.setObjectName\("InlineHelpButton"\)\s+button\.setFixedHeight\(30\)',
        'self.select_all_button = action_button("✅ Chọn tất cả", primary=True, color="success")\n        self.clear_button = action_button("❌ Bỏ chọn", primary=True, color="danger")\n        self.forex_button = action_button("💱 Forex", primary=True, color="info")\n        self.metal_crypto_button = action_button("🪙 Kim loại/Crypto", primary=True, color="info")'
    )
]

scanner_repls = [
    (
        r'self\.select_all_button\s*=\s*QPushButton\("Chọn tất cả khả dụng"\)\s+self\.clear_button\s*=\s*QPushButton\("Bỏ chọn"\)\s+for button in \(self\.select_all_button, self\.clear_button\):\s+button\.setObjectName\("InlineHelpButton"\)\s+button\.setFixedHeight\(30\)',
        'self.select_all_button = action_button("✅ Chọn tất cả khả dụng", primary=True, color="success")\n        self.clear_button = action_button("❌ Bỏ chọn", primary=True, color="danger")'
    )
]

journal_repls = [
    (
        r'close_btn\s*=\s*QPushButton\("Đóng"\)\s+close_btn\.setObjectName\("SecondaryButton"\)',
        'close_btn = action_button("❌ Đóng", primary=True, color="danger")'
    )
]

process_file('ui/screens/backtest_screen.py', backtest_repls)
process_file('ui/screens/scanner_screen.py', scanner_repls)
process_file('ui/screens/journal_screen.py', journal_repls, add_import=True)

print("Dialog buttons updated.")
