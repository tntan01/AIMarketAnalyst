from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from controllers.app_controller import AppController
from services.ai_service import AIProviderConfig, AIService


def test_app_controller_services_are_singletons():
    app = AppController()

    assert app.settings_service is app.settings_service
    assert app.mt5 is app.mt5
    assert app.scanner_controller is app.scanner_controller
    assert app.scanner_controller.mt5 is app.mt5


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


def test_main_registers_app_shutdown_callback():
    source = Path("main.py").read_text(encoding="utf-8")

    assert "app.aboutToQuit.connect(app_ctrl.shutdown)" in source


def test_screen_constructors_are_wired_to_app_controller():
    scanner_source = Path("ui/screens/scanner_screen.py").read_text(encoding="utf-8")
    detail_source = Path("ui/screens/scanner_detail_screen.py").read_text(encoding="utf-8")

    assert "app .scanner_controller if app else ScannerController" in scanner_source
    assert "def __init__(self, navigate=None, *, app=None)" in detail_source
    assert "app.journal_controller if app else JournalController()" in detail_source
