"""Policy and compact representation for scanner runtime snapshots.

Full evidence is useful for replaying a decision, but is much too expensive to
write for every scheduled scan.  This module makes that distinction explicit
and keeps the small scheduled-scan record safe to retain for longer.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any


PERSISTENCE_FULL = "full"
PERSISTENCE_SUMMARY = "summary"
PERSISTENCE_NONE = "none"
_VALID_MODES = {PERSISTENCE_FULL, PERSISTENCE_SUMMARY, PERSISTENCE_NONE}
_SAMPLE_STATE = "scanner-persistence-v1.json"

# Explicitly whitelist display/decision fields.  In particular this excludes
# candle data, SMC breakdowns and observability payloads duplicated in a row.
SUMMARY_ROW_FIELDS = (
    "symbol", "broker_symbol", "rank", "scanner_group", "scanner_action",
    "scanner_decision", "candidate_status", "legacy_candidate_status",
    "trade_permission", "best_side", "best_score", "buy_score", "sell_score",
    "setup_score", "market_regime", "short_reason", "selected_side",
    "selected_zone_id", "selected_zone_type", "risk_reward",
    "expected_effective_rr", "entry_status", "scan_id", "row_id",
    "settings_hash", "rollout_stage", "analysis_error",
    "analysis_status", "pipeline_route", "fast_path_version",
    "fast_reject_reason",
    "entry_zone_source",
    "zone_origin_class",
)


def normalize_persistence_mode(value: object, *, default: str = PERSISTENCE_FULL) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in _VALID_MODES else default


def summary_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in SUMMARY_ROW_FIELDS if key in row}


class ScannerPersistenceService:
    """Choose full evidence only when it has material diagnostic value."""

    def __init__(self, root: Path, *, sample_interval: timedelta = timedelta(hours=1)) -> None:
        self.root = root
        self.sample_interval = sample_interval

    def select_mode(self, result: dict[str, Any]) -> str:
        requested = normalize_persistence_mode(result.get("persistence_mode"))
        if requested != PERSISTENCE_SUMMARY:
            return requested
        if self._has_material_event(result) or self._sample_due():
            return PERSISTENCE_FULL
        return PERSISTENCE_SUMMARY

    def record(self, mode: str, *, now: datetime | None = None) -> None:
        if mode != PERSISTENCE_FULL:
            return
        timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        path = self.root / "cache" / _SAMPLE_STATE
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"last_full_at": timestamp.isoformat()}), encoding="utf-8")
        temporary.replace(path)

    def _sample_due(self, *, now: datetime | None = None) -> bool:
        path = self.root / "cache" / _SAMPLE_STATE
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            last = datetime.fromisoformat(str(raw["last_full_at"]))
            last = last.astimezone(timezone.utc)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return True
        return (now or datetime.now(timezone.utc)).astimezone(timezone.utc) - last >= self.sample_interval

    @staticmethod
    def _has_material_event(result: dict[str, Any]) -> bool:
        trade = result.get("auto_trade_results")
        if isinstance(trade, dict) and (int(trade.get("opened", 0) or 0) > 0 or trade.get("errors")):
            return True
        if result.get("rollout_metrics_error") or result.get("snapshot_error"):
            return True
        for row in result.get("rows", []):
            if not isinstance(row, dict):
                continue
            if row.get("analysis_error"):
                return True
            if str(row.get("scanner_action", "")).lower() == "ready":
                return True
            permission = row.get("trade_permission")
            status = permission.get("status") if isinstance(permission, dict) else permission
            if str(status or "").lower() == "allowed":
                return True
        return False
