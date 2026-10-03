from __future__ import annotations

import logging
import os
import sys

from pathlib import Path

from config.paths import ensure_runtime_dirs
from services.logging_service import configure_logging
from services.runtime_retention_service import scanner_retention


def _icon_path() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent
    return base / "assets" / "icons" / "app.ico"


def main() -> int:
    ensure_runtime_dirs()
    configure_logging()
    # Phục hồi chờ phải áp dụng TRƯỚC khi bất kỳ service nào mở DB và trước
    # cả retention (retention dọn snapshot cũ) — điểm an toàn duy nhất theo
    # plan backup-restore §4.3; điểm gọi apply này là duy nhất.
    try:
        from services.backup_service import BackupService

        restore = BackupService().apply_pending_restore()
        if restore.applied:
            logging.getLogger(__name__).info(
                "Khởi động: đã áp dụng bản phục hồi (%d mục; bản an toàn: %s)",
                restore.applied_files,
                restore.safety_backup,
            )
        elif restore.errors:
            logging.getLogger(__name__).error(
                "Khởi động: thư mục phục hồi chờ không nguyên vẹn — giữ dữ "
                "liệu hiện tại; lỗi: %s",
                "; ".join(restore.errors),
            )
    except Exception:
        logging.getLogger(__name__).exception("Khởi động: áp dụng phục hồi thất bại")
    scanner_retention.ensure_started()

    # Must be called BEFORE QApplication for Windows taskbar icon
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AIMarketAnalyst")

    try:
        from PyQt6.QtGui import QIcon
        from PyQt6.QtWidgets import QApplication
        from controllers.app_controller import AppController
        from ui.main_window import MainWindow
    except ImportError as exc:
        print("PyQt6 is not installed. Run: pip install -r requirements.txt")
        print(exc)
        return 1

    app = QApplication(sys.argv)
    app_ctrl = AppController()
    app_ctrl.news_controller.run_startup_turn()
    app.aboutToQuit.connect(app_ctrl.shutdown)
    ico = _icon_path()
    app_icon = QIcon(str(ico)) if ico.exists() else QIcon()
    if ico.exists():
        app.setWindowIcon(app_icon)
    window = MainWindow(app_ctrl)
    if not app_icon.isNull():
        window.setWindowIcon(app_icon)
    # Startup/restore/persist là policy của MainWindow; main.py không tự quyết
    # định trạng thái cửa sổ (R1: một owner duy nhất).
    window.apply_startup_policy()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
