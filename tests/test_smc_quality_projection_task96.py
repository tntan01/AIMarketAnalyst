"""Task 96 — validator/projection read ``quality_raw`` and B/Q/L/C.

The new projection reads the canonical final selection straight through: it
never rebuilds the retired subtotal, never re-applies the old penalty/cap
pipeline and never rescales.  The SMC raw keeps its 0–15 range and the outer
TechnicalScore weights/raw maxima are untouched.

Boundary of this task: only the validator/projection are updated here.  Wiring
``TechnicalScore``/consumers onto it belongs to tasks 106–107.
"""

from __future__ import annotations

import importlib
from fractions import Fraction

import pytest

from core.technical_signal_scorer import (
    SMC_QUALITY_RAW_VERSION,
    TECHNICAL_COMPONENT_RAW_MAX,
    TECHNICAL_REGIME_WEIGHTS,
    SmcQualityRawProjection,
    TechnicalScoreDataError,
    project_smc_quality_raw,
    validate_smc_quality_raw_result,
)
from core.smc_quality import evaluate_candidate_sets
from core.smc_selection import finalize_canonical_result, select_canonical_sides
from core.smc_scoring_result import SmcScoringResult
from core.smc_versions import SMC_SELECTION_VERSION

_COORD = importlib.import_module("tests.test_smc_selection_coordinator_task93")

_AS_OF = _COORD._AS_OF
_MIN_RR = Fraction(2, 1)


def _result(*, zones=None, technical=None, core_reason_codes=()):
    technical = technical or _COORD._technical()
    candidate_sets = evaluate_candidate_sets(
        _COORD._context(zones if zones is not None else [_COORD._ob("smcz-raw", 101.0, 102.0)]),
        technical,
        as_of=_AS_OF,
        core_reason_codes=core_reason_codes,
    )
    return finalize_canonical_result(
        select_canonical_sides(candidate_sets, technical, min_rr=_MIN_RR)
    )


# -- The projection reads the canonical values ---------------------------------


def test_projection_reads_the_canonical_raw_and_components_unchanged():
    result = _result()

    projection = project_smc_quality_raw(result, "buy")

    assert isinstance(projection, SmcQualityRawProjection)
    # Hand-computed in the task93 fixture: B .8925, Q .70825, L 0, C .75 ->
    # S 10.02775 -> raw 10.
    assert projection.raw == 10
    assert projection.total == pytest.approx(10.02775, abs=1e-9)
    assert projection.b == pytest.approx(0.8925, abs=1e-9)
    assert projection.q == pytest.approx(0.70825, abs=1e-9)
    assert projection.l == 0.0
    assert projection.c == pytest.approx(0.75, abs=1e-9)
    assert projection.selected_zone_id == "smcz-raw"
    assert projection.selected_setup_id == "smcs-smcz-raw"
    assert projection.plan_available is True
    assert projection.quality_raw_version == SMC_QUALITY_RAW_VERSION
    assert projection.selection_version == SMC_SELECTION_VERSION


def test_projection_keeps_the_retired_pipeline_out_of_the_number():
    """No penalty/cap field may be rebuilt or subtracted from the raw."""

    result = _result()
    selection = result.side("buy").selection

    projection = project_smc_quality_raw(result, "buy")

    assert projection.raw == selection.quality_raw
    payload = projection.to_dict()
    for retired in ("subtotal", "penalty_points", "applied_cap", "penalties", "caps"):
        assert retired not in payload
    assert result.side("buy").breakdown == {}


def test_raw_stays_inside_the_canonical_zero_to_fifteen_range():
    buy_raw = project_smc_quality_raw(_result(), "buy").raw
    assert 0 <= buy_raw <= TECHNICAL_COMPONENT_RAW_MAX["smc"] == 15
    assert TECHNICAL_COMPONENT_RAW_MAX["trend"] == 25
    assert TECHNICAL_COMPONENT_RAW_MAX["location"] == 25
    assert TECHNICAL_COMPONENT_RAW_MAX["momentum"] == 20


def test_outer_weights_are_untouched_by_this_projection():
    assert TECHNICAL_REGIME_WEIGHTS["unknown"] == {
        "trend": 25,
        "momentum": 25,
        "location": 25,
        "smc": 25,
    }
    assert TECHNICAL_REGIME_WEIGHTS["trending_up"]["smc"] == 20
    assert TECHNICAL_REGIME_WEIGHTS["ranging"]["smc"] == 40


# -- Null and zero stay different ----------------------------------------------


def test_no_zone_reads_as_zero_and_core_unavailable_reads_as_null():
    technical = _COORD._technical()
    no_zone = _result(zones=[], technical=technical)
    unavailable = _result(
        technical=technical, core_reason_codes=("SMC_H4_COVERAGE_GAP",)
    )

    zero = project_smc_quality_raw(no_zone, "buy")
    missing = project_smc_quality_raw(unavailable, "buy")

    assert zero.raw == 0
    assert zero.state == "no_zone"
    assert zero.b is None and zero.q is None
    assert zero.readiness_status == "WATCH_ZONE"

    assert missing.raw is None
    assert missing.state == "data_unavailable"
    assert missing.readiness_status == "DATA_UNAVAILABLE"
    assert missing.raw != zero.raw


def test_watch_zone_keeps_its_raw_and_reports_the_plan_as_unavailable():
    result = _result(zones=[_COORD._ob("smcz-watch", 99.0, 100.0)],
                     technical=_COORD._technical(resistance=()))

    projection = project_smc_quality_raw(result, "buy")

    assert projection.raw == 10
    assert projection.plan_available is False
    assert projection.selected_zone_id == "smcz-watch"
    # No plan: the side can be watching or waiting, but never READY (task 95).
    assert projection.readiness_status in {"WATCH_ZONE", "WAITING_CONFIRMATION"}
    assert projection.state == "watch_zone"


# -- The validator fails closed -------------------------------------------------


def test_validator_accepts_the_final_result_and_rejects_a_raw_result():
    result = _result()
    assert validate_smc_quality_raw_result(result)
    assert not validate_smc_quality_raw_result(result.to_dict())
    assert not validate_smc_quality_raw_result(None)
    assert not validate_smc_quality_raw_result(
        SmcScoringResult(scoring_version="smc-v2", sides={})
    )


def test_projection_refuses_a_side_without_a_final_selection():
    result = _result()
    stripped = SmcScoringResult(
        scoring_version=result.scoring_version,
        sides={"buy": type(result.side("buy"))(score=10, breakdown={})},
    )

    with pytest.raises(TechnicalScoreDataError):
        project_smc_quality_raw(stripped, "buy")


def test_projection_refuses_an_out_of_range_or_inconsistent_raw():
    result = _result()
    side = result.side("buy")
    selection = side.selection
    bad = SmcScoringResult(
        scoring_version=result.scoring_version,
        sides={
            "buy": type(side)(score=16, breakdown={}, selection=_with(selection, 16)),
            "sell": result.side("sell"),
        },
    )

    assert not validate_smc_quality_raw_result(bad)
    with pytest.raises(TechnicalScoreDataError):
        project_smc_quality_raw(bad, "buy")


def test_projection_refuses_a_feature_outside_the_unit_interval():
    result = _result()
    side = result.side("buy")
    bad = SmcScoringResult(
        scoring_version=result.scoring_version,
        sides={
            "buy": type(side)(
                score=10, breakdown={}, selection=_with(side.selection, None, q=1.5)
            ),
            "sell": result.side("sell"),
        },
    )

    with pytest.raises(TechnicalScoreDataError):
        project_smc_quality_raw(bad, "buy")


def test_projection_rejects_an_invalid_side():
    with pytest.raises(TechnicalScoreDataError):
        project_smc_quality_raw(_result(), "sideways")


def _with(selection, raw, **overrides):
    """Forge a payload that never went through the final-selection constructor.

    R100-01: the DTO now refuses an inconsistent payload at construction, so a
    malformed payload has to be forged the way a foreign/deserialized one would
    arrive.  The assertions themselves are unchanged: the validator and the
    projection must still refuse it.
    """

    import dataclasses

    changes = {} if raw is None else {"quality_raw": raw}
    changes.update(overrides)
    values = {
        item.name: getattr(selection, item.name)
        for item in dataclasses.fields(type(selection))
    }
    values.update(changes)
    forged = object.__new__(type(selection))
    for name, value in values.items():
        object.__setattr__(forged, name, value)
    return forged
