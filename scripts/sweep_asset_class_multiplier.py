"""Sweep asset_class_sl_multiplier values for metals/crypto.

Runs system backtest + walk-forward for each multiplier value × each symbol,
exports sweep_result.json + sweep_report.md for manual review.

Usage:
  python scripts/sweep_asset_class_multiplier.py --asset-class crypto --symbols BTC/USD --values 1.0 1.4 1.8
  python scripts/sweep_asset_class_multiplier.py --asset-class metals --values 1.0 1.1 1.2 1.3
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core.risk_engine as _re

from scripts.run_baseline_validation import (
    _connect_mt5,
    _load_settings,
    _process_symbol_with_timeout,
    _log_symbol_result,
    DEFAULT_IS_MONTHS,
    DEFAULT_OOS_MONTHS,
    DEFAULT_LOOKBACK_MONTHS,
    DEFAULT_TIMEOUT_SECONDS,
    WARNING_TRADE_THRESHOLD,
    WF_WARNING_VERDICTS,
)

DEFAULT_VALUES_METALS = [1.0, 1.1, 1.2, 1.3]
DEFAULT_VALUES_CRYPTO = [1.0, 1.2, 1.4, 1.6, 1.8]
DEFAULT_SYMBOLS = {
    "metals": ["XAU/USD", "XAG/USD"],
    "crypto": ["BTC/USD"],
}

# ── Multiplier override (in-process, no file writes) ────────────────────────

_ORIGINAL_MULTIPLIERS: dict[str, float] | None = None


def _override_multiplier(asset_class: str, value: float) -> None:
    """Temporarily set ASSET_CLASS_SL_MULTIPLIER[asset_class] = value."""
    global _ORIGINAL_MULTIPLIERS
    if _ORIGINAL_MULTIPLIERS is None:
        _ORIGINAL_MULTIPLIERS = dict(_re.ASSET_CLASS_SL_MULTIPLIER)
    _re.ASSET_CLASS_SL_MULTIPLIER[asset_class] = value


def _restore_multipliers() -> None:
    """Restore ASSET_CLASS_SL_MULTIPLIER to original values."""
    global _ORIGINAL_MULTIPLIERS
    if _ORIGINAL_MULTIPLIERS is not None:
        _re.ASSET_CLASS_SL_MULTIPLIER.clear()
        _re.ASSET_CLASS_SL_MULTIPLIER.update(_ORIGINAL_MULTIPLIERS)
        _ORIGINAL_MULTIPLIERS = None


def _get_multiplier_for(asset_class: str) -> float:
    """Read the current effective multiplier for an asset class."""
    return float(_re.ASSET_CLASS_SL_MULTIPLIER.get(asset_class, 1.0))


# ── CLI ─────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Sweep asset_class_sl_multiplier cho metals hoặc crypto.",
    )
    p.add_argument(
        "--asset-class", required=True,
        choices=["metals", "crypto"],
        help="Nhóm tài sản cần sweep (bắt buộc chọn 1).",
    )
    p.add_argument(
        "--symbols", type=str, nargs="*", metavar="SYM",
        help="Danh sách symbols. Mặc định: metals → XAU/USD,XAG/USD ; crypto → BTC/USD.",
    )
    p.add_argument(
        "--values", type=float, nargs="*", metavar="V",
        help="Danh sách giá trị multiplier cần thử. Mặc định: metals=[1.0,1.1,1.2,1.3] ; crypto=[1.0,1.2,1.4,1.6,1.8].",
    )
    p.add_argument(
        "--start", type=str, metavar="YYYY-MM-DD",
        help="Ngày bắt đầu backtest. Mặc định: 24 tháng trước ngày chạy.",
    )
    p.add_argument(
        "--end", type=str, metavar="YYYY-MM-DD",
        help="Ngày kết thúc backtest. Mặc định: hôm nay.",
    )
    p.add_argument(
        "--is-months", type=int, default=DEFAULT_IS_MONTHS,
        help=f"Số tháng in-sample cho walk-forward (default: {DEFAULT_IS_MONTHS}).",
    )
    p.add_argument(
        "--oos-months", type=int, default=DEFAULT_OOS_MONTHS,
        help=f"Số tháng out-of-sample cho walk-forward (default: {DEFAULT_OOS_MONTHS}).",
    )
    p.add_argument(
        "--output-dir", type=str, metavar="DIR",
        help="Thư mục xuất kết quả. Mặc định: data/temp/sweep_reports/<asset_class>_<timestamp>/",
    )
    p.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Timeout mỗi symbol (giây). Mặc định: {DEFAULT_TIMEOUT_SECONDS}.",
    )
    return p


# ── Sweep entry ──────────────────────────────────────────────────────────────

SweepRow = dict[str, Any]


def run_single_sweep(
    mt5,
    app_settings,
    symbol: str,
    start: datetime,
    end: datetime,
    multiplier: float,
    is_months: int,
    oos_months: int,
    timeout: int,
) -> SweepRow:
    """Run backtest + walk-forward for one symbol at one multiplier value."""
    r = _process_symbol_with_timeout(
        mt5, app_settings, symbol, start, end,
        is_months, oos_months, timeout,
    )
    summary = r.get("backtest_summary") or {}
    wf = r.get("wf_result") or {}
    return {
        "multiplier": multiplier,
        "symbol": symbol,
        "error": r.get("error"),
        "total_trades": summary.get("total_trades", 0),
        "win_rate": summary.get("win_rate", 0),
        "expectancy_r": summary.get("expectancy_r", 0) or 0.0,
        "profit_factor": summary.get("profit_factor", 0) or 0.0,
        "max_drawdown_r": summary.get("max_drawdown_r", 0) or 0.0,
        "average_r": summary.get("average_r", 0) or 0.0,
        "wf_verdict": wf.get("verdict", "INCONCLUSIVE"),
        "robustness_score": wf.get("robustness_score"),
        "elapsed_seconds": r.get("elapsed_seconds", 0),
    }


# ── Output ───────────────────────────────────────────────────────────────────

def _format_pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.0f}%"


def _format_r(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:+.2f}"


def build_sweep_report(
    asset_class: str,
    rows: list[SweepRow],
    config: dict[str, Any],
) -> str:
    """Build sweep_report.md with per-symbol tables sorted by expectancy_r."""
    now_str = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    symbols = sorted({r["symbol"] for r in rows})

    lines = [
        f"# Asset Class SL Multiplier Sweep — {asset_class.upper()}",
        "",
        f"**Generated:** {now_str}",
        f"**Asset class:** {asset_class}",
        f"**Date range:** {config['start']} → {config['end']}",
        f"**Walk-Forward:** IS={config['is_months']}m / OOS={config['oos_months']}m",
        f"**Values tested:** {', '.join(str(v) for v in config['values'])}",
        "",
    ]

    for symbol in symbols:
        sym_rows = [r for r in rows if r["symbol"] == symbol]
        # Sort by expectancy_r descending
        sym_rows.sort(key=lambda r: r["expectancy_r"], reverse=True)

        lines.append(f"## {symbol}")
        lines.append("")
        lines.append(
            "| Multiplier | Trades | Win Rate | E[R] | PF | Max DD(R) | Avg R | "
            "WF Verdict | Robustness |"
        )
        lines.append(
            "|------------|--------|----------|------|----|-----------|-------|"
            "------------|------------|"
        )

        for row in sym_rows:
            warnings = []
            if row.get("error"):
                warnings.append(f"ERROR: {row['error']}")
            if row["total_trades"] < WARNING_TRADE_THRESHOLD and not row.get("error"):
                warnings.append(f"⚠ LOW SAMPLE ({row['total_trades']} trades)")
            if row.get("wf_verdict") in WF_WARNING_VERDICTS:
                warnings.append(f"WF: {row['wf_verdict']}")

            warning_text = f" {', '.join(warnings)}" if warnings else ""
            robustness = f"{row['robustness_score']:.0f}" if row.get("robustness_score") is not None else "—"

            lines.append(
                f"| {row['multiplier']:.1f} | {row['total_trades']} "
                f"| {_format_pct(row['win_rate'])} "
                f"| {_format_r(row['expectancy_r'])} "
                f"| {row['profit_factor']:.2f} "
                f"| {row['max_drawdown_r']:.1f} "
                f"| {_format_r(row['average_r'])} "
                f"| {row.get('wf_verdict', '—')} "
                f"| {robustness} |{warning_text}"
            )

        lines.append("")

    # ── Recommendation ───────────────────────────────────────────────────
    lines.append("## Recommendation")
    lines.append("")

    best = find_best_multiplier(rows, min_trades=WARNING_TRADE_THRESHOLD)
    if best is None:
        lines.append(
            "**Không có giá trị nào đủ tin cậy trong lần sweep này** — "
            "cần thêm dữ liệu hoặc mở rộng khoảng `--values`."
        )
    else:
        lines.append(
            f"**Đề xuất `asset_class_sl_multiplier.{asset_class} = {best['multiplier']:.1f}`**"
        )
        lines.append("")
        lines.append(f"- Symbol: {best['symbol']}")
        lines.append(f"- Trades: {best['total_trades']}")
        lines.append(f"- E[R]: {best['expectancy_r']:+.2f}R")
        lines.append(f"- Win Rate: {best['win_rate']:.0f}%")
        lines.append(f"- WF Verdict: {best['wf_verdict']}")
        lines.append(f"- Robustness: {best.get('robustness_score', '—')}")
        lines.append("")
        lines.append(
            "Copy giá trị này vào `config/risk_params.json` → "
            "`asset_class_sl_multiplier` → key tương ứng."
        )

    lines.append("")
    lines.append("### Legend")
    lines.append("- ⚠ **LOW SAMPLE**: < 30 trades, kết quả chưa đủ tin cậy thống kê")
    lines.append("- ⚠ **WF: INCONCLUSIVE**: Walk-forward không đủ dữ liệu để kết luận")
    lines.append("- ⚠ **WF: OVERFITTING**: Hệ thống overfit — hiệu suất IS khác biệt lớn so với OOS")
    lines.append("")
    lines.append("---")
    lines.append("*Report generated by scripts/sweep_asset_class_multiplier.py*")

    return "\n".join(lines)


def find_best_multiplier(
    rows: list[SweepRow],
    min_trades: int = 30,
) -> SweepRow | None:
    """Find the best multiplier by expectancy_r, filtering unreliable rows.

    Criteria (all must be satisfied):
      - total_trades >= min_trades
      - wf_verdict NOT in {"OVERFITTING", "INCONCLUSIVE"}
      - no error

    Returns the row with highest expectancy_r, or None.
    """
    excluded_verdicts = {"OVERFITTING", "INCONCLUSIVE"}
    candidates = [
        r for r in rows
        if not r.get("error")
        and r["total_trades"] >= min_trades
        and r.get("wf_verdict") not in excluded_verdicts
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda r: r["expectancy_r"])


def build_sweep_json(
    asset_class: str,
    rows: list[SweepRow],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Build sweep_result.json payload."""
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "asset_class": asset_class,
        "config": config,
        "results": rows,
        "recommendation": find_best_multiplier(rows),
    }


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    asset_class = args.asset_class

    # Resolve symbols
    symbols = args.symbols if args.symbols else DEFAULT_SYMBOLS.get(asset_class, [])

    # Resolve values
    values = args.values if args.values else (
        DEFAULT_VALUES_METALS if asset_class == "metals" else DEFAULT_VALUES_CRYPTO
    )

    # Resolve dates
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    end = datetime.fromisoformat(args.end) if args.end else today
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = datetime.fromisoformat(args.start) if args.start else (
        end - timedelta(days=DEFAULT_LOOKBACK_MONTHS * 31)
    )
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)

    if start >= end:
        print("[ERROR] --start phải trước --end.")
        return 1

    # Resolve output dir
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path(f"data/temp/sweep_reports/{asset_class}_{ts}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Connect MT5 & load settings
    mt5 = _connect_mt5()
    if mt5 is None:
        return 1

    app_settings = _load_settings()

    config = {
        "asset_class": asset_class,
        "symbols": symbols,
        "values": values,
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
        "is_months": args.is_months,
        "oos_months": args.oos_months,
    }

    print(f"=== Asset Class SL Multiplier Sweep ===")
    print(f"  Asset:       {asset_class}")
    print(f"  Symbols:     {', '.join(symbols)}")
    print(f"  Values:      {values}")
    print(f"  Range:       {config['start']} → {config['end']}")
    print(f"  Walk-Forward: IS={args.is_months}m / OOS={args.oos_months}m")
    print(f"  Output:      {output_dir}")
    print(f"  Timeout:     {args.timeout}s/symbol")
    print()

    all_rows: list[SweepRow] = []
    total_combos = len(values) * len(symbols)
    combo_idx = 0

    for val in values:
        _override_multiplier(asset_class, val)
        try:
            for symbol in symbols:
                combo_idx += 1
                print(
                    f"[{combo_idx}/{total_combos}] "
                    f"[{asset_class}={val}] {symbol}...",
                    end=" ", flush=True,
                )
                t0 = time.time()
                row = run_single_sweep(
                    mt5, app_settings, symbol, start, end,
                    val, args.is_months, args.oos_months, args.timeout,
                )
                all_rows.append(row)

                elapsed = time.time() - t0
                if row.get("error"):
                    print(f"SKIPPED: {row['error']} ({elapsed:.0f}s)")
                else:
                    print(
                        f"{row['total_trades']} trades | "
                        f"WR {row['win_rate']:.0f}% | "
                        f"E[R] {row['expectancy_r']:+.2f} | "
                        f"verdict: {row['wf_verdict']} | "
                        f"{elapsed:.0f}s"
                    )
        finally:
            _restore_multipliers()

    # ── Export ──────────────────────────────────────────────────────────
    print()
    print("── Exporting reports ──")

    json_data = build_sweep_json(asset_class, all_rows, config)
    json_path = output_dir / "sweep_result.json"
    json_path.write_text(
        json.dumps(json_data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"  [OK] {json_path}")

    md_content = build_sweep_report(asset_class, all_rows, config)
    md_path = output_dir / "sweep_report.md"
    md_path.write_text(md_content, encoding="utf-8")
    print(f"  [OK] {md_path}")

    # Final recommendation
    best = find_best_multiplier(all_rows)
    print()
    if best:
        print(
            f"Best multiplier: {best['multiplier']:.1f} "
            f"({best['symbol']}: E[R]={best['expectancy_r']:+.2f}, "
            f"verdict={best['wf_verdict']})"
        )
    else:
        print("No reliable multiplier found — need more data or wider sweep.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
