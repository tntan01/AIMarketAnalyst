from __future__ import annotations

import sys

from config.paths import ensure_runtime_dirs
from services.logging_service import configure_logging


def main() -> int:
    ensure_runtime_dirs()
    configure_logging()

    try:
        from PyQt6.QtWidgets import QApplication
        from ui.main_window import MainWindow
    except ImportError as exc:
        print("PyQt6 is not installed. Run: pip install -r requirements.txt")
        print(exc)
        return 1

    app = QApplication(sys.argv)
    window = MainWindow()
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
