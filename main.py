from __future__ import annotations

import sys
from pathlib import Path

from config.paths import ensure_runtime_dirs
from services.logging_service import configure_logging


def _icon_path() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent
    return base / "assets" / "icons" / "app.ico"


def main() -> int:
    ensure_runtime_dirs()
    configure_logging()

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
    ico = _icon_path()
    app_icon = QIcon(str(ico)) if ico.exists() else QIcon()
    if ico.exists():
        app.setWindowIcon(app_icon)
    window = MainWindow(app_ctrl)
    if not app_icon.isNull():
        window.setWindowIcon(app_icon)
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
