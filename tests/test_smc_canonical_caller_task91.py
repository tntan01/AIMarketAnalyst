"""R80-91-03 (option A) — canonical caller seam at the scorer boundary.

`score_smc` must run the canonical chain (evidence → candidate evaluation →
B/Q/L/C → readiness/order) exactly once per snapshot and expose it on the
internal diagnostics channel, without touching the legacy scores, selected
zones or the serialized result contract.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib

from core.market_models import Candle
from core.smc_models import CandidateEvaluation, SmcCandidateSet, SmcQualityBreakdown
from core.smc_scorer import (
    CANONICAL_DIAGNOSTICS_ERROR,
    CANONICAL_DIAGNOSTICS_VERSION,
    evaluate_canonical_diagnostics,
    score_smc,
)

_QUALITY_MODULE = importlib.import_module("tests.test_smc_quality_task88")
_AS_OF = "2026-02-06T06:00:00+00:00"
_REGIME = {"primary": "trend_up"}
# After the fixture zone availability (2026-02-05) so the entry visit opens.
_TIME0 = datetime(2026, 2, 6, tzinfo=timezone.utc)


def _candle(index: int, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        time=_TIME0 + timedelta(minutes=15 * index),
        open=open_,
        high=high,
        low=low,
        close=close,
    )


def _m15_confirming_zone(zone_low=99.0, zone_high=100.0):
    """M15 window whose rejection candle confirms the hand-computed OB zone."""

    rows: list[tuple[float, float, float, float]] = []
    price = 101.2
    for index in range(20):
        swing = 0.35 if index % 2 == 0 else -0.3
        close = price + swing
        rows.append((price, max(price, close) + 0.25, min(price, close) - 0.25, close))
        price = close
    rows.append((100.9, 101.0, zone_low + 0.6, zone_low + 0.8))
    rows.append((zone_low + 0.8, zone_high + 0.25, zone_low - 0.1, zone_high + 0.15))
    return [_candle(index, *row) for index, row in enumerate(rows)]


def _context():
    return _QUALITY_MODULE._context(_QUALITY_MODULE._zone())


def _technical():
    return _QUALITY_MODULE._technical()


# -- Adapter is the single canonical caller ----------------------------------


def test_score_smc_calls_the_canonical_adapter_once_with_the_snapshot(monkeypatch):
    from core import smc_scorer

    calls: list[dict] = []
    real = smc_scorer.evaluate_canonical_diagnostics

    def spy(smc, technical=None, **kwargs):
        calls.append({"smc": smc, "technical": technical, **kwargs})
        return real(smc, technical, **kwargs)

    monkeypatch.setattr(smc_scorer, "evaluate_canonical_diagnostics", spy)
    context = _context()
    technical = _technical()
    m15 = _m15_confirming_zone()

    result = score_smc(
        context,
        technical,
        _REGIME,
        m15_candles=m15,
        m15_as_of=_AS_OF,
        canonical_core_reason_codes=("SMC_H4_COVERAGE_GAP",),
    )

    assert len(calls) == 1, "the canonical chain must run exactly once per snapshot"
    call = calls[0]
    assert call["smc"] is context
    assert call["technical"] is technical
    assert call["m15_candles"] is m15
    assert call["m15_as_of"] == _AS_OF
    assert call["as_of"] == _AS_OF
    assert call["core_reason_codes"] == ("SMC_H4_COVERAGE_GAP",)
    assert result.diagnostics is not None
    assert result.diagnostics["diagnostics_version"] == CANONICAL_DIAGNOSTICS_VERSION


def test_score_smc_without_m15_still_runs_the_chain_once(monkeypatch):
    from core import smc_scorer

    calls: list[str] = []
    real = smc_scorer.evaluate_canonical_diagnostics

    def spy(smc, technical=None, **kwargs):
        calls.append("canonical")
        return real(smc, technical, **kwargs)

    monkeypatch.setattr(smc_scorer, "evaluate_canonical_diagnostics", spy)
    result = score_smc(_context(), _technical(), _REGIME)

    assert calls == ["canonical"]
    diagnostics = result.diagnostics
    assert diagnostics["sides"]["buy"]["state"] in {"evaluated", "no_zone"}
    assert diagnostics["sides"]["buy"]["readiness"]["m15_status"] == "missing"


# -- Observable canonical output ---------------------------------------------


def test_runtime_diagnostics_expose_quality_order_and_readiness():
    diagnostics = evaluate_canonical_diagnostics(
        _context(),
        _technical(),
        as_of=_AS_OF,
        m15_candles=_m15_confirming_zone(),
        m15_as_of=_AS_OF,
    )

    buy = diagnostics["sides"]["buy"]
    assert buy["state"] == "evaluated"
    # Hand-computed values of the shared fixture (see test_smc_quality_task88):
    # B .8925, Q .70825, L 0, C .75 -> S 10.02775 -> raw 10.
    assert buy["quality_raw"] == 10
    assert (buy["b"], buy["q"], buy["l"], buy["c"]) == (
        0.8925000000000001,
        0.70825,
        0.0,
        0.75,
    )
    # Ordered candidates are the mandatory-passed ones only.
    assert buy["ordered_candidate_ids"] == ["smcz-hand-1"]
    assert [candidate["candidate_id"] for candidate in buy["candidates"]] == [
        "smcz-hand-1"
    ]
    candidate = buy["candidates"][0]
    assert candidate["mandatory_passed"] is True
    assert candidate["b"] == buy["b"]

    # No planner exists in this lot: readiness never claims READY and asks for
    # the plan, keeping the local-ready state visible instead.
    readiness = buy["readiness"]
    assert readiness["plan_available"] is None
    assert readiness["can_consider_entry"] is False
    assert readiness["can_execute"] is False
    assert readiness["revalidation_required"] is True
    assert readiness["status"] in {"WATCH_ZONE", "WAITING_CONFIRMATION"}
    assert readiness["smc_state"] in {"LOCAL_READY_PLAN_PENDING", "READY_FOR_REVALIDATION"}
    assert "SMC_PLAN_UNAVAILABLE" in readiness["reason_codes"]


def test_runtime_diagnostics_hide_hard_rejected_candidates_from_the_order():
    context = _QUALITY_MODULE._two_zone_context()
    diagnostics = evaluate_canonical_diagnostics(
        context, _QUALITY_MODULE._technical(price=109.5, atr=2.0), as_of=_AS_OF
    )

    buy = diagnostics["sides"]["buy"]
    assert buy["quality_raw"] == 7
    assert buy["ordered_candidate_ids"] == ["smcz-near"]
    rejected = next(
        candidate for candidate in buy["candidates"] if candidate["candidate_id"] == "smcz-far"
    )
    assert rejected["mandatory_passed"] is False
    assert rejected["quality_raw"] == 10
    assert "ZONE_BEYOND_HARD_DISTANCE" in rejected["rejection_codes"]


def test_missing_core_data_is_unavailable_and_never_zero():
    diagnostics = evaluate_canonical_diagnostics(
        _context(),
        _technical(),
        as_of=_AS_OF,
        core_reason_codes=("SMC_H4_COVERAGE_GAP",),
    )

    for side in ("buy", "sell"):
        payload = diagnostics["sides"][side]
        assert payload["state"] == "data_unavailable"
        assert payload["quality_raw"] is None
        assert payload["quality_score"] is None
        assert "SMC_H4_COVERAGE_GAP" in payload["reason_codes"]
        assert payload["readiness"]["status"] == "DATA_UNAVAILABLE"


def test_m15_changes_readiness_but_not_the_quality_of_the_candidate():
    without_m15 = evaluate_canonical_diagnostics(
        _context(), _technical(), as_of=_AS_OF
    )["sides"]["buy"]
    with_m15 = evaluate_canonical_diagnostics(
        _context(),
        _technical(),
        as_of=_AS_OF,
        m15_candles=_m15_confirming_zone(),
        m15_as_of=_AS_OF,
    )["sides"]["buy"]

    for key in ("b", "q", "l", "c", "quality_raw", "quality_score", "total"):
        assert without_m15[key] == with_m15[key], key
    assert without_m15["readiness"]["m15_status"] == "missing"
    assert with_m15["readiness"]["m15_status"] == "confirmed"
    assert (
        without_m15["readiness"]["status"],
        with_m15["readiness"]["status"],
    ) == ("WAITING_CONFIRMATION", "WATCH_ZONE")


# -- Legacy route and boundary discipline ------------------------------------


def test_legacy_result_is_unaffected_by_the_canonical_diagnostics(monkeypatch):
    from core import smc_scorer

    context = _context()
    technical = _technical()
    baseline = score_smc(context, technical, _REGIME)

    monkeypatch.setattr(
        smc_scorer,
        "evaluate_canonical_diagnostics",
        lambda *args, **kwargs: {"sentinel": True},
    )
    replaced = score_smc(context, technical, _REGIME)

    assert replaced.to_dict() == baseline.to_dict()
    assert replaced.side("buy").score == baseline.side("buy").score
    assert replaced.side("buy").selected_zone_id == baseline.side("buy").selected_zone_id
    assert replaced.diagnostics == {"sentinel": True}

    # The serialized contract never carries the diagnostics channel.
    assert "canonical_diagnostics" not in baseline.to_dict()
    assert "canonical_diagnostics" not in baseline.side("buy").to_dict()


def test_canonical_failure_is_recorded_and_never_breaks_the_legacy_route(monkeypatch):
    from core import smc_scorer

    context = _context()
    technical = _technical()
    baseline = score_smc(context, technical, _REGIME)

    def explode(*args, **kwargs):
        raise ValueError("canonical chain unavailable")

    monkeypatch.setattr(smc_scorer, "evaluate_canonical_diagnostics", explode)
    degraded = score_smc(context, technical, _REGIME)

    assert degraded.to_dict() == baseline.to_dict()
    assert degraded.diagnostics["state"] == "error"
    assert degraded.diagnostics["reason_codes"] == [CANONICAL_DIAGNOSTICS_ERROR]
    assert "ValueError" in degraded.diagnostics["error"]


def test_the_canonical_caller_never_touches_planner_or_coordinator(monkeypatch):
    from core import scanner_scenario_producers

    def must_not_run(*args, **kwargs):  # pragma: no cover - failure path
        raise AssertionError("the canonical caller must not build plans")

    monkeypatch.setattr(
        scanner_scenario_producers, "produce_scenario_plans", must_not_run
    )
    monkeypatch.setattr(
        scanner_scenario_producers, "produce_scenario_plans_from_zones", must_not_run
    )

    diagnostics = evaluate_canonical_diagnostics(
        _context(), _technical(), as_of=_AS_OF
    )
    result = score_smc(_context(), _technical(), _REGIME, m15_as_of=_AS_OF)

    for payload in list(diagnostics["sides"].values()) + list(
        result.diagnostics["sides"].values()
    ):
        assert "plan" not in payload
        assert "plan_available" not in payload
        assert payload["readiness"]["plan_available"] is None
        assert set(payload) == {
            "state",
            "quality_raw",
            "quality_score",
            "b",
            "q",
            "l",
            "c",
            "total",
            "reason_codes",
            "ordered_candidate_ids",
            "readiness",
            "candidates",
        }
    assert "scanner_scenario_producers" not in dir(
        importlib.import_module("core.smc_scorer")
    )


def test_canonical_caller_does_not_recompute_or_reselect(monkeypatch):
    """The seam converts typed data only: no second evaluation, no new zone."""

    from core import smc_scorer
    from core.smc_quality import evaluate_candidate_sets as real_sets

    set_calls: list[str] = []

    def counting_sets(smc, technical=None, **kwargs):
        set_calls.append("evaluate_candidate_sets")
        return real_sets(smc, technical, **kwargs)

    monkeypatch.setattr(smc_scorer, "evaluate_candidate_sets", counting_sets)
    result = score_smc(_context(), _technical(), _REGIME, m15_as_of=_AS_OF)

    assert set_calls == ["evaluate_candidate_sets"]
    # The legacy selected-zone channel is untouched by the canonical chain.
    assert result.side("buy").selected_zone_id == result.side("buy").selected_zone_id
    assert result.to_dict() == score_smc(
        _context(), _technical(), _REGIME, m15_as_of=_AS_OF
    ).to_dict()


def test_candidate_set_and_readiness_types_stay_typed_for_callers():
    """The seam keeps returning the typed canonical values to direct callers."""

    sets = _QUALITY_MODULE.evaluate_candidate_sets(
        _context(), _technical(), as_of=_AS_OF
    )
    candidate_set = sets["buy"]
    assert isinstance(candidate_set, SmcCandidateSet)
    assert isinstance(candidate_set.quality, SmcQualityBreakdown)
    assert all(
        isinstance(candidate, CandidateEvaluation) for candidate in candidate_set.candidates
    )
