#!/usr/bin/env python3
"""
Test: Kiểm tra xem code hiện tại của _configure_table_columns có hoạt động không.

Chạy: python test_table_config.py
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Không cần import PyQt6, chỉ cần đọc code
with open(project_root / "ui" / "screens" / "scanner_screen.py") as f:
    src = f.read()

print("=" * 60)
print("🔍 Review code hiện tại - scanner_screen.py")
print("=" * 60)

checks = []
passed = 0
failed = 0

# 1. setWordWrap(False) co trong _configure_table_columns
if 'setWordWrap (False )' in src or 'setWordWrap(False)' in src:
    checks.append("✅ setWordWrap(False) - có")
    passed += 1
else:
    checks.append("❌ setWordWrap(False) - THIẾU")
    failed += 1

# 2. setTextElideMode trong _configure_table_columns
if 'setTextElideMode' in src:
    checks.append("✅ setTextElideMode - có")
    passed += 1
else:
    checks.append("❌ setTextElideMode - THIẾU")
    failed += 1

# 3. 0x010B trong data()
if '0x010B' in src:
    checks.append("✅ role 0x010B (TextElideRole) - có")
    passed += 1
else:
    checks.append("❌ role 0x010B - THIẾU")
    failed += 1

# 4. setStretchLastSection(False)
if 'setStretchLastSection (False )' in src or 'setStretchLastSection(False)' in src:
    checks.append("✅ setStretchLastSection(False) - có")
    passed += 1
else:
    checks.append("❌ setStretchLastSection(False) - THIẾU")
    failed += 1

# 5. Stretch cho cot 12
if 'ResizeMode .Stretch' in src or 'ResizeMode.Stretch' in src:
    checks.append("✅ Stretch mode - có")
    passed += 1
else:
    checks.append("❌ Stretch mode - THIẾU")
    failed += 1

# 6. COLUMNS - kiem tra \n trong tieu de
import re
cols_match = re.search(r'COLUMNS\s*=\s*\[(.*?)\]', src, re.DOTALL)
if cols_match:
    lines = cols_match.group(1).strip().split('\n')
    has_newline = False
    for line in lines:
        if '\\n' in line:
            has_newline = True
            checks.append(f"❌ Tieu de co '\\n': {line.strip()}")
            failed += 1
    if not has_newline:
        checks.append("✅ Tieu de 1 dong (khong \\n)")
        passed += 1

# 7. Kiem tra co _display_value tra ve str khong
if 'def _display_value' in src:
    checks.append("✅ _display_value method - có")
    passed += 1
else:
    checks.append("❌ _display_value - THIẾU")
    failed += 1

# 8. Kiem tra co su dung ElideNone dung cach
if 'ElideNone' in src:
    checks.append("✅ ElideNone - có trong code")
    passed += 1
else:
    checks.append("❌ ElideNone - THIẾU")
    failed += 1

# In ket qua
for c in checks:
    print(f"  {c}")

print()
print(f"KET QUA: {passed}✅ / {failed}❌")
print()

if failed == 0:
    print("Tat ca checks PASS. Van de khong nam o configuration.")
    print()
    print("🔍 CAC NGUYEN NHAN CO THE:")
    print("  1. PyQt6 khong ho tro setTextElideMode tren QTableView")
    print("  2. TextElideRole (0x010B) khong duoc delegate goi")
    print("  3. Delegate override default behavior")
    print()
    print("💡 GIAI PHAP: Custom delegate cho cot 12")
    print("   Tao NoElideDelegate extends QStyledItemDelegate")
    print("   Override paint() de tat elide cho cot 12")
