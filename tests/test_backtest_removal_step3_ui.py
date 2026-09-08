"""Bước 3 gỡ Backtest (2026-09-08): xác minh UI không còn phụ thuộc Backtest.

Kiểm tra khởi động/điều hướng (MainWindow), lưu Settings (bảng mã quét với
quyền Quét + Auto-trade độc lập) và màn Scanner (danh sách quét theo
scan_enabled) — tất cả chạy offscreen với app giả, không MT5, không lệnh thật.
"""

from __future__ import annotations

import os
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QCheckBox, QMessageBox

from config.settings import SymbolScanSettings
from tools.capture_ui_style_baseline import _fake_app, _patch_external_activity
from tools.ui_layout_audit import load_visual_qa_fonts
from ui.main_window import MainWindow, nav_route
from ui.screens.scanner_screen import (
    ScannerScreen,
    ScannerSymbolSelectionDialog,
)
from ui.screens.settings_screen import SettingsScreen


def _app():
    return QApplication.instance() or QApplication([])


def test_main_window_has_no_backtest_route_and_falls_back_to_dashboard() -> None:
    app = _app()
    load_visual_qa_fonts()
    fake_app = _fake_app("dark")

    with ExitStack() as stack:
        _patch_external_activity(stack)
        with patch("ui.screens.scanner_screen.QTimer.singleShot"), patch.object(
            QMessageBox, "warning"
        ):
            window = MainWindow(fake_app)
        try:
            # Màn Backtest không còn được đăng ký.
            assert "backtest" not in window.screens
            assert "backtest" not in window.nav_buttons
            assert len(window.nav_buttons) == 6
            assert set(window.screens) == {
                "dashboard",
                "scanner",
                "supply_demand",
                "orders",
                "scanner_detail",
                "journal",
                "journal_detail",
                "settings",
            }

            # Điều hướng cũ "backtest" ⇒ ứng dụng mở về màn hình hợp lệ.
            window.navigate("scanner")
            assert window.stack.currentWidget() is window.screens["scanner"]
            window.navigate("backtest")
            assert window.stack.currentWidget() is window.screens["dashboard"]

            # Các tuyến live khác vẫn hoạt động (Nhật ký phải giữ nguyên).
            window.navigate("journal")
            assert window.stack.currentWidget() is window.screens["journal"]
            window.navigate("settings")
            assert window.stack.currentWidget() is window.screens["settings"]
        finally:
            window.close()
    app.processEvents()

    # nav_route không còn khóa "backtest" và fallback an toàn.
    assert nav_route("journal") == "journal"
    assert nav_route("backtest") == "dashboard"


def test_settings_table_has_independent_scan_and_auto_trade_controls(
    tmp_path: Path,
) -> None:
    from services.settings_service import SettingsService

    app = _app()
    load_visual_qa_fonts()
    fake_app = _fake_app("dark")
    # Settings nền: 1 mã đã bật quét (cấu hình mới từ Bước 2), chưa có
    # bằng chứng kiểm định ⇒ không được cấp quyền auto-trade.
    service = SettingsService(tmp_path / "settings.json")
    base = service.load()
    base.trading.symbol_settings["EUR/USD"] = SymbolScanSettings(
        scan_enabled=True,
    )
    fake_app.settings_service.settings = base

    with ExitStack() as stack:
        _patch_external_activity(stack)
        screen = SettingsScreen(None, app=fake_app)
        try:
            table = screen.mt5_symbols_table
            # Bảng 10 cột: không còn 4 cột bằng chứng "…BT".
            assert table.columnCount() == 10
            headers = [
                table.horizontalHeaderItem(i).text()
                for i in range(table.columnCount())
            ]
            assert headers[5] == "Quét"
            assert headers[9] == "Auto-trade"
            assert not any("BT" in header for header in headers)

            # Nút dán cấu hình backtest đã gỡ.
            assert not hasattr(screen, "mt5_paste_config_button")
            assert not hasattr(screen, "_paste_backtest_configs")
            assert not hasattr(screen, "_show_backtest_preview")

            symbols = list(screen.mt5_display_symbols)
            row = symbols.index("EUR/USD")
            scan_box = table.cellWidget(row, 5).findChild(QCheckBox)
            auto_box = table.cellWidget(row, 9).findChild(QCheckBox)
            assert scan_box.isChecked() is True  # theo scan_enabled đã lưu
            # Bước 4b: quyền auto-trade là lựa chọn tường minh — checkbox
            # luôn bật được; fail-closed nằm ở tầng payload/Router (không
            # có cấu hình chiến lược ⇒ không phát payload ⇒ không auto-trade).
            assert auto_box.isEnabled() is True
            assert auto_box.isChecked() is False

            # Bật quét thêm 1 mã chưa cấu hình rồi lưu.
            row2 = symbols.index("GBP/USD")
            scan_box2 = table.cellWidget(row2, 5).findChild(QCheckBox)
            scan_box2.setChecked(True)
            screen._save_mt5_symbol_settings()

            saved = fake_app.settings_service.load().trading
            assert saved.symbol_settings["GBP/USD"].scan_enabled is True
            assert saved.symbol_settings["GBP/USD"].auto_trade_permitted is False
            assert "GBP/USD" in saved.enabled_symbols
            assert "EUR/USD" in saved.enabled_symbols
        finally:
            screen.close()
    app.processEvents()


def test_scanner_screen_scan_list_follows_scan_enabled_only(
    tmp_path: Path,
) -> None:
    from services.settings_service import SettingsService

    app = _app()
    load_visual_qa_fonts()
    fake_app = _fake_app("dark")
    service = SettingsService(tmp_path / "settings.json")
    base = service.load()
    # EUR/USD bật quét nhưng KHÔNG có quyền auto-trade; GBP/USD có entry
    # nhưng tắt quét ⇒ chỉ EUR/USD vào danh sách quét.
    base.trading.symbol_settings["EUR/USD"] = SymbolScanSettings(
        scan_enabled=True,
    )
    base.trading.symbol_settings["GBP/USD"] = SymbolScanSettings(
        scan_enabled=False,
    )
    fake_app.settings_service.settings = base

    with ExitStack() as stack:
        _patch_external_activity(stack)
        with patch("ui.screens.scanner_screen.QTimer.singleShot"):
            screen = ScannerScreen(None, app=fake_app)
        try:
            assert screen.scan_symbols == ["EUR/USD"]
        finally:
            screen.close()
    app.processEvents()

    # Dialog chọn mã không còn nhắc "Backtest".
    from PyQt6.QtWidgets import QLabel

    dialog = ScannerSymbolSelectionDialog(
        ["EUR/USD", "GBP/USD"], {"EUR/USD"}, {"EUR/USD", "GBP/USD"}, ["EUR/USD"]
    )
    try:
        intro = dialog.findChild(QLabel, "HelperText")
        assert intro is not None
        assert "Backtest" not in intro.text()
        tooltips = " ".join(
            box.toolTip() for box in dialog.checkboxes.values()
        )
        assert "Backtest" not in tooltips
    finally:
        dialog.close()
