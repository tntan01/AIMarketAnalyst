"""Phase 18.3 — test demo analysis snapshot generation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.phase18_run_demo_analysis import run_demo_analysis


def test_demo_analysis_5_symbols(tmp_path):
    output_file = tmp_path / "snapshot.json"
    results = run_demo_analysis(output_file)

    assert len(results) == 5, f"Expected 5 symbols, got {len(results)}"

    symbols = {r["symbol"] for r in results}
    assert symbols == {"EUR/USD", "GBP/JPY", "USD/JPY", "XAU/USD", "AUD/USD"}

    for row in results:
        assert isinstance(row["buy_score"], int)
        assert isinstance(row["sell_score"], int)
        assert isinstance(row["best_score"], int)
        assert isinstance(row["final_score"], int)
        assert 0 <= row["final_score"] <= 100
        assert isinstance(row["decision_engine_decision"], str)
        assert len(row["decision_engine_decision"]) > 0
        assert isinstance(row["decision_action"], str)
        assert isinstance(row["trade_permission"], str)
        assert row["trade_permission"] in ("allowed", "caution", "blocked")

    # JSON file exists and is valid
    assert output_file.is_file()
    data = json.loads(output_file.read_text(encoding="utf-8"))
    assert len(data) == 5


def test_script_runnable():
    """Verify the script's main() runs without error."""
    from scripts.phase18_run_demo_analysis import main
    main()
    snapshot = Path(__file__).resolve().parent.parent / "data" / "phase18_demo_analysis_snapshot.json"
    assert snapshot.is_file()
