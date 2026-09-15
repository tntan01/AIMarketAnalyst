"""D101-01 — the canonical façade feeds the snapshot of the real callers.

The public ``build_smc_context`` keeps running the LEGACY detector; the
snapshot seam uses ``core.smc_canonical_context`` instead, so the canonical
evaluator receives canonical evidence on the same closed-candle set.  These
tests go through the RUNTIME callers (Scanner live producer and the Analyze
pipeline), not through synthetic quality fixtures.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.market_models import Candle
from core.smc_canonical_context import build_canonical_timeframe_context
from core.smc_context import build_smc_context
from core.smc_quality import QUALITY_FORMATION_ATR_UNAVAILABLE
from core.smc_scoring_result import SELECTION_STATE_DATA_UNAVAILABLE

UTC = timezone.utc
NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)


def _zoned_candles():
    """The Scanner release fixture: triangle waves with REAL H4 swings."""

    from tests.test_scanner_release import _zoned_candles as fixture

    return fixture()


def _smooth_candles():
    from tests.test_scanner_release import _live_candles as fixture

    return fixture()


# ---------------------------------------------------------------------------
# Scanner runtime caller
# ---------------------------------------------------------------------------


def test_scanner_live_producer_reaches_the_canonical_evaluator():
    """A real Scanner fixture is no longer blanked by missing legacy evidence.

    Before the façade every zone came from the legacy detector without an
    evidence block, so every side was ``data_unavailable`` with
    ``FORMATION_ATR_UNAVAILABLE``.  The valid outcomes now are ``no_zone`` or a
    real evaluated candidate set.
    """

    from core.scanner_live_producers import derive_live_analysis

    d1, h4, h1 = _zoned_candles()
    analysis = derive_live_analysis(
        d1,
        h4,
        h1,
        symbol="XAUUSD",
        captured_at=NOW,
        tick_size=0.01,
        min_rr=2.0,
    )
    snapshot = analysis["smc_snapshot"]
    assert snapshot.as_of == NOW
    assert snapshot.core_reason_codes == ()

    evaluation = analysis["smc_evaluation"]
    for side in ("buy", "sell"):
        candidate_set = evaluation.candidate_sets[side]
        if candidate_set.state == SELECTION_STATE_DATA_UNAVAILABLE:
            # Only a genuine per-candidate defect may make a side unavailable.
            assert QUALITY_FORMATION_ATR_UNAVAILABLE in candidate_set.reason_codes
            assert any(
                QUALITY_FORMATION_ATR_UNAVAILABLE in candidate.rejection_codes
                for candidate in candidate_set.candidates
            ), "the reason must be traceable to a real candidate"
    # At least one side must carry real evaluated candidates for this fixture.
    assert any(
        evaluation.candidate_sets[side].state != SELECTION_STATE_DATA_UNAVAILABLE
        for side in ("buy", "sell")
    )


def test_scanner_canonical_zones_carry_their_own_evidence():
    """Every canonical zone declares the evidence the evaluator measures."""

    d1, h4, h1 = _zoned_candles()
    context = build_canonical_timeframe_context(
        h4,
        symbol="XAUUSD",
        timeframe="H4",
        as_of=NOW,
        tick_size=0.01,
    )
    zones = [
        *context["order_blocks"],
        *context["fvg"],
        *context["demand_zones"],
        *context["supply_zones"],
    ]
    assert zones, "the fixture must produce canonical zones"
    for zone in zones:
        assert zone.get("zone_id")
        assert zone.get("original_bounds")
        # A canonical payload always carries its own evidence block; a raw
        # candidate keeps the detector's un-promoted status.
        assert (
            zone.get("departure_measurement") is not None
            or zone.get("middle_measurement") is not None
            or zone.get("base_measurement") is not None
        )
        assert zone.get("lifecycle_status") in {
            "candidate",
            "confirmed",
            "usable",
            "invalid",
            "expired",
        }


def test_raw_candidates_never_become_usable_without_confirmation():
    """A detector candidate stays a candidate — no promotion by the façade."""

    d1, h4, h1 = _zoned_candles()
    context = build_canonical_timeframe_context(
        h4,
        symbol="XAUUSD",
        timeframe="H4",
        as_of=NOW,
        tick_size=0.01,
    )
    for zone in [*context["order_blocks"], *context["fvg"]]:
        if zone.get("lifecycle_status") == "candidate":
            assert zone.get("available_at") is None
            assert zone.get("usable") is not True


# ---------------------------------------------------------------------------
# Missing evidence still fails closed
# ---------------------------------------------------------------------------


def test_a_canonical_zone_without_formation_atr_fails_closed():
    """Canonical provenance with no usable ATR is a real defect, not a zero."""

    from core.smc_quality import evaluate_candidate

    zone = {
        "zone_id": "smcz-no-atr",
        "setup_id": "smcs-no-atr",
        "family": "ob",
        "direction": "buy",
        "lifecycle_status": "confirmed",
        "available_at": "2026-08-12T00:00:00+00:00",
        "original_bounds": {"low": 99.0, "high": 100.0},
        "low": 99.0,
        "high": 100.0,
        "tick_size": 0.1,
        "departure_measurement": {
            "direction": "buy",
            "atr_before_event": None,
            "status": "unavailable",
            "reason_codes": [],
        },
    }
    evaluation, mandatory_missing = evaluate_candidate(
        side="buy",
        timeframe="H4",
        family="order_block",
        zone=zone,
        timeframe_data={"structure": "HH/HL", "bos": True, "displacement": "bullish"},
        smc={"confluence": {"timeframe_evidence": {}}},
        price=99.5,
        execution_atr=2.0,
        as_of=NOW,
        m15_candles=None,
        m15_as_of=None,
    )
    assert mandatory_missing is True
    assert evaluation.mandatory_passed is False
    assert evaluation.quality_raw is None
    # The defect is traceable to the missing reference ATR, either through the
    # formation gate or through the geometry that consumes it.
    assert {"FORMATION_ATR_UNAVAILABLE", "ZONE_GEOMETRY_UNAVAILABLE"} & set(
        evaluation.rejection_codes
    )


def test_a_canonical_zone_without_tick_size_fails_that_candidate_closed():
    """D101-02: the tick dependency fails the candidate, not the snapshot."""

    from core.smc_geometry import GEOMETRY_TICK_SIZE_UNAVAILABLE
    from core.smc_quality import evaluate_candidate

    zone = {
        "zone_id": "smcz-no-tick",
        "setup_id": "smcs-no-tick",
        "family": "ob",
        "direction": "buy",
        "lifecycle_status": "confirmed",
        "available_at": "2026-08-12T00:00:00+00:00",
        "original_bounds": {"low": 99.0, "high": 100.0},
        "low": 99.0,
        "high": 100.0,
        "departure_measurement": {
            "direction": "buy",
            "body_atr": 0.6,
            "body_range": 0.8,
            "directional_close_location": 0.86,
            "atr_before_event": 2.0,
            "status": "ok",
            "reason_codes": [],
        },
    }
    evaluation, _ = evaluate_candidate(
        side="buy",
        timeframe="H4",
        family="order_block",
        zone=zone,
        timeframe_data={"structure": "HH/HL", "bos": True, "displacement": "bullish"},
        smc={"confluence": {"timeframe_evidence": {}}},
        price=99.5,
        execution_atr=2.0,
        as_of=NOW,
        m15_candles=None,
        m15_as_of=None,
    )
    assert GEOMETRY_TICK_SIZE_UNAVAILABLE in evaluation.rejection_codes
    assert evaluation.mandatory_passed is False


def test_a_payload_without_canonical_provenance_keeps_its_documented_reference():
    """The R80-91-02 boundary is unchanged: legacy payloads are not failed."""

    from core.smc_geometry import GEOMETRY_TICK_SIZE_UNAVAILABLE
    from core.smc_quality import evaluate_candidate

    legacy = {
        "zone_id": "smcz-legacy",
        "family": "demand",
        "direction": "buy",
        "lifecycle_status": "confirmed",
        "low": 99.0,
        "high": 100.0,
    }
    evaluation, _ = evaluate_candidate(
        side="buy",
        timeframe="H4",
        family="demand",
        zone=legacy,
        timeframe_data={"structure": "HH/HL", "bos": True, "displacement": "bullish"},
        smc={"confluence": {"timeframe_evidence": {}}},
        price=99.5,
        execution_atr=2.0,
        as_of=NOW,
        m15_candles=None,
        m15_as_of=None,
    )
    assert GEOMETRY_TICK_SIZE_UNAVAILABLE not in evaluation.rejection_codes


# ---------------------------------------------------------------------------
# The legacy route is untouched
# ---------------------------------------------------------------------------


def test_legacy_public_builder_is_not_changed_by_the_facade():
    """``build_smc_context`` keeps producing the approved legacy payload."""

    d1, h4, h1 = _zoned_candles()
    legacy = build_smc_context(d1, h4, h1, symbol="XAUUSD")

    assert set(legacy) >= {"D1", "H4", "H1", "confluence", "domain_version"}
    for timeframe in ("H4", "H1"):
        for zone in legacy[timeframe].get("order_blocks") or []:
            # The legacy detector publishes its own measurements but never the
            # canonical evidence block the evaluator reads.
            assert "departure_measurement" not in zone
            assert "original_bounds" not in zone
        assert "structure" in legacy[timeframe]
        assert "bos" in legacy[timeframe]


def test_the_canonical_facade_produces_canonical_evidence_where_legacy_does_not():
    d1, h4, h1 = _zoned_candles()
    canonical = build_canonical_timeframe_context(
        h4, symbol="XAUUSD", timeframe="H4", as_of=NOW, tick_size=0.01
    )
    assert any(
        zone.get("original_bounds") for zone in canonical["order_blocks"]
    ), "the canonical façade must publish formation evidence"


# ---------------------------------------------------------------------------
# Cutoff discipline
# ---------------------------------------------------------------------------


def test_only_candles_closed_at_the_cutoff_take_part():
    d1, h4, h1 = _zoned_candles()
    cutoff = NOW
    context = build_canonical_timeframe_context(
        h4, symbol="XAUUSD", timeframe="H4", as_of=cutoff, tick_size=0.01
    )
    late = [
        Candle(
            time=cutoff + timedelta(hours=4 * index),
            open=1000.0,
            high=1010.0,
            low=990.0,
            close=1005.0,
        )
        for index in range(1, 6)
    ]
    extended = build_canonical_timeframe_context(
        [*h4, *late], symbol="XAUUSD", timeframe="H4", as_of=cutoff, tick_size=0.01
    )
    assert extended["structure"] == context["structure"]
    assert len(extended["order_blocks"]) == len(context["order_blocks"])
    assert len(extended["fvg"]) == len(context["fvg"])


# ---------------------------------------------------------------------------
# Analyze runtime caller
# ---------------------------------------------------------------------------


def test_analyze_pipeline_uses_the_canonical_snapshot():
    from core.analysis_pipeline import AnalysisPipeline
    from core.risk_engine import AnalysisInput

    d1, h4, h1 = _zoned_candles()
    pipeline = AnalysisPipeline()
    result = pipeline.execute(
        AnalysisInput(
            symbol="XAUUSD",
            broker_symbol="XAUUSD",
            account_balance=10_000.0,
            risk_percent=1.0,
        ),
        {"D1": d1, "H4": h4, "H1": h1},
        snapshot_as_of=NOW,
        tick_size=0.01,
    )
    assert result is not None
    snapshot = pipeline._smc_snapshot
    assert snapshot is not None and snapshot.as_of == NOW
    assert snapshot.core_reason_codes == ()
    # The pipeline reads the SAME canonical result the Scanner would produce.
    evaluation = pipeline._smc_evaluation
    assert evaluation is not None
    assert evaluation.snapshot is snapshot
    for side in ("buy", "sell"):
        assert evaluation.candidate_sets[side].state in {
            "evaluated",
            "no_zone",
            "data_unavailable",
        }
