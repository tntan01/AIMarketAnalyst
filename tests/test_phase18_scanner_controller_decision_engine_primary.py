"""Phase 18 — test that ScannerController.run_market_scan
passes use_decision_engine_action=True to analyze_symbol.

These tests currently FAIL because the controller does not yet pass the flag.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.settings_service import SettingsService
from services.telegram_alert_service import TelegramAlertResult
from core.scanner import ScannerRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_analyze_symbol(captured_kwargs_list: list[dict]):
    """Return a fake analyze_symbol that captures **kwargs and returns a valid
    analysis result suitable for scanner_row_from_analysis."""

    def fake_analyze_symbol(request, candles, **kwargs):
        captured_kwargs_list.append(dict(kwargs))

        return {
            "symbol": request.symbol,
            "data_quality": kwargs.get("data_quality") or {
                "broker_symbol": request.broker_symbol,
                "terminal_connected": True,
                "broker_logged_in": True,
                "spread_status": "normal",
            },
            "technical": {"price": 1.1000, "atr_h4": 0.0020, "atr_d1": 0.0030},
            "market_regime": {"primary": "trend_up"},
            "direction_bias": {"best_side": "buy", "score_gap": 20},
            "trade_permission": {"status": "allowed", "reason": "ok"},
            "scenario_scores": {
                "buy": {
                    "signal_score": 86, "total": 86, "smc_quality": 12,
                    "macro_alignment": 15, "macro_confidence": 1.0,
                },
                "sell": {
                    "signal_score": 40, "total": 40, "smc_quality": 2,
                    "macro_alignment": 15, "macro_confidence": 1.0,
                },
            },
            "decision_summary": {
                "action": "ready", "best_scenario": "buy", "best_score": 86,
                "score_gap": 20,
            },
            "decision_engine": {
                "decision": "READY_TO_TRADE", "legacy_action": "ready",
            },
            "final_score": 84,
            "scenarios": [{
                "type": "buy",
                "entry_status": "confirmed_entry",
                "entry_zone": [1.0990, 1.1010],
                "risk_reward": "1:2.0",
                "expected_effective_rr": 1.8,
                "ready_to_trade": True,
                "price_in_entry_zone": True,
                "h1_confirmation": True,
                "position_sizing": {"suggested_lot": 0.1},
            }],
            "macro": {"ai_summary": ""},
        }

    return fake_analyze_symbol


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_scanner_controller_enables_decision_engine_action(tmp_path, monkeypatch):
    """ScannerController.run_market_scan must call analyze_symbol
    with use_decision_engine_action=True."""
    from controllers.scanner_controller import ScannerController
    from services.mt5_service import MT5Service, MT5ConnectionStatus
    from services.news_service import NewsService

    # --- Fake MT5 connection status ---
    fake_status = MT5ConnectionStatus(
        initialized=True,
        terminal_connected=True,
        logged_in=True,
        trade_allowed=True,
    )

    # --- Fake MT5Service ---
    fake_mt5 = MagicMock(spec=MT5Service)
    fake_mt5.connection_status.return_value = fake_status
    fake_mt5.account_balance.return_value = 12345.67
    fake_mt5.available_symbols.return_value = ["EURUSD", "GBPUSD", "XAUUSD"]
    fake_mt5.resolve_symbol.return_value = "EURUSD"
    fake_mt5.load_primary_timeframes.return_value = {
        "D1": [], "H4": [], "H1": [], "M15": [],
    }
    fake_mt5.symbol_data_quality.return_value = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "broker_symbol": "EURUSD",
        "spread_status": "normal",
        "spread_points": 1.2,
    }
    fake_mt5.quote_to_usd_rate.return_value = 1.0

    # --- Fake NewsService ---
    fake_news = MagicMock(spec=NewsService)
    fake_news.preload_macro_contexts.return_value = None
    fake_news.data_quality_flags.return_value = {
        "macro_context": {
            "events": [],
            "macro_alignment_scores": {"buy": 15, "sell": 15},
            "macro_data_quality": 1.0,
        },
    }

    # --- Fake TelegramService ---
    fake_telegram = SimpleNamespace()
    fake_telegram.send_ready_trade_alerts = MagicMock(
        return_value=TelegramAlertResult(attempted=0, sent=0, errors=[])
    )
    fake_telegram.send_summary_alert = MagicMock(return_value=0)

    # --- Settings ---
    settings_service = SettingsService(tmp_path / "settings.json")

    # --- Build controller ---
    controller = ScannerController(
        settings_service=settings_service,
        mt5_service=fake_mt5,
        news_service=fake_news,
        telegram_service=fake_telegram,
    )

    # --- Patch yfinance to avoid network calls ---
    monkeypatch.setattr(
        "controllers.scanner_controller.yf.download",
        lambda *a, **kw: pd.DataFrame(),
    )

    # --- Patch analyze_symbol ---
    captured_kwargs_list: list[dict] = []
    monkeypatch.setattr(
        "controllers.scanner_controller.analyze_symbol",
        _make_fake_analyze_symbol(captured_kwargs_list),
    )

    # --- Run ---
    result = controller.run_market_scan(
        request=ScannerRequest(
            symbols=["EUR/USD"],
            account_balance=10_000,
            risk_percent=1,
            timezone_name="Asia/Ho_Chi_Minh",
            max_ai_details=0,
        ),
    )

    # --- Assert: flag was passed ---
    assert len(captured_kwargs_list) == 1, (
        f"Expected exactly 1 call to analyze_symbol, got {len(captured_kwargs_list)}"
    )
    call_kwargs = captured_kwargs_list[0]
    assert call_kwargs.get("use_decision_engine_action") is True, (
        f"Expected use_decision_engine_action=True, "
        f"got {call_kwargs.get('use_decision_engine_action')!r}. "
        f"ScannerController must opt in to decision engine as primary decision source."
    )

    # --- Assert: scanner row has correct decision ---
    rows = result["rows"]
    assert len(rows) == 1
    assert rows[0]["scanner_decision"] == "READY_TO_TRADE", (
        f"Expected scanner_decision=READY_TO_TRADE, got {rows[0]['scanner_decision']}"
    )
