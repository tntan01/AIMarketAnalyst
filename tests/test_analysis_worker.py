from __future__ import annotations

from PyQt6.QtCore import QThread

from controllers.analysis_controller import AnalysisController
from workers.analysis_worker import AnalysisWorker


def test_controller_creates_single_analysis_qthread_worker() -> None:
    controller = AnalysisController()

    thread, worker = controller.create_single_analysis_worker(
        symbol="EUR/USD",
        broker_symbol="EURUSDm",
        account_balance=10_000,
        risk_percent=1,
        timezone_name="Asia/Ho_Chi_Minh",
    )

    try:
        assert isinstance(thread, QThread)
        assert isinstance(worker, AnalysisWorker)
        assert worker.request["symbol"] == "EUR/USD"
        assert worker.thread() is thread
    finally:
        thread.quit()
        thread.wait(1000)
