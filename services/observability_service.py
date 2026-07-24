"""Structured JSON event logging for scanner and order execution."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from threading import RLock
from typing import Any

from config.paths import app_data_dir
from core.scanner_observability import (
    SCANNER_OBSERVABILITY_VERSION,
    redact_sensitive,
)


class StructuredObservabilityService:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (
            app_data_dir() / "logs" / "scanner-events.jsonl"
        )
        self._lock = RLock()
        self._logger = logging.getLogger("scanner.events")

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
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(encoded + "\n")
        level = getattr(logging, event["severity"], logging.INFO)
        self._logger.log(level, encoded)
        return event


structured_observability = StructuredObservabilityService()
