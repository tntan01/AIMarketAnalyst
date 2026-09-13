"""Task 71 acceptance matrix for liquidity/context evidence ownership."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.smc_confluence import build_d1_reaction_evidence
from core.smc_context import _attach_zone_sweep_links, detect_liquidity_sweeps
from core.smc_sweep_linking import mark_sweeps_consumed


START = datetime(2026, 9, 11, tzinfo=timezone.utc)


def _candles(count: int = 4) -> list[Candle]:
    return [
        Candle(
            time=START + timedelta(hours=index),
            open=100,
            high=101,
            low=99,
            close=100,
            volume=100,
        )
        for index in range(count)
    ]


def _sweep() -> dict[str, object]:
    return {
        "sweep_id": "sweep-context-1",
        "side": "buy",
        "kind": "swept_low",
        "level": 105,
        "index": 2,
        "time": "2026-09-11T02:00:00+00:00",
        "reclaimed_at": "2026-09-11T03:00:00+00:00",
        "source_pool_id": "pool-low-1",
    }


def _claim(setup_id: str, zone_id: str) -> dict[str, object]:
    return {
        "sweep_id": "sweep-context-1",
        "setup_id": setup_id,
        "zone_id": zone_id,
        "side": "buy",
        "reclaimed_at": "2026-09-11T03:00:00+00:00",
        "setup_available_at": "2026-09-11T03:05:00+00:00",
    }


def test_sweep_source_time_and_pool_provenance_are_preserved():
    result = detect_liquidity_sweeps(
        [
            Candle(START, 100, 101, 99.5, 100),
            Candle(START + timedelta(hours=1), 100, 101, 99, 100),
            Candle(START + timedelta(hours=2), 100, 110.3, 99, 109.9),
        ],
        {
            "highs": [],
            "lows": [{"level": 99.2, "index": 1, "swing_id": "pool-low-1"}],
        },
        timeframe="H1",
    )

    sweep = result["swept_lows"][0]
    assert sweep["source_pool_id"] == "pool-low-1"
    assert sweep["reclaimed_at"] == "2026-09-11T02:00:00+00:00"


def test_consumed_evidence_has_one_assignment_and_one_contribution():
    result = mark_sweeps_consumed(
        {"swept_lows": [_sweep()], "swept_highs": []},
        [_claim("setup-1", "ob-child"), _claim("setup-1", "fvg-child")],
    )

    assert len(result["assignments"]) == 1
    assert sum(
        claim["contribution_applied"] for claim in result["claims"]
    ) == 1
    assert result["sweeps"]["swept_lows"][0]["consumed"] is True


def test_duplicate_family_children_share_linked_sweep_without_duplicate_source():
    zones = [
        {
            "zone_id": "ob-child",
            "setup_id": "setup-family",
            "direction": "buy",
            "low": 100,
            "high": 110,
            "origin_index": 1,
            "formation_start_index": 0,
            "departure_end_index": 3,
        },
        {
            "zone_id": "fvg-child",
            "setup_id": "setup-family",
            "direction": "buy",
            "low": 101,
            "high": 111,
            "origin_index": 1,
            "formation_start_index": 0,
            "departure_end_index": 3,
        },
    ]
    sweeps = {"swept_lows": [_sweep()], "swept_highs": []}

    _attach_zone_sweep_links(
        (("demand", zones),),
        sweeps,
        candles=_candles(4),
        symbol="EUR/USD",
        timeframe="H1",
        tf_minutes=60,
    )

    assert zones[0]["linked_sweep_id"] == zones[1]["linked_sweep_id"]
    assert sweeps["swept_lows"][0]["linked_zone_ids"] == [
        "fvg-child",
        "ob-child",
    ]


def test_d1_proximity_only_has_no_reaction_evidence():
    result = build_d1_reaction_evidence(
        {"zone_id": "d1-zone", "proximity": True, "d1_reaction": True},
        {"visits": []},
    )

    assert result["valid"] is False
    assert result["score"] == 0.0


def test_d1_canonical_reaction_is_the_single_source_of_truth():
    lifecycle = {
        "visits": [{
            "zone_id": "d1-zone",
            "visit_id": "d1-zone:visit-1",
            "visit_state": "completed_reacted",
            "reacted_at": "2026-09-11T10:00:00+00:00",
        }],
        "age_bars": 2,
        "lifecycle_stale": False,
        "lifecycle_expired": False,
    }
    canonical = build_d1_reaction_evidence({"zone_id": "d1-zone"}, lifecycle)
    with_legacy = build_d1_reaction_evidence(
        {"zone_id": "d1-zone", "proximity": False, "d1_reaction": False},
        lifecycle,
    )

    assert canonical == with_legacy
    assert canonical["valid"] is True


def test_legacy_conflicting_reaction_flags_cannot_override_open_visit():
    result = build_d1_reaction_evidence(
        {"zone_id": "d1-zone", "d1_reaction": True, "reacted": True},
        {
            "visits": [{
                "zone_id": "d1-zone",
                "visit_id": "d1-zone:visit-1",
                "visit_state": "open",
                "reacted_at": None,
            }]
        },
    )

    assert result["valid"] is False
    assert result["score"] == 0.0
