"""Phase 18 — test that AnalysisController.run_single_analysis
passes use_decision_engine_action=True to analyze_symbol.

These tests currently FAIL because the controller does not yet pass the flag.
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.market_models import Candle
from services.settings_service import SettingsService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_candles(count: int = 100) -> list[Candle]:
    """Return a list of synthetic Candle objects for D1/H4/H1/M15."""
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows: list[Candle] = []
    for i in range(count):
        close = 1.1000 + i * 0.0001
        rows.append(Candle(
            time=base_time + timedelta(hours=i),
            open=close - 0.00005,
            high=close + 0.00010,
            low=close - 0.00010,
            close=close,
            volume=100,
        ))
    return rows


def _fake_news_data_quality_flags(_symbol: str) -> dict:
    return {
        "macro_context": {
            "events": [],
            "macro_alignment_scores": {"buy": 15, "sell": 15},
            "macro_data_quality": 1.0,
            "latest_headlines": [],
            "latest_statements": [],
        },
    }


def _fake_macro_freshness_status() -> dict:
    return {"confidence_multiplier": 1.0}


def _make_fake_analyze_symbol(captured_kwargs: list[dict]):
    """Return a fake analyze_symbol that captures kwargs and returns a valid result."""

    def fake_analyze_symbol(request, candles_by_timeframe, **kwargs):
        captured_kwargs.append(dict(kwargs))

        best_side = "buy"
        best_score = 62
        return {
            "symbol": request.symbol,
            "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "data_quality": {
                "terminal_connected": True,
                "broker_logged_in": True,
                "spread_status": "normal",
                "broker_symbol": request.broker_symbol or "EURUSD",
            },
            "market_regime": {"primary": "range"},
            "direction_bias": {
                "best_side": best_side,
                "buy_score": 57,
                "sell_score": 43,
                "score_gap": 14,
                "is_clear_bias": True,
                "min_gap": 10,
            },
            "trade_permission": {"status": "caution", "reason": "Expected RR thap"},
            "decision_summary": {
                "main_view": f"{request.symbol}: uu tien {best_side.upper()} co dieu kien",
                "action": "watch",
                "best_scenario": best_side,
                "best_score": best_score,
                "best_side": best_side,
                "score_gap": 14,
                "is_clear_bias": True,
                "min_score_gap": 10,
                "gate_decision_cap": None,
                "gate_allowed": True,
                "gate_block_codes": [],
                "gate_warning_codes": [],
                "account_guard_blocked": False,
                "account_guard_block_codes": [],
                "decision_engine_enabled": kwargs.get("use_decision_engine_action", False),
                "decision_engine_decision": "WATCH_ONLY",
            },
            "decision_engine": {
                "decision": "WATCH_ONLY",
                "final_score": 62,
                "decision_label": "Chi theo doi",
                "legacy_action": "watch",
                "reason_codes": ["DECISION_WATCH_ONLY"],
                "warning_codes": [],
                "block_codes": [],
                "decision_cap": None,
                "allowed": True,
                "score_breakdown": {},
                "reason": "Score in watch range.",
            },
            "scenario_scores": {
                "buy": {
                    "signal_score": 57, "total": 57,
                    "macro_alignment": 15, "macro_confidence": 1.0, "smc_quality": 8,
                    "trend_alignment": 10, "momentum_alignment": 8, "location_quality": 12,
                    "risk_condition": 8, "reason_codes": [], "penalty_codes": [],
                },
                "sell": {
                    "signal_score": 43, "total": 43,
                    "macro_alignment": 15, "macro_confidence": 1.0, "smc_quality": 4,
                    "trend_alignment": 6, "momentum_alignment": 5, "location_quality": 8,
                    "risk_condition": 8, "reason_codes": [], "penalty_codes": [],
                },
            },
            "trade_gate": {
                "allowed": True,
                "decision_cap": None,
                "block_codes": [],
                "warning_codes": [],
                "reasons": [],
            },
            "account_guard": {
                "allowed": True,
                "blocked": False,
                "block_codes": [],
                "warning_codes": [],
                "stats": {},
            },
            "scenarios": [{
                "type": "buy",
                "entry_status": "waiting_confirmation",
                "entry_zone": [1.0980, 1.1020],
                "risk_reward": "1:1.7",
                "expected_effective_rr": 0.8,
                "ready_to_trade": False,
                "price_in_entry_zone": True,
                "h1_confirmation": False,
                "position_sizing": {"suggested_lot": 0.1, "account_balance": request.account_balance},
                "m15_quality": None,
            }],
            "macro": {"ai_summary": ""},
            "final_score": 62,
            "final_score_detail": {
                "final_score": 62,
                "signal_score": 57,
                "evidence_score": 50,
                "execution_quality_score": 100,
                "weighted_components": {},
            },
            "evidence": {"evidence_score": 50},
            "execution_quality": {"execution_quality_score": 100, "source": "fallback"},
            "entry_checklist": [],
            "backtest": {},
            "pattern_backtest": {},
            "why_not_opposite": {"sell": "SELL yeu hon"},
            "confidence_reason": [],
            "risk_management": {"max_risk_pct": 1.0, "warnings": []},
            "ai_provider": {},
            "chart_payload": {},
            "reason_codes": [],
            "penalty_codes": [],
            "warning_codes": [],
            "block_codes": [],
            "reason_messages": [],
            "smc": {},
            "smc_trade_flags": {},
            "technical": {"price": 1.1000, "atr_h4": 0.005},
        }

    return fake_analyze_symbol


# ---------------------------------------------------------------------------
# Test: AnalysisController enables decision engine action
# ---------------------------------------------------------------------------


def test_analysis_controller_enables_decision_engine_action(tmp_path, monkeypatch):
    """AnalysisController.run_single_analysis must call analyze_symbol
    with use_decision_engine_action=True."""
    from controllers.analysis_controller import AnalysisController
    from services.mt5_service import MT5Service
    from services.news_service import NewsService

    # --- Fake services ---
    settings_service = SettingsService(tmp_path / "settings.json")

    fake_mt5 = MagicMock(spec=MT5Service)
    fake_mt5.account_balance.return_value = 12345.67
    fake_mt5.load_ohlcv.return_value = _fake_candles()
    fake_mt5.symbol_data_quality.return_value = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "broker_symbol": "EURUSD",
        "spread_status": "normal",
        "spread_points": 1.2,
    }
    fake_mt5.quote_to_usd_rate.return_value = 1.0

    fake_news = MagicMock(spec=NewsService)
    fake_news.data_quality_flags.side_effect = _fake_news_data_quality_flags
    fake_news.macro_freshness_status.side_effect = _fake_macro_freshness_status

    # --- Build controller ---
    controller = AnalysisController(
        settings_service=settings_service,
        mt5_service=fake_mt5,
        news_service=fake_news,
    )

    # --- Patch yfinance to avoid network calls in _fetch_correlation_data ---
    captured_kwargs: list[dict] = []

    # Import the controller module so we can patch its analyze_symbol reference
    import controllers.analysis_controller as ctrl_module

    monkeypatch.setattr(
        ctrl_module, "analyze_symbol",
        _make_fake_analyze_symbol(captured_kwargs),
    )
    monkeypatch.setattr(
        controller, "_fetch_correlation_data",
        lambda _symbol: {},
    )

    # --- Run ---
    controller.run_single_analysis(
        symbol="EUR/USD",
        broker_symbol="EURUSD",
        account_balance=10_000,
        risk_percent=1,
        timezone_name="Asia/Ho_Chi_Minh",
    )

    # --- Assert ---
    assert len(captured_kwargs) == 1, (
        f"Expected exactly 1 call to analyze_symbol, got {len(captured_kwargs)}"
    )
    call_kwargs = captured_kwargs[0]

    assert call_kwargs.get("use_decision_engine_action") is True, (
        f"Expected use_decision_engine_action=True, "
        f"got {call_kwargs.get('use_decision_engine_action')!r}. "
        f"Controller must opt in to decision engine as primary decision source."
    )
