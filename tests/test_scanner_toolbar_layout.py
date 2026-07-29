from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QSizePolicy

from tools.capture_ui_style_baseline import _fake_app, _patch_external_activity
from tools.ui_layout_audit import load_visual_qa_fonts
from ui.screens.scanner_screen import ScannerScreen
from ui.theme_manager import ThemeManager


def test_scanner_starts_in_manual_mode_without_scheduling_a_scan() -> None:
    app = QApplication.instance() or QApplication([])
    fake_app = _fake_app("dark")
    settings = fake_app.settings_service.settings
    settings.notifications.auto_scan_interval_minutes = 60
    settings.trading.symbol_settings = {"EUR/USD": object()}

    with patch("ui.screens.scanner_screen.QTimer.singleShot") as single_shot:
        screen = ScannerScreen(None, app=fake_app)
        app.processEvents()

    assert single_shot.call_count == 0
    assert screen.scan_mode_combo.currentData() == "once"
    assert screen.scan_interval_combo.currentData() == 3600
    assert screen.scan_symbols == ["EUR/USD"]
    assert screen.selected_scan_symbols == ["EUR/USD"]
    assert screen.auto_scan_active is False
    assert screen.auto_scan_timer.isActive() is False

    screen.close()


def test_scanner_controls_share_one_compact_row_at_smallest_viewport() -> None:
    app = QApplication.instance() or QApplication([])
    load_visual_qa_fonts()

    with ExitStack() as stack:
        _patch_external_activity(stack)
        screen = ScannerScreen(None, app=_fake_app("dark"))
        screen.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        ThemeManager().apply(screen, theme="dark")
        screen.resize(1366, 768)
        screen.show()

        # The stop button is only visible while automatic scanning is active.
        # Force that state so the widest form of the toolbar is verified.
        screen.stop_auto_scan_button.setVisible(True)
        app.processEvents()

        controls = (
            screen.scan_mode_label,
            screen.scan_mode_combo,
            screen.scan_interval_label,
            screen.scan_interval_combo,
            screen.auto_trade_check,
            screen.scan_button,
            screen.stop_auto_scan_button,
            screen.show_orders_button,
        )
        centers = [
            control.mapTo(screen, control.rect().center()).y()
            for control in controls
        ]
        left_edges = [
            control.mapTo(screen, control.rect().topLeft()).x()
            for control in controls
        ]
        right_edge = controls[-1].mapTo(
            screen,
            controls[-1].rect().topRight(),
        ).x()

        assert max(centers) - min(centers) <= 1
        assert left_edges == sorted(left_edges)
        assert screen.width() == 1366
        assert right_edge < screen.width()

        for control in controls:
            assert control.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Fixed
            assert control.width() <= control.sizeHint().width() + 1

        screen.close()
