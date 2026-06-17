from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from config.paths import app_data_dir
from services.data_provider import DataProvider
from services.journal_service import JournalEntry, JournalFilter, JournalService
from services.mt5_service import MT5Service


class JournalController:
    def __init__(
        self,
        journal_service: JournalService | None = None,
        data_provider: DataProvider | None = None,
        # Backward compat
        mt5_service: MT5Service | None = None,
    ) -> None:
        self.journal_service = journal_service or JournalService()
        self.data_provider: DataProvider = data_provider or mt5_service or MT5Service()

    def list_entries(self, filters: JournalFilter | None = None) -> list[JournalEntry]:
        return self.journal_service.list_entries(filters)

    def get_entry(self, entry_id: int) -> JournalEntry | None:
        return self.journal_service.get_entry(entry_id)

    def symbols(self) -> list[str]:
        return self.journal_service.symbols()

    def stats(self) -> dict[str, object]:
        return self.journal_service.stats()

    def performance_summary(self) -> dict[str, object]:
        return self.journal_service.performance_summary()

    def sync_mt5_history(self, days: int = 90) -> dict[str, object]:
        end = datetime.now(UTC)
        start = end - timedelta(days=max(1, int(days)))
        trades = self.data_provider.closed_trade_history(start=start, end=end)
        return self.journal_service.sync_mt5_closed_trades(trades)

    def save_analysis(self, analysis: dict[str, object], *, mode: str = "scanner_detail", note: str = "") -> int:
        return self.journal_service.create_from_analysis(analysis, mode=mode, note=note)

    def save_scanner_row(self, row: dict[str, object], *, note: str = "") -> int:
        return self.journal_service.create_from_scanner_row(row, note=note)

    def update_note(self, entry_id: int, note: str) -> None:
        self.journal_service.update_note(entry_id, note)

    def update_lifecycle(self, entry_id: int, updates: dict[str, object]) -> dict[str, object] | None:
        return self.journal_service.update_lifecycle(entry_id, updates)

    def delete_entry(self, entry_id: int) -> None:
        self.journal_service.delete_entry(entry_id)

    def export_entry_json(self, entry: JournalEntry) -> Path:
        export_dir = app_data_dir() / "journal_exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        path = export_dir / f"journal_{entry.id}_{entry.symbol.replace('/', '')}.json"
        payload = json.loads(entry.analysis_json)
        payload["journal_note"] = entry.note
        payload["journal_id"] = entry.id
        payload["journal_lifecycle"] = {
            "trade_status": entry.trade_status,
            "opened_at": entry.opened_at,
            "closed_at": entry.closed_at,
            "planned_lot": entry.planned_lot,
            "actual_lot": entry.actual_lot,
            "planned_entry": entry.planned_entry,
            "actual_entry": entry.actual_entry,
            "planned_sl": entry.planned_sl,
            "actual_sl": entry.actual_sl,
            "planned_tp": entry.planned_tp,
            "actual_tp": entry.actual_tp,
            "actual_exit": entry.actual_exit,
            "result": entry.result,
            "result_r": entry.result_r,
            "result_pct": entry.result_pct,
            "result_amount": entry.result_amount,
            "exit_reason": entry.exit_reason,
            "manual_mistake_tags": entry.manual_mistake_tags,
            "auto_mistake_tags": entry.auto_mistake_tags,
            "execution_quality_score": entry.execution_quality_score,
            "mt5_deal_id": entry.mt5_deal_id,
            "mt5_order_id": entry.mt5_order_id,
            "mt5_position_id": entry.mt5_position_id,
            "synced_from": entry.synced_from,
            "synced_at_utc": entry.synced_at_utc,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
