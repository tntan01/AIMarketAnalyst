from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

import workers.ai_test_worker as ai_test_worker_module
from ui.screens.settings_screen import SettingsScreen


def test_ai_key_check_runs_in_worker_and_restores_button(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(ai_test_worker_module.AIService, "test_model_response", lambda self: True)

    screen = SettingsScreen()
    screen.ai_provider_combo.setCurrentText("DeepSeek")
    assert screen.ai_model_combo.count() > 0
    screen.ai_model_combo.setCurrentIndex(0)
    screen.ai_api_key_input.setText("test-key")
    screen._update_ai_button_state()

    assert screen.ai_test_button.isEnabled()
    screen._test_ai_key()

    assert screen.ai_test_thread is not None
    assert screen.ai_test_worker is not None
    assert not screen.ai_test_button.isEnabled()
    assert screen.ai_test_button.text() != "Kiểm tra"

    loop = QEventLoop()
    screen.ai_test_thread.finished.connect(loop.quit)
    QTimer.singleShot(3000, loop.quit)
    loop.exec()
    app.processEvents()

    assert screen.ai_test_thread is None
    assert screen.ai_test_worker is None
    assert screen.ai_test_button.text() == "Kiểm tra"
    assert screen.ai_test_button.isEnabled()
    assert "hợp lệ" in screen.ai_status_label.text()
