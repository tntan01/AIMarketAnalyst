"""Comprehensive backtest integration verification."""
from __future__ import annotations

import sys, traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_all():
    ok, fail = 0, 0

    def check(desc, condition):
        nonlocal ok, fail
        if condition:
            ok += 1
        else:
            fail += 1
            print(f"  FAIL: {desc}")

    # ================================================================
    # 1. Module imports
    # ================================================================
    print("[1] Module imports...")
    try:
        from core.system_backtest_engine import (
            BacktestRequest, trade_open_block_reason, should_open_trade,
            select_trade_scenario, build_fallback_scenario,
            BACKTEST_FUNNEL_KEYS,
        )
        check("system_backtest_engine", True)
    except Exception:
        check("system_backtest_engine", False)
        return

    try:
        from controllers.backtest_controller import BacktestController
        check("backtest_controller", True)
    except Exception:
        check("backtest_controller", False)

    try:
        from ui.screens.backtest_screen import BacktestScreen
        check("backtest_screen", True)
    except Exception:
        check("backtest_screen", False)

    try:
        from core.backtest_to_scanner_config import recommend_scanner_configs
        check("backtest_to_scanner_config", True)
    except Exception:
        check("backtest_to_scanner_config", False)

    try:
        from config.settings import SymbolScanSettings
        check("SymbolScanSettings", True)
    except Exception:
        check("SymbolScanSettings", False)

    # ================================================================
    # 2. BacktestRequest — no mode field
    # ================================================================
    print("[2] BacktestRequest defaults...")
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    req = BacktestRequest(symbol="EUR/USD", broker_symbol="EURUSD",
                          start=now, end=now,
                          initial_balance=10000, risk_percent=1.0)
    check("no 'mode' attr", not hasattr(req, "mode"))
    check("spread_price=0", req.spread_price == 0.0)
    check("min_final_score=0", req.min_final_score == 0)
    check("account_guard_enabled=False", req.account_guard_enabled is False)
    check("allow_macro=False", req.allow_macro is False)

    # ================================================================
    # 3. Funnel keys
    # ================================================================
    print("[3] Funnel keys...")
    check("fallback_scenario in funnel", "fallback_scenario" in BACKTEST_FUNNEL_KEYS)
    check("trade_opened in funnel", "trade_opened" in BACKTEST_FUNNEL_KEYS)
    check("no_trade_scenario in funnel", "no_trade_scenario" in BACKTEST_FUNNEL_KEYS)

    # ================================================================
    # 4. Controller layer
    # ================================================================
    print("[4] Controller layer...")
    from unittest.mock import MagicMock
    from services.settings_service import SettingsService

    svc = MagicMock(spec=SettingsService)
    mock_settings = MagicMock()
    mock_settings.trading.account_currency = "USD"
    mock_settings.trading.lot_step = 0.01
    mock_settings.trading.minimum_lot = 0.01
    mock_settings.trading.contract_size_override = {}
    mock_settings.trading.symbol_settings = {}
    mock_settings.trading.enabled_symbols = []
    mock_settings.display.timezone = "Asia/Ho_Chi_Minh"
    svc.load.return_value = mock_settings
    dp = MagicMock()
    dp.available_symbols.return_value = ["EURUSD"]
    dp.resolve_symbol.return_value = "EURUSD"
    dp.symbol_data_quality.return_value = {}

    ctrl = BacktestController(settings_service=svc, data_provider=dp)
    reqs = ctrl.build_requests(symbols=["EUR/USD"], start=now, end=now,
                               initial_balance=10000, risk_percent=1.0)
    check("build_requests returns 1", len(reqs) == 1)
    check("symbol correct", reqs[0].symbol == "EUR/USD")

    req = ctrl.build_request(symbol="EUR/USD", start=now, end=now,
                             initial_balance=10000, risk_percent=1.0)
    check("build_request is BacktestRequest", isinstance(req, BacktestRequest))

    # ================================================================
    # 5. Fallback scenario
    # ================================================================
    print("[5] Fallback scenario...")

    class FC:
        def __init__(self, close):
            self.close = close; self.open = close; self.high = close; self.low = close

    # Buy
    a = {"decision_summary": {"best_side": "buy", "best_score": 55},
         "technical": {"atr_h4": 0.0050},
         "market_regime": {"primary": "trend_up"}}
    s = build_fallback_scenario(a, FC(1.0800))
    check("buy scenario not None", s is not None)
    if s:
        check("buy: type=buy", s["type"] == "buy")
        check("buy: _fallback=True", s["_fallback"] is True)
        check("buy: entry_status=watch_zone", s["entry_status"] == "watch_zone")
        check("buy: SL below price", s["stop_loss"] < 1.0800)
        check("buy: TP above price", s["take_profit"][0] > 1.0800)
        risk = 1.0800 - s["stop_loss"]
        reward = s["take_profit"][0] - 1.0800
        check("buy: RR ratio ~1:2", 1.5 < reward / risk < 3.5)

    # Sell
    a["decision_summary"]["best_side"] = "sell"
    s = build_fallback_scenario(a, FC(1.0800))
    check("sell scenario not None", s is not None)
    if s:
        check("sell: SL above price", s["stop_loss"] > 1.0800)
        check("sell: TP below price", s["take_profit"][0] < 1.0800)

    # Neutral → None
    a["decision_summary"]["best_side"] = "neutral"
    check("neutral returns None", build_fallback_scenario(a, FC(1.0800)) is None)

    # No ATR
    a["decision_summary"]["best_side"] = "buy"
    a["technical"] = {}
    s = build_fallback_scenario(a, FC(1.0800))
    check("no-ATR fallback works", s is not None and s["stop_loss"] < 1.0800)

    # Invalid candle
    check("None candle → None", build_fallback_scenario(a, None) is None)
    check("bad candle → None", build_fallback_scenario(a, "bad") is None)

    # ================================================================
    # 6. Standard gate + fallback
    # ================================================================
    print("[6] Standard gate filter + fallback...")
    a_full = {
        "decision_summary": {"best_side": "buy", "best_score": 62},
        "technical": {"atr_h4": 0.0050},
        "market_regime": {"primary": "range"},
        "trade_gate": {"allowed": True},
        "trade_permission": {"status": "caution"},
        "decision_engine": {"decision": "AGGRESSIVE_SETUP"},
        "final_score": 62,
    }
    s = build_fallback_scenario(a_full, FC(1.0800))
    check("passes Standard gate", trade_open_block_reason(a_full, s) is None)
    check("blocked by min_score=65",
          trade_open_block_reason(a_full, s, min_final_score=65) == "blocked_by_score")
    check("passes min_score=50",
          trade_open_block_reason(a_full, s, min_final_score=50) is None)

    a_full["trade_gate"]["allowed"] = False
    check("blocked by gate",
          trade_open_block_reason(a_full, s) == "blocked_by_trade_gate")

    a_full["trade_gate"]["allowed"] = True
    a_full["trade_permission"]["status"] = "denied"
    check("blocked by permission",
          trade_open_block_reason(a_full, s) == "blocked_by_permission")

    a_full["trade_permission"]["status"] = "allowed"
    a_full["decision_engine"]["decision"] = "STAND_ASIDE"
    check("blocked by decision",
          trade_open_block_reason(a_full, s) == "blocked_by_decision")

    # ================================================================
    # 7. Trade simulation
    # ================================================================
    print("[7] Trade simulation...")
    from core.system_backtest_engine import simulate_trade_from_analysis

    a_full["decision_engine"]["decision"] = "AGGRESSIVE_SETUP"
    a_full["trade_permission"]["status"] = "caution"
    s = build_fallback_scenario(a_full, FC(1.0800))

    base = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    future = []
    for i in range(20):
        fc = FC(1.0790 + i * 0.0010)
        fc.time = base + timedelta(minutes=15 * i)
        future.append(fc)

    breq = BacktestRequest(
        symbol="EUR/USD", broker_symbol="EURUSD",
        start=base - timedelta(days=1), end=base + timedelta(days=1),
        initial_balance=10000, risk_percent=1.0,
        setup_expiry_bars=50, max_holding_bars=100,
    )

    from core.system_backtest_engine import find_entry_fill
    entry = find_entry_fill(side="buy", scenario=s,
                            future_candles=future,
                            setup_expiry_bars=50, request=breq)
    check("entry fill found", entry is not None)
    if entry:
        _fc, ep, _fi = entry
        check(f"entry price near zone ({ep:.5f})", 1.0780 < ep < 1.0815)

    trade = simulate_trade_from_analysis(
        request=breq, analysis=a_full, scenario=s,
        entry_candle=FC(1.0800), future_candles=future,
    )
    check("trade simulated", trade is not None)
    if trade:
        check("trade has expected_effective_rr", hasattr(trade, "expected_effective_rr"))

    # ================================================================
    # 8. recommend_scanner_configs
    # ================================================================
    print("[8] recommend_scanner_configs...")
    trades = []
    for i in range(15):
        trades.append({
            "symbol": "EUR/USD", "side": "buy",
            "market_regime": "trend_up",
            "signal_score": 70 + i, "final_score": 65 + i,
            "expected_effective_rr": 1.5 + (i % 3) * 0.3,
            "result": "win" if i % 2 == 0 else "loss",
            "result_r": 1.5 if i % 2 == 0 else -1.0,
        })

    recs = recommend_scanner_configs({"trades": trades, "summary": {}})
    check("EUR/USD in recs", "EUR/USD" in recs)
    cfg = recs.get("EUR/USD")
    check("cfg not None", cfg is not None)
    if cfg:
        check("has regime", "regime" in cfg)
        check("has side", "side" in cfg)
        check("has min_score", "min_score" in cfg)
        check("has min_rr", "min_rr" in cfg)
        check("has _evidence", "_evidence" in cfg)

    # ================================================================
    # 9. Field mapping backtest -> SymbolScanSettings
    # ================================================================
    print("[9] Field mapping...")
    ss = SymbolScanSettings()
    ss.backtest = True
    if cfg:
        ss.auto_trade_regime = cfg["regime"]
        ss.auto_trade_side = cfg["side"]
        ss.min_score = int(cfg["min_score"])
        ss.min_expected_rr = float(cfg["min_rr"])
        check("backtest=True", ss.backtest is True)
        check("regime mapped", ss.auto_trade_regime == cfg["regime"])
        check("side mapped", ss.auto_trade_side == cfg["side"])

    # ================================================================
    # 10. UI Widget creation
    # ================================================================
    print("[10] UI widget creation...")
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    screen = BacktestScreen(app=None)

    cols = [label for _, label in screen.TRADE_COLUMNS]
    check("8 columns", len(cols) == 8)
    check("correct columns",
          cols == ["STT", "Thời gian vào", "Hướng", "Kết quả", "R",
                    "Điểm", "Regime", "RR kỳ vọng"])

    for attr in ["run_button", "apply_config_btn", "progress", "status_label",
                 "symbol_summary", "symbol_button", "start_date", "end_date",
                 "balance_input", "risk_input", "table"]:
        check(f"has {attr}", hasattr(screen, attr))

    for attr in ["mode_combo", "spread_input", "slippage_input", "max_holding_input",
                 "min_score_input", "guard_checkbox", "macro_checkbox", "recommend_btn",
                 "help_button"]:
        check(f"no {attr}", not hasattr(screen, attr))

    check("apply button hidden", screen.apply_config_btn.isHidden())

    # Verify stretch is configured
    header = screen.table.horizontalHeader()
    check("stretch last section", header.stretchLastSection())

    screen.deleteLater()
    app.quit()

    # ================================================================
    # Summary
    # ================================================================
    print()
    total = ok + fail
    print("=" * 60)
    print(f"RESULTS: {ok}/{total} passed, {fail} failed")
    print("=" * 60)
    return fail == 0


if __name__ == "__main__":
    success = test_all()
    sys.exit(0 if success else 1)
