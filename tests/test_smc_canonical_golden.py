"""Golden characterization of the canonical SMC runtime.

Locks the full-pipeline decision path (mode ``v2``) *before* the v1/shadow
removal.  The locked fields must never be sourced from legacy/shadow/comparison
payloads, so the fixture stays valid as the canonical runtime replaces the old
dual-runner.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

import pytest

from core.analysis_engine import analyze_symbol
from core.market_models import Candle
from core.risk_engine import AnalysisInput


_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "smc_canonical" / "golden_cases.json"
)

# Keys that belong exclusively to the SMC scorer shadow router / comparison
# payload.  The golden fixture must never source its locked fields from them.
_FORBIDDEN_GOLDEN_KEYS = {
    "legacy",
    "active",
    "shadow",
    "shadow_status",
    "comparison",
    "policy",
    "decision_source",
    "decision_impact_allowed",
    "selection_source",
    "shadow_enabled",
    "shadow_scoring_version",
    "shadow_selected_zone",
    "shadow_selected_zone_id",
    "shadow_selected_zone_type",
}


def _fixture() -> dict:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _candles(
    count: int,
    *,
    start: float,
    step: float,
    bar_minutes: int,
) -> list[Candle]:
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = start
    result: list[Candle] = []
    for index in range(count):
        direction = 1 if index % 7 != 6 else -1
        body = step * direction
        open_price = price
        close_price = price + body
        result.append(Candle(
            time=timestamp,
            open=round(open_price, 5),
            high=round(max(open_price, close_price) + abs(step) * 0.7, 5),
            low=round(min(open_price, close_price) - abs(step) * 0.7, 5),
            close=round(close_price, 5),
            volume=float(1000 + index),
        ))
        price = close_price
        timestamp += timedelta(minutes=bar_minutes)
    return result


def _pipeline_input() -> tuple[AnalysisInput, dict[str, list[Candle]]]:
    request = AnalysisInput(
        symbol="EUR/USD",
        broker_symbol="EURUSDm",
        account_balance=10_000,
        risk_percent=1.0,
        account_currency="USD",
        lot_step=0.01,
        minimum_lot=0.01,
        contract_size_override=100_000,
        timezone_name="Asia/Ho_Chi_Minh",
    )
    candles = {
        "D1": _candles(120, start=1.05, step=0.00020, bar_minutes=1440),
        "H4": _candles(240, start=1.06, step=0.00010, bar_minutes=240),
        "H1": _candles(300, start=1.07, step=0.00005, bar_minutes=60),
    }
    return request, candles


def _run_case(monkeypatch, case: dict[str, Any]) -> dict[str, Any]:
    import core.analysis_pipeline as pipeline_module

    request, candles = _pipeline_input()
    monkeypatch.setattr(
        pipeline_module,
        "build_smc_context",
        lambda d1, h4, h1, *, scan_interval_min=15, symbol="": case["smc"],
    )
    monkeypatch.setattr(
        pipeline_module,
        "build_technical_snapshot",
        lambda d1, h4, h1: case["technical"],
    )
    monkeypatch.setattr(
        pipeline_module,
        "detect_market_regime",
        lambda technical, news_in_3h=False: case["market_regime"],
    )
    return analyze_symbol(request, candles)


def _run_case_tier1(monkeypatch, case: dict[str, Any]) -> dict[str, Any]:
    import core.analysis_pipeline as pipeline_module

    request, candles = _pipeline_input()
    monkeypatch.setattr(
        pipeline_module,
        "build_smc_context",
        lambda d1, h4, h1, *, scan_interval_min=15, symbol="": case["smc"],
    )
    monkeypatch.setattr(
        pipeline_module,
        "build_technical_snapshot",
        lambda d1, h4, h1: case["technical"],
    )
    monkeypatch.setattr(
        pipeline_module,
        "detect_market_regime",
        lambda technical, news_in_3h=False: case["market_regime"],
    )
    return analyze_symbol(
        request,
        candles,
        scanner_fast_tier1=True,
    )


def _extract(result: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "best_side": result["direction_bias"]["best_side"],
        "direction_bias": {
            key: result["direction_bias"].get(key)
            for key in (
                "best_side",
                "buy_score",
                "sell_score",
                "score_gap",
                "is_clear_bias",
            )
        },
    }
    sides: dict[str, Any] = {}
    for side in ("buy", "sell"):
        score = result["scenario_scores"][side]
        consumer = result["smc_consumer"]["sides"][side]
        sides[side] = {
            "smc_quality": score.get("smc_quality"),
            "signal_score": score.get("signal_score"),
            "smc_scoring_version": score.get("smc_scoring_version"),
            "selected_zone_id": consumer.get("selected_zone_id"),
            "selected_zone_type": consumer.get("selected_zone_type"),
            "selected_zone_timeframe": consumer.get(
                "selected_zone_timeframe"
            ),
            "score_breakdown": consumer.get("score_breakdown"),
        }
    out["sides"] = sides
    out["trade_gate"] = {
        key: result["trade_gate"].get(key)
        for key in ("allowed", "decision_cap", "block_codes", "warning_codes")
    }
    out["decision_engine"] = {
        key: result["decision_engine"].get(key)
        for key in ("decision", "legacy_action")
    }
    primary = next(
        (
            scenario
            for scenario in result["scenarios"]
            if scenario.get("priority") == "primary"
        ),
        None,
    )
    out["scenario"] = (
        {
            "type": primary.get("type"),
            "entry_status": primary.get("entry_status"),
            "entry_zone": primary.get("entry_zone"),
            "entry_zone_id": primary.get("entry_zone_id"),
            "stop_loss": primary.get("stop_loss"),
            "take_profit": primary.get("take_profit"),
            "trigger_type": primary.get("trigger_type"),
            "ready_to_trade": primary.get("ready_to_trade"),
            "position_sizing": primary.get("position_sizing"),
        }
        if primary is not None
        else None
    )
    return out


@pytest.mark.parametrize(
    "case",
    [case for case in _fixture()["cases"]],
    ids=[case["name"] for case in _fixture()["cases"]],
)
def test_golden_canonical_runtime_matches(monkeypatch, case):
    result = _run_case(monkeypatch, case)
    actual = _extract(result)
    assert actual == case["expected"]


def test_golden_expected_never_locks_shadow_payload():
    for case in _fixture()["cases"]:
        _assert_no_forbidden_keys(case["expected"], path=case["name"])


def test_score_smc_is_called_exactly_once_per_symbol(monkeypatch):
    import core.analysis_pipeline as pipeline_module
    from core.smc_scorer import score_smc as _real_score_smc

    calls: list[str] = []

    def _spy(smc, technical, market_regime=None, m15_candles=None):
        calls.append("score_smc")
        return _real_score_smc(
            smc, technical, market_regime, m15_candles=m15_candles
        )

    monkeypatch.setattr(pipeline_module, "score_smc", _spy)
    case = _fixture()["cases"][0]

    _run_case(monkeypatch, case)

    assert len(calls) == 1


def test_tier1_survivor_total_score_smc_calls_is_one(monkeypatch):
    import core.analysis_pipeline as pipeline_module
    import core.smc_prefilter as prefilter_module
    from core.smc_scorer import score_smc as _real_score_smc

    calls: list[str] = []

    def _spy(smc, technical, market_regime=None, m15_candles=None):
        calls.append("score_smc")
        return _real_score_smc(
            smc, technical, market_regime, m15_candles=m15_candles
        )

    monkeypatch.setattr(prefilter_module, "score_smc", _spy)
    monkeypatch.setattr(pipeline_module, "score_smc", _spy)
    case = _fixture()["cases"][0]

    _run_case_tier1(monkeypatch, case)

    # Tier-1 scored once; the full route must reuse that result.
    assert len(calls) == 1


def test_tier1_scorer_error_fails_closed_without_retry(monkeypatch):
    import core.analysis_pipeline as pipeline_module
    import core.smc_prefilter as prefilter_module
    from core.scanner import scanner_row_from_analysis
    from core.scanner_candidate_engine import evaluate_scanner_candidate

    prefilter_calls: list[str] = []

    def _explode(smc, technical, market_regime=None, m15_candles=None):
        prefilter_calls.append("score_smc")
        raise RuntimeError("scorer blew up")

    def _must_not_run(smc, technical, market_regime=None, m15_candles=None):
        raise AssertionError("full route must not re-score after Tier-1 error")

    monkeypatch.setattr(prefilter_module, "score_smc", _explode)
    monkeypatch.setattr(pipeline_module, "score_smc", _must_not_run)
    case = _fixture()["cases"][0]

    result = _run_case_tier1(monkeypatch, case)

    assert result["analysis_status"] == "structural_reject"
    assert "SMC_SCORING_ERROR" in result["block_codes"]
    assert len(prefilter_calls) == 1
    row = scanner_row_from_analysis(result)
    candidate = evaluate_scanner_candidate(row)
    assert candidate.auto_trade_candidate is False


def test_full_route_scorer_error_fails_closed(monkeypatch):
    import core.analysis_pipeline as pipeline_module
    from core.scanner import scanner_row_from_analysis
    from core.scanner_candidate_engine import evaluate_scanner_candidate

    def _explode(smc, technical, market_regime=None, m15_candles=None):
        raise RuntimeError("scorer blew up")

    monkeypatch.setattr(pipeline_module, "score_smc", _explode)
    case = _fixture()["cases"][0]

    result = _run_case(monkeypatch, case)

    assert result["analysis_status"] == "structural_reject"
    assert "SMC_SCORING_ERROR" in result["block_codes"]
    row = scanner_row_from_analysis(result)
    candidate = evaluate_scanner_candidate(row)
    assert candidate.auto_trade_candidate is False


def test_fixture_has_required_cases_and_scoring_version():
    fixture = _fixture()
    names = {case["name"] for case in fixture["cases"]}
    assert {
        "buy_selected_zone",
        "sell_selected_zone",
        "no_zone",
        "fvg_h1_only",
        "order_block",
        "broken_stale",
        "choch_cap",
        "missing_data_valid",
    }.issubset(names)
    for case in fixture["cases"]:
        for side in ("buy", "sell"):
            assert case["expected"]["sides"][side]["smc_scoring_version"] == "smc-v2"


def _assert_no_forbidden_keys(value: Any, *, path: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _FORBIDDEN_GOLDEN_KEYS:
                raise AssertionError(
                    f"{path} locks forbidden SMC shadow key {key!r}"
                )
            _assert_no_forbidden_keys(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_forbidden_keys(item, path=f"{path}[{index}]")
