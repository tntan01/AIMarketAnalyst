"""D101-01 — the canonical façade feeds the snapshot of the real callers.

The public ``build_smc_context`` keeps running the LEGACY detector; the
snapshot seam uses ``core.smc_canonical_context`` instead, so the canonical
evaluator receives canonical evidence on the same closed-candle set.  These
tests go through the RUNTIME callers (Scanner live producer and the Analyze
pipeline), not through synthetic quality fixtures.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from core.market_models import Candle, candle_close_at
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


def _sweep_candles():
    """H4 series with one confirmed swing high and one reclaiming sweep bar."""

    base = datetime(2026, 8, 11, 0, 0, 0, tzinfo=UTC)
    rows: list[Candle] = []

    def add(open_: float, high: float, low: float, close: float) -> None:
        rows.append(
            Candle(
                time=base + timedelta(hours=4 * len(rows)),
                open=open_,
                high=high,
                low=low,
                close=close,
            )
        )

    # ATR warm-up: calm oscillation around 100.
    for _ in range(15):
        add(100.0, 101.0, 99.0, 100.0)
    # Rise into the pivot peak.
    for high in (103.0, 105.0, 107.0, 108.5, 109.5):
        add(high - 1.0, high, high - 2.0, high - 0.5)
    # The pivot high.
    add(109.5, 112.0, 108.5, 109.0)
    # Lower highs on both sides confirm the pivot.
    for high in (110.0, 108.5, 107.0, 105.5, 104.0):
        add(high - 1.0, high, high - 2.0, high - 0.5)
    # Quiet base below the pivot.
    for _ in range(4):
        add(103.0, 104.0, 102.5, 103.5)
    # The sweep bar: wick through the pivot level, close back below it.
    add(103.5, 113.0, 103.0, 110.5)
    # Post-sweep drift keeps the sweep inside the 60-bar lookback.
    for _ in range(19):
        add(106.0, 107.5, 105.0, 106.5)
    return rows


def test_the_facade_feeds_the_sweep_detector_its_threshold_inputs():
    """Ca 1 (smc-bqlc-producer-gaps): sweeps are detected on the canonical path.

    Before the wiring the façade called the detector without tick/ATR, so its
    fail-closed guard returned an empty list on every snapshot and L never saw
    any evidence (NO_RELATED_SWEEP 92/92 in the replay corpus).
    """

    candles = _sweep_candles()
    cutoff = candles[-1].time + timedelta(hours=4)
    context = build_canonical_timeframe_context(
        candles, symbol="EURUSD", timeframe="H4", as_of=cutoff, tick_size=0.01
    )
    swept_highs = context["zone_link_sweeps"]["swept_highs"]
    assert swept_highs, "a wick-through-and-reclaim bar must be detected"
    sweep = swept_highs[0]
    assert sweep["source_pool_id"], "the sweep must carry its pool lineage"
    assert sweep["depth_atr"] is not None


def test_without_a_tick_the_sweep_detector_stays_fail_closed():
    """No computable excursion threshold still yields an empty sweep list."""

    candles = _sweep_candles()
    cutoff = candles[-1].time + timedelta(hours=4)
    context = build_canonical_timeframe_context(
        candles, symbol="EURUSD", timeframe="H4", as_of=cutoff, tick_size=None
    )
    assert context["zone_link_sweeps"]["swept_highs"] == []
    assert context["zone_link_sweeps"]["swept_lows"] == []


def test_the_facade_stamps_the_current_atr_on_every_zone():
    """Ca 2 (smc-bqlc-producer-gaps): the lifecycle rules get their ATR input.

    Before the stamping, ``enrich_zones`` read ``zone["atr_current"]`` that no
    producer ever wrote, so the reaction follow-through, the visit tolerance
    and the break buffer could never compute: ``metadata_state`` stayed
    ``unknown`` and every canonical zone was flagged unusable.
    """

    d1, h4, h1 = _zoned_candles()
    context = build_canonical_timeframe_context(
        h4, symbol="XAUUSD", timeframe="H4", as_of=NOW, tick_size=0.01
    )
    zones = [
        *context["order_blocks"],
        *context["fvg"],
        *context["demand_zones"],
        *context["supply_zones"],
    ]
    assert zones, "the fixture must produce canonical zones"
    for zone in zones:
        atr_current = zone.get("atr_current")
        assert atr_current is not None and atr_current > 0
        assert math.isfinite(atr_current)
        assert zone.get("metadata_state") == "available"


def test_structure_event_age_is_joined_only_for_resolvable_confirmation_events():
    """Ca 3 (smc-bqlc-producer-gaps): the event-age join is fail-closed.

    The evaluator reads ``zone["structure_event_age_bars"]`` for the trigger
    feature but no producer ever wrote it, so every side fell back to the zone
    age with ``STRUCTURE_EVENT_TIME_UNAVAILABLE`` (92/92 in the replay corpus).
    The join stamps exactly the zones whose ``confirmation_event_id`` resolves
    to a concrete closed candle; everything else keeps the fallback.
    """

    from core.smc_canonical_context import _stamp_structure_event_age_bars

    base = datetime(2026, 8, 11, 0, 0, 0, tzinfo=UTC)
    closed = [
        Candle(
            time=base + timedelta(hours=4 * index),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
        )
        for index in range(10)
    ]

    def close_at(index: int) -> str:
        return candle_close_at(closed[index].time, "H4").isoformat()

    events = [
        {"event_id": "bos-early", "occurred_at": close_at(4), "confirmed_at": close_at(4)},
        {"event_id": "bos-last", "occurred_at": close_at(9), "confirmed_at": close_at(9)},
        # confirmed_at matches no candle close; occurred_at does.
        {
            "event_id": "bos-occurred",
            "occurred_at": close_at(3),
            "confirmed_at": "2026-08-11T00:30:00+00:00",
        },
        # Neither timestamp matches a closed candle.
        {
            "event_id": "bos-offgrid",
            "occurred_at": "2026-08-11T01:00:00+00:00",
            "confirmed_at": "2026-08-11T02:00:00+00:00",
        },
        # Unparseable timestamp.
        {
            "event_id": "bos-broken",
            "occurred_at": None,
            "confirmed_at": "not-a-timestamp",
        },
    ]
    zones = [
        {"zone_id": "z-early", "confirmation_event_id": "bos-early"},
        {"zone_id": "z-unconfirmed"},
        {"zone_id": "z-empty", "confirmation_event_id": ""},
        {"zone_id": "z-unknown-event", "confirmation_event_id": "bos-missing"},
        {"zone_id": "z-offgrid", "confirmation_event_id": "bos-offgrid"},
        {"zone_id": "z-broken", "confirmation_event_id": "bos-broken"},
        {"zone_id": "z-occurred", "confirmation_event_id": "bos-occurred"},
        {"zone_id": "z-last", "confirmation_event_id": "bos-last"},
    ]

    _stamp_structure_event_age_bars(zones, events, closed, "H4")

    by_id = {zone["zone_id"]: zone for zone in zones}
    assert by_id["z-early"]["structure_event_age_bars"] == 5
    assert type(by_id["z-early"]["structure_event_age_bars"]) is int
    assert by_id["z-occurred"]["structure_event_age_bars"] == 6
    assert by_id["z-last"]["structure_event_age_bars"] == 0  # clamped at the bar itself
    for zone_id in (
        "z-unconfirmed",
        "z-empty",
        "z-unknown-event",
        "z-offgrid",
        "z-broken",
    ):
        assert "structure_event_age_bars" not in by_id[zone_id]


def test_the_facade_stamps_structure_event_age_on_confirmed_zones():
    """Ca 3 (smc-bqlc-producer-gaps): the canonical payload feeds trigger age.

    The field is produced only for zones carrying a resolvable
    ``confirmation_event_id`` (Owner decision 04/10/2026); every other zone
    keeps the documented ``age_bars`` fallback and no key.  The triangle-wave
    fixture confirms no OB, so a dedicated candle path supplies the positive
    case end to end through the façade.
    """

    d1, h4, h1 = _zoned_candles()
    context = build_canonical_timeframe_context(
        h4, symbol="XAUUSD", timeframe="H4", as_of=NOW, tick_size=0.01
    )
    zones = [
        *context["order_blocks"],
        *context["fvg"],
        *context["demand_zones"],
        *context["supply_zones"],
    ]
    assert zones, "the fixture must produce canonical zones"
    # This fixture confirms no zone against a structure event: the field must
    # stay absent for every one of them (the documented fallback behavior).
    assert all(not zone.get("confirmation_event_id") for zone in zones)
    assert all("structure_event_age_bars" not in zone for zone in zones)

    # Positive case: the dedicated H4 path that really produces a BOS-confirmed
    # order block (same fixture the fast-path OB regression uses).
    from tests.scanner_fast_path_fixtures import _bearish_order_block_path

    candles = _bearish_order_block_path(1.1, 240)
    cutoff = candles[-1].time + timedelta(hours=4)
    ob_context = build_canonical_timeframe_context(
        candles, symbol="EUR/USD", timeframe="H4", as_of=cutoff, tick_size=0.00001
    )
    ob_zones = [
        *ob_context["order_blocks"],
        *ob_context["fvg"],
        *ob_context["demand_zones"],
        *ob_context["supply_zones"],
    ]
    closed = [
        candle for candle in candles if candle_close_at(candle.time, "H4") <= cutoff
    ]
    assert any(zone.get("confirmation_event_id") for zone in ob_zones), (
        "the dedicated OB path must confirm at least one zone"
    )
    for zone in ob_zones:
        if not zone.get("confirmation_event_id"):
            assert "structure_event_age_bars" not in zone
            continue
        age = zone.get("structure_event_age_bars")
        assert type(age) is int and age >= 0
        event = next(
            event
            for event in ob_context["structure_events"]
            if event.get("event_id") == zone["confirmation_event_id"]
        )
        confirm_index = next(
            index
            for index, candle in enumerate(closed)
            if candle_close_at(candle.time, "H4").isoformat()
            == event.get("confirmed_at")
        )
        assert age == len(closed) - 1 - confirm_index


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
