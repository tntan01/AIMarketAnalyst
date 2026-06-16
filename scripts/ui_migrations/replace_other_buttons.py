import sys

def process_dashboard():
    with open('ui/screens/dashboard_screen.py', 'r', encoding='utf-8') as f:
        content = f.read()
        
    replacements = [
        (
            'retry = QPushButton("Thử lại MT5")\n            retry.setObjectName("PrimaryButton")',
            'retry = action_button("🔄 Thử lại MT5", primary=True, color="info")'
        ),
        (
            'help_btn = QPushButton("Giải thích chỉ số")\n        help_btn.setObjectName("MarketHelpBtn")\n        help_btn.setCursor(Qt.CursorShape.PointingHandCursor)',
            'help_btn = action_button("❓ Giải thích chỉ số", primary=True, color="info")'
        ),
        (
            'self.econ_refresh_button = QPushButton("L\\u00e0m m\\u1edbi")\n        self.econ_refresh_button.setObjectName("PrimaryButton")\n        self.econ_refresh_button.setProperty("dashboardRefresh", True)\n        self.econ_refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)\n        self.econ_refresh_button.setToolTip("T\\u1ea3i l\\u1ea1i to\\u00e0n b\\u1ed9 l\\u1ecbch kinh t\\u1ebf")\n        self.econ_refresh_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))\n        self.econ_refresh_button.setFixedHeight(28)\n        self.econ_refresh_button.setMinimumWidth(76)\n        self.econ_refresh_button.setMaximumWidth(92)\n        self.econ_refresh_button.setIconSize(QSize(12, 12))',
            'self.econ_refresh_button = action_button("🔄 Làm mới", primary=True, color="info")\n        self.econ_refresh_button.setProperty("dashboardRefresh", True)\n        self.econ_refresh_button.setToolTip("Tải lại toàn bộ lịch kinh tế")'
        ),
        (
            'refresh_button.setText("L\\u00e0m m\\u1edbi")',
            'refresh_button.setText("🔄 Làm mới")'
        ),
        (
            'ai_btn = QPushButton("🤖 Xem tác động")\n        ai_btn.setObjectName("AIImpactBtn")\n        ai_btn.setCursor(Qt.CursorShape.PointingHandCursor)\n        ai_btn.setStyleSheet(\n            "QPushButton#AIImpactBtn {"\n            "  font-size:13px; font-weight:600; padding:8px 18px;"\n            "  background:#2563eb; color:#fff; border:none; border-radius:6px;"\n            "}"\n            "QPushButton#AIImpactBtn:hover { background:#1d4ed8; }"\n            "QPushButton#AIImpactBtn:disabled { background:#334155; color:#64748b; }"\n        )',
            'ai_btn = action_button("🤖 Xem tác động", primary=True, color="info")'
        ),
        (
            'close_btn = QPushButton("Đóng")\n        close_btn.setObjectName("PrimaryButton")\n        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)',
            'close_btn = action_button("❌ Đóng", primary=True, color="danger")'
        )
    ]
    
    for old, new in replacements:
        if old not in content:
            print(f"Failed to find dashboard string: {repr(old[:50])}")
        else:
            content = content.replace(old, new)
            
    with open('ui/screens/dashboard_screen.py', 'w', encoding='utf-8') as f:
        f.write(content)

def process_backtest():
    with open('ui/screens/backtest_screen.py', 'r', encoding='utf-8') as f:
        content = f.read()
        
    replacements = [
        (
            'self.symbol_button = QPushButton("Chọn mã")\n        self.symbol_button.setObjectName("InlineHelpButton")\n        self.symbol_button.setFixedHeight(34)',
            'self.symbol_button = action_button("🔍 Chọn mã", primary=True, color="info")'
        ),
        (
            'load_btn = QPushButton("📂 Xem lại kết quả backtest")\n        load_btn.setObjectName("LoadFileButton")\n        load_btn.setCursor(Qt.CursorShape.PointingHandCursor)\n        load_btn.setFixedHeight(22)',
            'load_btn = action_button("📂 Xem lại kết quả", primary=True, color="success")'
        ),
        (
            'analyze_btn = QPushButton("🤖 Phân tích")\n        analyze_btn.setObjectName("AnalyzeFileButton")\n        analyze_btn.setCursor(Qt.CursorShape.PointingHandCursor)\n        analyze_btn.setFixedHeight(22)',
            'analyze_btn = action_button("🤖 Phân tích", primary=True, color="info")'
        ),
        (
            'for btn in (load_btn, analyze_btn):\n            btn.setStyleSheet(\n                "QPushButton {"\n                "  font-size: 11px; padding: 1px 8px;"\n                "  background: #0d9488; color: #fff; border: 1px solid #14b8a6; border-radius: 4px;"\n                "}"\n                "QPushButton:hover {"\n                "  background: #0f766e; border-color: #2dd4bf;"\n                "}"\n            )',
            ''
        ),
        (
            'close_btn = QPushButton("Đóng")\n            close_btn.setObjectName("PrimaryButton")',
            'close_btn = action_button("❌ Đóng", primary=True, color="danger")'
        ),
        (
            'self.select_all_button = QPushButton("Chọn tất cả")\n        self.clear_button = QPushButton("Bỏ chọn")\n        self.forex_button = QPushButton("Forex")\n        self.metal_crypto_button = QPushButton("Kim loại/Crypto")\n\n        for button in (\n            self.select_all_button,\n            self.clear_button,\n            self.forex_button,\n            self.metal_crypto_button,\n        ):\n            button.setObjectName("InlineHelpButton")\n            button.setCursor(Qt.CursorShape.PointingHandCursor)',
            'self.select_all_button = action_button("✅ Chọn tất cả", primary=True, color="success")\n        self.clear_button = action_button("❌ Bỏ chọn", primary=True, color="danger")\n        self.forex_button = action_button("💱 Forex", primary=True, color="info")\n        self.metal_crypto_button = action_button("🪙 Kim loại/Crypto", primary=True, color="info")'
        )
    ]
    
    for old, new in replacements:
        if old not in content:
            print(f"Failed to find backtest string: {repr(old[:50])}")
        else:
            content = content.replace(old, new)
            
    with open('ui/screens/backtest_screen.py', 'w', encoding='utf-8') as f:
        f.write(content)

process_dashboard()
process_backtest()
print("Done")
