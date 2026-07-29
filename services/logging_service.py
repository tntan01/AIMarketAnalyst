from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config.paths import log_path


APP_LOG_MAX_BYTES = 20 * 1024 * 1024
# Current file + four archived files = a 100 MiB budget for app.log.
APP_LOG_BACKUP_COUNT = 4


def build_app_log_handler(path: Path) -> RotatingFileHandler:
    """Create the bounded handler for the human-readable application log."""
    return RotatingFileHandler(
        path,
        maxBytes=APP_LOG_MAX_BYTES,
        backupCount=APP_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )


def configure_logging() -> None:
    log_file = log_path()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[build_app_log_handler(log_file), logging.StreamHandler()],
    )
