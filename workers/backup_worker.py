from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from services.backup_service import BackupService
from workers.base_worker import WorkerState


class BackupWorker(QObject):
    """Chạy sao lưu/phục hồi ngoài main thread để UI không đứng.

    Chỉ bao bọc concurrency — không chứa logic nghiệp vụ (tầng workers);
    mọi quyết định nằm trong ``services/backup_service.py``.
    """

    backup_done = pyqtSignal(str)
    restore_staged = pyqtSignal(str, str)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, mode: str, *, dest_dir: Path | None = None,
                 zip_path: Path | None = None) -> None:
        super().__init__()
        self.mode = mode
        self.dest_dir = dest_dir
        self.zip_path = zip_path
        self.state = WorkerState.IDLE

    @pyqtSlot()
    def run(self) -> None:
        self.state = WorkerState.RUNNING
        service = BackupService()
        try:
            if self.mode == "backup":
                result = service.create_backup(dest_dir=self.dest_dir)
                message = (
                    f"Đã tạo bản sao lưu: {result.zip_path} "
                    f"({len(result.manifest['entries'])} tệp)"
                )
                if result.warnings:
                    message += " — lưu ý: " + "; ".join(result.warnings)
                self.state = WorkerState.FINISHED
                self.backup_done.emit(message)
            elif self.mode == "restore":
                result = service.stage_restore(self.zip_path)
                if result.ok:
                    self.state = WorkerState.FINISHED
                    self.restore_staged.emit(result.message, str(result.safety_backup or ""))
                else:
                    self.state = WorkerState.FAILED
                    self.failed.emit("; ".join(result.errors))
            else:
                self.state = WorkerState.FAILED
                self.failed.emit(f"Chế độ không hỗ trợ: {self.mode}")
        except Exception as exc:
            self.state = WorkerState.FAILED
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()
