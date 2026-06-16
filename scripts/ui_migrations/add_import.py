import re

def add_import(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if 'from ui.screens.shared import action_button' not in content:
        content = re.sub(
            r'(from PyQt6\.QtWidgets import [^\n]+)',
            r'\1\nfrom ui.screens.shared import action_button',
            content,
            count=1
        )
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

add_import('ui/screens/dashboard_screen.py')
add_import('ui/screens/backtest_screen.py')
print("Imports added.")
