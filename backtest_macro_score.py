"""Backtest macro score edge — validate whether higher macro scores correlate with
better trade outcomes.

Usage:
  python backtest_macro_score.py              # real data
  python backtest_macro_score.py --demo       # simulated data for testing
"""

from __future__ import annotations

import json
import random
import sqlite3
import sys
from pathlib import Path
from typing import Any

# -- project bootstrap -------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config.paths import journal_db_path

DB_PATH = journal_db_path()

MACRO_BUCKETS = [
    (0, 5), (6, 10), (11, 15), (16, 20), (21, 25), (26, 30),
]


def _extract_macro(analysis_json: str, side: str) -> dict[str, Any]:
    """Parse macro_score and macro_confidence from the stored JSON blob.

    Supports two formats:
    1. Scanner row:  ``{"macro_score": 20, "macro_confidence": 0.85, ...}``
    2. Full analysis: ``{"scenario_scores": {"buy": {"macro_alignment": ...}}, "macro": {"macro_confidence": ...}}``
    """
    try:
        data = json.loads(analysis_json)
    except (json.JSONDecodeError, TypeError):
        return {"macro_score": None, "macro_confidence": None}

    if not isinstance(data, dict):
        return {"macro_score": None, "macro_confidence": None}

    # --- try scanner-row format first ---
    ms_raw = data.get("macro_score")
    mc_raw = data.get("macro_confidence")
    if ms_raw is not None:
        try:
            ms = int(ms_raw)
        except (TypeError, ValueError):
            ms = None
        try:
            mc = float(mc_raw) if mc_raw is not None else None
        except (TypeError, ValueError):
            mc = None
        return {"macro_score": ms, "macro_confidence": mc}

    # --- fallback: full analysis format ---
    scores = data.get("scenario_scores", {})
    if isinstance(scores, dict):
        side_scores = scores.get(side, {})
        if isinstance(side_scores, dict):
            ms_raw = side_scores.get("macro_alignment")
            if ms_raw is not None:
                try:
                    ms = int(ms_raw)
                except (TypeError, ValueError):
                    ms = None
                macro_section = data.get("macro", {})
                mc_raw = macro_section.get("macro_confidence") if isinstance(macro_section, dict) else None
                try:
                    mc = float(mc_raw) if mc_raw is not None else None
                except (TypeError, ValueError):
                    mc = None
                return {"macro_score": ms, "macro_confidence": mc}

    return {"macro_score": None, "macro_confidence": None}


def _determine_side(row: dict[str, Any]) -> str | None:
    """Return 'buy' or 'sell' for a trade row, or None if unclear."""
    scenario = str(row.get("selected_scenario") or "").strip().lower()
    if scenario in ("buy", "sell"):
        return scenario
    try:
        buy_s = int(row.get("buy_score") or 0)
        sell_s = int(row.get("sell_score") or 0)
    except (TypeError, ValueError):
        return None
    if buy_s > sell_s:
        return "buy"
    if sell_s > buy_s:
        return "sell"
    return None


def load_trades() -> list[dict[str, Any]]:
    """Query closed trades with result_r and non-empty analysis_json."""
    if not DB_PATH.exists():
        print(f"[ERROR] Database not found: {DB_PATH}")
        print("Make sure the journal database exists and contains trade data.")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT id, symbol, selected_scenario, buy_score, sell_score,"
        "       result_r, result_amount, result_pct, analysis_json, mode"
        "  FROM journal_entries"
        " WHERE closed_at IS NOT NULL AND closed_at != ''"
        "   AND analysis_json IS NOT NULL AND analysis_json != ''"
        " ORDER BY closed_at DESC"
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def bucket_label(lo: int, hi: int) -> str:
    return f"[{lo}-{hi}]"


def compute_stats(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return {"count": 0, "win_rate": 0.0, "avg_rr": 0.0,
                "profit_factor": 0.0, "avg_confidence": None}

    wins = [t for t in trades if (t.get("result_r") or 0) > 0]
    losses = [t for t in trades if (t.get("result_r") or 0) <= 0]
    total_profit = sum(t.get("result_r", 0) for t in wins)
    total_loss = sum(abs(t.get("result_r", 0)) for t in losses)

    confs = [t.get("macro_confidence") for t in trades if t.get("macro_confidence") is not None]

    return {
        "count": len(trades),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0.0,
        "avg_rr": round(sum(t.get("result_r", 0) for t in trades) / len(trades), 3),
        "profit_factor": round(total_profit / total_loss, 2) if total_loss > 0 else float("inf"),
        "avg_confidence": round(sum(confs) / len(confs), 3) if confs else None,
    }


def _make_result_r(amount: float | None) -> float | None:
    """Use result_amount as approximate result in R if result_r is missing."""
    if amount is None:
        return None
    # rough heuristic: $100 ≈ 1R for a standard 1% risk on $10k account
    return round(abs(amount) / 100.0, 3) if abs(amount) > 0 else 0.0


def _generate_demo_trades(n: int = 80) -> list[dict[str, Any]]:
    """Generate simulated trades with a known macro-score edge."""
    rng = random.Random(42)
    symbols = ["EUR/USD", "USD/JPY", "GBP/USD", "AUD/USD", "USD/CAD", "NZD/USD"]
    sides = ["buy", "sell"]
    trades: list[dict[str, Any]] = []

    for _ in range(n):
        ms = rng.randint(0, 30)
        # inject a positive edge: higher macro_score -> slightly better expected outcome
        # baseline win rate ~45%, +1% per macro point above 15
        base_wr = 0.45
        edge = max(0, (ms - 15) * 0.008)  # up to +12% at macro=30
        win = rng.random() < (base_wr + edge)

        if win:
            # winners: 0.5R to 3.5R, slightly higher for high macro
            result_r = round(rng.uniform(0.5, 3.5) + edge * 2.0, 2)
        else:
            # losers: -0.5R to -1.5R
            result_r = round(-rng.uniform(0.5, 1.5), 2)

        trades.append({
            "symbol": rng.choice(symbols),
            "side": rng.choice(sides),
            "macro_score": ms,
            "macro_confidence": round(rng.uniform(0.3, 1.0), 2),
            "result_r": result_r,
            "result_pct": round(result_r * rng.uniform(0.8, 1.2), 2),
        })

    return trades


def run_analysis(trades: list[dict[str, Any]]) -> None:
    """Core analysis: bucket, stats, correlation, charts."""
    print(f"\n  Trades with usable macro data: {len(trades)}")

    if len(trades) < 5:
        print("\n[WARN] Too few trades for meaningful analysis (need >= 5).")
        return

    # ---- bucket analysis ----------------------------------------------------
    print("\n" + "-" * 65)
    print(f"  {'Bucket':<12} {'Count':>6} {'Win Rate':>9} {'Avg R:R':>8} {'Prof.Factor':>11} {'Avg Conf':>8}")
    print("-" * 65)

    bucket_stats: list[dict[str, Any]] = []
    all_x: list[float] = []
    all_y: list[float] = []

    for lo, hi in MACRO_BUCKETS:
        bucket_trades = [t for t in trades if lo <= t["macro_score"] <= hi]
        stats = compute_stats(bucket_trades)
        stats["bucket"] = bucket_label(lo, hi)
        stats["lo"] = lo
        stats["hi"] = hi
        bucket_stats.append(stats)

        label = bucket_label(lo, hi)
        conf_str = f"{stats['avg_confidence']:.2f}" if stats["avg_confidence"] else "  N/A"
        pf_str = f"{stats['profit_factor']:.2f}" if stats["profit_factor"] != float("inf") else "  inf"
        print(f"  {label:<12} {stats['count']:>6} {stats['win_rate']:>8.1f}% {stats['avg_rr']:>8.3f} {pf_str:>11} {conf_str:>8}")

        for t in bucket_trades:
            all_x.append(float(t["macro_score"]))
            all_y.append(float(t["result_r"] or 0))

    # ---- correlation coefficient --------------------------------------------
    n = len(all_x)
    if n >= 3:
        mean_x = sum(all_x) / n
        mean_y = sum(all_y) / n
        cov = sum((all_x[i] - mean_x) * (all_y[i] - mean_y) for i in range(n))
        std_x = (sum((x - mean_x) ** 2 for x in all_x) ** 0.5)
        std_y = (sum((y - mean_y) ** 2 for y in all_y) ** 0.5)
        if std_x > 0 and std_y > 0:
            corr = cov / (std_x * std_y)
        else:
            corr = 0.0
    else:
        corr = 0.0

    # ---- conclusion ---------------------------------------------------------
    print("\n" + "=" * 65)
    print("  CONCLUSION")
    print("=" * 65)
    print(f"  Correlation coefficient (macro_score vs result_r): r = {corr:.4f}")
    print(f"  Sample size: {n} trades")

    if corr > 0.10:
        print("  => POSITIVE correlation: higher macro scores tend to produce")
        print("     better trade outcomes. The macro scoring system has edge.")
    elif corr > -0.10:
        print("  => WEAK correlation: macro scores do NOT strongly predict")
        print("     trade outcomes. The scoring may need recalibration.")
    else:
        print("  => NEGATIVE correlation: higher macro scores actually predict")
        print("     WORSE outcomes. The scoring logic may be inverted.")

    # ---- charts (matplotlib) ------------------------------------------------
    try:
        _plot_charts(bucket_stats, all_x, all_y, corr, n)
    except ImportError:
        print("\n  [INFO] matplotlib not installed. Skipping charts.")
        print("  Install with: pip install matplotlib")
    except Exception as exc:
        print(f"\n  [WARN] Chart rendering failed: {exc}")


def _plot_charts(
    bucket_stats: list[dict[str, Any]],
    all_x: list[float],
    all_y: list[float],
    corr: float,
    n: int,
) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

    # ---- Chart 1: Bar — bucket vs win rate --------------------------------
    labels = [s["bucket"] for s in bucket_stats]
    win_rates = [s["win_rate"] for s in bucket_stats]
    counts = [s["count"] for s in bucket_stats]
    colors = ["#d9534f" if w < 40 else "#f0ad4e" if w < 55 else "#5cb85c" for w in win_rates]

    bars = ax1.bar(labels, win_rates, color=colors, edgecolor="white", linewidth=0.8)
    ax1.axhline(y=50, color="gray", linestyle="--", linewidth=0.8, alpha=0.7)
    ax1.set_ylim(0, 100)
    ax1.set_ylabel("Win Rate (%)")
    ax1.set_title("Macro Score Bucket vs Win Rate")
    for bar, cnt, wr in zip(bars, counts, win_rates):
        if cnt > 0:
            ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
                     f"n={cnt}\n{wr:.0f}%", ha="center", va="bottom", fontsize=8)

    # ---- Chart 2: Scatter — macro_score vs result_r -----------------------
    x_arr = np.array(all_x)
    y_arr = np.array(all_y)
    ax2.scatter(x_arr, y_arr, alpha=0.55, c="#337ab7", edgecolors="white", linewidth=0.3, s=40)
    ax2.axhline(y=0, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)

    if n >= 3:
        coeffs = np.polyfit(x_arr, y_arr, 1)
        trend_y = np.polyval(coeffs, x_arr)
        ax2.plot(x_arr, trend_y, color="#d9534f", linewidth=1.5, alpha=0.8,
                 label=f"Trend (r={corr:.3f})")

    ax2.set_xlabel("Macro Score")
    ax2.set_ylabel("Result (R)")
    ax2.set_title(f"Macro Score vs Result R  (n={n})")
    ax2.legend(fontsize=8)
    ax2.grid(axis="y", alpha=0.3, linewidth=0.5)

    fig.suptitle("Macro Score Edge Backtest", fontsize=13, fontweight="bold")
    plt.tight_layout()

    out_path = Path(__file__).resolve().parent / "macro_score_backtest.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  Chart saved to: {out_path}")


def _print_db_diagnostics(rows: list[dict[str, Any]]) -> None:
    """Print what's actually in the database."""
    total = len(rows)
    with_rr = sum(1 for r in rows if r.get("result_r") is not None)
    with_amount = sum(1 for r in rows if r.get("result_amount") is not None)
    modes: dict[str, int] = {}
    for r in rows:
        m = str(r.get("mode") or "unknown")
        modes[m] = modes.get(m, 0) + 1

    # check how many have macro data in analysis_json
    with_macro = 0
    for r in rows:
        side = _determine_side(r)
        if side is None:
            continue
        macro = _extract_macro(r["analysis_json"], side)
        if macro["macro_score"] is not None:
            with_macro += 1

    print(f"\n  Database diagnostics:")
    print(f"    Closed trades found: {total}")
    print(f"    With result_r:       {with_rr}")
    print(f"    With result_amount:  {with_amount}")
    print(f"    With macro data:     {with_macro}")
    print(f"    By mode:             {modes}")
    print()
    if with_macro == 0:
        print("  [ISSUE] No trades have macro_score in analysis_json.")
        print("  Macro data is only stored for trades saved via the Scanner")
        print("  or Analysis screen (mode='scanner' or mode='analysis').")
        print("  MT5-synced trades (mode='mt5_history') do NOT contain macro scores.")
        print()
        print("  To populate macro data in the journal:")
        print("  1. Open a trade via Scanner -> 'Luu vao Nhat ky'")
        print("  2. Close the trade and update result_r in the journal")
        print("  3. Re-run: python backtest_macro_score.py")


def main() -> None:
    demo_mode = "--demo" in sys.argv

    print("=" * 65)
    print("  MACRO SCORE BACKTEST — Does macro_score have real edge?")
    if demo_mode:
        print("  MODE: DEMO (simulated data)")
    else:
        print(f"  Database: {DB_PATH}")
    print("=" * 65)

    if demo_mode:
        trades = _generate_demo_trades(80)
        print("\n  [DEMO] Using 80 simulated trades with known positive edge.")
        print("  (Higher macro_score -> slightly higher win rate & avg R:R)")
        run_analysis(trades)
        return

    all_rows = load_trades()
    if not all_rows:
        print("\n[ERROR] No closed trades found in the journal.")
        sys.exit(1)

    # ---- parse every trade --------------------------------------------------
    trades: list[dict[str, Any]] = []
    skipped_no_side = 0
    skipped_no_macro = 0
    skipped_no_result = 0

    for row in all_rows:
        side = _determine_side(row)
        if side is None:
            skipped_no_side += 1
            continue
        macro = _extract_macro(row["analysis_json"], side)
        ms = macro["macro_score"]
        if ms is None:
            skipped_no_macro += 1
            continue

        # use result_r first, fall back to synthetic from result_amount
        rr = row.get("result_r")
        if rr is None:
            rr = _make_result_r(row.get("result_amount"))
        if rr is None:
            skipped_no_result += 1
            continue

        trades.append({
            "symbol": row["symbol"],
            "side": side,
            "macro_score": ms,
            "macro_confidence": macro["macro_confidence"],
            "result_r": rr,
            "result_pct": row.get("result_pct"),
            "buy_score": row.get("buy_score"),
            "sell_score": row.get("sell_score"),
        })

    if not trades:
        _print_db_diagnostics(all_rows)
        print("\n  Run with --demo to test the analysis pipeline:")
        print("    python backtest_macro_score.py --demo")
        sys.exit(1)

    print(f"\n  Total closed trades: {len(all_rows)}")
    print(f"  Trades with usable macro + result data: {len(trades)}")
    if skipped_no_side:
        print(f"    Skipped (no side):       {skipped_no_side}")
    if skipped_no_macro:
        print(f"    Skipped (no macro data): {skipped_no_macro}")
    if skipped_no_result:
        print(f"    Skipped (no result_r):   {skipped_no_result}")

    run_analysis(trades)


if __name__ == "__main__":
    main()
