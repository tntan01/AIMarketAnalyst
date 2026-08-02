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


def test_signal_engine_has_no_v1_scorer():
    """Bước 13: scorer v1 và override path đã bị xóa khỏi signal_engine."""
    import core.signal_engine as engine

    assert not hasattr(engine, "smc_quality_score")
    assert not hasattr(engine, "apply_smc_score_override")
    assert not hasattr(engine, "_best_smc_zone")

    case = _golden()["cases"][0]
    composed = _compose("buy", case)
    assert composed["smc_quality"] == case["expected"]["sides"]["buy"][
        "smc_quality"
    ]
