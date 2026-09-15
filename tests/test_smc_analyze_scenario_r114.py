"""R114-01 — Analyze builds its scenario from the FINAL canonical selection.

Before this fix the Analyze route fed ``build_scenarios`` a ``preferred_zones``
entry read from the legacy ``SmcSideScoringResult.selected_zone`` field, which
the canonical finalizer never fills.  Every canonical side therefore arrived as
``None`` and no scenario could be built from the accepted setup; Analyze fell
back to the display-only ATR scenario even when the canonical side was
``evaluated`` with an available plan.

The fix is a reader-only adapter at the consumer boundary
(``scenario_preferred_zone_for_side``): it converts the FINAL selection — the
candidate the coordinator accepted — into the zone shape ``build_trade_plan``
already consumes.  It never looks for another zone and never recomputes
quality/B-Q-L-C, geometry, confirmation, lifecycle, score or the plan.

Every test below drives the REAL ``AnalysisPipeline.execute``: no evaluator,
coordinator, planner or risk/scenario owner is mocked.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from core.analysis_pipeline import AnalysisPipeline
from core.risk_engine import AnalysisInput
from core.smc_consumer_contract import (
    build_smc_consumer_from_canonical_result,
    scenario_preferred_zone_for_side,
    selected_zone_for_side,
    selection_for_side,
)
from core.smc_scoring_result import smc_selection_of

UTC = timezone.utc
NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)
# At this cutoff the canonical BUY side is ``evaluated`` with an accepted plan
# whose band sits on the correct side of price, inside the risk-owner distance.
CUTOFF = NOW - timedelta(hours=1)
_TICK = 0.01
# The owner R:R floor.  Without a certified policy the coordinator accepts no
# plan (PLAN_POLICY_UNAVAILABLE), which is the documented fail-closed behaviour.
_THRESHOLDS = {"min_rr": 2.0, "ready": 65, "wait": 55}
_MACRO = {"buy": 30, "sell": 0}

_TI = importlib.import_module("tests.test_analysis_pipeline_integration")


def _candles():
    from tests.test_scanner_release import _zoned_candles

    return _zoned_candles()


def _full_macro_context() -> dict[str, Any]:
    """All four USD-strength sources present, so macro confidence is not derated."""

    return _TI._correlation_context(
        {"dxy_candles", "vix_candles", "us10y_candles", "us2y_candles"}
    )


def _request() -> AnalysisInput:
    return AnalysisInput(
        symbol="XAUUSD",
        broker_symbol="XAUUSD",
        account_balance=10_000.0,
        risk_percent=1.0,
    )


def _analyze(**overrides: Any):
    """Run the real Analyze caller for the shared positive configuration."""

    d1, h4, h1 = _candles()
    kwargs: dict[str, Any] = {
        "snapshot_as_of": CUTOFF,
        "tick_size": _TICK,
        "thresholds": dict(_THRESHOLDS),
        "macro_alignment": dict(_MACRO),
        "macro_confidence": 1.0,
        "correlation_context": _full_macro_context(),
    }
    kwargs.update(overrides)
    pipeline = AnalysisPipeline()
    result = pipeline.execute(_request(), {"D1": d1, "H4": h4, "H1": h1}, **kwargs)
    return result, pipeline


def _scenario(result: dict[str, Any], side: str = "buy") -> dict[str, Any] | None:
    for item in result.get("scenarios") or []:
        if item.get("type") == side:
            return item
    return None


def _selection(pipeline: AnalysisPipeline, side: str):
    return smc_selection_of(pipeline._smc_evaluation.result.side(side))


# ---------------------------------------------------------------------------
# Positive — the scenario comes from the final selection
# ---------------------------------------------------------------------------


def test_a_canonical_selected_setup_produces_an_analyze_scenario():
    """The positive fixture really does reach an accepted canonical plan."""

    result, pipeline = _analyze()
    selection = _selection(pipeline, "buy")
    assert selection.state == "evaluated"
    assert selection.plan_available is True

    scenario = _scenario(result, "buy")
    assert scenario is not None, "the canonical plan must produce a scenario"
    assert scenario["entry_zone_source"] == "smc_selected"
    assert scenario["entry_zone_id"] == selection.selected_zone_id


def test_the_scenario_reads_the_same_candidate_as_the_final_selection():
    """Identity and geometry trace back to the selected setup, not another zone."""

    result, pipeline = _analyze()
    selection = _selection(pipeline, "buy")
    scenario = _scenario(result, "buy")
    source_zone = scenario["source_zone"]

    # No technical/legacy zone and no display fallback was used.
    assert scenario["entry_zone_source"] not in {"fallback", "technical", "smc_distant"}
    assert scenario["entry_zone_scoring_version"] != "non-smc-display-v1"
    assert source_zone["source"] == "smc_selected"
    assert source_zone["selection_status"] == "evaluated"
    # The zone geometry is the SELECTED band, unchanged (the scenario reports
    # it rounded for display, exactly as it does for a technical zone).
    assert source_zone["original_low"] == round(selection.zone_low, 5)
    assert source_zone["original_high"] == round(selection.zone_high, 5)
    assert selection.plan["zone_id"] == scenario["entry_zone_id"]
    assert selection.plan["setup_id"] == selection.selected_setup_id


def test_the_adapter_is_a_reader_and_does_not_touch_the_canonical_result():
    """The canonical result/selection/readiness survive the adapter untouched."""

    from core.smc_snapshot import evaluate_smc_snapshot

    _, pipeline = _analyze()
    contract = pipeline._smc_consumer_contract

    # An independent evaluation of the SAME frozen snapshot must agree exactly
    # with what the pipeline carries after building the scenario.
    replayed = evaluate_smc_snapshot(pipeline._smc_snapshot, min_rr=2.0)
    assert pipeline._smc_evaluation.result.to_dict() == replayed.result.to_dict()

    for side in ("buy", "sell"):
        selection = _selection(pipeline, side)
        payload = selection_for_side(contract, side)
        assert payload == selection.to_dict(), (
            "the consumer contract must carry the selection unchanged"
        )
        # The adapter may be called repeatedly without changing anything.
        before = selection.to_dict()
        scenario_preferred_zone_for_side(contract, side)
        scenario_preferred_zone_for_side(contract, side)
        assert selection.to_dict() == before


def test_the_adapter_converts_instead_of_recomputing():
    """The preferred zone carries identity/bounds — never a second score."""

    _, pipeline = _analyze()
    contract = pipeline._smc_consumer_contract
    selection = _selection(pipeline, "buy")
    zone = scenario_preferred_zone_for_side(contract, "buy")

    assert zone["zone_id"] == selection.selected_zone_id
    assert zone["setup_id"] == selection.selected_setup_id
    assert zone["direction"] == zone["side"] == "buy"
    assert zone["low"] == selection.zone_low
    assert zone["high"] == selection.zone_high
    # The midpoint convention of the retired ``SelectedSmcZone.from_zone``.
    assert zone["level"] == (selection.zone_low + selection.zone_high) / 2
    assert zone["source"] == "smc_selected"
    assert zone["selection_status"] == "evaluated"
    # No quality/B-Q-L-C/score of any kind is synthesised here.
    for recomputed in (
        "quality_raw", "quality_score", "b", "q", "l", "c", "total",
        "zone_quality_score", "zone_relevance_score", "zone_setup_score",
        "effective_zone_score", "lifecycle_status", "confirmation_state",
    ):
        assert recomputed not in zone, recomputed


# ---------------------------------------------------------------------------
# Fail-closed — nothing is invented, nothing falls back
# ---------------------------------------------------------------------------


def _contract_with_selection(for_side: str = "buy", **changes: Any) -> dict[str, Any]:
    """The real contract with one side's selection payload deliberately broken."""

    _, pipeline = _analyze()
    contract = pipeline._smc_consumer_contract
    payload = dict(contract["sides"][for_side]["selection"])
    payload.update(changes)
    broken = {"sides": {key: dict(value) for key, value in contract["sides"].items()}}
    broken["sides"][for_side]["selection"] = payload
    return broken


@pytest.mark.parametrize("state", ["no_zone", "data_unavailable", "watch_zone"])
def test_a_side_that_is_not_evaluated_has_no_preferred_zone(state: str):
    contract = _contract_with_selection("buy", state=state)
    assert scenario_preferred_zone_for_side(contract, "buy") is None


def test_a_side_without_an_accepted_plan_has_no_preferred_zone():
    contract = _contract_with_selection("buy", plan_available=False)
    assert scenario_preferred_zone_for_side(contract, "buy") is None


def test_a_selection_without_a_plan_payload_has_no_preferred_zone():
    contract = _contract_with_selection("buy", plan=None)
    assert scenario_preferred_zone_for_side(contract, "buy") is None


@pytest.mark.parametrize(
    "changes",
    [
        {"plan_zone_id": "smcz-other"},
        {"plan_setup_id": "smcs-other"},
        {"plan": {"zone_id": "smcz-other", "setup_id": "smcs-x", "direction": "buy"}},
    ],
)
def test_a_mismatched_plan_identity_has_no_preferred_zone(changes: dict):
    contract = _contract_with_selection("buy", **changes)
    assert scenario_preferred_zone_for_side(contract, "buy") is None


@pytest.mark.parametrize(
    "changes",
    [
        {"zone_low": None},
        {"zone_high": None},
        {"zone_low": 1010.0, "zone_high": 1000.0},   # inverted band
        {"zone_low": 1000.0, "zone_high": 1000.0},   # zero width
        {"zone_low": float("nan")},
        {"zone_high": float("inf")},
        {"zone_low": True},                          # a bool is not a price
    ],
)
def test_an_unusable_band_has_no_preferred_zone(changes: dict):
    contract = _contract_with_selection("buy", **changes)
    assert scenario_preferred_zone_for_side(contract, "buy") is None


def test_missing_identity_has_no_preferred_zone():
    for changes in (
        {"selected_zone_id": None},
        {"selected_setup_id": None},
        {"side": "hold"},
    ):
        contract = _contract_with_selection("buy", **changes)
        assert scenario_preferred_zone_for_side(contract, "buy") is None


def test_a_canonical_no_zone_route_never_reaches_a_scenario():
    """A canonical side without a selected setup never becomes READY."""

    from core.smc_scoring_result import SELECTION_STATE_NO_ZONE

    case = _no_zone_case()
    result, pipeline = _analyze_for_case(case)
    for side in ("buy", "sell"):
        selection = _selection(pipeline, side)
        assert selection.state == SELECTION_STATE_NO_ZONE
        assert scenario_preferred_zone_for_side(
            pipeline._smc_consumer_contract, side
        ) is None
    for scenario in result.get("scenarios") or []:
        assert scenario.get("ready_to_trade") is False
        assert scenario.get("entry_zone_source") != "smc_selected"


def test_a_legacy_payload_without_a_selection_keeps_its_old_reader():
    """Stored documents stay readable; they never gain canonical identity."""

    legacy_zone = {"zone_id": "z-legacy", "low": 1.0, "high": 1.1, "level": 1.05}
    legacy_contract = {
        "contract_version": "smc-consumer-v2",
        "sides": {
            "buy": {"side": "buy", "selection": None, "selected_zone": legacy_zone},
            "sell": {"side": "sell", "selection": None, "selected_zone": None},
        },
    }
    # The historical reader still serves the stored payload ...
    assert selected_zone_for_side(legacy_contract, "buy") == legacy_zone
    assert scenario_preferred_zone_for_side(legacy_contract, "buy") == legacy_zone
    # ... and it carries no canonical selection, so nothing claims one.
    assert selection_for_side(legacy_contract, "buy") is None


def test_the_canonical_route_never_populates_the_legacy_zone_field():
    """On a canonical result the old field stays empty, so it cannot mask a defect."""

    result, pipeline = _analyze()
    contract = pipeline._smc_consumer_contract
    selection = _selection(pipeline, "buy")
    assert selection.state == "evaluated"
    # The legacy field is still None even though the side is fully selected ...
    assert selected_zone_for_side(contract, "buy") is None
    # ... while the adapter serves the real selection.
    assert scenario_preferred_zone_for_side(contract, "buy") is not None
    assert _scenario(result, "buy")["entry_zone_source"] == "smc_selected"


def _no_zone_case() -> dict[str, Any]:
    import json
    from pathlib import Path

    path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "smc_canonical"
        / "golden_cases_canonical.json"
    )
    cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
    return next(case for case in cases if case["name"] == "no_zone")


def _analyze_for_case(case: dict[str, Any]):
    fixtures = importlib.import_module("tests.scanner_fast_path_fixtures")
    baseline = importlib.import_module("tests.test_scanner_fast_path_baseline")

    candles = fixtures.make_candles({"recipe": case["recipe"], "name": case["name"]})
    cutoff = baseline._cutoff(candles)
    pipeline = AnalysisPipeline()
    result = pipeline.execute(
        AnalysisInput(
            symbol=str(case["symbol"]),
            broker_symbol=str(case["symbol"]),
            account_balance=10_000.0,
            risk_percent=1.0,
        ),
        candles,
        m15_candles=candles["M15"],
        m15_as_of=cutoff,
        snapshot_as_of=cutoff,
        tick_size=float(case["tick_size"]),
        thresholds=dict(_THRESHOLDS),
    )
    return result, pipeline


# ---------------------------------------------------------------------------
# Gate preservation — the owners still decide
# ---------------------------------------------------------------------------


def test_the_macro_confidence_gate_still_blocks_the_canonical_plan():
    """With macro data missing the score gate still refuses the scenario."""

    result, pipeline = _analyze(correlation_context={})
    selection = _selection(pipeline, "buy")
    assert selection.state == "evaluated" and selection.plan_available is True
    assert pipeline._scores["buy"]["signal_score"] < 50
    scenario = _scenario(result, "buy")
    # The canonical plan exists but the score gate owns the outcome.
    assert scenario is None or scenario["entry_zone_source"] != "smc_selected"


def test_the_blocked_permission_gate_still_blocks_the_canonical_plan():
    """An abnormal spread blocks the plan through the existing risk gate."""

    result, pipeline = _analyze(data_quality={"spread_status": "abnormal"})
    selection = _selection(pipeline, "buy")
    assert selection.state == "evaluated" and selection.plan_available is True
    assert pipeline._trade_permission["status"] == "blocked"
    scenario = _scenario(result, "buy")
    assert scenario is None or scenario["entry_zone_source"] != "smc_selected"


def test_the_scenario_never_becomes_ready_on_its_own():
    """A built scenario is not a ready order: the gates still decide."""

    result, _ = _analyze()
    scenario = _scenario(result, "buy")
    assert scenario is not None
    assert scenario["ready_to_trade"] is False


def test_the_display_fallback_stays_labelled_and_never_claims_smc_identity():
    """When the owners block, the remaining scenario is display-only."""

    result, _ = _analyze(data_quality={"spread_status": "abnormal"})
    for scenario in result.get("scenarios") or []:
        if scenario.get("entry_zone_source") == "fallback":
            assert scenario["entry_zone_scoring_version"] == "non-smc-display-v1"
            assert scenario["entry_zone_id"] is None
            assert scenario["ready_to_trade"] is False


# ---------------------------------------------------------------------------
# Parity — Scanner and Analyze read the same accepted candidate
# ---------------------------------------------------------------------------


def test_scanner_and_analyze_agree_on_the_selected_identity():
    """The same snapshot yields the same selected zone/setup on both routes."""

    from core.scanner_live_producers import derive_live_analysis

    d1, h4, h1 = _candles()
    scanner = derive_live_analysis(
        d1, h4, h1, symbol="XAUUSD", captured_at=CUTOFF, tick_size=_TICK, min_rr=2.0
    )
    result, pipeline = _analyze()

    for side in ("buy", "sell"):
        live = smc_selection_of(scanner["canonical_smc"].side(side))
        analyzed = _selection(pipeline, side)
        assert analyzed.state == live.state
        assert analyzed.quality_raw == live.quality_raw
        assert analyzed.selected_zone_id == live.selected_zone_id
        assert analyzed.selected_setup_id == live.selected_setup_id
        assert analyzed.plan_available == live.plan_available

    # The Analyze scenario names the very zone the Scanner selected.
    scanner_selection = smc_selection_of(scanner["canonical_smc"].side("buy"))
    assert _scenario(result, "buy")["entry_zone_id"] == scanner_selection.selected_zone_id
