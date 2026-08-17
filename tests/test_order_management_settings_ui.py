from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from config.settings import default_settings
from services.settings_service import SettingsService
from ui.screens.settings_screen import SettingsScreen


_QAPP: QApplication | None = None


def _ensure_qapp() -> QApplication:
    global _QAPP
    app = QApplication.instance()
    if app is None:
        _QAPP = QApplication([])
        app = _QAPP
    return app


def _screen(path: Path) -> SettingsScreen:
    _ensure_qapp()
    screen = SettingsScreen.__new__(SettingsScreen)
    screen.app_settings = default_settings()
    screen.settings_service = SettingsService(path)
    screen._order_management_test_frame = screen._order_management_tab()
    return screen


def test_order_management_panel_defaults_to_live_state(
    tmp_path: Path,
) -> None:
    # Fully live since 2026-08-16: the OM feature flag and the manage-scope
    # selector are both removed — the panel shows only the policy inputs and
    # the live status label.
    screen = _screen(tmp_path / "settings.json")

    # hasattr() on an un-initialized QWidget raises RuntimeError; check the
    # instance dict directly instead.
    for removed_control in (
        "order_management_stage_input",
        "order_management_kill_switch_input",
        "order_management_canary_symbol_input",
        "order_management_enabled_input",
        "order_management_scope_input",
    ):
        assert removed_control not in screen.__dict__
    assert "Đang chạy thật" in screen.order_management_status_label.text()


def test_order_management_panel_round_trip_preserves_other_settings(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.json"
    screen = _screen(path)
    screen.app_settings.features.scanner_fast_tier1 = True
    screen.app_settings.default_symbol = "XAU/USD"
    screen.app_settings.trading.max_daily_loss_pct = 3.25

    screen.order_management_poll_interval_input.setValue(2.5)
    screen.order_management_refresh_interval_input.setValue(9.0)
    screen.order_management_be_trigger_input.setValue(1.4)
    screen.order_management_be_plus_pips_input.setValue(3.5)
    screen.order_management_trail_wide_input.setValue(3.2)
    screen.order_management_trail_tight_input.setValue(1.2)
    screen.order_management_trail_tight_trigger_input.setValue(2.8)
    screen.order_management_retry_initial_input.setValue(3.0)
    screen.order_management_retry_max_input.setValue(45.0)
    screen.order_management_retry_attempts_input.setValue(8)

    screen._save_order_management_settings()
    loaded = SettingsService(path).load()

    assert loaded.features.scanner_fast_tier1 is True
    assert loaded.default_symbol == "XAU/USD"
    assert loaded.trading.max_daily_loss_pct == 3.25
    assert loaded.order_management.poll_interval_seconds == 2.5
    assert loaded.order_management.refresh_interval_seconds == 9.0
    assert loaded.order_management.be_trigger_r == 1.4
    assert loaded.order_management.be_plus_pips == 3.5
    assert loaded.order_management.trail_wide_atr_multiplier == 3.2
    assert loaded.order_management.trail_tight_atr_multiplier == 1.2
    assert loaded.order_management.trail_tight_trigger_r == 2.8
    assert loaded.order_management.retry_initial_seconds == 3.0
    assert loaded.order_management.retry_max_seconds == 45.0
    assert loaded.order_management.max_retry_attempts == 8
    assert screen.order_management_status_label.text().startswith("Đã lưu.")
