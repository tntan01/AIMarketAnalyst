"""Baseline Validation — đo lường khách quan hiệu suất scanner hiện tại.

Chạy system backtest + walk-forward + param sensitivity trên toàn bộ
SUPPORTED_SYMBOLS, không sửa bất kỳ logic tính điểm/entry/SL/TP nào.

Usage:
  python scripts/run_baseline_validation.py --quick          # Smoke test (1 symbol + quick_sweep)
  python scripts/run_baseline_validation.py                  # Full run, all symbols
  python scripts/run_baseline_validation.py --symbols EUR/USD XAU/USD
  python scripts/run_baseline_validation.py --start 2025-01-01 --end 2025-12-31
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

# Force UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.constants import SUPPORTED_SYMBOLS
from core.system_backtest_engine import (
    BacktestRequest,
    BacktestResult,
    run_system_backtest,
    summarize_backtest_trades,
)
from core.walk_forward_engine import run_walk_forward
from core.param_sensitivity import (
    DEFAULT_SWEEP_CONFIGS,
    DEFAULT_PERIODS,
    DEFAULT_SYMBOLS,
    export_results,
    quick_sweep,
    sweep_params,
)

DEFAULT_TIMEOUT_SECONDS = 300  # 5 phút cho giai đoạn compute (backtest + walk-forward)
DEFAULT_IO_TIMEOUT_SECONDS = 120  # 2 phút cho giai đoạn MT5 I/O (fetch candles)
# Lý do 120s: load D1/H4/H1 (~30k bars) <15s, M15 chunked 2 năm (~13 chunks) <30s,
# tổng ~50s bình thường. 120s cho 2.4x headroom với network/symbol chậm.
DEFAULT_IS_MONTHS = 6
DEFAULT_OOS_MONTHS = 3
DEFAULT_LOOKBACK_MONTHS = 24

WARNING_TRADE_THRESHOLD = 30
WF_WARNING_VERDICTS = {"INCONCLUSIVE", "OVERFITTING"}


# ── CLI ────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Baseline Validation — đo lường khách quan hiệu suất scanner",
    )
    p.add_argument(
        "--symbols", type=str, nargs="*", metavar="SYM",
        help="Danh sách symbols cần chạy. Mặc định: toàn bộ SUPPORTED_SYMBOLS.",
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
        help="Thư mục xuất kết quả. Mặc định: data/temp/baseline_reports/<timestamp>/",
    )
    p.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Timeout mỗi symbol (giây). Mặc định: {DEFAULT_TIMEOUT_SECONDS}.",
    )
    p.add_argument(
        "--quick", action="store_true",
        help="Chạy smoke test: 1 symbol + quick_sweep() để kiểm tra nhanh.",
    )
    return p


# ── MT5 helpers ────────────────────────────────────────────────────────────────

def _connect_mt5():
    """Kết nối MT5, trả về MT5Service hoặc None."""
    try:
        from services.mt5_service import MT5Service
        mt5 = MT5Service()
        status = mt5.connection_status()
        if not status.connected or not status.logged_in:
            print(f"[ERROR] MT5 chưa sẵn sàng: connected={status.connected} logged_in={status.logged_in}")
            print("Mở MT5, đăng nhập, rồi chạy lại.")
            return None
        print(f"[OK] MT5 connected — {status.broker} | {status.server} | balance={status.balance}")
        return mt5
    except Exception as exc:
        print(f"[ERROR] Không thể kết nối MT5: {exc}")
        return None


def _load_settings():
    """Load AppSettings để lấy risk_percent, balance, v.v."""
    try:
        from services.settings_service import SettingsService
        svc = SettingsService()
        return svc.load()
    except Exception:
        from config.settings import default_settings
        return default_settings()


def _resolve_broker_symbol(mt5, app_symbol: str) -> str | None:
    """Resolve display symbol → MT5 broker symbol."""
    available = mt5.available_symbols(market_watch_only=True)
    return mt5.resolve_symbol(app_symbol, available)


def _load_candles_for_range(
    mt5,
    broker_symbol: str,
    start: datetime,
    end: datetime,
) -> dict[str, list]:
    """Load D1, H4, H1, M15 candles cho khoảng thời gian backtest.

    D1/H4/H1 cần warmup 520 ngày (như param_sensitivity.py).
    M15 cần warmup 90 ngày, load theo chunk 60 ngày.
    """
    warmup_start = start - timedelta(days=520)
    m15_start = start - timedelta(days=90)

    candles: dict[str, list] = {}

    for tf, (tf_start, tf_end) in {
        "D1": (warmup_start, end),
        "H4": (warmup_start, end),
        "H1": (warmup_start, end),
    }.items():
        try:
            candles[tf] = mt5.load_ohlcv_range(broker_symbol, tf, tf_start, tf_end)
        except Exception as exc:
            print(f"  [WARN] Không load được {tf} cho {broker_symbol}: {exc}")
            candles[tf] = []

    # M15 chunked
    try:
        candles["M15"] = _load_m15_chunked(mt5, broker_symbol, m15_start, end)
    except Exception as exc:
        print(f"  [WARN] Không load được M15 cho {broker_symbol}: {exc}")
        candles["M15"] = []

    return candles


def _load_m15_chunked(mt5, broker_symbol: str, start: datetime, end: datetime) -> list:
    """Load M15 candles in 60-day chunks to avoid MT5 limits."""
    all_candles: list = []
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=60), end)
        try:
            chunk = mt5.load_ohlcv_range(broker_symbol, "M15", chunk_start, chunk_end)
            if chunk:
                all_candles.extend(chunk)
        except Exception:
            pass
        chunk_start = chunk_end
    return all_candles


# ── Single-symbol processing ───────────────────────────────────────────────────
#
# Chia làm 2 giai đoạn rõ rệt để tránh thread-safety issue với MT5:
#   (A) MT5 I/O  — chạy TUẦN TỰ ở main thread, timeout 120s
#   (B) Compute  — backtest + walk-forward (thuần Python), bọc ThreadPoolExecutor + timeout 300s
#
# Nếu (A) fail → skip symbol, không vào (B).
# Nếu (B) timeout → thread worker bị bỏ, nhưng không còn giữ MT5 connection.

def _fetch_symbol_data(
    mt5,
    symbol: str,
    start: datetime,
    end: datetime,
    io_timeout: int = DEFAULT_IO_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Giai đoạn (A): MT5 I/O — resolve symbol + load candles.

    Chạy TUẦN TỰ ở main thread. Bọc trong ThreadPoolExecutor riêng với
    io_timeout ngắn (120s) để tránh treo vĩnh viễn nếu MT5 không phản hồi.
    KHÔNG gọi bất kỳ hàm backtest/compute nào ở đây.

    Returns:
        dict với keys: symbol, broker_symbol, candles, error
        Nếu error không None → giai đoạn (A) thất bại, không vào (B).
    """
    def _io_work():
        broker = _resolve_broker_symbol(mt5, symbol)
        if broker is None:
            return {
                "symbol": symbol,
                "broker_symbol": None,
                "candles": None,
                "error": f"Không tìm thấy broker symbol cho {symbol} trong Market Watch.",
            }

        candles = _load_candles_for_range(mt5, broker, start, end)

        # Kiểm tra dữ liệu tối thiểu
        from core.system_backtest_engine import validate_backtest_input
        try:
            validate_backtest_input(
                BacktestRequest(
                    symbol=symbol, broker_symbol=broker,
                    start=start, end=end,
                    initial_balance=10000, risk_percent=1.0,
                ),
                candles,
            )
        except ValueError as exc:
            return {
                "symbol": symbol,
                "broker_symbol": broker,
                "candles": None,
                "error": f"Thiếu dữ liệu: {exc}",
            }

        return {
            "symbol": symbol,
            "broker_symbol": broker,
            "candles": candles,
            "error": None,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_io_work)
        try:
            return future.result(timeout=io_timeout)
        except concurrent.futures.TimeoutError:
            return {
                "symbol": symbol,
                "broker_symbol": None,
                "candles": None,
                "error": f"MT5 I/O timeout sau {io_timeout}s",
            }


def _run_backtest_compute(
    app_settings,
    symbol: str,
    broker_symbol: str,
    candles: dict[str, list],
    start: datetime,
    end: datetime,
    is_months: int,
    oos_months: int,
) -> dict[str, Any]:
    """Giai đoạn (B): Compute — backtest + walk-forward (thuần Python).

    Được gọi trong ThreadPoolExecutor với timeout 300s.
    KHÔNG gọi bất kỳ MT5 API nào. Chỉ làm việc trên candles đã load.
    """
    trading = app_settings.trading
    request = BacktestRequest(
        symbol=symbol,
        broker_symbol=broker_symbol,
        start=start,
        end=end,
        initial_balance=float(trading.account_balance),
        risk_percent=float(trading.default_risk_percent),
        account_currency=trading.account_currency,
        lot_step=float(trading.lot_step),
        minimum_lot=float(trading.minimum_lot),
        contract_size_override=float(trading.contract_size_override) if trading.contract_size_override else None,
        timezone_name=app_settings.display.timezone,
        min_final_score=0,
    )

    bt_result = run_system_backtest(request, candles)
    summary = summarize_backtest_trades(bt_result.trades)

    wf_result: dict[str, Any]
    if summary.get("total_trades", 0) > 0:
        try:
            wf_result = run_walk_forward(
                request, candles,
                is_months=is_months,
                oos_months=oos_months,
                step_months=oos_months,
            )
        except Exception as exc:
            wf_result = {
                "error": str(exc),
                "verdict": "INCONCLUSIVE",
                "window_count": 0,
            }
    else:
        wf_result = {
            "verdict": "INCONCLUSIVE",
            "window_count": 0,
        }

    return {
        "backtest": bt_result,
        "backtest_summary": summary,
        "wf_result": wf_result,
    }


def _process_symbol_with_timeout(
    mt5,
    app_settings,
    symbol: str,
    start: datetime,
    end: datetime,
    is_months: int,
    oos_months: int,
    timeout: int,
) -> dict[str, Any]:
    """Orchestrator: chạy (A) I/O tuần tự, (B) compute với timeout.

    Flow:
      1. Gọi _fetch_symbol_data() — MT5 I/O, timeout 120s.
      2. Nếu có lỗi → trả về ngay, không vào compute.
      3. Gọi _run_backtest_compute() trong thread riêng, timeout 300s.
      4. Ghép kết quả và trả về.
    """
    t0 = time.time()

    # ── Phase A: MT5 I/O (sequential via dedicated executor) ──
    io_result = _fetch_symbol_data(mt5, symbol, start, end)
    if io_result["error"]:
        return {
            "symbol": symbol,
            "broker_symbol": io_result.get("broker_symbol"),
            "backtest": None,
            "backtest_summary": None,
            "wf_result": None,
            "error": io_result["error"],
            "elapsed_seconds": round(time.time() - t0, 1),
        }

    broker_symbol = io_result["broker_symbol"]
    candles = io_result["candles"]

    # ── Phase B: Compute (threaded with timeout) ──
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            _run_backtest_compute,
            app_settings, symbol, broker_symbol, candles,
            start, end, is_months, oos_months,
        )
        try:
            compute_result = future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return {
                "symbol": symbol,
                "broker_symbol": broker_symbol,
                "backtest": None,
                "backtest_summary": None,
                "wf_result": None,
                "error": f"Timeout sau {timeout}s (giai đoạn compute)",
                "elapsed_seconds": round(time.time() - t0, 1),
            }

    return {
        "symbol": symbol,
        "broker_symbol": broker_symbol,
        "backtest": compute_result["backtest"],
        "backtest_summary": compute_result["backtest_summary"],
        "wf_result": compute_result["wf_result"],
        "error": None,
        "elapsed_seconds": round(time.time() - t0, 1),
    }


# ── Output ─────────────────────────────────────────────────────────────────────

def _build_baseline_json(
    all_results: list[dict[str, Any]],
    param_results: list | None,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Tạo baseline_summary.json payload."""
    symbols_data = []
    for r in all_results:
        summary = r.get("backtest_summary") or {}
        wf = r.get("wf_result") or {}
        symbols_data.append({
            "symbol": r["symbol"],
            "broker_symbol": r["broker_symbol"],
            "error": r.get("error"),
            "elapsed_seconds": r.get("elapsed_seconds", 0),
            "total_trades": summary.get("total_trades", 0),
            "win_rate": summary.get("win_rate", 0),
            "expectancy_r": summary.get("expectancy_r", 0),
            "profit_factor": summary.get("profit_factor", 0),
            "max_drawdown_r": summary.get("max_drawdown_r", 0),
            "average_r": summary.get("average_r", 0),
            "average_win_r": summary.get("average_win_r", 0),
            "average_loss_r": summary.get("average_loss_r", 0),
            "max_consecutive_losses": summary.get("max_consecutive_losses", 0),
            "average_holding_bars": summary.get("average_holding_bars", 0),
            "wf_verdict": wf.get("verdict"),
            "wf_robustness_score": wf.get("robustness_score"),
            "wf_oos_is_ratio": wf.get("oos_is_expectancy_ratio"),
            "wf_window_count": wf.get("window_count", 0),
            "breakdowns": r.get("backtest") and _extract_breakdown_summary(r["backtest"]),
        })
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "config": config,
        "symbols": sorted(symbols_data, key=lambda s: s.get("expectancy_r", 0) or 0, reverse=True),
        "param_sensitivity": _serialize_param_results(param_results) if param_results else None,
    }


def _extract_breakdown_summary(bt_result: BacktestResult) -> dict[str, Any]:
    """Trích xuất tóm tắt breakdowns (by_side, by_regime, by_score_bucket)."""
    breakdowns = bt_result.breakdowns
    return {
        "by_side": {k: _summary_keys(v) for k, v in breakdowns.get("by_side", {}).items()},
        "by_market_regime": {k: _summary_keys(v) for k, v in breakdowns.get("by_market_regime", {}).items()},
        "by_final_score_bucket": {k: _summary_keys(v) for k, v in breakdowns.get("by_final_score_bucket", {}).items()},
    }


def _summary_keys(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_trades": d.get("total_trades", 0),
        "win_rate": d.get("win_rate", 0),
        "expectancy_r": d.get("expectancy_r", 0),
        "profit_factor": d.get("profit_factor", 0),
    }


def _serialize_param_results(results: list) -> list[dict[str, Any]]:
    """Serialize SweepResult list về dict cho JSON."""
    output = []
    for r in results:
        output.append({
            "json_key": getattr(r, "json_key", ""),
            "attr_name": getattr(r, "attr_name", ""),
            "stability_score": getattr(r, "stability_score", None),
            "verdict": getattr(r, "verdict", ""),
            "recommendation": getattr(r, "recommendation", ""),
            "runs_count": len(getattr(r, "runs", [])),
        })
    return output


def _format_r(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:+.2f}"


def _format_pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.0f}%"


def _build_markdown_report(
    all_results: list[dict[str, Any]],
    config: dict[str, Any],
) -> str:
    """Tạo baseline_report.md với bảng xếp hạng symbols."""
    now_str = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")

    # Sort theo expectancy_r giảm dần
    sorted_results = sorted(
        all_results,
        key=lambda r: (r.get("backtest_summary") or {}).get("expectancy_r", 0) or 0,
        reverse=True,
    )

    lines = [
        f"# Baseline Validation Report",
        f"",
        f"**Generated:** {now_str}",
        f"**Date range:** {config['start']} → {config['end']}",
        f"**Walk-Forward:** IS={config['is_months']}m / OOS={config['oos_months']}m",
        f"**Risk per trade:** {config['risk_percent']}%",
        f"**Initial balance:** ${config['initial_balance']:,.0f}",
        f"",
        f"## Summary",
        f"",
        f"| # | Symbol | Trades | Win Rate | E[R] | PF | Max DD(R) | Avg R | WF Verdict | Robustness |",
        f"|---|--------|--------|----------|------|----|-----------|-------|------------|------------|",
    ]

    for i, r in enumerate(sorted_results, start=1):
        summary = r.get("backtest_summary") or {}
        wf = r.get("wf_result") or {}
        error = r.get("error")

        total_trades = summary.get("total_trades", 0) if not error else 0
        win_rate = summary.get("win_rate", 0) if not error else 0
        expectancy = summary.get("expectancy_r", 0) if not error else None
        pf = summary.get("profit_factor", 0) if not error else None
        max_dd = summary.get("max_drawdown_r", 0) if not error else None
        avg_r = summary.get("average_r", 0) if not error else None
        wf_verdict = wf.get("verdict", "—") if not error else "—"
        robustness = wf.get("robustness_score") if not error else None

        # Warnings
        warnings = []
        if error:
            warnings.append(f"ERROR: {error}")
        if total_trades < WARNING_TRADE_THRESHOLD and not error:
            warnings.append(f"LOW SAMPLE ({total_trades} trades)")
        if wf_verdict in WF_WARNING_VERDICTS:
            warnings.append(f"WF: {wf_verdict}")

        warning_text = f" ⚠ {', '.join(warnings)}" if warnings else ""

        wf_display = wf_verdict if not error else "ERROR"
        robustness_display = f"{robustness:.0f}" if robustness is not None else "—"

        lines.append(
            f"| {i} | {r['symbol']} | {total_trades} | {_format_pct(win_rate)} "
            f"| {_format_r(expectancy)} | {pf if pf else '—'} "
            f"| {max_dd if max_dd is not None else '—'} "
            f"| {_format_r(avg_r)} | {wf_display} | {robustness_display} |{warning_text}"
        )

    # Tổng kết
    valid = [r for r in sorted_results if not r.get("error")]
    lines.append("")
    lines.append("## Aggregate")
    lines.append("")

    if valid:
        total_trades_all = sum(r.get("backtest_summary", {}).get("total_trades", 0) for r in valid)
        avg_expectancy = (
            sum(r.get("backtest_summary", {}).get("expectancy_r", 0) for r in valid) / len(valid)
            if valid else 0
        )
        robust_count = sum(
            1 for r in valid
            if (r.get("wf_result") or {}).get("verdict") == "ROBUST"
        )
        lines.append(f"- **Symbols processed:** {len(valid)} / {len(all_results)}")
        lines.append(f"- **Total trades across all symbols:** {total_trades_all}")
        lines.append(f"- **Average E[R]:** {_format_r(avg_expectancy)}")
        lines.append(f"- **Robust symbols (WF verdict=ROBUST):** {robust_count}/{len(valid)}")
    else:
        lines.append("_Không có symbol nào chạy thành công._")

    lines.append("")
    lines.append("### Legend")
    lines.append("- ⚠ **LOW SAMPLE**: < 30 trades, kết quả chưa đủ tin cậy thống kê")
    lines.append("- ⚠ **WF: INCONCLUSIVE**: Walk-forward không đủ dữ liệu để kết luận")
    lines.append("- ⚠ **WF: OVERFITTING**: Hệ thống overfit — hiệu suất IS khác biệt lớn so với OOS")
    lines.append(f"- **Veridct walk-forward:** ROBUST / SUSPECT / OVERFITTING / INCONCLUSIVE")
    lines.append("")
    lines.append("---")
    lines.append(f"*Report generated by scripts/run_baseline_validation.py*")

    return "\n".join(lines)


def _log_symbol_result(r: dict[str, Any]) -> None:
    """In 1 dòng kết quả ra console."""
    symbol = r["symbol"]
    error = r.get("error")
    if error:
        print(f"[{symbol}] SKIPPED: {error}")
        return

    summary = r.get("backtest_summary") or {}
    wf = r.get("wf_result") or {}
    total = summary.get("total_trades", 0)
    wr = summary.get("win_rate", 0)
    expectancy = summary.get("expectancy_r", 0) or 0
    verdict = wf.get("verdict", "—")
    elapsed = r.get("elapsed_seconds", 0)

    print(f"[{symbol}] {total} trades | WR {wr:.0f}% | E[R] {expectancy:+.2f} | verdict: {verdict} | {elapsed:.0f}s")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # ── Resolve dates ──────────────────────────────────────────────────────
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    end = datetime.fromisoformat(args.end) if args.end else today
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = datetime.fromisoformat(args.start) if args.start else (end - timedelta(days=DEFAULT_LOOKBACK_MONTHS * 31))
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)

    if start >= end:
        print("[ERROR] --start phải trước --end.")
        return 1

    # ── Resolve output dir ─────────────────────────────────────────────────
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("data/temp/baseline_reports") / ts
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Connect MT5 & load settings ────────────────────────────────────────
    mt5 = _connect_mt5()
    if mt5 is None:
        return 1

    app_settings = _load_settings()
    trading = app_settings.trading

    # ── Determine symbols ──────────────────────────────────────────────────
    if args.quick:
        symbols = [args.symbols[0] if args.symbols else "EUR/USD"]
    elif args.symbols:
        symbols = [s for s in args.symbols if s in SUPPORTED_SYMBOLS]
        if not symbols:
            print(f"[ERROR] Không có symbol hợp lệ trong --symbols. Hỗ trợ: {SUPPORTED_SYMBOLS}")
            return 1
    else:
        symbols = list(SUPPORTED_SYMBOLS)

    config = {
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
        "is_months": args.is_months,
        "oos_months": args.oos_months,
        "risk_percent": trading.default_risk_percent,
        "initial_balance": trading.account_balance,
        "account_currency": trading.account_currency,
        "symbol_count": len(symbols),
        "quick_mode": args.quick,
    }

    print(f"=== Baseline Validation ===")
    print(f"  Symbols:   {len(symbols)} ({', '.join(symbols[:5])}{'...' if len(symbols) > 5 else ''})")
    print(f"  Range:     {config['start']} → {config['end']}")
    print(f"  Walk-Forward: IS={args.is_months}m / OOS={args.oos_months}m")
    print(f"  Risk:      {config['risk_percent']}% | Balance: ${config['initial_balance']:,.0f}")
    print(f"  Output:    {output_dir}")
    print(f"  Timeout:   {args.timeout}s/symbol")
    print()

    # ── Phase 1: Backtest + Walk-Forward từng symbol ───────────────────────
    print("── Phase 1: System Backtest + Walk-Forward ──")
    all_results: list[dict[str, Any]] = []

    for idx, symbol in enumerate(symbols, start=1):
        print(f"[{idx}/{len(symbols)}] Processing {symbol}...", end=" ", flush=True)
        r = _process_symbol_with_timeout(
            mt5, app_settings, symbol, start, end,
            args.is_months, args.oos_months, args.timeout,
        )
        all_results.append(r)
        _log_symbol_result(r)

    # ── Phase 2: Param Sensitivity ─────────────────────────────────────────
    print()
    print("── Phase 2: Param Sensitivity ──")

    param_results = None
    if args.quick:
        print("Running quick_sweep() (4 params, 2 periods, EUR/USD)...")
        param_results = quick_sweep(
            data_provider=mt5,
            settings={
                "initial_balance": trading.account_balance,
                "risk_percent": trading.default_risk_percent,
                "account_currency": trading.account_currency,
                "lot_step": trading.lot_step,
                "minimum_lot": trading.minimum_lot,
                "contract_size_override": trading.contract_size_override,
            },
            progress_callback=print,
        )
    else:
        print(f"Running sweep_params() ({len(DEFAULT_SWEEP_CONFIGS)} params, {len(DEFAULT_PERIODS)} periods, {len(DEFAULT_SYMBOLS)} symbols)...")
        param_results = sweep_params(
            list(DEFAULT_SWEEP_CONFIGS),
            list(DEFAULT_PERIODS),
            list(DEFAULT_SYMBOLS),
            progress_callback=print,
            data_provider=mt5,
            backtest_settings={
                "initial_balance": trading.account_balance,
                "risk_percent": trading.default_risk_percent,
                "account_currency": trading.account_currency,
                "lot_step": trading.lot_step,
                "minimum_lot": trading.minimum_lot,
                "contract_size_override": trading.contract_size_override,
            },
        )

    # ── Export ─────────────────────────────────────────────────────────────
    print()
    print("── Exporting reports ──")

    # baseline_summary.json
    json_data = _build_baseline_json(all_results, param_results, config)
    json_path = output_dir / "baseline_summary.json"
    json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  [OK] {json_path}")

    # baseline_report.md
    md_content = _build_markdown_report(all_results, config)
    md_path = output_dir / "baseline_report.md"
    md_path.write_text(md_content, encoding="utf-8")
    print(f"  [OK] {md_path}")

    # param_sensitivity_report.html (dùng export_results từ core)
    if param_results:
        html_path = export_results(param_results, output_dir=output_dir)
        print(f"  [OK] {html_path}")
    else:
        print(f"  [SKIP] Không có param sensitivity results.")

    # ── Final summary ──────────────────────────────────────────────────────
    valid = [r for r in all_results if not r.get("error")]
    errors = [r for r in all_results if r.get("error")]
    print()
    print(f"=== Done ===")
    print(f"  Symbols OK:    {len(valid)}")
    print(f"  Symbols ERROR: {len(errors)}")
    if errors:
        for r in errors:
            print(f"    - {r['symbol']}: {r['error']}")
    print(f"  Reports: {output_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
