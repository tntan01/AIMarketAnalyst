from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from controllers.app_controller import AppController
from services.ai_service import AIProviderConfig, AIService


def test_app_controller_services_are_singletons():
    app = AppController()

    assert app.settings_service is app.settings_service
    assert app.mt5 is app.mt5
    assert app.scanner_controller is app.scanner_controller
    assert app.scanner_controller.mt5 is app.mt5
    assert app.order_management_service is app.order_management_service
    assert app.order_management_service.mt5 is app.mt5
    assert app.scanner_controller.order_management_service is app.order_management_service


def test_app_controller_creates_configured_ai_service():
    app = AppController()
    config = AIProviderConfig(provider="DeepSeek", model="deepseek-v4-flash", api_key="test")

    ai = app.create_ai_service(config)

    assert isinstance(ai, AIService)
    assert ai.config is config


def test_app_controller_shutdown_does_not_create_mt5_service():
    app = AppController()

    app.shutdown()

    assert app._mt5 is None


def test_app_controller_shutdown_disconnects_existing_mt5_service():
    app = AppController()
    mt5 = MagicMock()
    app._mt5 = mt5

    app.shutdown()

    mt5.disconnect.assert_called_once_with()


def test_app_controller_shutdown_waits_for_scanner_aftercare():
    app = AppController()
    controller = MagicMock()
    app._scanner_controller = controller

    app.shutdown()

    controller.wait_for_aftercare_shutdown.assert_called_once_with()


def test_app_controller_shutdown_disconnects_mt5_when_aftercare_wait_raises():
    app = AppController()
    controller = MagicMock()
    controller.wait_for_aftercare_shutdown.side_effect = RuntimeError("wait failed")
    app._scanner_controller = controller
    mt5 = MagicMock()
    app._mt5 = mt5

    with pytest.raises(RuntimeError, match="wait failed"):
        app.shutdown()

    mt5.disconnect.assert_called_once_with()


def test_app_controller_shutdown_flushes_order_management_before_disconnect():
    app = AppController()
    manager = MagicMock()
    mt5 = MagicMock()
    app._order_management_service = manager
    app._mt5 = mt5

    app.shutdown()

    manager.shutdown.assert_called_once_with()
    mt5.disconnect.assert_called_once_with()


def test_app_controller_shutdown_survives_marker_write_failure(tmp_path, monkeypatch):
    from controllers.scanner_controller import ScannerController
    from services.scanner_job_state import ScannerJobState

    job_state = ScannerJobState(runtime_root=tmp_path)
    controller = ScannerController(
        settings_service=MagicMock(),
        mt5=MagicMock(),
        news_service=MagicMock(),
        journal_service=MagicMock(),
        telegram_service=MagicMock(),
        retention_service=MagicMock(),
        job_state=job_state,
    )
    app = AppController()
    app._scanner_controller = controller
    mt5 = MagicMock()
    app._mt5 = mt5

    # Persist the initial incomplete marker, then make every later transition
    # fail exactly as a full/unwritable disk would.
    job_state.begin_aftercare("scan-1", durable=True)
    marker_before = job_state.marker_path("scan-1").read_bytes()

    def always_fail(self, scan_id, state, *, started_at=None, reason=None):
        raise OSError("disk full")

    monkeypatch.setattr(ScannerJobState, "_write_marker", always_fail)

    real_shutdown_wait = controller.wait_for_aftercare_shutdown
    shutdown_results = []
    wait_call_deltas = []
    condition_wait = MagicMock(wraps=job_state._condition.wait)
    monkeypatch.setattr(job_state._condition, "wait", condition_wait)

    def short_shutdown_wait():
        wait_calls_before = condition_wait.call_count
        shutdown_results.append(real_shutdown_wait(timeout=0.02))
        wait_call_deltas.append(condition_wait.call_count - wait_calls_before)

    monkeypatch.setattr(controller, "wait_for_aftercare_shutdown", short_shutdown_wait)

    app.shutdown()
    app.shutdown()

    # A marker-write failure never leaks through app shutdown. The first wait
    # consumes its bounded budget; the timed-out job then leaves the in-memory
    # running set, so the second shutdown returns without waiting it again.
    assert shutdown_results == [False, True]
    assert wait_call_deltas[0] >= 1
    assert wait_call_deltas[1] == 0
    assert job_state.active_jobs() == ()
    assert job_state.marker_path("scan-1").read_bytes() == marker_before
    assert job_state.load_marker("scan-1")["state"] == "running"
    assert mt5.disconnect.call_count == 2


def test_main_registers_app_shutdown_callback():
    source = Path("main.py").read_text(encoding="utf-8")

    assert "app.aboutToQuit.connect(app_ctrl.shutdown)" in source


def test_screen_constructors_are_wired_to_app_controller():
    scanner_source = Path("ui/screens/scanner_screen.py").read_text(encoding="utf-8")
    detail_source = Path("ui/screens/scanner_detail_screen.py").read_text(encoding="utf-8")

    assert "app .scanner_controller if app else ScannerController" in scanner_source
    assert "def __init__(self, navigate=None, *, app=None)" in detail_source
    assert "app.journal_controller if app else JournalController()" in detail_source
