import sys

content = open('ui/screens/scanner_screen.py', encoding='utf-8').read()

replacements = [
    (
        'self .symbol_select_button =QPushButton ("Chọn mã quét")\n        self .symbol_select_button .setObjectName ("InlineHelpButton")\n        self .symbol_select_button .setCursor (Qt .CursorShape .PointingHandCursor )',
        'self.symbol_select_button = action_button("🔍 Chọn mã quét", primary=True, color="info")'
    ),
    (
        'self .help_button =QPushButton (\'Giải thích ý nghĩa\')\n            self .help_button .setObjectName ("InlineHelpButton")\n            self .help_button .setCursor (Qt .CursorShape .PointingHandCursor )',
        'self.help_button = action_button("❓ Giải thích", primary=True, color="info")'
    ),
    (
        'self.select_all_button = QPushButton("Chọn tất cả khả dụng")\n        self.clear_button = QPushButton("Bỏ chọn")\n        for button in (self.select_all_button, self.clear_button):\n            button.setObjectName("InlineHelpButton")\n            button.setCursor(Qt.CursorShape.PointingHandCursor)\n            controls.addWidget(button)',
        'self.select_all_button = action_button("✅ Chọn tất cả", primary=True, color="success")\n        self.clear_button = action_button("❌ Bỏ chọn", primary=True, color="danger")\n        for button in (self.select_all_button, self.clear_button):\n            controls.addWidget(button)'
    )
]

for old, new in replacements:
    if old not in content:
        print(f"Failed to find: {old[:60]}...")
        sys.exit(1)
    content = content.replace(old, new)

open('ui/screens/scanner_screen.py', 'w', encoding='utf-8').write(content)
print("All buttons replaced successfully!")
