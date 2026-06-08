from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.analysis_engine import analyze_symbol, build_entry_checklist, confidence_reason
from core.risk_engine import AnalysisInput, position_sizing
from core.signal_engine import calc_risk_condition


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


def test_single_analysis_calculates_rule_based_scores_without_ai() -> None:
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        data_quality={"terminal_connected": True, "broker_logged_in": True, "spread_status": "normal"},
    )

    assert result["scenario_scores"]["buy"]["total"] > result["scenario_scores"]["sell"]["total"]
    assert result["scenario_scores"]["buy"]["signal_score"] == result["scenario_scores"]["buy"]["total"]
    assert result["scenario_scores"]["sell"]["signal_score"] == result["scenario_scores"]["sell"]["total"]
    assert result["scenario_scores"]["buy"]["macro_alignment"] == 10  # fallback neutral 15 * weight(20)/30 = 10
    assert result["decision_summary"]["best_scenario"] == "buy"
    assert "chart_payload" in result
    assert len(result["chart_payload"]["D1"]) == 240
    assert len(result["chart_payload"]["H4"]) == 240
    assert len(result["chart_payload"]["H1"]) == 120
    assert "entry_checklist" in result
    assert [item["label"] for item in result["entry_checklist"]] == ["Xu hướng", "Vùng POI", "Xác nhận H1", "Tin tức", "Spread", "R:R", "Lot"]
    assert "backtest" in result
    assert "summary" in result["backtest"]


def test_single_analysis_chart_payload_includes_m15_when_available() -> None:
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)
    m15 = _candles(80, 1.12, 0.00005, 0.0005)

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        data_quality={"terminal_connected": True, "broker_logged_in": True, "spread_status": "normal"},
        m15_candles=m15,
    )

    assert len(result["chart_payload"]["M15"]) == 80


def test_position_sizing_uses_price_distance_times_contract_size_for_xauusd() -> None:
    request = AnalysisInput(
        "XAU/USD",
        "XAUUSDm",
        account_balance=10_000,
        risk_percent=1,
        lot_step=0.01,
        minimum_lot=0.01,
        contract_size_override=100,
    )

    sizing = position_sizing(request, entry_price=2340, stop_loss=2324)

    assert sizing["risk_amount_usd"] == 100
    assert sizing["price_distance"] == 16
    assert sizing["contract_size"] == 100
    assert sizing["suggested_lot"] == 0.06


def test_risk_condition_matches_documented_components() -> None:
    assert calc_risk_condition(atr_current=10, atr_avg_14d=10, news_in_3h=False, spread_status="normal") == 15
    assert calc_risk_condition(atr_current=16, atr_avg_14d=10, news_in_3h=True, spread_status="abnormal") == 0


def test_entry_checklist_trend_matches_side_and_allows_range_edge_setup() -> None:
    buy_against_downtrend = build_entry_checklist(
        {"type": "buy", "entry_zone": [100, 102], "entry_status": "waiting_confirmation"},
        {"primary": "trend_down"},
        {"status": "allowed"},
        {"spread_status": "normal"},
        {"location_quality": 15},
    )
    range_at_edge = build_entry_checklist(
        {"type": "buy", "entry_zone": [100, 102], "entry_status": "waiting_confirmation"},
        {"primary": "range"},
        {"status": "allowed"},
        {"spread_status": "normal"},
        {"location_quality": 15},
    )

    assert buy_against_downtrend[0]["status"] == "wait"
    assert range_at_edge[0]["status"] == "pass"


def test_confidence_reason_includes_score_breakdown_macro_confidence_and_event_context() -> None:
    reasons = confidence_reason(
        {"structure_h4": "HH/HL"},
        {
            "buy": {
                "total": 76,
                "trend_alignment": 20,
                "momentum_alignment": 12,
                "location_quality": 15,
                "smc_quality": 11,
                "smc_reason": "Demand zone H4 fresh.",
                "risk_condition": 9,
                "macro_alignment": 6,
            },
            "sell": {
                "total": 42,
                "trend_alignment": 5,
                "momentum_alignment": 8,
                "location_quality": 3,
                "smc_quality": 2,
                "smc_reason": "Không có SMC zone thuận.",
                "risk_condition": 9,
                "macro_alignment": 6,
            },
        },
        {"status": "caution", "reason": "Có tin CPI."},
        {"H4": {"bos": True, "displacement": "bullish"}},
        macro_confidence=0.55,
        data_quality={"next_high_impact_event": "CPI 19:30"},
    )

    joined = "\n".join(reasons)
    assert "BUY components" in joined
    assert "trend=20" in joined
    assert "smc=11" in joined
    assert "BUY SMC: 11/15" in joined
    assert "Macro confidence low" in joined
    assert "CPI 19:30" in joined
