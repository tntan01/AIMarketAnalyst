from __future__ import annotations

import json

from core.decision_engine import WATCH_ONLY, make_final_decision
from core.risk_engine import AnalysisInput, build_scenarios, build_trade_plan
from core.smc_consumer_contract import (
    build_smc_consumer_from_canonical_result,
)
from core.statistical_edge_engine import calculate_evidence_score
from core.trade_gate_engine import check_trade_gates
from services.journal_converters import journal_entry_from_analysis


def _canonical_side(side: str, *, zone_id: str) -> dict:
    is_buy = side == "buy"
    return {
        "smc_quality": 12,
        "smc_reason": "canonical reason",
        "selected_zone": {
            "zone_id": zone_id,
            "type": "demand_zone" if is_buy else "supply_zone",
            "family": "demand" if is_buy else "supply",
            "direction": side,
            "timeframe": "H4",
            "zone_quality_score": 82,
            "zone_relevance_score": 70,
            "zone_setup_score": 77,
            "scoring_version": "smc-v2",
        },
        "selected_zone_id": zone_id,
        "selected_zone_type": "demand_zone" if is_buy else "supply_zone",
        "selected_zone_timeframe": "H4",
        "selected_zone_quality_score": 82,
        "selected_zone_relevance_score": 70,
        "selected_zone_setup_score": 77,
        "scoring_version": "smc-v2",
        "breakdown": {
            "side": side,
            "total": 12,
            "scoring_version": "smc-v2",
        },
    }


def test_consumer_contract_selects_buy_and_sell_from_one_result():
    contract = build_smc_consumer_from_canonical_result(
        result={
            "buy": _canonical_side("buy", zone_id="zone-buy"),
            "sell": _canonical_side("sell", zone_id="zone-sell"),
        }
    )

    assert contract["contract_version"] == "smc-consumer-v2"
    buy = contract["sides"]["buy"]
    sell = contract["sides"]["sell"]

    assert buy["selected_zone_id"] == "zone-buy"
    assert buy["selected_zone_type"] == "demand_zone"
    assert buy["selected_zone_timeframe"] == "H4"
    assert buy["scoring_version"] == "smc-v2"
    assert buy["score_breakdown"]["total"] == 12
    assert buy["selected_zone"]["zone_id"] == "zone-buy"

    assert sell["selected_zone_id"] == "zone-sell"
    assert sell["selected_zone_type"] == "supply_zone"
    assert sell["scoring_version"] == "smc-v2"
    assert sell["score_breakdown"]["total"] == 12

    # The canonical consumer has no shadow/legacy selection concept.
    assert "shadow_selected_zone" not in buy
    assert "shadow_selected_zone_id" not in buy
    assert "selection_source" not in buy
    assert "shadow_scoring_version" not in buy


def test_strict_preferred_zone_does_not_reselect(monkeypatch):
    def _unexpected_reselection(*args, **kwargs):
        raise AssertionError("risk engine reselected another zone")

    monkeypatch.setattr(
        "core.risk_engine.select_best_level",
        _unexpected_reselection,
    )
    result = build_trade_plan(
        "buy",
        AnalysisInput(
            symbol="TEST",
            broker_symbol="TEST",
            account_balance=10_000,
            risk_percent=1,
        ),
        {
            "price": 100.0,
            "atr_h4": 2.0,
            "atr_d1": 2.0,
            "support_zones": [{"level": 99.0}],
            "resistance_zones": [{"level": 105.0}],
        },
        {"H4": {}, "H1": {}},
        preferred_zone={
            "zone_id": "wrong-side",
            "low": 109.0,
            "high": 111.0,
            "level": 110.0,
        },
        strict_preferred_zone=True,
    )
    assert result is None


def test_active_v2_requires_a_canonical_zone_before_building_a_plan():
    scenarios = build_scenarios(
        AnalysisInput(
            symbol="TEST",
            broker_symbol="TEST",
            account_balance=10_000,
            risk_percent=1,
        ),
        {},
        {},
        {
            "buy": {"signal_score": 80},
            "sell": {"signal_score": 70},
        },
        {"status": "allowed"},
        preferred_zones={"buy": None, "sell": None},
        strict_preferred_zones=True,
        require_preferred_zones=True,
    )

    assert scenarios == []


def test_gate_uses_relevance_and_confirmed_h4_choch_safety_cap():
    gate = check_trade_gates(
        {
            "m15_quality": "strict",
            "expected_effective_rr": 2.0,
            "score_gap": 20,
            "zone_id": "zone-active",
            "zone_scoring_version": "smc-v1",
            "zone_relevance_score": 65,
            "zone_quality_score": 72,
            "zone_setup_score": 69,
            "zone_price_relation_valid": True,
            "h4_confirmed_choch_against_direction": True,
        }
    )

    assert gate["decision_cap"] == WATCH_ONLY
    assert "CHOCH_AGAINST_DIRECTION" in gate["warning_codes"]
    assert gate["smc_zone"]["selected_zone_id"] == "zone-active"

    decision = make_final_decision(
        final_score=100,
        gate_result=gate,
        entry_status="confirmed",
        score_gap=20,
        trade_permission={"status": "allowed"},
    )
    assert decision["decision"] == WATCH_ONLY


def test_statistical_zone_bucket_never_mixes_scoring_versions():
    trades = []
    for version, result_r in (("smc-v1", -1.0), ("smc-v2", 1.0)):
        for _ in range(20):
            trades.append(
                {
                    "symbol": "EURUSD",
                    "direction": "buy",
                    "status": "closed",
                    "result_r": result_r,
                    "entry_zone_score": 85,
                    "entry_zone_scoring_version": version,
                }
            )

    result = calculate_evidence_score(
        trades,
        "EURUSD",
        "buy",
        zone_score=85,
        zone_scoring_version="smc-v2",
    )

    assert result["group_used"] == "symbol_direction_zone"
    assert result["sample_size"] == 20
    assert result["zone_scoring_version_used"] == "smc-v2"


def test_journal_persists_selected_zone_version_and_breakdown():
    analysis = {
        "symbol": "EURUSD",
        "timestamp": "2026-01-01T00:00:00Z",
        "scenario_scores": {},
        "scenarios": [
            {
                "type": "buy",
                "entry_zone": [1.08, 1.09],
                "entry_zone_id": "zone-active",
                "entry_zone_score": 69,
                "entry_zone_quality_score": 72,
                "entry_zone_relevance_score": 64,
                "entry_zone_setup_score": 69,
                "entry_zone_scoring_version": "smc-v1",
                "smc_score_breakdown": {
                    "total": 9,
                    "selected_zone_id": "zone-active",
                },
            }
        ],
        "decision_summary": {
            "action": "watch",
            "best_side": "buy",
            "best_scenario": "buy",
        },
        "trade_permission": {"status": "caution"},
        "data_quality": {},
        "market_regime": {},
        "macro": {},
    }

    entry = journal_entry_from_analysis(analysis, mode="scanner_detail")

    assert entry.selected_zone_id == "zone-active"
    assert entry.entry_zone_scoring_version == "smc-v1"
    assert entry.entry_zone_quality_score == 72
    assert entry.entry_zone_relevance_score == 64
    assert entry.entry_zone_setup_score == 69
    assert json.loads(entry.smc_score_breakdown_json or "{}")[
        "selected_zone_id"
    ] == "zone-active"
