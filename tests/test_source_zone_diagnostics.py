from __future__ import annotations

from copy import deepcopy

from core.risk_engine import (
    build_source_zone_diagnostics,
    build_trade_plan,
)
from core.scanner import scanner_row_from_analysis
from tests.test_entry_tp_quality_diagnostics import (
    _base_smc,
    _base_tech,
    _req,
    _swing,
    _zone,
    candles,
    m15,
)


def _preferred_zone() -> dict[str, object]:
    return {
        "type": "bullish_order_block",
        "low": 1.0968,
        "high": 1.0982,
        "level": 1.0975,
        "zone_score": 88,
        "strength": "strong",
        "source": "smc_selected",
        "stale": True,
        "mitigated": True,
        "broken": False,
        "test_count": 4,
        "freshness_bars": 12,
        "displacement_multiple": 1.7,
        "liquidity_sweep": False,
        "zone_location": "discount",
    }


def _valid_plan(preferred_zone: dict[str, object]) -> dict[str, object]:
    technical = _base_tech(
        1.1000,
        0.0020,
        [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
        [_zone(1.1050, 1.1040, 1.1060, "strong", 70)],
    )
    smc = _base_smc()
    smc["H4"]["swings"] = {
        "highs": [_swing(1.1050, 10)],
        "lows": [_swing(1.0940, 5)],
    }
    plan = build_trade_plan(
        "buy",
        _req(),
        technical,
        smc,
        candles,
        m15_candles=m15,
        preferred_zone=preferred_zone,
        market_regime={"primary": "trend_up"},
    )
    assert plan is not None
    return plan


def test_trade_plan_contains_complete_source_zone_diagnostics() -> None:
    plan = _valid_plan(_preferred_zone())

    expected_phase_16a = {
        "zone_type": "bullish_order_block",
        "source": "smc_selected",
        "zone_score": 88,
        "strength": "strong",
        "stale": True,
        "mitigated": True,
        "broken": False,
        "test_count": 4,
        "freshness_bars": 12,
        "original_low": 1.0968,
        "original_high": 1.0982,
        "original_width": 0.0014,
        "original_width_atr": 0.7,
    }
    assert {
        key: plan["source_zone"][key]
        for key in expected_phase_16a
    } == expected_phase_16a
    assert isinstance(plan["source_zone"]["effective_zone_score"], int)
    assert isinstance(
        plan["source_zone"]["effective_zone_score_breakdown"],
        dict,
    )


def test_source_metadata_tiers_execution_width_by_effective_quality() -> None:
    enriched = _preferred_zone()
    legacy = {
        key: value
        for key, value in enriched.items()
        if key
        not in {
            "type",
            "stale",
            "mitigated",
            "broken",
            "test_count",
            "freshness_bars",
            "displacement_multiple",
            "liquidity_sweep",
            "zone_location",
        }
    }

    enriched_plan = _valid_plan(enriched)
    legacy_plan = _valid_plan(legacy)

    # SL, TP, and entry side are untouched by the source-zone metadata.
    for key in ("stop_loss", "take_profit", "entry_zone_source"):
        assert enriched_plan[key] == legacy_plan[key], key

    # The metadata (stale + mitigated) lowers effective zone quality, which
    # tiers the execution sub-zone width: weak → 0.25 ATR vs moderate → 0.18.
    # The lower-quality (enriched) zone therefore gets a wider sub-zone.
    assert enriched_plan["source_zone"]["effective_zone_score"] < legacy_plan[
        "source_zone"
    ]["effective_zone_score"]
    assert enriched_plan["execution_zone_quality"] == "weak"
    assert legacy_plan["execution_zone_quality"] == "moderate"
    assert enriched_plan["execution_zone_width_atr_target"] == 0.25
    assert legacy_plan["execution_zone_width_atr_target"] == 0.18
    assert enriched_plan["structural_execution_zone"][0] < legacy_plan[
        "structural_execution_zone"
    ][0]


def test_scanner_row_uses_source_zone_from_best_scenario() -> None:
    buy_source = build_source_zone_diagnostics(
        _preferred_zone(),
        0.0020,
        "buy",
    )
    sell_source = deepcopy(buy_source)
    assert sell_source is not None
    sell_source["zone_type"] = "bearish_order_block"
    result = {
        "symbol": "EUR/USD",
        "scenario_scores": {
            "buy": {"signal_score": 80},
            "sell": {"signal_score": 60},
        },
        "trade_permission": {"status": "allowed"},
        "scenarios": [
            {
                "type": "sell",
                "entry_zone": [1.1040, 1.1060],
                "entry_status": "watch_zone",
                "source_zone": sell_source,
            },
            {
                "type": "buy",
                "entry_zone": [1.0960, 1.0980],
                "entry_status": "watch_zone",
                "source_zone": buy_source,
            },
        ],
        "technical": {"price": 1.1000, "atr_h4": 0.0020},
        "decision_engine": {"legacy_action": "watch", "decision": "WATCH_ONLY"},
        "direction_bias": {"best_side": "buy"},
    }

    row = scanner_row_from_analysis(result)

    assert row["source_zone"] == buy_source
    assert row["analysis_result"]["scenarios"][1]["source_zone"] == buy_source


def test_legacy_scenario_without_source_zone_is_backward_compatible() -> None:
    result = {
        "symbol": "EUR/USD",
        "scenario_scores": {
            "buy": {"signal_score": 80},
            "sell": {"signal_score": 60},
        },
        "trade_permission": {"status": "allowed"},
        "scenarios": [
            {
                "type": "buy",
                "entry_zone": [1.0960, 1.0980],
                "entry_status": "watch_zone",
            }
        ],
        "technical": {"price": 1.1000, "atr_h4": 0.0020},
        "decision_engine": {"legacy_action": "watch", "decision": "WATCH_ONLY"},
        "direction_bias": {"best_side": "buy"},
    }

    row = scanner_row_from_analysis(result)

    assert "source_zone" in row
    assert row["source_zone"] is None
