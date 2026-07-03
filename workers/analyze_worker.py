from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from services.ai_service import AIService, AIProviderConfig
from workers.base_worker import WorkerState


class AnalyzeWorker(QObject):
    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, config: AIProviderConfig, prompt: str) -> None:
        super().__init__()
        self.config = config
        self.prompt = prompt
        self.state = WorkerState.IDLE

    @pyqtSlot()
    def run(self) -> None:
        self.state = WorkerState.RUNNING
        try:
            ai = AIService(self.config)
            response = ai.analyze(self.prompt)
        except Exception as exc:
            self.state = WorkerState.FAILED
            self.failed.emit(str(exc))
        else:
            self.state = WorkerState.FINISHED
            self.succeeded.emit(response)
        finally:
            self.finished.emit()
