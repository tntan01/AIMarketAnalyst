import sys

content = open('ui/screens/settings_screen.py', encoding='utf-8').read()

replacements = [
    ('self.ai_catalog_add_button = action_button("Thêm", primary=True)\n        self.ai_catalog_update_button = action_button("Sửa")\n        self.ai_catalog_delete_button = action_button("Xóa")\n        self._set_compact_action_button(self.ai_catalog_add_button)',
     'self.ai_catalog_add_button = action_button("➕ Thêm", primary=True)\n        self.ai_catalog_update_button = action_button("✏️ Sửa")\n        self.ai_catalog_delete_button = action_button("🗑️ Xóa", primary=True, color="danger")'),
     
    ('self.ai_test_button = action_button("Kiểm tra")\n        self.ai_save_button = action_button("Lưu", primary=True)\n        self.ai_delete_button = action_button("Xóa")\n        self._set_compact_action_button(self.ai_save_button)',
     'self.ai_test_button = action_button("🧪 Kiểm tra", primary=True, color="info")\n        self.ai_save_button = action_button("💾 Lưu", primary=True, color="success")\n        self.ai_delete_button = action_button("🗑️ Xóa", primary=True, color="danger")'),
     
    ('self.mt5_retry_button = action_button("Thử kết nối lại", primary=True)',
     'self.mt5_retry_button = action_button("🔄 Thử kết nối lại", primary=True, color="info")'),
     
    ('self.mt5_detect_button = action_button("Tự phát hiện mã broker", primary=True)\n        self.mt5_detect_button.clicked.connect(self.refresh_mt5_status)\n        mt5_button_row.addWidget(self.mt5_detect_button)\n        self.mt5_symbol_settings_button = action_button("Lưu cấu hình mã quét", primary=True)',
     'self.mt5_detect_button = action_button("🔍 Tự phát hiện mã broker", primary=True, color="info")\n        self.mt5_detect_button.clicked.connect(self.refresh_mt5_status)\n        mt5_button_row.addWidget(self.mt5_detect_button)\n        self.mt5_symbol_settings_button = action_button("💾 Lưu cấu hình mã quét", primary=True, color="success")'),
     
    ('self.trading_save_button = action_button("Lưu cài đặt giao dịch", primary=True)',
     'self.trading_save_button = action_button("💾 Lưu cài đặt giao dịch", primary=True, color="success")'),
     
    ('self.display_save_button = action_button("Lưu hiển thị", primary=True)',
     'self.display_save_button = action_button("💾 Lưu hiển thị", primary=True, color="success")'),
     
    ('self.advanced_save_button = action_button("Lưu nâng cao", primary=True)',
     'self.advanced_save_button = action_button("💾 Lưu nâng cao", primary=True, color="success")'),
     
    ('frame.layout().addWidget(action_button("Lưu nâng cao", primary=True))',
     'frame.layout().addWidget(action_button("💾 Lưu nâng cao", primary=True, color="success"))')
]

for old, new in replacements:
    if old not in content:
        print(f'Error finding: {old[:50]}...')
        sys.exit(1)
    content = content.replace(old, new)

open('ui/screens/settings_screen.py', 'w', encoding='utf-8').write(content)
print('Done!')
