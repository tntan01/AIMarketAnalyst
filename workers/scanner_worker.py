from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from workers.base_worker import WorkerState


class ScannerWorker(QObject):
    progress = pyqtSignal(int, str)
    succeeded = pyqtSignal(dict)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, task: Callable[..., dict[str, Any]], request: dict[str, Any]) -> None:
        super().__init__()
        self.task = task
        self.request = request
        self.state = WorkerState.IDLE

    @pyqtSlot()
    def run(self) -> None:
        mt5 = None
        initialized = False
        self.state = WorkerState.RUNNING
        try:
            import MetaTrader5 as mt5

            initialized = mt5.initialize()
            if not initialized:
                raise RuntimeError("Khong khoi tao duoc ket noi MT5 cho scanner.")
            self.progress.emit(5, "Đang chuẩn bị quét thị trường...")
            result = self.task(**self.request, _progress_callback=self._emit_progress)
        except Exception as exc:
            self.state = WorkerState.FAILED
            self.failed.emit(str(exc))
        else:
            self.state = WorkerState.FINISHED
            self.progress.emit(100, "Hoàn tất quét thị trường.")
            self.succeeded.emit(result)
        finally:
            if initialized and mt5 is not None:
                mt5.shutdown()
            self.finished.emit()

    def _emit_progress(self, percent: int, message: str) -> None:
        self.progress.emit(max(0, min(100, percent)), message)
