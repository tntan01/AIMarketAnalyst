from __future__ import annotations

from logging.handlers import RotatingFileHandler
from pathlib import Path

from services.logging_service import (
    APP_LOG_BACKUP_COUNT,
    APP_LOG_MAX_BYTES,
    build_app_log_handler,
)


def test_app_log_handler_uses_the_configured_rotation_budget(tmp_path: Path) -> None:
    handler = build_app_log_handler(tmp_path / "app.log")
    try:
        assert isinstance(handler, RotatingFileHandler)
        assert handler.maxBytes == APP_LOG_MAX_BYTES
        assert handler.backupCount == APP_LOG_BACKUP_COUNT
    finally:
        handler.close()
