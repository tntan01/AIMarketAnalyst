from __future__ import annotations

import json
from pathlib import Path

from config.paths import app_data_dir
from services.journal_service import JournalEntry, JournalFilter, JournalService


class JournalController:
    def __init__(self, journal_service: JournalService | None = None) -> None:
        self.journal_service = journal_service or JournalService()

    def list_entries(self, filters: JournalFilter | None = None) -> list[JournalEntry]:
        return self.journal_service.list_entries(filters)

    def get_entry(self, entry_id: int) -> JournalEntry | None:
        return self.journal_service.get_entry(entry_id)

    def symbols(self) -> list[str]:
        return self.journal_service.symbols()

    def stats(self) -> dict[str, object]:
        return self.journal_service.stats()

    def save_analysis(self, analysis: dict[str, object], *, mode: str = "scanner_detail", note: str = "") -> int:
        return self.journal_service.create_from_analysis(analysis, mode=mode, note=note)

    def save_scanner_row(self, row: dict[str, object], *, note: str = "") -> int:
        return self.journal_service.create_from_scanner_row(row, note=note)

    def update_note(self, entry_id: int, note: str) -> None:
        self.journal_service.update_note(entry_id, note)

    def delete_entry(self, entry_id: int) -> None:
        self.journal_service.delete_entry(entry_id)

    def export_entry_json(self, entry: JournalEntry) -> Path:
        export_dir = app_data_dir() / "journal_exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        path = export_dir / f"journal_{entry.id}_{entry.symbol.replace('/', '')}.json"
        payload = json.loads(entry.analysis_json)
        payload["journal_note"] = entry.note
        payload["journal_id"] = entry.id
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
