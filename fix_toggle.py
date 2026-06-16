import sys

# Update scanner_screen.py
content = open('ui/screens/scanner_screen.py', encoding='utf-8').read()
old_code = 'self .auto_trade_check =QPushButton ("Tự động vào lệnh MT5")\n        self .auto_trade_check .setObjectName ("AutoTradeToggle")\n        self .auto_trade_check .setCheckable (True )\n        self .auto_trade_check .setCursor (Qt .CursorShape .PointingHandCursor )\n        self .auto_trade_check .setFixedHeight (34 )'
new_code = 'self.auto_trade_check = QPushButton("🤖 Tự động vào lệnh MT5")\n        self.auto_trade_check.setObjectName("AutoTradeToggle")\n        self.auto_trade_check.setCheckable(True)\n        self.auto_trade_check.setCursor(Qt.CursorShape.PointingHandCursor)'
if old_code not in content:
    print('Failed to find python snippet')
    sys.exit(1)
content = content.replace(old_code, new_code)
open('ui/screens/scanner_screen.py', 'w', encoding='utf-8').write(content)

# Update ui/styles.qss
qss = open('ui/styles.qss', encoding='utf-8').read()
old_qss = 'QPushButton#AutoTradeToggle {\n  color: #e5e7eb;\n  font-weight: 700;\n  padding: 4px 10px;\n  border: 1px solid #475569;\n  border-radius: 6px;\n  background: #0b1220;\n}'
new_qss = 'QPushButton#AutoTradeToggle {\n  color: #e5e7eb;\n  font-weight: 700;\n  min-height: 24px;\n  max-height: 24px;\n  padding: 0px 6px;\n  border: 1px solid #475569;\n  border-radius: 6px;\n  background: #0b1220;\n}'
if old_qss not in qss:
    print('Failed to find qss snippet')
    sys.exit(1)
qss = qss.replace(old_qss, new_qss)
open('ui/styles.qss', 'w', encoding='utf-8').write(qss)

print('Success')
