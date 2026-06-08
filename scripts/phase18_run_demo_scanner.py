"""Phase 18.4 — run scanner pipeline: analysis → row → sort → output, save snapshot.

Usage: python scripts/phase18_run_demo_scanner.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scanner import (
    scanner_row_from_analysis,
    sort_scanner_rows,
    build_scanner_output,
    ScannerRequest,
)
from scripts.phase18_run_demo_analysis import run_demo_analysis
from tests.test_phase18_demo_data_fixtures import build_demo_analysis_input


def run_demo_scanner(output_path: str | Path | None = None) -> dict:
    """Run scanner pipeline for all 5 symbols, return output dict."""
    analysis_results = run_demo_analysis()

    rows = []
    for result in analysis_results:
        sym = result["symbol"]
        broker = build_demo_analysis_input(sym).broker_symbol
        # Re-run full analysis to get actual analysis_result dict
        from tests.test_phase18_demo_data_fixtures import (
            build_demo_candles_by_timeframe,
            build_demo_data_quality,
        )
        from core.analysis_engine import analyze_symbol

        request = build_demo_analysis_input(sym)
        candles = build_demo_candles_by_timeframe(sym)
        dq = build_demo_data_quality(sym)
        full_result = analyze_symbol(
            request, candles, data_quality=dq,
            macro_alignment={"buy": 15, "sell": 15}, macro_confidence=1.0,
        )
        row = scanner_row_from_analysis(full_result, broker_symbol=broker)
        rows.append(row)

    sorted_rows = sort_scanner_rows(rows)
    scanner_request = ScannerRequest(
        symbols=list(sorted({r["symbol"] for r in sorted_rows})),
        account_balance=10_000,
        risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh",
        max_ai_details=0,
    )
    output = build_scanner_output(sorted_rows, scanner_request, ai_called=0)

    # Build lightweight snapshot rows
    snapshot_rows = []
    for row in sorted_rows:
        snapshot_rows.append({
            "rank": row.get("rank"),
            "symbol": row.get("symbol"),
            "broker_symbol": row.get("broker_symbol"),
            "scanner_group": row.get("scanner_group"),
            "scanner_action": row.get("scanner_action"),
            "scanner_decision": row.get("scanner_decision"),
            "best_side": row.get("best_side"),
            "buy_score": row.get("buy_score"),
            "sell_score": row.get("sell_score"),
            "best_score": row.get("best_score"),
            "final_score": row.get("final_score"),
            "opportunity_score": row.get("opportunity_score"),
            "trade_permission": row.get("trade_permission"),
            "entry_status": row.get("entry_status"),
            "m15_quality": row.get("m15_quality"),
            "expected_effective_rr": row.get("expected_effective_rr"),
            "risk_reward": row.get("risk_reward"),
            "score_gap": row.get("score_gap"),
            "ranking_reason_codes": row.get("ranking_reason_codes", []),
            "ranking_warning_codes": row.get("ranking_warning_codes", []),
            "ranking_penalty_codes": row.get("ranking_penalty_codes", []),
        })

    summary = output.get("summary", {})
    snapshot = {
        "mode": output.get("mode"),
        "symbols_scanned": output.get("symbols_scanned"),
        "summary": summary,
        "rows": snapshot_rows,
    }

    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    return snapshot


def main() -> None:
    output = Path(__file__).resolve().parent.parent / "data" / "phase18_demo_scanner_snapshot.json"
    snapshot = run_demo_scanner(output)
    summary = snapshot.get("summary", {})
    print(f"Scanner snapshot: {snapshot['symbols_scanned']} symbols scanned, saved to {output}")
    print(f"  Summary: ready_now={summary.get('ready_now_count')} "
          f"waiting={summary.get('waiting_confirmation_count')} "
          f"watch={summary.get('watch_zone_count')} blocked={summary.get('blocked_count')}")
    for row in snapshot.get("rows", []):
        print(f"  #{row['rank']} {row['symbol']}: group={row['scanner_group']} "
              f"opp={row['opportunity_score']} final={row['final_score']}")


if __name__ == "__main__":
    main()
