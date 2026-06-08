"""Phase 18.6 — demo journal workflow: save analysis, update outcome, list closed trades.

Usage: python scripts/phase18_demo_journal_workflow.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.journal_service import JournalService
from tests.test_phase18_demo_data_fixtures import (
    build_demo_candles_by_timeframe,
    build_demo_analysis_input,
    build_demo_data_quality,
)
from core.analysis_engine import analyze_symbol


def run_demo_journal_workflow(
    db_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> dict:
    """Run journal workflow: create entries, update outcome, list closed trades."""
    db = Path(db_path) if db_path else (
        Path(__file__).resolve().parent.parent / "data" / "phase18_demo_journal.db"
    )

    # Clean start
    db.unlink(missing_ok=True)
    service = JournalService(db_path=db)

    # Create entries for first 3 symbols
    entry_ids = []
    symbols = ["EUR/USD", "GBP/JPY", "USD/JPY"]

    for sym in symbols:
        request = build_demo_analysis_input(sym)
        candles = build_demo_candles_by_timeframe(sym)
        dq = build_demo_data_quality(sym)
        result = analyze_symbol(
            request, candles, data_quality=dq,
            macro_alignment={"buy": 15, "sell": 15}, macro_confidence=1.0,
        )
        eid = service.create_from_analysis(result, mode="single_analysis")
        entry_ids.append(eid)

    # Update outcome for first entry (simulate closed trade)
    if entry_ids:
        service.update_trade_outcome(entry_ids[0], {
            "result_r": 1.2,
            "result_pct": 1.0,
            "closed_at": "2026-06-04T12:00:00Z",
            "exit_reason": "take_profit",
            "actual_entry": 1.0865,
            "actual_exit": 1.0920,
            "actual_lot": 0.10,
            "auto_mistake_tags": ["closed_too_early"],
            "execution_quality_score": 80,
        })

    # Also close a second entry with a loss
    if len(entry_ids) >= 2:
        service.update_trade_outcome(entry_ids[1], {
            "result_r": -1.0,
            "result_pct": -0.8,
            "closed_at": "2026-06-04T10:00:00Z",
            "exit_reason": "stop_loss",
            "actual_lot": 0.15,
            "planned_lot": 0.10,
            "execution_quality_score": 60,
        })

    closed_trades = service.list_closed_trades_for_account_guard()

    report = {
        "entries_created": len(entry_ids),
        "entry_ids": entry_ids,
        "closed_trades_count": len(closed_trades),
        "sample_closed_trade_keys": list(closed_trades[0].keys()) if closed_trades else [],
        "db_path": str(db),
    }

    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return report


def main() -> None:
    output = Path(__file__).resolve().parent.parent / "data" / "phase18_demo_journal_report.json"
    report = run_demo_journal_workflow(output_path=output)
    print(f"Created {report['entries_created']} journal entries")
    print(f"Closed trades: {report['closed_trades_count']}")
    print(f"Keys available: {', '.join(report['sample_closed_trade_keys'][:10])}...")
    print(f"Report saved to {output}")


if __name__ == "__main__":
    main()
