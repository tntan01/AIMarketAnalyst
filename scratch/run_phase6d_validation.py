from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from controllers.backtest_controller import BacktestController
from core.backtest_contract import BACKTEST_PURPOSE_VALIDATION


def progress(percent: int, message: str) -> None:
    safe_message = message.encode("ascii", "backslashreplace").decode("ascii")
    print(f"PROGRESS {percent}% {safe_message}", flush=True)


def count_release_clean(rows: list[dict]) -> int:
    return sum(1 for row in rows if not row.get("strategy_rejection_reasons"))


def top_reasons(rows: list[dict], key: str) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(key)
        if isinstance(value, list):
            values = value or ["<empty>"]
        else:
            values = [value or "<empty>"]
        for item in values:
            text = str(item or "<empty>")
            counts[text] = counts.get(text, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:20]


def latest_backtest_snapshot() -> Path | None:
    root = Path.home() / "AppData" / "Roaming" / "ai-market-analyst" / "backtests"
    candidates = sorted(
        root.glob("backtest_EURUSD_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def main() -> None:
    controller = BacktestController()
    request = controller.build_request(
        symbol="EUR/USD",
        start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        end=datetime(2026, 6, 1, tzinfo=timezone.utc),
        initial_balance=10_000,
        risk_percent=1.0,
        purpose=BACKTEST_PURPOSE_VALIDATION,
        execution_mode="EXECUTION_PARITY",
    )
    result = controller.run_backtest(
        request=request,
        research_validation_enabled=False,
        monte_carlo_requested=False,
        _progress_callback=progress,
    )

    snapshot_path = str(result.get("snapshot_path", "") or "")
    snapshot_file = Path(snapshot_path) if snapshot_path else latest_backtest_snapshot()
    if snapshot_file is None or not snapshot_file.exists():
        raise FileNotFoundError(f"Không tìm thấy snapshot hợp lệ: {snapshot_path!r}")
    data = json.loads(snapshot_file.read_text(encoding="utf-8"))
    validation = data.get("validation_replay") or {}
    wf = data.get("walk_forward") or {}
    top_rows = data.get("candidate_ledger") or []
    is_rows = validation.get("is_candidate_ledger") or []
    oos_rows = validation.get("oos_candidate_ledger") or []

    summary = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "snapshot_path": str(snapshot_file),
        "request": {
            "purpose": (data.get("request") or {}).get("purpose"),
            "execution_mode": (data.get("request") or {}).get("execution_mode"),
            "broker_symbol": (data.get("request") or {}).get("broker_symbol"),
        },
        "run_policy": data.get("run_policy"),
        "lifecycle": data.get("lifecycle"),
        "top": {
            "rows": len(top_rows),
            "base_eligible": sum(1 for row in top_rows if row.get("base_eligible") is True),
            "release_clean": count_release_clean(top_rows),
            "release_reasons": top_reasons(top_rows, "strategy_rejection_reasons"),
            "simulation_reasons": top_reasons(top_rows, "simulation_rejection_reason"),
        },
        "validation": {
            "status": validation.get("status"),
            "reason": validation.get("reason"),
            "frozen_strategy_config": validation.get("frozen_strategy_config"),
            "probe_config_from_is": validation.get("probe_config_from_is"),
            "is_rows": len(is_rows),
            "is_base_eligible": sum(1 for row in is_rows if row.get("base_eligible") is True),
            "is_release_clean": count_release_clean(is_rows),
            "is_release_reasons": top_reasons(is_rows, "strategy_rejection_reasons"),
            "is_simulation_reasons": top_reasons(is_rows, "simulation_rejection_reason"),
            "oos_rows": len(oos_rows),
            "oos_release_clean": count_release_clean(oos_rows),
            "oos_release_reasons": top_reasons(oos_rows, "strategy_rejection_reasons"),
            "oos_simulation_reasons": top_reasons(oos_rows, "simulation_rejection_reason"),
        },
        "walk_forward": {
            "verdict": wf.get("verdict"),
            "window_count": wf.get("window_count"),
            "successful_window_count": wf.get("successful_window_count"),
            "aggregate_is": wf.get("aggregate_is"),
            "aggregate_oos": wf.get("aggregate_oos"),
            "oos_is_expectancy_ratio": wf.get("oos_is_expectancy_ratio"),
            "robustness_score": wf.get("robustness_score"),
            "window_errors": [
                {
                    "window_id": item.get("window_id"),
                    "error": item.get("error"),
                    "frozen_strategy_config": item.get("frozen_strategy_config"),
                    "oos_summary": item.get("oos_summary"),
                }
                for item in wf.get("windows", [])
                if item.get("error")
            ],
        },
    }
    print("SUMMARY " + json.dumps(summary, ensure_ascii=True, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
