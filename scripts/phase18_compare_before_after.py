"""Phase 18.5 — compare before/after scoring snapshots, safe on missing baseline.

Usage: python scripts/phase18_compare_before_after.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _load_snapshot(path: Path) -> list[dict]:
    """Load a snapshot JSON file.  Supports list or dict with 'rows' key."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "rows" in data:
        return data["rows"]
    raise ValueError(f"Unrecognised snapshot format in {path}")


def compare_snapshots(
    before_path: str | Path | None,
    after_path: str | Path,
    output_path: str | Path | None = None,
) -> dict:
    """Compare before/after snapshots by symbol.

    If *before_path* does not exist or is ``None``, returns a report
    with ``baseline_available: false``.
    """
    after_file = Path(after_path)
    if not after_file.is_file():
        raise FileNotFoundError(f"After snapshot not found: {after_file}")

    after_rows = _load_snapshot(after_file)
    after_map = {}
    for row in after_rows:
        sym = row.get("symbol", "unknown")
        after_map[sym] = row

    before_rows: list[dict] = []
    before_map: dict[str, dict] = {}

    if before_path:
        before_file = Path(before_path)
        if before_file.is_file():
            before_rows = _load_snapshot(before_file)
            for row in before_rows:
                sym = row.get("symbol", "unknown")
                before_map[sym] = row

    if not before_rows:
        return {
            "baseline_available": False,
            "message": "Không tìm thấy before snapshot, chỉ ghi after snapshot summary.",
            "after_count": len(after_rows),
            "after_symbols": sorted(after_map.keys()),
            "comparisons": [],
        }

    comparisons = []
    all_symbols = sorted(set(list(before_map.keys()) + list(after_map.keys())))

    for sym in all_symbols:
        before = before_map.get(sym, {})
        after = after_map.get(sym, {})
        before_best = before.get("best_score")
        after_best = after.get("best_score")
        delta = None
        if isinstance(before_best, (int, float)) and isinstance(after_best, (int, float)):
            delta = int(after_best) - int(before_best)

        comparisons.append({
            "symbol": sym,
            "before_best_score": before_best,
            "after_best_score": after_best,
            "after_final_score": after.get("final_score"),
            "after_opportunity_score": after.get("opportunity_score"),
            "before_decision": before.get("decision_action") or before.get("scanner_action"),
            "after_decision": after.get("scanner_group") or after.get("decision_action"),
            "score_delta": delta,
        })

    report = {
        "baseline_available": True,
        "before_count": len(before_rows),
        "after_count": len(after_rows),
        "comparisons": comparisons,
    }

    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return report


def main() -> None:
    project = Path(__file__).resolve().parent.parent
    before = project / "data" / "before_scoring_upgrade_snapshot.json"
    after = project / "data" / "phase18_demo_scanner_snapshot.json"
    output = project / "data" / "phase18_before_after_report.json"

    report = compare_snapshots(before, after, output)

    if report["baseline_available"]:
        print(f"Compared {len(report['comparisons'])} symbols:")
        for c in report["comparisons"]:
            print(f"  {c['symbol']}: before_best={c['before_best_score']} "
                  f"after_best={c['after_best_score']} "
                  f"final={c['after_final_score']} delta={c['score_delta']}")
    else:
        print(report["message"])
        print(f"After count: {report['after_count']}")

    print(f"Report saved to {output}")


if __name__ == "__main__":
    main()
