#!/usr/bin/env python3
"""Phase 4B -- Diagnostic: measure impact of base-case RR on gate/ranking.

Compares best-case vs base-case effective RR across scanner rows without
changing any production behaviour.  Answers the question:
  "If gate + ranking used base RR instead of best RR, how many setups
   would have been affected?"

Usage::

    python scripts/compare_rr_anchor_impact.py [path/to/scan_result.json]

If no path is given, the script looks for the most recent snapshot in
``app_data/``.

Options::

    --min-rr FLOAT     Gate threshold (default 1.3)
    --limit N          Top-N rows to show in detail tables (default 20)
    --json-output PATH Write full report as JSON
    --csv PATH         Write per-row comparison as CSV
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants (mirrors production — read-only, never changed)
# ---------------------------------------------------------------------------

_RR_STRONG = 2.0
_RR_WEAK = 1.3


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class RowRR:
    symbol: str
    best_side: str
    group: str
    action: str
    best_score: int
    opportunity_score: int | None
    rr_best: float | None           # best-case nominal RR
    rr_base: float | None           # base-case nominal RR
    rr_worst: float | None          # worst-case nominal RR
    eff_best: float | None          # best-case effective RR (after spread)
    eff_base: float | None          # base-case effective RR (after spread)
    eff_worst: float | None         # worst-case effective RR (after spread)


@dataclass
class ImpactReport:
    total_rows: int
    rows_with_both: int             # rows with both best and base effective RR
    base_fail_best_pass: int        # base < min_rr AND best >= min_rr
    lost_strong_tier: int           # best >= 2.0 but base < 2.0
    lost_weak_tier: int             # best >= 1.3 but base < 1.3
    avg_best: float
    avg_base: float
    avg_drop: float                 # avg(eff_best - eff_base)
    max_drop: float
    min_rr: float
    rows: list[RowRR] = field(default_factory=list)

    @property
    def pct_affected(self) -> float:
        return (self.base_fail_best_pass / max(1, self.rows_with_both)) * 100


# ---------------------------------------------------------------------------
# Parser — flexible input formats
# ---------------------------------------------------------------------------


def _resolve_best_side(row: dict[str, Any]) -> str:
    """Return best_side string from a row dict, preferring direction_bias."""
    bias = row.get("direction_bias")
    if isinstance(bias, dict):
        side = bias.get("best_side", "")
        if side in ("buy", "sell"):
            return str(side)
    side = row.get("best_side", "")
    if side in ("buy", "sell"):
        return str(side)
    return ""


def _find_best_scenario(scenarios: list[dict[str, Any]], best_side: str) -> dict[str, Any] | None:
    """Find the scenario matching *best_side* by ``type`` or ``side`` key."""
    if not isinstance(scenarios, list) or not scenarios:
        return None
    if not best_side:
        return scenarios[0] if isinstance(scenarios[0], dict) else None
    for s in scenarios:
        if not isinstance(s, dict):
            continue
        if s.get("type") == best_side or s.get("side") == best_side:
            return s
    # Fallback: first valid scenario
    for s in scenarios:
        if isinstance(s, dict):
            return s
    return None


def _safe_float(value: object) -> float | None:
    """Convert value to float, returning None on any failure."""
    if value is None:
        return None
    try:
        f = float(value)
        if f != f or f == float("inf") or f == float("-inf"):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _parse_rr_string(value: object) -> float | None:
    """Parse '1:X.X' string to float X.X, or return float/None directly."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return _safe_float(value)
    text = str(value)
    if ":" in text:
        try:
            return float(text.split(":", 1)[1])
        except (ValueError, IndexError):
            return None
    return _safe_float(value)


def _extract_rr_fields(row: dict[str, Any]) -> RowRR:
    """Extract all RR-related fields from a scanner row dict."""
    symbol = str(row.get("symbol", "?"))
    best_side = _resolve_best_side(row)
    group = str(row.get("scanner_group", "") or row.get("group", ""))
    action = str(row.get("scanner_action", "") or row.get("scanner_group", ""))
    best_score = int(row.get("best_score", 0) or 0)
    opp = row.get("opportunity_score")
    opp_score = int(opp) if opp is not None else None

    # --- Nominal RR (from risk_reward_range or string) ---
    rr_range = row.get("risk_reward_range")
    if isinstance(rr_range, dict):
        rr_best = _safe_float(rr_range.get("best"))
        rr_base = _safe_float(rr_range.get("base"))
        rr_worst = _safe_float(rr_range.get("worst"))
    else:
        rr_best = _parse_rr_string(row.get("risk_reward"))
        rr_base = _safe_float(row.get("risk_reward_base"))
        rr_worst = _safe_float(row.get("risk_reward_worst"))

    # --- Effective RR (after spread) ---
    eff_best = _safe_float(row.get("expected_effective_rr"))
    eff_base = _safe_float(row.get("expected_effective_rr_base"))
    eff_worst = _safe_float(row.get("expected_effective_rr_worst"))

    # --- Fallback: pull from analysis_result.scenarios if row-level is missing ---
    ar = row.get("analysis_result")
    if isinstance(ar, dict) and (eff_base is None or eff_best is None):
        scenarios = ar.get("scenarios", [])
        sc = _find_best_scenario(scenarios, best_side)
        if isinstance(sc, dict):
            if eff_best is None:
                eff_best = _safe_float(sc.get("expected_effective_rr"))
            if eff_base is None:
                eff_base = _safe_float(sc.get("expected_effective_rr_base"))
            if eff_worst is None:
                eff_worst = _safe_float(sc.get("expected_effective_rr_worst"))

    return RowRR(
        symbol=symbol,
        best_side=best_side,
        group=group,
        action=action,
        best_score=best_score,
        opportunity_score=opp_score,
        rr_best=rr_best,
        rr_base=rr_base,
        rr_worst=rr_worst,
        eff_best=eff_best,
        eff_base=eff_base,
        eff_worst=eff_worst,
    )


def parse_input(source: object) -> list[dict[str, Any]]:
    """Parse a flexible input into a flat list of scanner row dicts.

    Supported formats:
    - ``list[dict]`` — direct list of rows
    - ``{"rows": [...]}`` — scanner output wrapper
    - ``{"scanner_rows": [...]}`` — alt wrapper
    - ``{"result": {"rows": [...]}}`` — nested result
    - ``dict`` with a ``symbol`` key → single-row list
    """
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
        # Single row
        if "symbol" in source:
            return [source]

    return []


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def compute_impact(parsed_rows: list[dict[str, Any]], min_rr: float) -> ImpactReport:
    """Analyze all rows and produce an ImpactReport."""
    rows_rr: list[RowRR] = []
    eff_bests: list[float] = []
    eff_bases: list[float] = []
    drops: list[float] = []

    base_fail_best_pass = 0
    lost_strong = 0
    lost_weak = 0
    rows_with_both = 0

    for row in parsed_rows:
        rr = _extract_rr_fields(row)
        rows_rr.append(rr)

        if rr.eff_best is None:
            continue

        eff_bests.append(rr.eff_best)

        if rr.eff_base is not None and rr.eff_base > 0:
            eff_bases.append(rr.eff_base)
            drop = rr.eff_best - rr.eff_base
            drops.append(drop)
            rows_with_both += 1

            # --- Tier shifts ---
            if rr.eff_base < min_rr and rr.eff_best >= min_rr:
                base_fail_best_pass += 1

            if rr.eff_best >= _RR_STRONG and rr.eff_base < _RR_STRONG:
                lost_strong += 1

            if rr.eff_best >= _RR_WEAK and rr.eff_base < _RR_WEAK:
                lost_weak += 1

    avg_best = sum(eff_bests) / len(eff_bests) if eff_bests else 0.0
    avg_base = sum(eff_bases) / len(eff_bases) if eff_bases else 0.0
    avg_drop = sum(drops) / len(drops) if drops else 0.0
    max_drop = max(drops) if drops else 0.0

    # Sort rows by drop for convenience
    rows_rr.sort(key=lambda r: (
        -(r.eff_best - r.eff_base) if (r.eff_best is not None and r.eff_base is not None) else 0
    ))

    return ImpactReport(
        total_rows=len(rows_rr),
        rows_with_both=rows_with_both,
        base_fail_best_pass=base_fail_best_pass,
        lost_strong_tier=lost_strong,
        lost_weak_tier=lost_weak,
        avg_best=round(avg_best, 2),
        avg_base=round(avg_base, 2),
        avg_drop=round(avg_drop, 2),
        max_drop=round(max_drop, 2),
        min_rr=min_rr,
        rows=rows_rr,
    )


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _format_row_line(rr: RowRR) -> str:
    b = f"{rr.eff_best:.1f}" if rr.eff_best is not None else "?"
    ba = f"{rr.eff_base:.1f}" if rr.eff_base is not None else "?"
    w = f"{rr.eff_worst:.1f}" if rr.eff_worst is not None else "?"
    drop = f"{(rr.eff_best or 0) - (rr.eff_base or 0):.2f}" if (rr.eff_best is not None and rr.eff_base is not None) else "?"
    opp = str(rr.opportunity_score) if rr.opportunity_score is not None else "-"
    return (
        f"  {rr.symbol:<10s} {rr.best_side:<5s} "
        f"best={b:<5s} base={ba:<5s} worst={w:<5s} "
        f"drop={drop:<5s} "
        f"grp={rr.group:<22s} opp={opp:<4s} sc={rr.best_score}"
    )


def print_report(report: ImpactReport, limit: int = 20) -> None:
    """Print a human-readable impact report to stdout."""
    print("=" * 82)
    print("  Phase 4B -- RR Anchor Impact Diagnostic")
    print("=" * 82)
    print()
    print(f"  Total rows scanned       : {report.total_rows}")
    print(f"  Rows with base + best RR : {report.rows_with_both}")
    print(f"  Min RR threshold         : {report.min_rr}")
    print()
    print(f"  Average best RR          : {report.avg_best:.2f}")
    print(f"  Average base RR          : {report.avg_base:.2f}")
    print(f"  Average drop (best->base) : {report.avg_drop:.2f}")
    print(f"  Max drop                 : {report.max_drop:.2f}")
    print()
    print(f"  Base < min_rr while best >= min_rr : {report.base_fail_best_pass} "
          f"({report.pct_affected:.1f}% of rows with both RR)")
    print(f"  Lost STRONG tier (best>=2.0, base<2.0): {report.lost_strong_tier}")
    print(f"  Lost WEAK tier  (best>=1.3, base<1.3): {report.lost_weak_tier}")
    print()

    # --- Top drops ---
    rows_with_drop = [r for r in report.rows if r.eff_best is not None and r.eff_base is not None]
    by_drop = sorted(rows_with_drop, key=lambda r: -(r.eff_best - r.eff_base))
    print(f"  Top {limit} rows by largest best->base drop:")
    print(f"  {'Symbol':<10s} {'Side':<5s} {'Best':>5s} {'Base':>5s} {'Worst':>5s} {'Drop':>5s} {'Group':<22s} {'Opp':>4s} {'Score'}")
    print(f"  {'-'*10} {'-'*5} {'-'*5} {'-'*5} {'-'*5} {'-'*5} {'-'*22} {'-'*4} {'-'*5}")
    for rr in by_drop[:limit]:
        print(_format_row_line(rr))
    print()

    # --- Base fail, best pass ---
    fail_pass = [
        r for r in rows_with_drop
        if r.eff_base is not None and r.eff_best is not None
        and r.eff_base < report.min_rr and r.eff_best >= report.min_rr
    ]
    print(f"  Top {min(limit, len(fail_pass))} rows where base fails (base < {report.min_rr}) "
          f"but best passes (best >= {report.min_rr}):")
    if fail_pass:
        print(f"  {'Symbol':<10s} {'Side':<5s} {'Best':>5s} {'Base':>5s} {'Worst':>5s} {'Drop':>5s} {'Group':<22s} {'Opp':>4s} {'Score'}")
        print(f"  {'-'*10} {'-'*5} {'-'*5} {'-'*5} {'-'*5} {'-'*5} {'-'*22} {'-'*4} {'-'*5}")
        for rr in fail_pass[:limit]:
            print(_format_row_line(rr))
    else:
        print("  (none — all rows with base RR pass the gate)")
    print()

    # --- Tier shifts ---
    strong_lost = [r for r in rows_with_drop
                   if r.eff_best is not None and r.eff_base is not None
                   and r.eff_best >= _RR_STRONG and r.eff_base < _RR_STRONG]
    weak_lost = [r for r in rows_with_drop
                 if r.eff_best is not None and r.eff_base is not None
                 and r.eff_best >= _RR_WEAK and r.eff_base < _RR_WEAK]

    print(f"  Rows that lost STRONG tier (best >= {_RR_STRONG} -> base < {_RR_STRONG}): "
          f"{len(strong_lost)}")
    if strong_lost:
        for rr in strong_lost[:limit]:
            print(_format_row_line(rr))
    print()

    print(f"  Rows that lost WEAK tier (best >= {_RR_WEAK} -> base < {_RR_WEAK}): "
          f"{len(weak_lost)}")
    if weak_lost:
        for rr in weak_lost[:limit]:
            print(_format_row_line(rr))
    print()

    # --- Recommendation ---
    print("  -- Recommendation --")
    if report.pct_affected < 5 and report.avg_drop < 0.3:
        print(f"  Impact is LOW ({report.pct_affected:.1f}% affected, avg drop {report.avg_drop:.2f}).")
        print("  Safe to recalibrate thresholds: drop _RR_WEAK from 1.3->1.1, _RR_STRONG from 2.0->1.7.")
    elif report.pct_affected < 15:
        print(f"  Impact is MODERATE ({report.pct_affected:.1f}% affected, avg drop {report.avg_drop:.2f}).")
        print("  Consider recalibrating: _RR_WEAK: 1.3->1.1, _RR_STRONG: 2.0->1.8.  Run more data first.")
    else:
        print(f"  Impact is SIGNIFICANT ({report.pct_affected:.1f}% affected, avg drop {report.avg_drop:.2f}).")
        print("  Do NOT recalibrate blindly.  Verify zone width distribution first.")
    print()
    print("=" * 82)


def report_as_dict(report: ImpactReport) -> dict[str, Any]:
    """Serialize the report to a JSON-safe dict."""
    return {
        "total_rows": report.total_rows,
        "rows_with_both": report.rows_with_both,
        "base_fail_best_pass": report.base_fail_best_pass,
        "pct_affected": round(report.pct_affected, 1),
        "lost_strong_tier": report.lost_strong_tier,
        "lost_weak_tier": report.lost_weak_tier,
        "avg_best": report.avg_best,
        "avg_base": report.avg_base,
        "avg_drop": report.avg_drop,
        "max_drop": report.max_drop,
        "min_rr": report.min_rr,
        "rows": [
            {
                "symbol": r.symbol,
                "best_side": r.best_side,
                "group": r.group,
                "action": r.action,
                "best_score": r.best_score,
                "opportunity_score": r.opportunity_score,
                "rr_best": r.rr_best,
                "rr_base": r.rr_base,
                "rr_worst": r.rr_worst,
                "eff_best": r.eff_best,
                "eff_base": r.eff_base,
                "eff_worst": r.eff_worst,
                "drop": round(r.eff_best - r.eff_base, 4)
                if (r.eff_best is not None and r.eff_base is not None) else None,
            }
            for r in report.rows
        ],
    }


def write_csv(report: ImpactReport, path: str) -> None:
    """Write per-row RR comparison as CSV."""
    import csv
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "symbol", "best_side", "group", "action", "best_score",
            "opportunity_score", "rr_best", "rr_base", "rr_worst",
            "eff_best", "eff_base", "eff_worst", "drop",
        ])
        for r in report.rows:
            drop = round(r.eff_best - r.eff_base, 4) if (
                r.eff_best is not None and r.eff_base is not None
            ) else ""
            w.writerow([
                r.symbol, r.best_side, r.group, r.action, r.best_score,
                r.opportunity_score or "", r.rr_best or "", r.rr_base or "",
                r.rr_worst or "", r.eff_best or "", r.eff_base or "",
                r.eff_worst or "", drop,
            ])


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def _find_latest_snapshot() -> Path | None:
    """Find the most recent scanner snapshot JSON under app_data/."""
    candidates: list[Path] = []

    # Common snapshot directories
    for parent in (
        Path("app_data/scanner_snapshots"),
        Path("data/scanner_snapshots"),
        Path("data"),
    ):
        if parent.is_dir():
            for p in parent.glob("*.json"):
                if p.is_file():
                    candidates.append(p)

    if not candidates:
        return None

    # Sort by modification time, newest first
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 4B -- measure impact of base-case RR on gate/ranking",
    )
    parser.add_argument(
        "input_path", nargs="?", default=None,
        help="Path to a scanner result JSON file",
    )
    parser.add_argument(
        "--min-rr", type=float, default=1.3,
        help="Gate RR threshold (default: 1.3)",
    )
    parser.add_argument(
        "--limit", type=int, default=20,
        help="Top-N rows in detail tables (default: 20)",
    )
    parser.add_argument(
        "--json-output", type=str, default=None,
        help="Write full report as JSON to this path",
    )
    parser.add_argument(
        "--csv", type=str, default=None,
        help="Write per-row comparison as CSV to this path",
    )

    args = parser.parse_args()

    # Resolve input
    input_path = args.input_path
    if input_path is None:
        snapshot = _find_latest_snapshot()
        if snapshot is None:
            print("[ERROR] No input file specified and no snapshot found in app_data/ or data/.",
                  file=sys.stderr)
            print("Usage: python scripts/compare_rr_anchor_impact.py path/to/scan_result.json",
                  file=sys.stderr)
            sys.exit(1)
        input_path = str(snapshot)
        print(f"[INFO] Using latest snapshot: {snapshot}", file=sys.stderr)

    try:
        with open(input_path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        print(f"[ERROR] File not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"[ERROR] Invalid JSON in {input_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    parsed = parse_input(raw)
    if not parsed:
        print("[ERROR] No valid scanner rows found in the input file.", file=sys.stderr)
        sys.exit(1)

    report = compute_impact(parsed, min_rr=args.min_rr)
    print_report(report, limit=args.limit)

    if args.json_output:
        with open(args.json_output, "w", encoding="utf-8") as fh:
            json.dump(report_as_dict(report), fh, indent=2, ensure_ascii=False)
        print(f"[INFO] JSON report written to {args.json_output}", file=sys.stderr)

    if args.csv:
        write_csv(report, args.csv)
        print(f"[INFO] CSV written to {args.csv}", file=sys.stderr)


if __name__ == "__main__":
    main()
