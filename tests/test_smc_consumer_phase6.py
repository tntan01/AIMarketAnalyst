from __future__ import annotations

import json

from core.decision_engine import WATCH_ONLY, make_final_decision
from core.risk_engine import AnalysisInput, build_scenarios, build_trade_plan
from core.smc_consumer_contract import build_smc_consumer_contract
from core.statistical_edge_engine import calculate_evidence_score
from core.trade_gate_engine import check_trade_gates
from services.journal_converters import journal_entry_from_analysis


def _legacy_zone(zone_id: str = "zone-active") -> dict:
    return {
        "zone_id": zone_id,
        "type": "bullish_order_block",
        "family": "order_block",
        "direction": "buy",
        "low": 99.0,
        "high": 100.0,
        "origin_index": 10,
        "origin_time": "2026-01-01T00:00:00+00:00",
        "departure_end_index": 12,
        "zone_quality_score": 72,
        "zone_relevance_score": 64,
        "zone_setup_score": 69,
        "zone_score": 69,
        "scoring_version": "smc-v1",
    }


def test_consumer_contract_keeps_shadow_out_of_active_decision_path():
    active_zone = _legacy_zone()
    shadow_zone = {
        **active_zone,
        "zone_id": "zone-shadow",
        "scoring_version": "smc-v2",
        "zone_setup_score": 88,
    }
    diagnostics = {
        "policy": {
            "decision_source": "smc-v1",
            "active_version": "smc-v1",
            "decision_impact_allowed": False,
        },
        "active": {
            "buy": {
                "selected_zone_id": "zone-active",
                "scoring_version": "smc-v1",
                "breakdown": {"total": 9, "scoring_version": "smc-v1"},
            },
            "sell": {},
        },
        "shadow": {
            "buy": {
                "selected_zone": shadow_zone,
                "selected_zone_id": "zone-shadow",
                "scoring_version": "smc-v2",
                "breakdown": {"total": 12, "scoring_version": "smc-v2"},
            },
        },
    }

    contract = build_smc_consumer_contract(
        smc={
            "symbol": "TEST",
            "H4": {"order_blocks": [active_zone]},
            "H1": {},
        },
        scoring_diagnostics=diagnostics,
    )
    buy = contract["sides"]["buy"]

    assert buy["selected_zone_id"] == "zone-active"
    assert buy["scoring_version"] == "smc-v1"
    assert buy["shadow_selected_zone_id"] == "zone-shadow"
    assert buy["selected_zone"]["smc_score_breakdown"]["total"] == 9


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
