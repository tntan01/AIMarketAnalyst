import re

def process_file(filepath, replacements):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    for old_pattern, new_pattern in replacements:
        content, count = re.subn(old_pattern, new_pattern, content)
        if count == 0:
            print(f"Warning: pattern not found in {filepath}: {old_pattern[:50]}")
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

backtest_repls = [
    (
        r'buttons\s*=\s*QDialogButtonBox.*?root\.addWidget\(buttons\)',
        'buttons_layout = QHBoxLayout()\n        buttons_layout.setContentsMargins(0, 8, 0, 0)\n        buttons_layout.setSpacing(8)\n        buttons_layout.addStretch(1)\n        cancel_btn = action_button("❌ Hủy", primary=False, color="danger")\n        ok_btn = action_button("✅ Áp dụng", primary=True, color="success")\n        buttons_layout.addWidget(cancel_btn)\n        buttons_layout.addWidget(ok_btn)\n        root.addLayout(buttons_layout)'
    ),
    (
        r'buttons\.accepted\.connect\(self\._accept_if_valid\)\s+buttons\.rejected\.connect\(self\.reject\)',
        'ok_btn.clicked.connect(self._accept_if_valid)\n        cancel_btn.clicked.connect(self.reject)'
    ),
    (
        r'buttons\s*=\s*QDialogButtonBox.*?root\.addWidget\(buttons\)',
        'buttons_layout = QHBoxLayout()\n        buttons_layout.addStretch(1)\n        close_btn = action_button("❌ Đóng", primary=False, color="danger")\n        buttons_layout.addWidget(close_btn)\n        root.addLayout(buttons_layout)'
    ),
    (
        r'buttons\.accepted\.connect\(self\.accept\)\s+buttons\.rejected\.connect\(self\.reject\)',
        'close_btn.clicked.connect(self.accept)'
    )
]

# We need to handle the ScannerHelpDialog close button and the OK/Cancel in scanner_screen.py
scanner_repls = [
    (
        r'buttons\s*=\s*QDialogButtonBox\(QDialogButtonBox\.StandardButton\.Ok \| QDialogButtonBox\.StandardButton\.Cancel\).*?root\.addWidget\(buttons\)',
        'buttons_layout = QHBoxLayout()\n        buttons_layout.setContentsMargins(0, 8, 0, 0)\n        buttons_layout.setSpacing(8)\n        buttons_layout.addStretch(1)\n        cancel_btn = action_button("❌ Hủy", primary=False, color="danger")\n        ok_btn = action_button("✅ Áp dụng", primary=True, color="success")\n        buttons_layout.addWidget(cancel_btn)\n        buttons_layout.addWidget(ok_btn)\n        root.addLayout(buttons_layout)'
    ),
    (
        r'buttons\.accepted\.connect\(self\._accept_if_valid\)\s+buttons\.rejected\.connect\(self\.reject\)',
        'ok_btn.clicked.connect(self._accept_if_valid)\n        cancel_btn.clicked.connect(self.reject)'
    ),
    (
        r'buttons\s*=\s*QDialogButtonBox.*?layout\.addWidget\(buttons\)',
        'buttons_layout = QHBoxLayout()\n        buttons_layout.addStretch(1)\n        close_btn = action_button("❌ Đóng", primary=False, color="danger")\n        close_btn.clicked.connect(self.accept)\n        buttons_layout.addWidget(close_btn)\n        layout.addLayout(buttons_layout)'
    ),
    (
        r'buttons\s*\.rejected\s*\.connect\s*\(self\s*\.reject\s*\)\s*buttons\s*\.accepted\s*\.connect\s*\(self\s*\.accept\s*\)',
        '' # Replaced inside the layout setup above
    )
]

process_file('ui/screens/backtest_screen.py', backtest_repls)
process_file('ui/screens/scanner_screen.py', scanner_repls)

print("QDialogButtonBox replaced.")
