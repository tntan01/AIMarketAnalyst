from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QTableView

from controllers.journal_controller import JournalController
from services.journal_service import JournalFilter, JournalService
from ui.screens.journal_screen import JournalScreen, JournalTableModel


def _analysis(symbol: str = "EUR/USD", action: str = "watch") -> dict[str, object]:
    return {
        "timestamp": "2026-05-29T07:35:00Z",
        "symbol": symbol,
        "data_quality": {"broker_symbol": symbol.replace("/", "") + ".r", "price_source": "MT5"},
        "market_regime": {"primary": "trend_up"},
        "direction_bias": "buy",
        "trade_permission": {"status": "caution"},
        "decision_summary": {"action": action, "best_scenario": "buy", "best_score": 78},
        "scenario_scores": {"buy": {"total": 78}, "sell": {"total": 42}},
        "scenarios": [
            {
                "type": "buy",
                "entry_zone": [1.1, 1.2],
                "stop_loss": 1.0,
                "take_profit": [1.3, 1.4],
                "risk_reward": "1:2.1",
                "position_sizing": {"suggested_lot": 0.1},
            }
        ],
        "macro": {"ai_summary": "Chờ H1 xác nhận."},
    }


def test_journal_service_migrates_saves_filters_and_updates_note(tmp_path) -> None:
    service = JournalService(tmp_path / "journal.db")
    entry_id = service.create_from_analysis(_analysis(), note="Ghi chú đầu")

    entries = service.list_entries(JournalFilter(symbol="EUR/USD", min_score=70))
    assert len(entries) == 1
    assert entries[0].id == entry_id
    assert entries[0].buy_score == 78
    assert entries[0].trade_permission == "caution"

    service.update_note(entry_id, "Chờ thêm xác nhận.")
    updated = service.get_entry(entry_id)
    assert updated is not None
    assert updated.note == "Chờ thêm xác nhận."

    assert service.list_entries(JournalFilter(symbol="GBP/USD")) == []
    service.delete_entry(entry_id)
    assert service.get_entry(entry_id) is None


def test_journal_controller_exports_json_without_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    service = JournalService(tmp_path / "journal.db")
    controller = JournalController(service)
    entry_id = controller.save_analysis(_analysis("XAU/USD"))
    entry = controller.get_entry(entry_id)
    assert entry is not None

    path = controller.export_entry_json(entry)
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["symbol"] == "XAU/USD"
    assert data["journal_id"] == entry_id
    assert "api_key" not in json.dumps(data).lower()


def test_journal_screen_uses_table_view_model_and_filters(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    service = JournalService(tmp_path / "journal.db")
    controller = JournalController(service)
    controller.save_analysis(_analysis("EUR/USD"))
    controller.save_analysis(_analysis("GBP/USD", "stand_aside"))

    screen = JournalScreen()
    screen.journal_controller = controller
    screen.refresh_status()

    assert isinstance(screen.table, QTableView)
    assert isinstance(screen.table_model, JournalTableModel)
    assert screen.table_model.rowCount() == 2

    screen.symbol_input.setCurrentText("EUR/USD")
    screen._apply_filters()

    assert screen.table_model.rowCount() == 1
    assert screen.table_model.entry_at(0).symbol == "EUR/USD"
