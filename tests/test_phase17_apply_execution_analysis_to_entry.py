"""Phase 17.10 — test apply_execution_analysis_to_entry() utility."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.journal_service import JournalService, JournalEntry


def _create_closed_entry(service: JournalService, symbol="EUR/USD", direction="buy",
                         result_r=-1.0, closed_at="2026-06-04T09:00:00Z",
                         actual_lot=0.10, planned_lot=0.10, **extra):
    entry = JournalEntry(
        id=None,
        timestamp_utc="2026-06-04T08:00:00Z",
        saved_at_utc="2026-06-04T08:00:01Z",
        symbol=symbol, broker_symbol=symbol.replace("/", ""),
        mode="single_analysis", data_source="MT5",
        market_regime="trend_up", decision="watch",
        direction_bias=direction, trade_permission="allowed",
        buy_score=82, sell_score=55,
        selected_scenario=direction, entry_zone="", stop_loss="", take_profit="",
        risk_reward="", suggested_lot=0.10, ai_commentary="", analysis_json="{}",
        result_r=result_r, result_pct=-0.8, closed_at=closed_at,
        exit_reason="stop_loss", actual_lot=actual_lot, planned_lot=planned_lot,
        **extra,
    )
    return service.create(entry)


def test_apply_to_existing_entry(tmp_path):
    service = JournalService(db_path=tmp_path / "test_phase17.db")

    # Previous losing trade
    _create_closed_entry(service, result_r=-1.0, closed_at="2026-06-04T09:00:00Z",
                         actual_lot=0.10, planned_lot=0.10)

    # Current trade: oversized + soon after loss
    current_id = _create_closed_entry(
        service,
        result_r=-0.5,
        closed_at="2026-06-04T10:00:00Z",
        actual_lot=0.20,  # oversized
    )

    result = service.apply_execution_analysis_to_entry(current_id)
    assert result is not None
    assert "detection" in result
    assert "execution_quality" in result

    fetched = service.get_entry(current_id)
    assert fetched is not None
    # Execution quality score should be set (may not be 100 if mistakes found)
    assert fetched.execution_quality_score is not None


def test_apply_to_nonexistent_returns_none(tmp_path):
    service = JournalService(db_path=tmp_path / "test_phase17.db")
    assert service.apply_execution_analysis_to_entry(9999) is None


def test_apply_updates_auto_tags(tmp_path):
    service = JournalService(db_path=tmp_path / "test_phase17.db")
    current_id = _create_closed_entry(
        service,
        actual_lot=0.20, planned_lot=0.10,  # oversized
    )
    service.apply_execution_analysis_to_entry(current_id)
    fetched = service.get_entry(current_id)
    assert fetched is not None
    # Should have some auto_tags if oversized detected
    auto_tags = fetched.auto_mistake_tags or ""
    assert "oversized" in auto_tags or fetched.execution_quality_score != 100
