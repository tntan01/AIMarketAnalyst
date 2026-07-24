#!/usr/bin/env python3
"""Phase 13A — Diagnostic: measure entry zone width and TP1 clearance quality.

Reads a scanner snapshot JSON and produces statistics on entry zone width
and TP1 distance from far edge, broken down by source.

Usage::

    python scripts/compare_entry_tp_quality.py [path/to/scan_result.json]

Options::

    --json-output PATH   Write full report as JSON
    --csv PATH           Write per-row data as CSV
    --limit N            Top-N rows in detail tables (default 20)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class RowDiag:
    symbol: str
    side: str
    entry_low: float | None
    entry_high: float | None
    entry_zone_width: float | None
    entry_zone_width_atr: float | None
    entry_zone_source: str
    stop_loss: float | None
    tp1: float | None
    tp1_source: str
    tp1_clearance_from_far_edge: float | None
    tp1_clearance_atr: float | None
    expected_effective_rr: float | None
    expected_effective_rr_base: float | None
    tp1_effective_rr_base: float | None
    # Phase 13B.1 diagnostics
    tp1_candidates_checked: int = 0
    tp1_selected_source: str | None = None
    tp1_selected_target_rank: int | None = None
    tp1_rej_clearance: int = 0
    tp1_rej_nominal_rr: int = 0
    tp1_rej_effective_rr: int = 0
    tp1_rej_not_past: int = 0


@dataclass
class QualityReport:
    total_rows: int
    rows_with_entry_zone: int
    rows_with_tp1: int
    rows_without_tp1: int
    rows_with_valid_tp1_clearance: int
    rows_with_invalid_negative_tp1_clearance: int
    rows_with_valid_atr: int
    avg_zone_width_atr: float
    max_zone_width_atr: float
    pct_zone_width_gt_0_4_atr: float
    pct_zone_width_gt_0_5_atr: float
    pct_zone_width_gt_0_6_atr: float
    avg_tp1_clearance_atr: float
    min_tp1_clearance_atr: float
    pct_tp1_clearance_lt_0_10_atr: float
    pct_tp1_clearance_lt_0_15_atr: float
    pct_tp1_clearance_lt_0_20_atr: float
    pct_best_rr_pass_base_rr_fail: float
    zone_source_breakdown: dict[str, int]
    tp1_source_breakdown: dict[str, int]
    rows: list[RowDiag] = field(default_factory=list)
    # Phase 13B.1: selection diagnostics (available only when snapshot has them)
    selection_diag_available: bool = False
    selection_diag: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
        if f != f or f == float("inf") or f == float("-inf"):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _resolve_side(row: dict[str, Any]) -> str:
    bias = row.get("direction_bias")
    if isinstance(bias, dict):
        s = bias.get("best_side", "")
        if s in ("buy", "sell"):
            return str(s)
    s = row.get("best_side", "")
    return str(s) if s in ("buy", "sell") else ""


def _find_scenario(scenarios: list, best_side: str) -> dict | None:
    if not isinstance(scenarios, list):
        return None
    for s in scenarios:
        if isinstance(s, dict) and (s.get("type") == best_side or s.get("side") == best_side):
            return s
    for s in scenarios:
        if isinstance(s, dict):
            return s
    return None


def _extract_row(row: dict[str, Any]) -> RowDiag:
    side = _resolve_side(row)

    # Top-level scanner row fields
    ez = row.get("entry_zone")
    if isinstance(ez, list) and len(ez) >= 2:
        elow = _safe_float(ez[0])
        ehigh = _safe_float(ez[1])
        # ensure correct ordering
        if elow is not None and ehigh is not None and elow > ehigh:
            elow, ehigh = ehigh, elow
    else:
        elow = ehigh = None

    tp_raw = row.get("take_profit")
    tp1 = None
    if isinstance(tp_raw, list) and len(tp_raw) > 0:
        tp1 = _safe_float(tp_raw[0])
    elif tp_raw is not None:
        tp1 = _safe_float(tp_raw)

    return RowDiag(
        symbol=str(row.get("symbol", "?")),
        side=side,
        entry_low=elow,
        entry_high=ehigh,
        entry_zone_width=_safe_float(row.get("entry_zone_width")),
        entry_zone_width_atr=_safe_float(row.get("entry_zone_width_atr")),
        entry_zone_source=str(row.get("entry_zone_source") or ""),
        stop_loss=_safe_float(row.get("stop_loss")),
        tp1=tp1,
        tp1_source=str(row.get("tp1_source") or ""),
        tp1_clearance_from_far_edge=_safe_float(row.get("tp1_clearance_from_far_edge")),
        tp1_clearance_atr=_safe_float(row.get("tp1_clearance_atr")),
        expected_effective_rr=_safe_float(row.get("expected_effective_rr")),
        expected_effective_rr_base=_safe_float(row.get("expected_effective_rr_base")),
        tp1_effective_rr_base=_safe_float(row.get("tp1_effective_rr_base")),
    )
    # Phase 13B.1: diagnostics
    diag = row.get("tp1_selection_diagnostics")
    if isinstance(diag, dict):
        result.tp1_candidates_checked = int(diag.get("candidates_checked", 0) or 0)
        result.tp1_selected_source = diag.get("selected_source")
        result.tp1_selected_target_rank = diag.get("selected_target_rank")
        rejected = diag.get("rejected_by_reason", {})
        if isinstance(rejected, dict):
            result.tp1_rej_clearance = int(rejected.get("clearance_too_low", 0) or 0)
            result.tp1_rej_nominal_rr = int(rejected.get("nominal_rr_too_low", 0) or 0)
            result.tp1_rej_effective_rr = int(rejected.get("effective_rr_too_low", 0) or 0)
            result.tp1_rej_not_past = int(rejected.get("not_past_far_edge", 0) or 0)
    return result


def parse_input(source: object) -> list[dict[str, Any]]:
    """Flexible input parser: list of rows, dict with rows, nested result, or single row."""
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


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _find_best_scenario_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Extract best-side scenario data from analysis_result if available."""
    ar = row.get("analysis_result")
    if not isinstance(ar, dict):
        return row  # use top-level fields
    scenarios = ar.get("scenarios", [])
    best_side = _resolve_side(row)
    sc = _find_scenario(scenarios, best_side)
    if sc is None:
        return row
    # Merge scenario fields into row-like dict (scenario fields take precedence)
    merged = dict(row)
    for k in (
        "entry_zone", "entry_zone_width", "entry_zone_width_atr",
        "entry_zone_source", "stop_loss", "take_profit",
        "tp1_source", "tp1_clearance_from_far_edge", "tp1_clearance_atr",
        "expected_effective_rr", "expected_effective_rr_base",
        "tp1_effective_rr_base",
    ):
        if k in sc and k not in merged:
            merged[k] = sc[k]
    return merged


def compute_quality(parsed_rows: list[dict[str, Any]]) -> QualityReport:
    rows_diag: list[RowDiag] = []
    zone_widths_atr: list[float] = []
    tp1_clearances_atr: list[float] = []
    rows_with_zone = 0
    rows_with_tp1 = 0
    rows_without_tp1 = 0
    rows_with_valid_tp1_clearance = 0
    rows_with_invalid_negative_tp1_clearance = 0
    rows_with_valid_atr = 0
    best_pass_base_fail = 0
    best_base_both = 0
    zone_source_counts: Counter[str] = Counter()
    tp1_source_counts: Counter[str] = Counter()

    for raw_row in parsed_rows:
        row = _find_best_scenario_from_row(raw_row)
        diag = _extract_row(row)
        rows_diag.append(diag)

        zone_source_counts[diag.entry_zone_source or "unknown"] += 1
        tp1_source_counts[diag.tp1_source or "unknown"] += 1

        if diag.entry_zone_width_atr is not None and diag.entry_zone_width_atr > 0:
            rows_with_zone += 1
            zone_widths_atr.append(diag.entry_zone_width_atr)
            rows_with_valid_atr += 1

        if diag.tp1 is not None:
            rows_with_tp1 += 1
            # Check if clearance is valid (non-negative)
            if diag.tp1_clearance_from_far_edge is not None and diag.tp1_clearance_from_far_edge >= 0:
                if diag.tp1_clearance_atr is not None and diag.tp1_clearance_atr >= 0:
                    tp1_clearances_atr.append(diag.tp1_clearance_atr)
                    rows_with_valid_tp1_clearance += 1
                elif diag.tp1_clearance_atr is None:
                    rows_with_valid_tp1_clearance += 1  # valid clearance, no ATR
            elif diag.tp1_clearance_from_far_edge is not None and diag.tp1_clearance_from_far_edge < 0:
                rows_with_invalid_negative_tp1_clearance += 1
        else:
            rows_without_tp1 += 1

        if diag.expected_effective_rr is not None and diag.expected_effective_rr_base is not None:
            best_base_both += 1
            if diag.expected_effective_rr >= 1.3 and diag.expected_effective_rr_base < 1.3:
                best_pass_base_fail += 1

    # Phase 13B.1: diagnostic aggregation
    has_diag = any(r.tp1_candidates_checked > 0 or r.tp1_selected_source is not None
                   for r in rows_diag)
    sel_diag: dict[str, Any] = {"available": has_diag}
    if has_diag:
        total_checked = sum(r.tp1_candidates_checked for r in rows_diag)
        sel_diag["total_candidates_checked"] = total_checked
        sel_diag["rows_with_diagnostics"] = sum(1 for r in rows_diag if r.tp1_candidates_checked > 0)
        sel_diag["total_rej_clearance"] = sum(r.tp1_rej_clearance for r in rows_diag)
        sel_diag["total_rej_nominal_rr"] = sum(r.tp1_rej_nominal_rr for r in rows_diag)
        sel_diag["total_rej_effective_rr"] = sum(r.tp1_rej_effective_rr for r in rows_diag)
        sel_diag["total_rej_not_past"] = sum(r.tp1_rej_not_past for r in rows_diag)
        # Target rank stats
        rank_vals = [r.tp1_selected_target_rank for r in rows_diag
                     if r.tp1_selected_target_rank is not None]
        sel_diag["rows_with_target_zone_selection"] = len(rank_vals)
        sel_diag["rank_1_count"] = sum(1 for v in rank_vals if v == 1)
        sel_diag["rank_gt_1_count"] = sum(1 for v in rank_vals if v > 1)
        sel_diag["avg_rank"] = round(sum(rank_vals) / len(rank_vals), 2) if rank_vals else 0
        # Source breakdown
        src_counts: dict[str, int] = {}
        for r in rows_diag:
            if r.tp1_selected_source:
                src_counts[r.tp1_selected_source] = src_counts.get(r.tp1_selected_source, 0) + 1
        sel_diag["selected_source_breakdown"] = src_counts
        rows_no_tp1 = sum(1 for r in rows_diag if r.tp1_source == "none" or r.tp1 is None)
        sel_diag["rows_no_valid_tp1"] = rows_no_tp1

    def pct_zone_gt(threshold: float) -> float:
        if not zone_widths_atr:
            return 0.0
        return sum(1 for v in zone_widths_atr if v > threshold) / len(zone_widths_atr) * 100

    def pct_clear_lt(threshold: float) -> float:
        if not tp1_clearances_atr:
            return 0.0
        return sum(1 for v in tp1_clearances_atr if v < threshold) / len(tp1_clearances_atr) * 100

    return QualityReport(
        total_rows=len(rows_diag),
        rows_with_entry_zone=rows_with_zone,
        rows_with_tp1=rows_with_tp1,
        rows_without_tp1=rows_without_tp1,
        rows_with_valid_tp1_clearance=rows_with_valid_tp1_clearance,
        rows_with_invalid_negative_tp1_clearance=rows_with_invalid_negative_tp1_clearance,
        rows_with_valid_atr=rows_with_valid_atr,
        avg_zone_width_atr=round(sum(zone_widths_atr) / len(zone_widths_atr), 4) if zone_widths_atr else 0.0,
        max_zone_width_atr=round(max(zone_widths_atr), 4) if zone_widths_atr else 0.0,
        pct_zone_width_gt_0_4_atr=round(pct_zone_gt(0.4), 1),
        pct_zone_width_gt_0_5_atr=round(pct_zone_gt(0.5), 1),
        pct_zone_width_gt_0_6_atr=round(pct_zone_gt(0.6), 1),
        avg_tp1_clearance_atr=round(sum(tp1_clearances_atr) / len(tp1_clearances_atr), 4) if tp1_clearances_atr else 0.0,
        min_tp1_clearance_atr=round(min(tp1_clearances_atr), 4) if tp1_clearances_atr else 0.0,
        pct_tp1_clearance_lt_0_10_atr=round(pct_clear_lt(0.10), 1),
        pct_tp1_clearance_lt_0_15_atr=round(pct_clear_lt(0.15), 1),
        pct_tp1_clearance_lt_0_20_atr=round(pct_clear_lt(0.20), 1),
        pct_best_rr_pass_base_rr_fail=round(
            best_pass_base_fail / max(1, best_base_both) * 100, 1
        ),
        zone_source_breakdown=dict(zone_source_counts),
        tp1_source_breakdown=dict(tp1_source_counts),
        selection_diag_available=has_diag,
        selection_diag=sel_diag,
        rows=rows_diag,
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_report(report: QualityReport, limit: int = 20) -> None:
    print("=" * 72)
    print("  Phase 13A — Entry Zone & TP1 Quality Diagnostic")
    print("=" * 72)
    print()
    print(f"  Total rows                : {report.total_rows}")
    print(f"  Rows with entry zone      : {report.rows_with_entry_zone}")
    print(f"  Rows with TP1             : {report.rows_with_tp1}")
    print(f"  Rows without TP1          : {report.rows_without_tp1}")
    print(f"  Rows with valid clearance  : {report.rows_with_valid_tp1_clearance}")
    print(f"  Rows with invalid (-) clr  : {report.rows_with_invalid_negative_tp1_clearance}")
    print(f"  Rows with valid ATR diag   : {report.rows_with_valid_atr}")
    print()
    print(f"  --- Entry Zone Width (ATR) ---")
    print(f"  Avg zone width (ATR)      : {report.avg_zone_width_atr:.4f}")
    print(f"  Max zone width (ATR)      : {report.max_zone_width_atr:.4f}")
    print(f"  % zone width > 0.4 ATR    : {report.pct_zone_width_gt_0_4_atr:.1f}%")
    print(f"  % zone width > 0.5 ATR    : {report.pct_zone_width_gt_0_5_atr:.1f}%")
    print(f"  % zone width > 0.6 ATR    : {report.pct_zone_width_gt_0_6_atr:.1f}%")
    print()
    print(f"  --- TP1 Clearance from Far Edge (ATR) ---")
    print(f"  Avg clearance (ATR)       : {report.avg_tp1_clearance_atr:.4f}")
    print(f"  Min clearance (ATR)       : {report.min_tp1_clearance_atr:.4f}")
    print(f"  % clearance < 0.10 ATR    : {report.pct_tp1_clearance_lt_0_10_atr:.1f}%")
    print(f"  % clearance < 0.15 ATR    : {report.pct_tp1_clearance_lt_0_15_atr:.1f}%")
    print(f"  % clearance < 0.20 ATR    : {report.pct_tp1_clearance_lt_0_20_atr:.1f}%")
    print()
    print(f"  --- RR Anchor ---")
    print(f"  % best RR pass, base fail : {report.pct_best_rr_pass_base_rr_fail:.1f}%")
    print()
    print(f"  --- Entry Zone Source Breakdown ---")
    for src, count in sorted(report.zone_source_breakdown.items()):
        print(f"  {src:<30s} : {count}")
    print()
    print(f"  --- TP1 Source Breakdown ---")
    for src, count in sorted(report.tp1_source_breakdown.items()):
        print(f"  {src:<30s} : {count}")
    print()
    # Phase 13B.1: selection diagnostics
    if report.selection_diag_available:
        print(f"  --- TP1 Selection Diagnostics ---")
        sd = report.selection_diag
        print(f"  Candidates checked (total) : {sd.get('total_candidates_checked', 0)}")
        print(f"  Rejected clearance low     : {sd.get('total_rej_clearance', 0)}")
        print(f"  Rejected nominal RR low    : {sd.get('total_rej_nominal_rr', 0)}")
        print(f"  Rejected effective RR low  : {sd.get('total_rej_effective_rr', 0)}")
        print(f"  Target rank 1              : {sd.get('rank_1_count', 0)}")
        print(f"  Target rank > 1            : {sd.get('rank_gt_1_count', 0)}")
        print(f"  Avg target rank            : {sd.get('avg_rank', 0)}")
        print(f"  Rows no valid TP1          : {sd.get('rows_no_valid_tp1', 0)}")
    print()

    # Top widest zones
    by_width = sorted(
        [r for r in report.rows if r.entry_zone_width_atr is not None],
        key=lambda r: -(r.entry_zone_width_atr or 0),
    )
    print(f"  Top {limit} rows by zone width (ATR):")
    print(f"  {'Symbol':<10s} {'Side':<5s} {'Width':>7s} {'W/ATR':>7s} {'Src':<18s} {'TP1 Src':<22s} {'Clr/ATR':>7s}")
    print(f"  {'-'*10} {'-'*5} {'-'*7} {'-'*7} {'-'*18} {'-'*22} {'-'*7}")
    for r in by_width[:limit]:
        w = f"{r.entry_zone_width:.5f}" if r.entry_zone_width is not None else "?"
        wa = f"{r.entry_zone_width_atr:.4f}" if r.entry_zone_width_atr is not None else "?"
        ca = f"{r.tp1_clearance_atr:.4f}" if r.tp1_clearance_atr is not None else "?"
        print(f"  {r.symbol:<10s} {r.side:<5s} {w:>7s} {wa:>7s} {r.entry_zone_source:<18s} {r.tp1_source:<22s} {ca:>7s}")
    print()
    print("=" * 72)


def report_as_dict(report: QualityReport) -> dict[str, Any]:
    return {
        "total_rows": report.total_rows,
        "rows_with_entry_zone": report.rows_with_entry_zone,
        "rows_with_tp1": report.rows_with_tp1,
        "rows_without_tp1": report.rows_without_tp1,
        "rows_with_valid_tp1_clearance": report.rows_with_valid_tp1_clearance,
        "rows_with_invalid_negative_tp1_clearance": report.rows_with_invalid_negative_tp1_clearance,
        "rows_with_valid_atr": report.rows_with_valid_atr,
        "avg_zone_width_atr": report.avg_zone_width_atr,
        "max_zone_width_atr": report.max_zone_width_atr,
        "pct_zone_width_gt_0_4_atr": report.pct_zone_width_gt_0_4_atr,
        "pct_zone_width_gt_0_5_atr": report.pct_zone_width_gt_0_5_atr,
        "pct_zone_width_gt_0_6_atr": report.pct_zone_width_gt_0_6_atr,
        "avg_tp1_clearance_atr": report.avg_tp1_clearance_atr,
        "min_tp1_clearance_atr": report.min_tp1_clearance_atr,
        "pct_tp1_clearance_lt_0_10_atr": report.pct_tp1_clearance_lt_0_10_atr,
        "pct_tp1_clearance_lt_0_15_atr": report.pct_tp1_clearance_lt_0_15_atr,
        "pct_tp1_clearance_lt_0_20_atr": report.pct_tp1_clearance_lt_0_20_atr,
        "pct_best_rr_pass_base_rr_fail": report.pct_best_rr_pass_base_rr_fail,
        "zone_source_breakdown": report.zone_source_breakdown,
        "tp1_source_breakdown": report.tp1_source_breakdown,
        "selection_diag": report.selection_diag,
        "rows": [
            {
                "symbol": r.symbol, "side": r.side,
                "entry_low": r.entry_low, "entry_high": r.entry_high,
                "entry_zone_width": r.entry_zone_width,
                "entry_zone_width_atr": r.entry_zone_width_atr,
                "entry_zone_source": r.entry_zone_source,
                "stop_loss": r.stop_loss, "tp1": r.tp1,
                "tp1_source": r.tp1_source,
                "tp1_clearance_from_far_edge": r.tp1_clearance_from_far_edge,
                "tp1_clearance_atr": r.tp1_clearance_atr,
                "expected_effective_rr": r.expected_effective_rr,
                "expected_effective_rr_base": r.expected_effective_rr_base,
                "tp1_effective_rr_base": r.tp1_effective_rr_base,
            }
            for r in report.rows
        ],
    }


def write_csv(report: QualityReport, path: str) -> None:
    import csv
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "symbol", "side", "entry_low", "entry_high", "entry_zone_width",
            "entry_zone_width_atr", "entry_zone_source", "stop_loss", "tp1",
            "tp1_source", "tp1_clearance_from_far_edge", "tp1_clearance_atr",
            "expected_effective_rr", "expected_effective_rr_base",
            "tp1_effective_rr_base",
        ])
        for r in report.rows:
            w.writerow([
                r.symbol, r.side, r.entry_low or "", r.entry_high or "",
                r.entry_zone_width or "", r.entry_zone_width_atr or "",
                r.entry_zone_source, r.stop_loss or "", r.tp1 or "",
                r.tp1_source, r.tp1_clearance_from_far_edge or "",
                r.tp1_clearance_atr or "", r.expected_effective_rr or "",
                r.expected_effective_rr_base or "", r.tp1_effective_rr_base or "",
            ])


def _find_latest_snapshot() -> Path | None:
    candidates: list[Path] = []
    for parent in (Path("app_data/scanner_snapshots"), Path("data/scanner_snapshots"), Path("data")):
        if parent.is_dir():
            for p in parent.glob("*.json"):
                if p.is_file():
                    candidates.append(p)
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 13A — entry zone & TP1 quality diagnostic")
    parser.add_argument("input_path", nargs="?", default=None, help="Path to scanner result JSON")
    parser.add_argument("--json-output", type=str, default=None)
    parser.add_argument("--csv", type=str, default=None)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    input_path = args.input_path
    if input_path is None:
        snapshot = _find_latest_snapshot()
        if snapshot is None:
            print("[ERROR] No input file and no snapshot found.", file=sys.stderr)
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
        print(f"[ERROR] Invalid JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    parsed = parse_input(raw)
    if not parsed:
        print("[ERROR] No valid rows found.", file=sys.stderr)
        sys.exit(1)

    report = compute_quality(parsed)
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
