from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd

from controllers.scanner_controller import ScannerController
from core.scanner import ScannerRequest
from services.mt5_service import MT5ConnectionStatus, MT5OrderResult, MT5Service
from services.news_service import NewsService
from services.settings_service import SettingsService
from services.telegram_alert_service import TelegramAlertResult


def _analysis_result(request, _candles, **_kwargs):
    return {
        "symbol": request.symbol,
        "data_quality": {"broker_symbol": request.broker_symbol},
        "technical": {"price": 1.1000, "atr_h4": 0.0020, "atr_d1": 0.0030},
        "market_regime": {"primary": "trend_up"},
        "direction_bias": "buy",
        "trade_permission": {"status": "allowed", "reason": "ok"},
        "scenario_scores": {
            "buy": {"signal_score": 86, "total": 86, "smc_quality": 12, "macro_alignment": 15, "macro_confidence": 1.0},
            "sell": {"signal_score": 40, "total": 40, "smc_quality": 2, "macro_alignment": 15, "macro_confidence": 1.0},
        },
        "decision_summary": {"action": "ready", "best_scenario": "buy", "best_score": 86, "score_gap": 20},
        "decision_engine": {"decision": "READY_TO_TRADE", "legacy_action": "ready"},
        "final_score": 84,
        "scenarios": [
            {
                "type": "buy",
                "entry_status": "confirmed_entry",
                "entry_zone": [1.0990, 1.1010],
                "stop_loss": 1.0950,
                "take_profit": [1.1120, 1.1200],
                "risk_reward": "1:2.0",
                "expected_effective_rr": 1.8,
                "ready_to_trade": True,
                "price_in_entry_zone": True,
                "h1_confirmation": True,
                "position_sizing": {"suggested_lot": 0.12, "risk_pct": request.risk_percent},
            }
        ],
        "macro": {"ai_summary": ""},
    }


def _controller(tmp_path, fake_mt5):
    fake_news = MagicMock(spec=NewsService)
    fake_news.preload_macro_contexts.return_value = None
    fake_news.data_quality_flags.return_value = {
        "macro_context": {
            "events": [],
            "macro_alignment_scores": {"buy": 15, "sell": 15},
            "macro_data_quality": 1.0,
        },
    }
    fake_telegram = SimpleNamespace()
    fake_telegram.send_ready_trade_alerts = MagicMock(return_value=TelegramAlertResult(0, 0, []))
    fake_telegram.send_summary_alert = MagicMock(return_value=0)
    return ScannerController(
        settings_service=SettingsService(tmp_path / "settings.json"),
        mt5_service=fake_mt5,
        news_service=fake_news,
        telegram_service=fake_telegram,
    )


def _fake_mt5():
    fake_mt5 = MagicMock(spec=MT5Service)
    fake_mt5.connection_status.return_value = MT5ConnectionStatus(True, True, True, True)
    fake_mt5.account_balance.return_value = 10_000.0
    fake_mt5.available_symbols.return_value = ["EURUSD"]
    fake_mt5.resolve_symbol.return_value = "EURUSD"
    fake_mt5.load_primary_timeframes.return_value = {"D1": [], "H4": [], "H1": [], "M15": []}
    fake_mt5.symbol_data_quality.return_value = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "broker_symbol": "EURUSD",
        "spread_status": "normal",
    }
    fake_mt5.quote_to_usd_rate.return_value = 1.0
    return fake_mt5


def test_auto_scan_places_one_ready_order(monkeypatch, tmp_path):
    fake_mt5 = _fake_mt5()
    fake_mt5.has_open_position_or_order.return_value = False
    fake_mt5.place_market_order.return_value = MT5OrderResult(
        True, "EUR/USD", "EURUSD", "buy", 0.12, price=1.1, stop_loss=1.095, take_profit=1.112, order_id=123
    )
    monkeypatch.setattr("controllers.scanner_controller.yf.download", lambda *a, **kw: pd.DataFrame())
    monkeypatch.setattr("controllers.scanner_controller.analyze_symbol", _analysis_result)

    result = _controller(tmp_path, fake_mt5).run_market_scan(
        request=ScannerRequest(["EUR/USD"], 10_000, 1.0, "Asia/Ho_Chi_Minh", max_ai_details=0, auto_trade_enabled=True)
    )

    fake_mt5.place_market_order.assert_called_once_with(
        symbol="EUR/USD",
        broker_symbol="EURUSD",
        side="buy",
        volume=0.12,
        stop_loss=1.095,
        take_profit=1.112,
        comment="AMA EUR/USD",
    )
    assert result["auto_trade_results"]["opened"] == 1
    assert result["auto_trade_results"]["risk_percent"] == 1.0


def test_auto_scan_skips_symbol_with_existing_order(monkeypatch, tmp_path):
    fake_mt5 = _fake_mt5()
    fake_mt5.has_open_position_or_order.return_value = True
    monkeypatch.setattr("controllers.scanner_controller.yf.download", lambda *a, **kw: pd.DataFrame())
    monkeypatch.setattr("controllers.scanner_controller.analyze_symbol", _analysis_result)

    result = _controller(tmp_path, fake_mt5).run_market_scan(
        request=ScannerRequest(["EUR/USD"], 10_000, 1.0, "Asia/Ho_Chi_Minh", max_ai_details=0, auto_trade_enabled=True)
    )

    fake_mt5.place_market_order.assert_not_called()
    assert result["auto_trade_results"]["opened"] == 0
    assert result["auto_trade_results"]["skipped"] == 1
