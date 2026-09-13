"""Task 69 contracts for exclusive sweep ownership and contribution dedupe."""

from __future__ import annotations

from core.smc_sweep_linking import (
    assign_sweep_ownership,
    mark_sweeps_consumed,
)
from core.smc_context import _attach_zone_sweep_links
from core.market_models import Candle
from datetime import datetime, timedelta, timezone


def _claim(
    setup_id: str,
    *,
    sweep_id: str = "sweep-1",
    zone_id: str = "zone-1",
    available_at: str = "2026-09-11T10:05:00+00:00",
) -> dict[str, object]:
    return {
        "sweep_id": sweep_id,
        "setup_id": setup_id,
        "zone_id": zone_id,
        "side": "buy",
        "reclaimed_at": "2026-09-11T10:00:00+00:00",
        "setup_available_at": available_at,
    }


def _sweeps(*items: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    values = list(items) or [_sweep(index=10)]
    return {
        "swept_lows": values,
        "swept_highs": [],
    }


def _sweep(*, index: int) -> dict[str, object]:
    return {
        "sweep_id": "sweep-1",
        "side": "buy",
        "kind": "swept_low",
        "level": 105,
        "index": index,
        "time": f"2026-09-11T{index:02d}:00:00+00:00",
        "reclaimed_at": f"2026-09-11T{index:02d}:00:00+00:00",
    }


def test_same_setup_children_have_one_assignment_and_one_contribution():
    result = assign_sweep_ownership([
        _claim("setup-z", zone_id="child-ob"),
        _claim("setup-z", zone_id="child-fvg"),
    ])

    assert set(result["assignments"]) == {"sweep-1"}
    assert result["assignments"]["sweep-1"]["owner_setup_id"] == "setup-z"
    assert sum(
        claim["contribution_applied"] for claim in result["claims"]
    ) == 1
    assert result["claims"][0]["assignment_id"] == result["claims"][1]["assignment_id"]


def test_owner_is_earliest_claim_time_not_smallest_setup_id():
    result = assign_sweep_ownership([
        _claim("setup-z", available_at="2026-09-11T10:05:00+00:00"),
        _claim(
            "setup-a",
            zone_id="late-child",
            available_at="2026-09-11T10:20:00+00:00",
        ),
    ])

    assignment = result["assignments"]["sweep-1"]
    assert assignment["owner_setup_id"] == "setup-z"
    assert assignment["claim_eligible_at"] == "2026-09-11T10:05:00+00:00"


def test_same_claim_time_uses_stable_setup_id_tie_break():
    result = assign_sweep_ownership([
        _claim("setup-z"),
        _claim("setup-a", zone_id="child-a"),
    ])

    assert result["assignments"]["sweep-1"]["owner_setup_id"] == "setup-a"


def test_existing_owner_history_is_not_revoked_by_late_setup():
    result = assign_sweep_ownership(
        [_claim("setup-a", available_at="2026-09-11T09:00:00+00:00")],
        assignment_history={
            "sweep-1": {
                "owner_setup_id": "setup-z",
                "assignment_id": "assignment-old",
                "assigned_at": "2026-09-11T10:05:00+00:00",
                "claim_eligible_at": "2026-09-11T10:05:00+00:00",
            }
        },
    )

    assert result["assignments"]["sweep-1"]["owner_setup_id"] == "setup-z"
    assert result["assignments"]["sweep-1"]["assignment_id"] == "assignment-old"


def test_missing_owner_history_fails_closed():
    result = assign_sweep_ownership(
        [_claim("setup-z")],
        history_complete=False,
    )

    assert result["assignments"] == {}
    assert result["reason_codes"] == ["SWEEP_OWNER_HISTORY_INCOMPLETE"]


def test_mark_sweeps_consumed_preserves_one_assignment_and_marks_source():
    result = mark_sweeps_consumed(
        _sweeps(),
        [
            _claim("setup-z", zone_id="child-ob"),
            _claim("setup-z", zone_id="child-fvg"),
        ],
    )

    sweep = result["sweeps"]["swept_lows"][0]
    assert sweep["consumed"] is True
    assert sweep["pool_consumed"] is True
    assert sweep["owner_setup_id"] == "setup-z"
    assert sweep["assignment_id"] == result["assignments"]["sweep-1"]["assignment_id"]
    assert sweep["contribution_applied"] is True


def test_assignment_id_is_stable_when_duplicate_claims_are_replayed():
    claims = [_claim("setup-z", zone_id="child-ob"), _claim("setup-z", zone_id="child-fvg")]
    first = assign_sweep_ownership(claims)
    second = assign_sweep_ownership(list(reversed(claims)))

    assert first["assignments"] == second["assignments"]


def test_context_broadcasts_assignment_and_consumed_source_to_setup_children():
    start = datetime(2026, 9, 11, tzinfo=timezone.utc)
    candles = [
        Candle(
            time=start + timedelta(hours=index),
            open=120,
            high=121,
            low=119,
            close=120,
            volume=100,
        )
        for index in range(20)
    ]
    zones = [
        {
            "zone_id": "child-ob",
            "setup_id": "setup-1",
            "low": 100,
            "high": 110,
            "direction": "buy",
            "origin_index": 10,
            "formation_start_index": 8,
            "departure_end_index": 12,
        },
        {
            "zone_id": "child-fvg",
            "setup_id": "setup-1",
            "low": 101,
            "high": 111,
            "direction": "buy",
            "origin_index": 10,
            "formation_start_index": 8,
            "departure_end_index": 12,
        },
    ]
    sweeps = _sweeps(_sweep(index=11))

    _attach_zone_sweep_links(
        (("demand", zones),),
        sweeps,
        candles=candles,
        symbol="EUR/USD",
        timeframe="H1",
        tf_minutes=60,
    )

    assert zones[0]["sweep_assignment_id"] == zones[1]["sweep_assignment_id"]
    assert sum(
        zone["sweep_contribution_applied"] for zone in zones
    ) == 1
    assert sweeps["swept_lows"][0]["consumed"] is True
    assert sweeps["swept_lows"][0]["owner_setup_id"] == "setup-1"
