import re

def process_file(filepath, replacements):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    for old, new in replacements:
        content = content.replace(old, new)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

backtest_repls = [
    (
        """        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_btn is not None:
            ok_btn.setText("✅ Áp dụng")
            ok_btn.setObjectName("PrimaryButton"); ok_btn.setProperty("compactPrimary", "true")
        if cancel_btn is not None:
            cancel_btn.setText("❌ Hủy")
            cancel_btn.setObjectName("SecondaryButton")
        root.addWidget(buttons)""",
        """        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 8, 0, 0)
        buttons_layout.setSpacing(8)
        buttons_layout.addStretch(1)
        cancel_btn = action_button("❌ Hủy", primary=False, color="danger")
        ok_btn = action_button("✅ Áp dụng", primary=True, color="success")
        buttons_layout.addWidget(cancel_btn)
        buttons_layout.addWidget(ok_btn)
        root.addLayout(buttons_layout)"""
    ),
    (
        """        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)""",
        """        ok_btn.clicked.connect(self._accept_if_valid)
        cancel_btn.clicked.connect(self.reject)"""
    )
]

scanner_repls = [
    (
        """        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_btn is not None:
            ok_btn.setText("✅ Áp dụng")
            ok_btn.setObjectName("PrimaryButton"); ok_btn.setProperty("compactPrimary", "true")
        if cancel_btn is not None:
            cancel_btn.setText("❌ Hủy")
            cancel_btn.setObjectName("SecondaryButton")
        root.addWidget(buttons)""",
        """        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 8, 0, 0)
        buttons_layout.setSpacing(8)
        buttons_layout.addStretch(1)
        cancel_btn = action_button("❌ Hủy", primary=False, color="danger")
        ok_btn = action_button("✅ Áp dụng", primary=True, color="success")
        buttons_layout.addWidget(cancel_btn)
        buttons_layout.addWidget(ok_btn)
        root.addLayout(buttons_layout)"""
    ),
    (
        """        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)""",
        """        ok_btn.clicked.connect(self._accept_if_valid)
        cancel_btn.clicked.connect(self.reject)"""
    ),
    (
        """        buttons =QDialogButtonBox (QDialogButtonBox .StandardButton .Close )
        buttons .rejected .connect (self .reject )
        buttons .accepted .connect (self .accept )
        close_btn =buttons .button (QDialogButtonBox .StandardButton .Close )
        if close_btn is not None :
            close_btn.setText('❌ Đóng')
            close_btn.setObjectName("SecondaryButton")
            close_btn.clicked.connect(self.accept)
        layout .addWidget (buttons )""",
        """        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch(1)
        close_btn = action_button("❌ Đóng", primary=False, color="danger")
        close_btn.clicked.connect(self.accept)
        buttons_layout.addWidget(close_btn)
        layout.addLayout(buttons_layout)"""
    )
]

process_file('ui/screens/backtest_screen.py', backtest_repls)
process_file('ui/screens/scanner_screen.py', scanner_repls)

print("Direct string replacement done.")
