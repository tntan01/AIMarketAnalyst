from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEventLoop, QThread, QTimer
from PyQt6.QtWidgets import QApplication, QHeaderView, QTableView

import pandas as pd

from controllers.scanner_controller import ScannerController
import controllers.scanner_controller as scanner_controller_module
from core.market_models import Candle
from core.scanner import ScannerRequest, classify_scanner_action, price_vs_entry_zone, sort_scanner_rows
from config.settings import AISettings, AppSettings, NotificationSettings
from services.mt5_service import MT5ConnectionStatus
from services.settings_service import SettingsService
from services.telegram_alert_service import TelegramAlertResult
from ui.screens.scanner_screen import ScannerScreen, ScannerTableModel
from workers.scanner_worker import ScannerWorker


def _candles(count: int, start: float, step: float, amplitude: float) -> list[Candle]:
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows: list[Candle] = []
    for index in range(count):
        wave = amplitude * ((index % 10) - 5) / 5
        close = start + index * step + wave
        open_price = close - step * 0.2
        rows.append(
            Candle(
                time=base_time + timedelta(hours=index),
                open=open_price,
                high=max(open_price, close) + amplitude * 0.8,
                low=min(open_price, close) - amplitude * 0.8,
                close=close,
                volume=100,
            )
        )
    return rows


class _FakeMT5Service:
    def connection_status(self):
        return MT5ConnectionStatus(True, True, True, True)

    def account_balance(self):
        return 12_345.67

    def available_symbols(self, market_watch_only: bool = True):
        return ["EURUSD.r", "GBPUSD.r"]

    def configured_symbols_in_market_watch(self):
        return [("EUR/USD", "EURUSD.r"), ("GBP/USD", "GBPUSD.r")]

    def resolve_symbol(self, app_symbol: str, available_symbols: list[str]):
        return {"EUR/USD": "EURUSD.r", "GBP/USD": "GBPUSD.r"}.get(app_symbol)

    def load_ohlcv(self, broker_symbol: str, timeframe: str, bars: int):
        if broker_symbol == "GBPUSD.r":
            raise RuntimeError("Không lấy được OHLCV")
        counts = {"D1": 240, "H4": 240, "H1": 120, "M15": 200}
        return _candles(counts[timeframe], 1.05, 0.0004, 0.002)

    def load_primary_timeframes(self, broker_symbol: str, bars_by_timeframe: dict[str, int]):
        if broker_symbol == "GBPUSD.r":
            raise RuntimeError("Không lấy được OHLCV")
        return {
            tf: _candles(bars, 1.05, 0.0004, 0.002)
            for tf, bars in bars_by_timeframe.items()
        }

    def symbol_data_quality(self, display_symbol: str, broker_symbol: str):
        return {
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "broker_symbol": broker_symbol,
            "contract_size": 100000,
        }


class _FakeTelegramService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def send_ready_trade_alerts(self, rows, *, bot_token: str, chat_ids: list[str]):
        self.calls.append({"rows": rows, "bot_token": bot_token, "chat_ids": chat_ids})
        return TelegramAlertResult(attempted=1, sent=1, errors=[])

    def send_summary_alert(self, rows, *, bot_token: str, chat_ids: list[str], timestamp: str):
        return 0


class _FakeNewsService:
    def preload_macro_contexts(self, symbols): pass
    def data_quality_flags(self, symbol, include_latest_statements=True):
        return {
            "macro_context": {
                "events": [],
                "macro_alignment_scores": {"buy": 15, "sell": 15},
                "macro_data_quality": 1.0,
            },
        }
    def macro_freshness_status(self):
        return {"confidence_multiplier": 1.0}


def test_scanner_action_and_sorting_follow_document_priority() -> None:
    assert classify_scanner_action(best_score=82, permission="allowed", has_trade_plan=True, h1_confirmation=True) == "ready"
    assert classify_scanner_action(best_score=76, permission="caution", has_trade_plan=False) == "watch"
    assert classify_scanner_action(best_score=65, permission="allowed", has_trade_plan=False) == "wait"
    assert classify_scanner_action(best_score=82, permission="blocked", has_trade_plan=True) == "skip"

    rows = sort_scanner_rows(
        [
            {"symbol": "C", "scanner_action": "skip", "trade_permission": "blocked", "best_score": 90},
            {"symbol": "B", "scanner_action": "watch", "trade_permission": "caution", "best_score": 95},
            {"symbol": "A", "scanner_action": "ready", "trade_permission": "allowed", "best_score": 80},
        ]
    )
    assert [row["symbol"] for row in rows] == ["A", "B", "C"]
    assert [row["rank"] for row in rows] == [1, 2, 3]


def test_price_vs_entry_zone_classifies_current_price_location() -> None:
    assert price_vs_entry_zone(101, [100, 102], 10) == "in_zone"
    assert price_vs_entry_zone(106, [100, 102], 10) == "near_zone"
    assert price_vs_entry_zone(108, [100, 102], 10) == "far"


def test_scanner_controller_runs_rule_engine_without_ai_for_all_symbols(tmp_path) -> None:
    controller = ScannerController(SettingsService(tmp_path / "settings.json"), _FakeMT5Service())
    result = controller.run_market_scan(
        request=ScannerRequest(
            symbols=["EUR/USD", "GBP/USD", "USD/JPY"],
            account_balance=10_000,
            risk_percent=1,
            timezone_name="Asia/Ho_Chi_Minh",
            max_ai_details=3,
        )
    )

    assert result["mode"] == "scanner"
    assert result["symbols_scanned"] == 3
    assert result["ai_called"] == 0
    assert len(result["rows"]) == 3
    assert result["rows"][0]["rank"] == 1
    assert any(row["symbol"] == "USD/JPY" and row["trade_permission"] == "blocked" for row in result["rows"])


def test_scanner_controller_uses_mt5_balance_for_analysis_input(tmp_path, monkeypatch) -> None:
    import sys as _sys

    captured_balances: list[float] = []

    def fake_analyze_symbol(request, candles, *, data_quality=None, macro_alignment=None, macro_confidence=1.0, ai_meta=None, ai_commentary=None, m15_candles=None, **kwargs):
        captured_balances.append(request.account_balance)
        return {
            "symbol": request.symbol,
            "data_quality": data_quality or {},
            "market_regime": {"primary": "trend_up"},
            "direction_bias": "buy",
            "trade_permission": {"status": "allowed", "reason": "ok"},
            "scenario_scores": {"buy": {"total": 80, "smc_quality": 9}, "sell": {"total": 40, "smc_quality": 2}},
            "decision_summary": {"action": "ready", "best_scenario": "buy", "best_score": 80},
            "scenarios": [{"type": "buy", "risk_reward": "1:2.0", "position_sizing": {"account_balance": request.account_balance}}],
            "macro": {"ai_summary": ""},
        }

    ctrl_mod = _sys.modules["controllers.scanner_controller"]
    _orig_analyze = ctrl_mod.analyze_symbol
    _orig_yf_download = ctrl_mod.yf.download
    ctrl_mod.analyze_symbol = fake_analyze_symbol
    ctrl_mod.yf.download = lambda *a, **kw: pd.DataFrame()
    try:
        controller = ScannerController(SettingsService(tmp_path / "settings.json"), _FakeMT5Service(), news_service=_FakeNewsService())
        controller.run_market_scan(
            request=ScannerRequest(
                symbols=["EUR/USD"],
                account_balance=10_000,
                risk_percent=1,
                timezone_name="Asia/Ho_Chi_Minh",
                max_ai_details=0,
            )
        )

        assert captured_balances == [12_345.67]
    finally:
        ctrl_mod.analyze_symbol = _orig_analyze
        ctrl_mod.yf.download = _orig_yf_download


def test_scanner_controller_sends_telegram_alert_for_ready_trade(tmp_path, monkeypatch) -> None:
    import sys as _sys

    settings_service = SettingsService(tmp_path / "settings.json")
    settings_service.save(
        AppSettings(
            ai=AISettings(),
            notifications=NotificationSettings(
                telegram_bot_token="bot-token",
                telegram_chat_ids=["100"],
                auto_scan_interval_minutes=5,
            ),
        )
    )
    telegram = _FakeTelegramService()

    def fake_analyze_symbol(request, candles, *, data_quality=None, macro_alignment=None, macro_confidence=1.0, ai_meta=None, ai_commentary=None, m15_candles=None, **kwargs):
        return {
            "symbol": request.symbol,
            "data_quality": data_quality or {},
            "technical": {"price": 1.1, "atr_h4": 0.01},
            "market_regime": {"primary": "trend_up"},
            "direction_bias": "buy",
            "trade_permission": {"status": "allowed", "reason": "ok"},
            "scenario_scores": {"buy": {"total": 86, "smc_quality": 12}, "sell": {"total": 40, "smc_quality": 2}},
            "decision_summary": {"action": "ready", "best_scenario": "buy", "best_score": 86},
            "scenarios": [
                {
                    "type": "buy",
                    "entry_zone": [1.095, 1.105],
                    "stop_loss": 1.09,
                    "take_profit": [1.12],
                    "risk_reward": "1:2.0",
                    "ready_to_trade": True,
                    "price_in_entry_zone": True,
                    "h1_confirmation": True,
                    "position_sizing": {"suggested_lot": 0.1, "account_balance": request.account_balance},
                }
            ],
            "macro": {"ai_summary": ""},
        }

    ctrl_mod = _sys.modules["controllers.scanner_controller"]
    _orig_analyze = ctrl_mod.analyze_symbol
    _orig_yf_download = ctrl_mod.yf.download
    ctrl_mod.analyze_symbol = fake_analyze_symbol
    ctrl_mod.yf.download = lambda *a, **kw: pd.DataFrame()
    try:
        controller = ScannerController(settings_service, _FakeMT5Service(), telegram_service=telegram, news_service=_FakeNewsService())

        result = controller.run_market_scan(
            request=ScannerRequest(["EUR/USD"], 10_000, 1, "Asia/Ho_Chi_Minh", max_ai_details=0)
        )

        assert result["telegram_alerts"]["sent"] == 1
        assert telegram.calls[0]["bot_token"] == "bot-token"
        assert telegram.calls[0]["chat_ids"] == ["100"]
        assert telegram.calls[0]["rows"][0]["scanner_action"] == "ready"
    finally:
        ctrl_mod.analyze_symbol = _orig_analyze
        ctrl_mod.yf.download = _orig_yf_download


def test_scanner_worker_emits_progress_and_keeps_qthread_alive(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    controller = ScannerController(SettingsService(tmp_path / "settings.json"), _FakeMT5Service())
    thread, worker = controller.create_scan_worker(
        ScannerRequest(["EUR/USD"], 10_000, 1, "Asia/Ho_Chi_Minh", max_ai_details=0)
    )

    progress: list[int] = []
    results: list[dict[str, object]] = []
    worker.progress.connect(lambda percent, _message: progress.append(percent))
    worker.succeeded.connect(results.append)
    thread.start()

    loop = QEventLoop()
    thread.finished.connect(loop.quit)
    QTimer.singleShot(3000, loop.quit)
    loop.exec()
    app.processEvents()

    assert isinstance(worker, ScannerWorker)
    assert isinstance(thread, QThread)
    assert results
    assert progress[-1] == 100


def test_scanner_screen_uses_table_view_model() -> None:
    app = QApplication.instance() or QApplication([])
    screen = ScannerScreen()

    assert isinstance(screen.table, QTableView)
    assert isinstance(screen.table_model, ScannerTableModel)
    assert "price_vs_zone" in [key for key, _label in ScannerTableModel.COLUMNS]
    reason_column = [key for key, _label in ScannerTableModel.COLUMNS].index("short_reason")
    assert screen.table.horizontalHeader().sectionResizeMode(reason_column) == QHeaderView.ResizeMode.Interactive
    assert len(screen.symbol_boxes) == 29
    assert screen.scan_mode_combo.currentData() == "once"
    assert screen.scan_interval_combo.findData(300) >= 0
    assert screen.stop_auto_scan_button.text() == "Dừng quét tự động"


def test_scanner_screen_enables_only_market_watch_symbols() -> None:
    app = QApplication.instance() or QApplication([])
    screen = ScannerScreen()
    screen.mt5_service = _FakeMT5Service()
    screen.refresh_status()

    enabled = {box.text() for box in screen.symbol_boxes if box.isEnabled()}
    checked = {box.text() for box in screen.symbol_boxes if box.isChecked()}

    assert enabled == {"EUR/USD", "GBP/USD"}
    assert checked == {"EUR/USD", "GBP/USD"}

    usd_jpy = next(box for box in screen.symbol_boxes if box.text() == "USD/JPY")
    assert not usd_jpy.isEnabled()
    assert not usd_jpy.isChecked()
