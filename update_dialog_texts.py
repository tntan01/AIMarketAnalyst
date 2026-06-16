import re

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Thêm emoji vào Áp dụng, Hủy, Đóng trong setText
    replacements = [
        (r'ok_btn\.setText\("Áp dụng"\)', 'ok_btn.setText("✅ Áp dụng")'),
        (r'cancel_btn\.setText\("Hủy"\)', 'cancel_btn.setText("❌ Hủy")'),
        (r'close_btn\.setText\("Đóng"\)', 'close_btn.setText("❌ Đóng")'),
        (r'ok_btn\.setObjectName\("PrimaryButton"\)', 'ok_btn.setObjectName("PrimaryButton"); ok_btn.setProperty("compactPrimary", "true")'),
        (r'cancel_btn\.setObjectName\("SecondaryButton"\)', 'cancel_btn.setObjectName("SecondaryButton")'),
    ]

    for old, new in replacements:
        content = re.sub(old, new, content)

    # Đảm bảo các nút trong QDialogButtonBox cũng có compactPrimary nếu có
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

process_file('ui/screens/backtest_screen.py')
process_file('ui/screens/scanner_screen.py')

print("QDialogButtonBox text updated.")
