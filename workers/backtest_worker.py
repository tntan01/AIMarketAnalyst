from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from workers.base_worker import WorkerState


class BacktestWorker(QObject):
    progress = pyqtSignal(int, str)
    succeeded = pyqtSignal(dict)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, task: Callable[..., dict[str, Any]], request: dict[str, Any]) -> None:
        super().__init__()
        self.task = task
        self.request = request
        self.state = WorkerState.IDLE
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    @pyqtSlot()
    def run(self) -> None:
        self.state = WorkerState.RUNNING
        try:
            self.progress.emit(5, "Đang chuẩn bị backtest...")
            result = self.task(**self.request, _progress_callback=self._emit_progress)
        except BacktestCancelled as exc:
            self.state = WorkerState.CANCELLED
            self.cancelled.emit(str(exc))
        except Exception as exc:
            self.state = WorkerState.FAILED
            self.failed.emit(str(exc))
        else:
            self.state = WorkerState.FINISHED
            self.progress.emit(100, "Hoàn tất backtest.")
            self.succeeded.emit(result)
        finally:
            self.finished.emit()

    def _emit_progress(self, percent: int, message: str) -> None:
        if self._cancel_requested:
            raise BacktestCancelled(
                "Đã hủy backtest an toàn; chưa tạo snapshot kết quả dở dang."
            )
        self.progress.emit(max(0, min(100, percent)), message)


class BacktestCancelled(RuntimeError):
    pass
