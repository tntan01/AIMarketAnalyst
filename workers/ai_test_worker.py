from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from services.ai_service import AIProviderConfig, AIService
from workers.base_worker import WorkerState


class AITestWorker(QObject):
    succeeded = pyqtSignal()
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, config: AIProviderConfig) -> None:
        super().__init__()
        self.config = config
        self.state = WorkerState.IDLE

    @pyqtSlot()
    def run(self) -> None:
        self.state = WorkerState.RUNNING
        try:
            if AIService(self.config).test_model_response():
                self.state = WorkerState.FINISHED
                self.succeeded.emit()
            else:
                self.state = WorkerState.FAILED
                self.failed.emit("Model AI không trả về phản hồi.")
        except Exception as exc:
            self.state = WorkerState.FAILED
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()
