"""Bước 07 — scenario composition is decoupled from the v1 SMC scorer.

``compose_scenario_score`` takes a precomputed SMC side score/breakdown, so the
final scenario score can be computed without invoking ``smc_quality_score``.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.signal_engine import (
    calc_risk_condition,
    compose_scenario_score,
    score_scenario,
)
from core.smc_context import extract_smc_trade_flags


_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "smc_canonical" / "golden_cases.json"
)


def _golden() -> dict:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _risk_score(technical: dict) -> int:
    return calc_risk_condition(
        technical.get("atr_h4") or technical.get("atr_d1") or 0.0,
        (
            technical.get("atr_avg_14d")
            or technical.get("atr_h4")
            or technical.get("atr_d1")
            or 0.0
        ),
        False,
        "normal",
    )


def _compose(side: str, case: dict) -> dict:
    expected = case["expected"]["sides"][side]
    return compose_scenario_score(
        side,
        case["technical"],
        smc_quality=expected["smc_quality"],
        smc_flags=extract_smc_trade_flags(case["smc"], side),
        risk_score=_risk_score(case["technical"]),
        macro_score=15,
        macro_confidence=1.0,
        market_regime=case["market_regime"],
        correlation_adjustment=0.0,
        macro_context={"buy": 15, "sell": 15},
    )


def test_composition_reproduces_golden_v2_final_scores():
    for case in _golden()["cases"]:
        for side in ("buy", "sell"):
            expected = case["expected"]["sides"][side]
            composed = _compose(side, case)
            assert composed["signal_score"] == expected["signal_score"], (
                case["name"],
                side,
            )
            assert composed["smc_quality"] == expected["smc_quality"], (
                case["name"],
                side,
            )


def test_composition_does_not_call_smc_quality_score(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("smc_quality_score must not be called")

    monkeypatch.setattr("core.signal_engine.smc_quality_score", _boom)
    case = _golden()["cases"][0]

    composed = _compose("buy", case)

    assert composed["smc_quality"] == case["expected"]["sides"]["buy"][
        "smc_quality"
    ]


def test_score_scenario_matches_composition_with_v1_quality():
    case = _golden()["cases"][0]
    technical = case["technical"]
    smc = case["smc"]
    risk_score = _risk_score(technical)

    legacy = score_scenario(
        "buy",
        technical,
        smc,
        risk_score,
        15,
        macro_confidence=1.0,
        market_regime=case["market_regime"],
        correlation_adjustment=0.0,
        macro_context={"buy": 15, "sell": 15},
    )
    composed = compose_scenario_score(
        "buy",
        technical,
        smc_quality=legacy["smc_quality"],
        smc_reason=legacy["smc_reason"],
        smc_flags=legacy["smc_flags"],
        risk_score=risk_score,
        macro_score=15,
        macro_confidence=1.0,
        market_regime=case["market_regime"],
        correlation_adjustment=0.0,
        macro_context={"buy": 15, "sell": 15},
    )

    assert composed["signal_score"] == legacy["signal_score"]
    assert composed["smc_quality"] == legacy["smc_quality"]
    assert composed["penalty_codes"] == legacy["penalty_codes"]
    assert composed["smc_score_cap"] == legacy["smc_score_cap"]
