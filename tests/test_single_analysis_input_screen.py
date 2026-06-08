from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEventLoop, QThread, QTimer
from PyQt6.QtWidgets import QApplication, QFrame

from ui.screens.single_analysis_input_screen import SingleAnalysisInputScreen
from workers.analysis_worker import AnalysisWorker
from services.mt5_service import MT5ConnectionStatus


class _FakeController:
    def create_single_analysis_worker(self, **request):
        thread = QThread()
        worker = AnalysisWorker(self._run, request)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        return thread, worker

    def _run(self, **request):
        progress = request.pop("_progress_callback", None)
        if progress:
            progress(50, "Đang chạy test...")
        time.sleep(0.05)
        return {
            "symbol": request["symbol"],
            "decision_summary": {"action": "watch", "main_view": "worker ok"},
            "direction_bias": "buy",
            "trade_permission": {"status": "caution", "reason": "test"},
            "market_regime": {"primary": "trend_up", "structure": "HH/HL"},
            "scenario_scores": {"buy": {"total": 70}, "sell": {"total": 40}},
            "scenarios": [],
            "macro": {"ai_summary": "fallback"},
        }


class _FakeMT5Service:
    def connection_status(self):
        return MT5ConnectionStatus(
            initialized=True,
            terminal_connected=True,
            logged_in=True,
            trade_allowed=True,
            balance=12_345.67,
            currency="USD",
        )

    def account_balance(self):
        return 12_345.67

    def configured_symbols_in_market_watch(self):
        return [("EUR/USD", "EURUSD.r"), ("GBP/USD", "GBPUSD.r")]

    def aliases_for(self, symbol):
        return {"EUR/USD": ["EURUSD"], "GBP/USD": ["GBPUSD"]}.get(symbol, [])


def test_click_analyze_keeps_qthread_alive_until_finished() -> None:
    app = QApplication.instance() or QApplication([])
    navigated: list[tuple[str, dict[str, object]]] = []
    screen = SingleAnalysisInputScreen(lambda route, payload=None: navigated.append((route, payload or {})))
    screen.mt5_service = _FakeMT5Service()
    screen.analysis_controller = _FakeController()
    screen.refresh_status()

    assert [screen.symbol_input.itemText(index) for index in range(screen.symbol_input.count())] == ["EUR/USD", "GBP/USD"]
    assert screen.broker_symbol_input.text() == "EURUSD.r"
    assert "Chạy %" not in screen.data_status_labels
    assert screen.progress_bar.objectName() == "AnalysisProgressBar"
    assert screen.data_source_box.objectName() == "CompactInfoRow"
    assert screen.analysis_risk_card.objectName() == "AnalysisRiskCard"
    assert screen.analysis_section.height() == screen.risk_section.height()
    separators = [item for item in screen.analysis_risk_card.findChildren(QFrame) if item.objectName() == "VerticalSeparator"]
    assert separators
    assert separators[0].height() >= min(screen.analysis_section.height(), screen.risk_section.height()) - 24
    assert all(item.height() >= 68 for item in screen.data_status_items)
    assert screen.data_status_labels["MT5"].text() == "Đã kết nối"
    assert screen.data_status_labels["Broker"].text() == "Đã đăng nhập"
    assert screen.balance_input.value() == 12_345.67
    assert not screen.balance_input.isEnabled()
    labels = [label.text() for label in screen.findChildren(__import__("PyQt6.QtWidgets").QtWidgets.QLabel)]
    ascii_labels = [ascii(label) for label in labels]
    assert "'\\u0110i\\u1ec1u ki\\u1ec7n v\\xe0o l\\u1ec7nh'" not in ascii_labels

    screen._run_analysis()
    assert screen.analysis_thread is not None
    assert screen.analysis_thread.isRunning()

    loop = QEventLoop()
    screen.analysis_thread.finished.connect(loop.quit)
    QTimer.singleShot(2000, loop.quit)
    loop.exec()
    app.processEvents()

    assert screen.analysis_thread is None
    assert screen.analysis_worker is None
    assert screen.progress_bar.value() == 100
    assert navigated
    assert navigated[0][0] == "analysis_result"
