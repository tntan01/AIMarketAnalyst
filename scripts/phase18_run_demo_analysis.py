"""Phase 18.3 — run demo analysis for 5 symbols using fake candles, save snapshot JSON.

Usage: python scripts/phase18_run_demo_analysis.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.analysis_engine import analyze_symbol
from tests.test_phase18_demo_data_fixtures import (
    SYMBOL_CONFIGS,
    build_demo_candles_by_timeframe,
    build_demo_analysis_input,
    build_demo_data_quality,
)


def run_demo_analysis(output_path: str | Path | None = None) -> list[dict]:
    """Run analyze_symbol for all 5 symbols, return snapshot rows."""
    results: list[dict] = []

    for symbol in SYMBOL_CONFIGS:
        candles = build_demo_candles_by_timeframe(symbol)
        request = build_demo_analysis_input(symbol)
        dq = build_demo_data_quality(symbol)

        result = analyze_symbol(
            request,
            candles,
            data_quality=dq,
            macro_alignment={"buy": 15, "sell": 15},
            macro_confidence=1.0,
        )

        ds = result.get("decision_summary", {})
        if not isinstance(ds, dict):
            ds = {}
        de = result.get("decision_engine", {})
        if not isinstance(de, dict):
            de = {}

        scenarios = result.get("scenarios", [])
        top_scenario = scenarios[0] if scenarios and isinstance(scenarios[0], dict) else {}

        snapshot = {
            "symbol": symbol,
            "buy_score": int(result.get("scenario_scores", {}).get("buy", {}).get("signal_score", 0)),
            "sell_score": int(result.get("scenario_scores", {}).get("sell", {}).get("signal_score", 0)),
            "best_score": int(ds.get("best_score", 0)),
            "final_score": int(result.get("final_score", 0)),
            "decision_engine_decision": str(de.get("decision", "")),
            "decision_action": str(ds.get("action", "")),
            "trade_permission": str(result.get("trade_permission", {}).get("status", "")),
            "gate_decision_cap": ds.get("gate_decision_cap"),
            "score_gap": ds.get("score_gap"),
            "scenario_count": len(scenarios),
            "top_entry_status": str(top_scenario.get("entry_status", "")),
            "top_expected_effective_rr": top_scenario.get("expected_effective_rr"),
            "reason_codes": result.get("reason_codes", []),
            "warning_codes": result.get("warning_codes", []),
            "block_codes": result.get("block_codes", []),
        }
        results.append(snapshot)

    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    return results


def main() -> None:
    output = Path(__file__).resolve().parent.parent / "data" / "phase18_demo_analysis_snapshot.json"
    results = run_demo_analysis(output)
    print(f"Saved {len(results)} symbol snapshots to {output}")
    for r in results:
        print(f"  {r['symbol']}: buy={r['buy_score']} sell={r['sell_score']} "
              f"final={r['final_score']} decision={r['decision_engine_decision']} "
              f"permission={r['trade_permission']}")


if __name__ == "__main__":
    main()
