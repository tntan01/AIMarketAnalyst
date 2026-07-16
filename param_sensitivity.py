"""Param Sensitivity Scanner — CLI entry point.

Measures how stable each ATR-multiplier constant is across different market
regimes by sweeping values and running system backtests.

Usage:
  python param_sensitivity.py --full          # Full sweep, all params, all periods
  python param_sensitivity.py --quick         # Quick sweep (4 params, 2 periods, 1 symbol)
  python param_sensitivity.py --param min_sl_distance_atr    # Single param
  python param_sensitivity.py --param zone_sl_buffer_atr --symbol XAU/USD
  python param_sensitivity.py --open          # Open last report after running

Requires: MT5 terminal running and logged in for historical data.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path
from typing import Any

# Force UTF-8 on Windows to avoid cp1258 encoding errors with Vietnamese text
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Project bootstrap
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.param_sensitivity import (
    DEFAULT_PERIODS,
    DEFAULT_SWEEP_CONFIGS,
    DEFAULT_SYMBOLS,
    SECONDARY_SWEEP_CONFIGS,
    MarketPeriod,
    ParamSweepConfig,
    SweepResult,
    export_results,
    quick_sweep,
    sweep_params,
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Param Sensitivity Scanner — đo độ ổn định của hằng số ATR",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--full", action="store_true",
        help="Chạy full sweep: tất cả tham số, tất cả periods, tất cả symbols",
    )
    mode.add_argument(
        "--quick", action="store_true",
        help="Chạy quick sweep: 4 tham số ưu tiên, 2 periods, 1 symbol (~5 phút)",
    )
    mode.add_argument(
        "--param", type=str, metavar="JSON_KEY",
        help="Chỉ sweep 1 tham số (dùng json_key, vd: min_sl_distance_atr)",
    )
    p.add_argument(
        "--symbol", type=str, metavar="SYMBOL",
        help="Chỉ sweep symbol này (vd: EUR/USD, XAU/USD). Mặc định: tất cả.",
    )
    p.add_argument(
        "--period", type=str, metavar="NAME",
        help="Chỉ sweep period này (khớp 1 phần tên). Mặc định: tất cả.",
    )
    p.add_argument(
        "--secondary", action="store_true",
        help="Bao gồm cả secondary params (mặc định chỉ sweep priority params).",
    )
    p.add_argument(
        "--open", action="store_true",
        help="Tự động mở báo cáo HTML sau khi chạy xong.",
    )
    p.add_argument(
        "--output-dir", type=str, metavar="DIR",
        help="Thư mục xuất kết quả. Mặc định: %%APPDATA%%/AIMarketAnalyst/param_tuning",
    )
    return p


def _resolve_data_provider():
    """Try to get a connected data provider (MT5)."""
    try:
        from services.mt5_service import MT5Service
        mt5 = MT5Service()
        status = mt5.connection_status()
        if status.connected and status.logged_in:
            return mt5
        print(f"[WARN] MT5 connected={status.connected} logged_in={status.logged_in}")
        return None
    except Exception as exc:
        print(f"[WARN] Không thể kết nối MT5: {exc}")
        return None


def _resolve_settings():
    """Load settings for backtest params like balance, risk%, etc."""
    try:
        from services.settings_service import SettingsService
        svc = SettingsService()
        s = svc.load()
        return {
            "initial_balance": s.trading.account_balance,
            "risk_percent": s.trading.default_risk_percent,
            "account_currency": s.trading.account_currency,
            "lot_step": s.trading.lot_step,
            "minimum_lot": s.trading.minimum_lot,
            "contract_size_override": s.trading.contract_size_override,
        }
    except Exception:
        return {
            "initial_balance": 10000,
            "risk_percent": 1.0,
            "account_currency": "USD",
            "lot_step": 0.01,
            "minimum_lot": 0.01,
            "contract_size_override": None,
        }


def _select_configs(args: argparse.Namespace) -> list[ParamSweepConfig]:
    """Determine which sweep configs to run based on CLI args."""
    if args.param:
        # Find matching config by json_key
        all_configs = DEFAULT_SWEEP_CONFIGS + SECONDARY_SWEEP_CONFIGS
        for cfg in all_configs:
            if cfg.json_key == args.param:
                return [cfg]
        print(f"Unknown param: {args.param}")
        print(f"Available: {[c.json_key for c in all_configs]}")
        sys.exit(1)

    configs = list(DEFAULT_SWEEP_CONFIGS)
    if args.secondary:
        configs += SECONDARY_SWEEP_CONFIGS
    return configs


def _select_periods(args: argparse.Namespace) -> list[MarketPeriod]:
    """Filter periods based on --period arg (partial name match)."""
    if args.period:
        return [p for p in DEFAULT_PERIODS if args.period.lower() in p.name.lower()]
    return list(DEFAULT_PERIODS)


def _select_symbols(args: argparse.Namespace) -> list[str]:
    """Filter symbols based on --symbol arg."""
    if args.symbol:
        return [args.symbol]
    return list(DEFAULT_SYMBOLS)


def _print_summary(results: list[SweepResult]) -> None:
    """Print a summary table to the terminal."""
    print(f"\n{'='*80}")
    print(f"{'Attribute':<35} {'Verdict':<14} {'Stability':>9}  Recommendation")
    print(f"{'-'*80}")
    for r in results:
        verdict = r.verdict
        score = f"{r.stability_score:.0f}" if r.stability_score is not None else "—"
        print(f"{r.attr_name:<35} {verdict:<14} {score:>9}  {r.recommendation or '—'}")
    print(f"{'='*80}")


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if not (args.full or args.quick or args.param):
        parser.print_help()
        print("\nVí dụ:")
        print("  python param_sensitivity.py --quick          # Quick sweep (~5 phút)")
        print("  python param_sensitivity.py --full           # Full sweep (~30-80 phút)")
        print("  python param_sensitivity.py --param min_sl_distance_atr")
        return 0

    # Resolve data
    provider = _resolve_data_provider()
    settings = _resolve_settings()

    if provider is None:
        print("[ERROR] Cần MT5 đang mở và đăng nhập để load dữ liệu lịch sử.")
        print("Mở MT5, đăng nhập, rồi chạy lại.")
        return 1

    configs = _select_configs(args)
    periods = _select_periods(args)
    symbols = _select_symbols(args)

    print(f"Param Sensitivity Scanner")
    print(f"  Params:  {len(configs)} ({', '.join(c.json_key for c in configs)})")
    print(f"  Periods: {len(periods)} ({', '.join(p.name for p in periods)})")
    print(f"  Symbols: {len(symbols)} ({', '.join(symbols)})")
    print(f"  Total runs: {len(configs) * len(periods) * len(symbols) * 5} (ước tính)")
    print()

    # Run
    t0 = __import__("time").time()

    if args.quick and not args.param:
        results = quick_sweep(
            data_provider=provider,
            settings=settings,
            progress_callback=print,
        )
    else:
        results = sweep_params(
            configs, periods, symbols,
            progress_callback=print,
            data_provider=provider,
            backtest_settings=settings,
        )

    elapsed = __import__("time").time() - t0

    # Export
    output_dir = args.output_dir or None
    report_path = export_results(results, output_dir=output_dir)
    print(f"\nHoàn thành trong {elapsed:.0f}s. Báo cáo: {report_path}")

    _print_summary(results)

    if args.open:
        webbrowser.open(str(report_path))

    return 0


if __name__ == "__main__":
    sys.exit(main())
