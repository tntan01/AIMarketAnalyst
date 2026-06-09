from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.risk_engine import AnalysisInput, build_trade_plan, contract_size_for, contract_size_override_for_symbol, reward_risk
from core.signal_engine import clamp


def test_clamp() -> None:
    assert clamp(-10) == 0
    assert clamp(110) == 100
    assert clamp(50) == 50


def test_reward_risk() -> None:
    assert reward_risk(100, 95, 110) == 2


def _candles(rows: list[tuple[float, float, float, float]]) -> list[Candle]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(base + timedelta(hours=index), open_, high, low, close, 100)
        for index, (open_, high, low, close) in enumerate(rows)
    ]


def _request() -> AnalysisInput:
    return AnalysisInput(
        symbol="XAU/USD",
        broker_symbol="XAUUSD",
        account_balance=10_000,
        risk_percent=1,
    )


def test_build_trade_plan_uses_narrow_entry_zone_and_separate_watch_zone() -> None:
    technical = {
        "price": 104.0,
        "atr_h4": 10.0,
        "atr_d1": None,
        "support_zones": [{"level": 100.0, "strength": "strong"}],
        "resistance_zones": [{"level": 130.0, "strength": "strong"}],
    }

    plan = build_trade_plan(
        "buy",
        _request(),
        technical,
        {"H1": {"displacement": "bullish", "bos": True}, "H4": {"premium_discount": "discount"}},
        _candles(
            [
                (103.0, 104.0, 102.0, 103.5),
                (103.5, 104.5, 102.5, 103.0),
                (103.0, 106.0, 101.0, 105.0),
            ]
        ),
    )

    assert plan is not None
    assert plan["entry_zone"] == [98.0, 102.0]
    assert plan["watch_zone"] == [99.0, 105.0]
    assert plan["price_in_entry_zone"] is False
    assert plan["entry_status"] == "watch_zone"
    assert plan["ready_to_trade"] is False


def test_special_symbols_use_non_forex_contract_sizes() -> None:
    assert contract_size_for(AnalysisInput("XAG/USD", "XAGUSD", 10_000, 1)) == 5000.0
    assert contract_size_for(AnalysisInput("BTC/USD", "BTCUSD", 10_000, 1)) == 1.0


def test_special_symbol_contract_override_prefers_broker_value() -> None:
    assert contract_size_override_for_symbol("XAG/USD", {"contract_size": 1000}, 100000) == 1000.0
    assert contract_size_override_for_symbol("BTC/USD", {"contract_size": None}, 100000) == 1.0
    assert contract_size_override_for_symbol("EUR/USD", {"contract_size": 100}, 100000) == 100000
