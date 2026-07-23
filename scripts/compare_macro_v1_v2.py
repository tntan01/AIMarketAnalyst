#!/usr/bin/env python3
"""Phase 15G — Shadow comparison: Macro V1 vs Macro V2.

Reads a scanner snapshot JSON and compares ``macro_alignment_scores`` (V1)
with ``macro_v2`` (V2, shadow-only) per row.

Usage::

    python scripts/compare_macro_v1_v2.py [path/to/snapshot.json]

Options::

    --json-output PATH   Full report as JSON
    --csv PATH           Per-row detail as CSV
    --limit N            Top-N rows in detail tables (default 20)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class RowComparison:
    symbol: str
    side: str
    v1_buy: int | None
    v1_sell: int | None
    v2_buy: int | None
    v2_sell: int | None
    v2_confidence: float | None
    v2_pair_edge: int | None
    v1_direction: str        # "buy", "sell", "neutral"
    v2_direction: str
    agreement: bool          # V1 and V2 agree on direction
    score_gap_buy: int | None
    score_gap_sell: int | None
    v2_available: bool


@dataclass
class ComparisonReport:
    total_rows: int
    rows_with_v2: int
    rows_with_v1: int
    direction_agreement_pct: float
    bias_flips: int           # V1 buy, V2 sell (or vice versa)
    neutral_to_directional: int
    directional_to_neutral: int
    rows_with_both: int        # denominator for all transition rates
    rows_missing_v2: int
    transition_invariant_ok: bool
    avg_v1_buy: float
    avg_v1_sell: float
    avg_v2_buy: float
    avg_v2_sell: float
    avg_score_gap: float
    avg_v2_confidence: float
    rows_with_full_confidence: int
    rows_with_low_confidence: int
    rows: list[RowComparison] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse_input(source: object) -> list[dict[str, Any]]:
    if isinstance(source, list):
        return [r for r in source if isinstance(r, dict)]
    if isinstance(source, dict):
        for key in ("rows", "scanner_rows"):
            val = source.get(key)
            if isinstance(val, list):
                return [r for r in val if isinstance(r, dict)]
        result = source.get("result")
        if isinstance(result, dict):
            for key in ("rows", "scanner_rows"):
                val = result.get(key)
                if isinstance(val, list):
                    return [r for r in val if isinstance(r, dict)]
        if "symbol" in source:
            return [source]
    return []


def _safe_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_v1(row: dict[str, Any]) -> dict[str, Any] | None:
    """Extract V1 macro_alignment_scores from row or nested analysis_result."""
    ar = row.get("analysis_result")
    if isinstance(ar, dict):
        macro = ar.get("macro", {})
        if isinstance(macro, dict):
            driver = macro.get("driver_context", {})
            if isinstance(driver, dict):
                scores = driver.get("macro_alignment_scores")
                if isinstance(scores, dict):
                    return scores
    scores = row.get("macro_alignment_scores")
    if isinstance(scores, dict):
        return scores
    return None


def _resolve_v2(row: dict[str, Any]) -> dict[str, Any] | None:
    """Extract macro_v2 from row or nested analysis_result."""
    ar = row.get("analysis_result")
    if isinstance(ar, dict):
        macro = ar.get("macro", {})
        if isinstance(macro, dict):
            driver = macro.get("driver_context", {})
            if isinstance(driver, dict):
                v2 = driver.get("macro_v2")
                if isinstance(v2, dict):
                    return v2
    v2 = row.get("macro_v2")
    if isinstance(v2, dict):
        return v2
    return None


def _direction(buy: int | None, sell: int | None, *, gap: int = 5) -> str:
    """Classify direction matching _detect_macro_status gap threshold.
    |buy - sell| > gap → directional; else neutral."""
    if buy is None or sell is None:
        return "unknown"
    if buy > sell + gap:
        return "buy"
    if sell > buy + gap:
        return "sell"
    return "neutral"


def compare_row(row: dict[str, Any], *, direction_gap: int = 5,
                v2_multiplier: float = 1.25, edge_deadband: int = -1) -> RowComparison:
    v1 = _resolve_v1(row)
    v2_raw = _resolve_v2(row)
    sym = str(row.get("symbol", "?"))
    side = str(row.get("best_side", ""))

    v1_buy = _safe_int(v1["buy"]) if v1 else None
    v1_sell = _safe_int(v1["sell"]) if v1 else None
    v2_buy = _safe_int(v2_raw["buy"]) if v2_raw else None
    v2_sell = _safe_int(v2_raw["sell"]) if v2_raw else None
    v2_conf = float(v2_raw.get("confidence", 0)) if v2_raw else None
    v2_edge = _safe_int(v2_raw.get("pair_edge")) if v2_raw else None

    # Recompute V2 buy/sell if multiplier or edge_deadband differs from default
    if v2_raw and v2_edge is not None and (v2_multiplier != 1.25 or edge_deadband != -1):
        if edge_deadband >= 0 and abs(v2_edge) <= edge_deadband:
            v2_buy = 15
            v2_sell = 15
        else:
            raw = max(0.0, min(30.0, 15.0 + v2_edge * v2_multiplier))
            v2_buy = int(round(raw))
            v2_sell = 30 - v2_buy

    d1 = _direction(v1_buy, v1_sell, gap=direction_gap)
    d2 = _direction(v2_buy, v2_sell, gap=direction_gap)

    return RowComparison(
        symbol=sym, side=side,
        v1_buy=v1_buy, v1_sell=v1_sell,
        v2_buy=v2_buy, v2_sell=v2_sell,
        v2_confidence=v2_conf, v2_pair_edge=v2_edge,
        v1_direction=d1, v2_direction=d2,
        agreement=(d1 == d2),
        score_gap_buy=abs(v1_buy - v2_buy) if v1_buy is not None and v2_buy is not None else None,
        score_gap_sell=abs(v1_sell - v2_sell) if v1_sell is not None and v2_sell is not None else None,
        v2_available=v2_raw is not None,
    )


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def compute_comparison(parsed_rows: list[dict[str, Any]], *, direction_gap: int = 5,
                       v2_multiplier: float = 1.25, edge_deadband: int = -1) -> ComparisonReport:
    rows: list[RowComparison] = []
    agreements = 0
    flips = 0
    neut_to_dir = 0
    dir_to_neut = 0
    both_neutral = 0
    both_directional_same = 0
    both_directional_diff = 0
    v1_buys, v1_sells = [], []
    v2_buys, v2_sells = [], []
    gaps: list[float] = []
    confs: list[float] = []
    full_conf = 0
    low_conf = 0
    with_v1 = 0
    with_v2 = 0
    with_both = 0
    missing_v2 = 0

    for row in parsed_rows:
        r = compare_row(row, direction_gap=direction_gap, v2_multiplier=v2_multiplier,
                        edge_deadband=edge_deadband)
        rows.append(r)

        if r.v1_buy is not None:
            with_v1 += 1
            v1_buys.append(r.v1_buy)
            v1_sells.append(r.v1_sell or 0)
        if r.v2_available:
            with_v2 += 1
            v2_buys.append(r.v2_buy or 0)
            v2_sells.append(r.v2_sell or 0)
            if r.v2_confidence is not None:
                confs.append(r.v2_confidence)
                if r.v2_confidence >= 0.9:
                    full_conf += 1
                elif r.v2_confidence < 0.5:
                    low_conf += 1

        # Both V1 and V2 available → track transitions
        if r.v1_buy is not None and r.v2_available:
            with_both += 1
            if r.agreement:
                agreements += 1

            # Classify transition (mutually exclusive)
            if r.v1_direction == "buy" and r.v2_direction == "sell":
                flips += 1
            elif r.v1_direction == "sell" and r.v2_direction == "buy":
                flips += 1
            elif r.v1_direction == "neutral" and r.v2_direction in ("buy", "sell"):
                neut_to_dir += 1
            elif r.v1_direction in ("buy", "sell") and r.v2_direction == "neutral":
                dir_to_neut += 1
            elif r.v1_direction == "neutral" and r.v2_direction == "neutral":
                both_neutral += 1
            elif r.v1_direction == r.v2_direction:
                both_directional_same += 1
            else:
                both_directional_diff += 1
        elif r.v2_available and r.v1_buy is None:
            missing_v2 += 1
        elif r.v1_buy is not None and not r.v2_available:
            missing_v2 += 1
        if r.score_gap_buy is not None:
            gaps.append(r.score_gap_buy)

    total = len(rows)
    transition_total = flips + neut_to_dir + dir_to_neut + both_neutral + both_directional_same + both_directional_diff
    invariant_ok = transition_total == with_both

    return ComparisonReport(
        total_rows=total,
        rows_with_v2=with_v2,
        rows_with_v1=with_v1,
        rows_with_both=with_both,
        rows_missing_v2=missing_v2,
        direction_agreement_pct=round(agreements / max(1, with_both) * 100, 1),
        bias_flips=flips,
        neutral_to_directional=neut_to_dir,
        directional_to_neutral=dir_to_neut,
        transition_invariant_ok=invariant_ok,
        avg_v1_buy=round(sum(v1_buys) / len(v1_buys), 1) if v1_buys else 0,
        avg_v1_sell=round(sum(v1_sells) / len(v1_sells), 1) if v1_sells else 0,
        avg_v2_buy=round(sum(v2_buys) / len(v2_buys), 1) if v2_buys else 0,
        avg_v2_sell=round(sum(v2_sells) / len(v2_sells), 1) if v2_sells else 0,
        avg_score_gap=round(sum(gaps) / len(gaps), 1) if gaps else 0,
        avg_v2_confidence=round(sum(confs) / len(confs), 2) if confs else 0,
        rows_with_full_confidence=full_conf,
        rows_with_low_confidence=low_conf,
        rows=rows,
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def print_report(report: ComparisonReport, limit: int = 20) -> None:
    print("=" * 72)
    print("  Phase 15G — Macro V1 vs V2 Shadow Comparison")
    print("=" * 72)
    print()
    print(f"  Total rows                : {report.total_rows}")
    print(f"  Rows with V1 scores       : {report.rows_with_v1}")
    print(f"  Rows with V2 scores       : {report.rows_with_v2}")
    print(f"  Rows with BOTH            : {report.rows_with_both}")
    print(f"  Rows missing V2           : {report.rows_missing_v2}")
    print()
    print(f"  Direction agreement       : {report.direction_agreement_pct}%")
    print(f"  Bias flips (buy<->sell)   : {report.bias_flips}")
    print(f"  Neutral -> directional    : {report.neutral_to_directional}")
    print(f"  Directional -> neutral    : {report.directional_to_neutral}")
    print(f"  Transition invariant      : {'OK' if report.transition_invariant_ok else 'FAIL'}")
    print()
    print(f"  Avg V1 buy / sell         : {report.avg_v1_buy} / {report.avg_v1_sell}")
    print(f"  Avg V2 buy / sell         : {report.avg_v2_buy} / {report.avg_v2_sell}")
    print(f"  Avg score gap (buy)       : {report.avg_score_gap}")
    print()
    print(f"  Avg V2 confidence         : {report.avg_v2_confidence}")
    print(f"  Rows with conf >= 0.9     : {report.rows_with_full_confidence}")
    print(f"  Rows with conf < 0.5      : {report.rows_with_low_confidence}")
    print()
    print(f"  Top {limit} rows by largest score gap:")
    by_gap = sorted(
        [r for r in report.rows if r.score_gap_buy is not None],
        key=lambda r: -r.score_gap_buy,
    )
    print(f"  {'Symbol':<10s} {'Side':<5s} {'V1 B/S':>10s} {'V2 B/S':>10s} {'Gap':>5s} {'Agree':>6s} {'Conf':>5s}")
    print(f"  {'-'*10} {'-'*5} {'-'*10} {'-'*10} {'-'*5} {'-'*6} {'-'*5}")
    for r in by_gap[:limit]:
        v1 = f"{r.v1_buy}/{r.v1_sell}" if r.v1_buy else "?"
        v2 = f"{r.v2_buy}/{r.v2_sell}" if r.v2_buy else "?"
        gap = str(r.score_gap_buy) if r.score_gap_buy else "?"
        conf = f"{r.v2_confidence:.2f}" if r.v2_confidence else "?"
        print(f"  {r.symbol:<10s} {r.side:<5s} {v1:>10s} {v2:>10s} {gap:>5s} {str(r.agreement):>6s} {conf:>5s}")
    print()
    print("=" * 72)


def report_as_dict(report: ComparisonReport) -> dict[str, Any]:
    return {
        "total_rows": report.total_rows,
        "rows_with_v1": report.rows_with_v1,
        "rows_with_v2": report.rows_with_v2,
        "direction_agreement_pct": report.direction_agreement_pct,
        "bias_flips": report.bias_flips,
        "neutral_to_directional": report.neutral_to_directional,
        "directional_to_neutral": report.directional_to_neutral,
        "avg_v1_buy": report.avg_v1_buy,
        "avg_v1_sell": report.avg_v1_sell,
        "avg_v2_buy": report.avg_v2_buy,
        "avg_v2_sell": report.avg_v2_sell,
        "avg_score_gap": report.avg_score_gap,
        "avg_v2_confidence": report.avg_v2_confidence,
        "rows_with_full_confidence": report.rows_with_full_confidence,
        "rows_with_low_confidence": report.rows_with_low_confidence,
        "rows": [
            {
                "symbol": r.symbol, "side": r.side,
                "v1_buy": r.v1_buy, "v1_sell": r.v1_sell,
                "v2_buy": r.v2_buy, "v2_sell": r.v2_sell,
                "v2_confidence": r.v2_confidence, "v2_pair_edge": r.v2_pair_edge,
                "v1_direction": r.v1_direction, "v2_direction": r.v2_direction,
                "agreement": r.agreement,
                "score_gap_buy": r.score_gap_buy, "score_gap_sell": r.score_gap_sell,
            }
            for r in report.rows
        ],
    }


def write_csv(report: ComparisonReport, path: str) -> None:
    import csv
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "side", "v1_buy", "v1_sell", "v2_buy", "v2_sell",
                     "v2_confidence", "v2_pair_edge", "v1_direction", "v2_direction",
                     "agreement", "score_gap_buy", "score_gap_sell"])
        for r in report.rows:
            w.writerow([r.symbol, r.side, r.v1_buy or "", r.v1_sell or "",
                        r.v2_buy or "", r.v2_sell or "", r.v2_confidence or "",
                        r.v2_pair_edge or "", r.v1_direction, r.v2_direction,
                        r.agreement, r.score_gap_buy or "", r.score_gap_sell or ""])


def _find_latest_snapshot() -> Path | None:
    for parent in (Path("app_data/scanner_snapshots"), Path("data")):
        if parent.is_dir():
            snaps = sorted(parent.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if snaps:
                return snaps[0]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 15G — V1 vs V2 shadow comparison")
    parser.add_argument("input_path", nargs="?", default=None, help="Path to snapshot JSON")
    parser.add_argument("--json-output", type=str, default=None)
    parser.add_argument("--csv", type=str, default=None)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--direction-gap", type=int, default=5,
                        help="Min buy-sell gap for directional (default: 5, matches _detect_macro_status)")
    parser.add_argument("--multiplier", type=float, default=1.25,
                        help="V2 scale multiplier (default: 1.25)")
    parser.add_argument("--edge-deadband", type=int, default=-1,
                        help="If |pair_edge| <= deadband, force V2=15/15 neutral (default: -1=off)")
    args = parser.parse_args()

    input_path = args.input_path
    if input_path is None:
        snapshot = _find_latest_snapshot()
        if snapshot is None:
            print("[ERROR] No input file and no snapshot found.", file=sys.stderr)
            sys.exit(1)
        input_path = str(snapshot)
        print(f"[INFO] Using: {snapshot}", file=sys.stderr)

    try:
        with open(input_path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        print(f"[ERROR] File not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"[ERROR] Invalid JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    parsed = parse_input(raw)
    if not parsed:
        print("[ERROR] No valid rows found.", file=sys.stderr)
        sys.exit(1)

    report = compute_comparison(parsed, direction_gap=args.direction_gap,
                                 v2_multiplier=args.multiplier,
                                 edge_deadband=args.edge_deadband)
    print_report(report, limit=args.limit)

    if args.json_output:
        with open(args.json_output, "w", encoding="utf-8") as fh:
            json.dump(report_as_dict(report), fh, indent=2, ensure_ascii=False)
        print(f"[INFO] JSON written: {args.json_output}", file=sys.stderr)

    if args.csv:
        write_csv(report, args.csv)
        print(f"[INFO] CSV written: {args.csv}", file=sys.stderr)


if __name__ == "__main__":
    main()
