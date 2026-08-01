from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from workers.base_worker import WorkerState


class ScannerWorker(QObject):
    progress = pyqtSignal(int, str)
    succeeded = pyqtSignal(dict)
    core_succeeded = pyqtSignal(dict)
    aftercare_progress = pyqtSignal(int, str)
    aftercare_succeeded = pyqtSignal(dict)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(
        self,
        task: Callable[..., dict[str, Any]],
        request: dict[str, Any],
        *,
        split_aftercare: bool = False,
    ) -> None:
        super().__init__()
        self.task = task
        self.request = request
        self.split_aftercare = split_aftercare
        self.state = WorkerState.IDLE

    @pyqtSlot()
    def run(self) -> None:
        self.state = WorkerState.RUNNING
        try:
            if self.split_aftercare:
                self._run_split()
            else:
                self._run_single()
        except Exception as exc:
            self.state = WorkerState.FAILED
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def _run_single(self) -> None:
        self.progress.emit(5, "Đang chuẩn bị quét thị trường...")
        result = self.task(**self.request, _progress_callback=self._emit_progress)
        self.state = WorkerState.FINISHED
        self.progress.emit(100, "Hoàn tất quét thị trường.")
        self.succeeded.emit(result)

    def _run_split(self) -> None:
        self.progress.emit(5, "Đang chuẩn bị quét thị trường...")
        delta = self.task(
            **self.request,
            _progress_callback=self._emit_progress,
            _core_ready_callback=self._on_core_ready,
            _aftercare_progress_callback=self._emit_aftercare_progress,
            _return_aftercare_delta=True,
        )
        self.state = WorkerState.FINISHED
        self.progress.emit(100, "Hoàn tất quét thị trường.")
        self.aftercare_succeeded.emit(delta)

    def _on_core_ready(self, core_output: dict[str, Any]) -> None:
        self.core_succeeded.emit(core_output)

    def _emit_aftercare_progress(self, percent: int, message: str) -> None:
        self.aftercare_progress.emit(max(0, min(100, percent)), message)

    def _emit_progress(self, percent: int, message: str) -> None:
        self.progress.emit(max(0, min(100, percent)), message)
