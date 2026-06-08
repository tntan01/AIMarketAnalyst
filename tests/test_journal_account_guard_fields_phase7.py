from __future__ import annotations

import json
import sqlite3

from services.journal_service import (
    JournalEntry,
    JournalFilter,
    JournalService,
    entry_from_row,
    journal_entry_from_analysis,
)


def _analysis(symbol: str = "EUR/USD", action: str = "watch") -> dict[str, object]:
    return {
        "timestamp": "2026-06-04T07:35:00Z",
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


# ---------------------------------------------------------------------------
# Test 1 — migration adds fields to schema
# ---------------------------------------------------------------------------
def test_migration_adds_account_guard_columns(tmp_path) -> None:
    service = JournalService(tmp_path / "journal.db")
    service.create_from_analysis(_analysis())

    with service._connect() as conn:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(journal_entries)").fetchall()
        }

    for col in ("result_r", "result_pct", "closed_at", "exit_reason", "actual_lot", "planned_lot"):
        assert col in columns, f"Missing column: {col}"


# ---------------------------------------------------------------------------
# Test 2 — save journal with new fields and read them back
# ---------------------------------------------------------------------------
def test_save_and_read_with_account_guard_fields(tmp_path) -> None:
    service = JournalService(tmp_path / "journal.db")

    analysis = _analysis()
    entry_id = service.create_from_analysis(analysis, note="Test entry")

    # Update the record with new fields via direct SQL
    with service._connect() as conn:
        conn.execute(
            """UPDATE journal_entries
               SET result_r = -1.0, result_pct = -1.2,
                   closed_at = '2026-01-01T10:00:00+07:00',
                   exit_reason = 'stop_loss',
                   actual_lot = 0.10, planned_lot = 0.10
               WHERE id = ?""",
            (entry_id,),
        )
        conn.commit()

    entry = service.get_entry(entry_id)
    assert entry is not None
    assert entry.result_r == -1.0
    assert entry.result_pct == -1.2
    assert entry.closed_at == "2026-01-01T10:00:00+07:00"
    assert entry.exit_reason == "stop_loss"
    assert entry.actual_lot == 0.10
    assert entry.planned_lot == 0.10


# ---------------------------------------------------------------------------
# Test 3 — records without new fields don't crash
# ---------------------------------------------------------------------------
def test_old_record_without_new_fields_does_not_crash(tmp_path) -> None:
    service = JournalService(tmp_path / "journal.db")
    entry_id = service.create_from_analysis(_analysis())

    entry = service.get_entry(entry_id)
    assert entry is not None
    # New fields should be None (not populated)
    assert entry.result_r is None
    assert entry.result_pct is None
    assert entry.closed_at is None
    assert entry.exit_reason is None
    assert entry.actual_lot is None
    assert entry.planned_lot is None


# ---------------------------------------------------------------------------
# Test 4 — list_closed_trades_for_account_guard
# ---------------------------------------------------------------------------
def test_list_closed_trades_for_account_guard(tmp_path) -> None:
    service = JournalService(tmp_path / "journal.db")

    # Create 3 entries, 2 closed and 1 not
    e1 = service.create_from_analysis(_analysis("EUR/USD"))
    e2 = service.create_from_analysis(_analysis("GBP/USD"))
    e3 = service.create_from_analysis(_analysis("USD/JPY"))

    with service._connect() as conn:
        # Mark e1 and e2 as closed
        conn.execute(
            """UPDATE journal_entries
               SET closed_at = '2026-06-01T10:00:00+07:00', result_r = -0.5, result_pct = -0.6,
                   exit_reason = 'stop_loss', actual_lot = 0.10, planned_lot = 0.10
               WHERE id = ?""",
            (e1,),
        )
        conn.execute(
            """UPDATE journal_entries
               SET closed_at = '2026-06-02T10:00:00+07:00', result_r = 1.2, result_pct = 1.5,
                   exit_reason = 'take_profit', actual_lot = 0.10, planned_lot = 0.10
               WHERE id = ?""",
            (e2,),
        )
        conn.commit()

    trades = service.list_closed_trades_for_account_guard()
    assert len(trades) == 2

    # Each trade has required keys
    for trade in trades:
        assert "result_r" in trade
        assert "result_pct" in trade
        assert "closed_at" in trade
        assert "exit_reason" in trade
        assert "actual_lot" in trade
        assert "planned_lot" in trade
        assert "symbol" in trade
        assert "direction" in trade

    # Verify values
    eur_trade = next(t for t in trades if t["symbol"] == "EUR/USD")
    assert eur_trade["result_r"] == -0.5
    assert eur_trade["result_pct"] == -0.6
    assert eur_trade["exit_reason"] == "stop_loss"

    gbp_trade = next(t for t in trades if t["symbol"] == "GBP/USD")
    assert gbp_trade["result_r"] == 1.2
    assert gbp_trade["result_pct"] == 1.5
    assert gbp_trade["exit_reason"] == "take_profit"


# ---------------------------------------------------------------------------
# Test 5 — empty list when no closed trades
# ---------------------------------------------------------------------------
def test_list_closed_trades_empty_when_none_closed(tmp_path) -> None:
    service = JournalService(tmp_path / "journal.db")
    service.create_from_analysis(_analysis())
    service.create_from_analysis(_analysis("GBP/USD"))

    trades = service.list_closed_trades_for_account_guard()
    assert trades == []


# ---------------------------------------------------------------------------
# Test 6 — list_closed_trades respects limit
# ---------------------------------------------------------------------------
def test_list_closed_trades_respects_limit(tmp_path) -> None:
    service = JournalService(tmp_path / "journal.db")

    # Create 10 closed entries
    for i in range(10):
        eid = service.create_from_analysis(_analysis(f"EUR/USD"))
        with service._connect() as conn:
            conn.execute(
                "UPDATE journal_entries SET closed_at = ? WHERE id = ?",
                (f"2026-06-{(i + 1):02d}T10:00:00+07:00", eid),
            )
            conn.commit()

    trades_default = service.list_closed_trades_for_account_guard()
    assert len(trades_default) == 10

    trades_limited = service.list_closed_trades_for_account_guard(limit=3)
    assert len(trades_limited) == 3


# ---------------------------------------------------------------------------
# Test 7 — journal_entry_from_analysis defaults new fields to None
# ---------------------------------------------------------------------------
def test_journal_entry_from_analysis_defaults_new_fields() -> None:
    entry = journal_entry_from_analysis(_analysis(), mode="single_analysis")
    assert entry.result_r is None
    assert entry.result_pct is None
    assert entry.closed_at is None
    assert entry.exit_reason is None
    assert entry.actual_lot is None
    assert entry.planned_lot is None


# ---------------------------------------------------------------------------
# Test 8 — entry_from_row handles missing columns
# ---------------------------------------------------------------------------
def test_entry_from_row_handles_missing_columns() -> None:
    """Simulate a row from an older DB without the new columns."""

    class FakeRow:
        _data: dict[str, object]

        def __init__(self, data: dict[str, object]) -> None:
            self._data = data

        def __getitem__(self, key: str) -> object:
            if key in self._data:
                return self._data[key]
            raise KeyError(key)

    row = FakeRow({
        "id": 1,
        "timestamp_utc": "2026-06-01T00:00:00Z",
        "saved_at_utc": "2026-06-01T00:00:00Z",
        "symbol": "EUR/USD",
        "broker_symbol": "EURUSD.r",
        "mode": "single_analysis",
        "data_source": "MT5",
        "market_regime": "trend_up",
        "decision": "watch",
        "direction_bias": "buy",
        "trade_permission": "caution",
        "buy_score": 78,
        "sell_score": 42,
        "selected_scenario": "buy",
        "entry_zone": "[1.1, 1.2]",
        "stop_loss": "1.0",
        "take_profit": "[1.3, 1.4]",
        "risk_reward": "1:2.1",
        "suggested_lot": 0.1,
        "ai_commentary": "Test.",
        "analysis_json": "{}",
        "user_action": "",
        "result": "",
        "note": "",
    })
    entry = entry_from_row(row)  # type: ignore[arg-type]
    assert entry.symbol == "EUR/USD"
    assert entry.buy_score == 78
    assert entry.result_r is None
    assert entry.result_pct is None
    assert entry.closed_at is None


# ---------------------------------------------------------------------------
# Test 9 — full filter/list still works with new fields
# ---------------------------------------------------------------------------
def test_filter_still_works_with_new_fields(tmp_path) -> None:
    service = JournalService(tmp_path / "journal.db")
    service.create_from_analysis(_analysis("EUR/USD"))
    service.create_from_analysis(_analysis("GBP/USD", "stand_aside"))

    entries = service.list_entries(JournalFilter(symbol="EUR/USD", min_score=0))
    assert len(entries) == 1
    assert entries[0].symbol == "EUR/USD"
    # New fields present but None
    assert entries[0].result_r is None


# ---------------------------------------------------------------------------
# Test 10 — export JSON does not break with new fields
# ---------------------------------------------------------------------------
def test_export_json_with_new_fields(tmp_path) -> None:
    service = JournalService(tmp_path / "journal.db")
    analysis = _analysis("XAU/USD")
    entry_id = service.create_from_analysis(analysis)

    entry = service.get_entry(entry_id)
    assert entry is not None

    import dataclasses
    data = dataclasses.asdict(entry)
    json_str = json.dumps(data, ensure_ascii=False, default=str)
    parsed = json.loads(json_str)

    assert parsed["symbol"] == "XAU/USD"
    assert parsed["result_r"] is None
    assert parsed["result_pct"] is None
    assert parsed["closed_at"] is None
    assert "api_key" not in json_str.lower()


# ---------------------------------------------------------------------------
# Test 11 — stats still works after migration
# ---------------------------------------------------------------------------
def test_stats_still_works_with_new_fields(tmp_path) -> None:
    service = JournalService(tmp_path / "journal.db")
    service.create_from_analysis(_analysis("EUR/USD"))
    service.create_from_analysis(_analysis("GBP/USD"))

    stats = service.stats()
    assert stats["total"] == 2
    assert isinstance(stats["top_symbol"], str)
