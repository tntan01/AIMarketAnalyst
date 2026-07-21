"""Tests for select_top_levels and alternate_zones in build_trade_plan."""

import pytest


def test_select_top_levels_returns_sorted_top_n():
    from core.risk_engine import select_top_levels

    price = 1.1000
    zones = [
        {"level": 1.0995, "strength": "strong", "zone_score": 70},
        {"level": 1.0980, "strength": "strong", "zone_score": 95},
        {"level": 1.0960, "strength": "moderate", "zone_score": 60},
        {"level": 1.0940, "strength": "weak", "zone_score": 30},
    ]
    result = select_top_levels(zones, price, max_distance=0.0050 * 3.5, below=True, top_n=2)
    assert len(result) == 2
    assert result[0]["zone_score"] == 95
    assert result[1]["zone_score"] == 70


def test_build_trade_plan_returns_alternate_zones():
    from core.risk_engine import build_trade_plan, AnalysisInput
    from core.technical_context import build_technical_snapshot
    from core.smc_context import build_smc_context
    from tests.test_risk_engine import _trending_candles

    d1 = _trending_candles(200, start_price=1.1000, step=0.00002, bar_minutes=1440)
    h4 = _trending_candles(200, start_price=1.1000, step=0.00002, bar_minutes=240)
    h1 = _trending_candles(200, start_price=1.1000, step=0.00002, bar_minutes=60)
    m15 = _trending_candles(200, start_price=1.1000, step=0.00002, bar_minutes=15)

    technical = build_technical_snapshot(d1, h4, h1)
    smc = build_smc_context(d1, h4, h1)

    request = AnalysisInput(
        symbol="EUR/USD", broker_symbol="EURUSDm",
        account_balance=10_000.0, risk_percent=2.0, contract_size_override=100_000.0,
    )

    plan = build_trade_plan("buy", request, technical, smc, h1, m15_candles=m15)
    if plan is None:
        pytest.skip("No valid trade plan generated from test candle data")

    assert "alternate_zones" in plan, (
        f"Missing 'alternate_zones' key. Keys: {list(plan.keys())}"
    )
    alt = plan["alternate_zones"]
    assert isinstance(alt, list)
    for i in range(len(alt) - 1):
        s1 = alt[i].get("zone_score") or 0
        s2 = alt[i + 1].get("zone_score") or 0
        assert s1 >= s2, (
            f"alternate_zones not sorted: [{i}]={s1} < [{i+1}]={s2}"
        )
