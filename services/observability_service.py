"""Structured JSON event logging for scanner and order execution."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from threading import RLock
from typing import Any

from config.paths import app_data_dir
from core.scanner_observability import (
    SCANNER_OBSERVABILITY_VERSION,
    redact_sensitive,
)


STRUCTURED_LOG_MAX_BYTES = 20 * 1024 * 1024
# Current file + four archived files = a 100 MiB budget for scanner events.
STRUCTURED_LOG_BACKUP_COUNT = 4


class StructuredObservabilityService:
    def __init__(
        self,
        path: Path | None = None,
        *,
        max_bytes: int = STRUCTURED_LOG_MAX_BYTES,
        backup_count: int = STRUCTURED_LOG_BACKUP_COUNT,
    ) -> None:
        self.path = path or (
            app_data_dir() / "logs" / "scanner-events.jsonl"
        )
        self.max_bytes = max(0, int(max_bytes))
        self.backup_count = max(0, int(backup_count))
        self._lock = RLock()

    def _backup_path(self, index: int) -> Path:
        return self.path.with_name(f"{self.path.name}.{index}")

    def _rotate(self) -> None:
        if self.backup_count <= 0:
            self.path.unlink(missing_ok=True)
            return
        self._backup_path(self.backup_count).unlink(missing_ok=True)
        for index in range(self.backup_count - 1, 0, -1):
            source = self._backup_path(index)
            if source.exists():
                source.replace(self._backup_path(index + 1))
        if self.path.exists():
            self.path.replace(self._backup_path(1))

    def _write(self, encoded: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded_size = len(encoded.encode("utf-8")) + 1
        if (
            self.max_bytes
            and self.path.exists()
            and self.path.stat().st_size + encoded_size > self.max_bytes
        ):
            self._rotate()
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(encoded + "\n")

    def emit(
        self,
        event_type: str,
        *,
        scan_id: str = "",
        symbol: str = "",
        severity: str = "INFO",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "observability_version": SCANNER_OBSERVABILITY_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "event_type": str(event_type or "UNKNOWN_EVENT").upper(),
            "severity": str(severity or "INFO").upper(),
            "scan_id": str(scan_id or ""),
            "symbol": str(symbol or ""),
            "payload": redact_sensitive(payload or {}),
        }
        encoded = json.dumps(
            event,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        with self._lock:
            self._write(encoded)
        return event


structured_observability = StructuredObservabilityService()
