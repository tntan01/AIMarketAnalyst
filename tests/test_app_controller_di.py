from __future__ import annotations

from pathlib import Path

from controllers.app_controller import AppController
from services.ai_service import AIProviderConfig, AIService


def test_app_controller_services_are_singletons():
    app = AppController()

    assert app.settings_service is app.settings_service
    assert app.mt5_service is app.mt5_service
    assert app.scanner_controller is app.scanner_controller
    assert app.scanner_controller.mt5_service is app.mt5_service


def test_app_controller_creates_configured_ai_service():
    app = AppController()
    config = AIProviderConfig(provider="DeepSeek", model="deepseek-v4-flash", api_key="test")

    ai = app.create_ai_service(config)

    assert isinstance(ai, AIService)
    assert ai.config is config


def test_screen_constructors_are_wired_to_app_controller():
    scanner_source = Path("ui/screens/scanner_screen.py").read_text(encoding="utf-8")
    detail_source = Path("ui/screens/scanner_detail_screen.py").read_text(encoding="utf-8")

    assert "app .scanner_controller if app else ScannerController" in scanner_source
    assert "def __init__(self, navigate=None, *, app=None)" in detail_source
    assert "app.journal_controller if app else JournalController()" in detail_source
