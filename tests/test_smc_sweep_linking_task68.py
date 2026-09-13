"""Task 68 contracts for causal sweep/setup/visit linking."""

from __future__ import annotations

from core.smc_sweep_linking import associate_sweeps_to_zones


def _zone(zone_id: str, *, setup_id: str | None = None, **extra: object) -> dict[str, object]:
    zone: dict[str, object] = {
        "zone_id": zone_id,
        "setup_id": setup_id,
        "direction": "buy",
        "low": 100,
        "high": 110,
        "formation_start_index": 8,
        "origin_index": 10,
        "departure_end_index": 12,
    }
    zone.update(extra)
    return zone


def _sweeps(*items: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    return {"swept_lows": list(items), "swept_highs": []}


def _sweep(sweep_id: str = "sweep-1", *, index: int = 11, level: float = 105) -> dict[str, object]:
    return {
        "sweep_id": sweep_id,
        "side": "buy",
        "kind": "swept_low",
        "level": level,
        "index": index,
        "time": f"2026-09-11T{index:02d}:00:00+00:00",
        "reclaimed_at": f"2026-09-11T{index:02d}:01:00+00:00",
    }


def test_same_setup_children_reference_the_same_sweep():
    links = associate_sweeps_to_zones(
        [
            _zone("ob-child", setup_id="setup-1"),
            _zone("fvg-child", setup_id="setup-1", low=101, high=111),
        ],
        _sweeps(_sweep()),
        atr_value=10,
    )

    assert set(links) == {"ob-child", "fvg-child"}
    assert links["ob-child"].sweep_id == links["fvg-child"].sweep_id == "sweep-1"
    assert links["ob-child"].setup_id == links["fvg-child"].setup_id == "setup-1"


def test_one_sweep_is_not_reused_by_another_setup():
    links = associate_sweeps_to_zones(
        [
            _zone("setup-a-child", setup_id="setup-a"),
            _zone("setup-z-child", setup_id="setup-z"),
        ],
        _sweeps(_sweep()),
        atr_value=10,
    )

    assert len(links) == 1


def test_visit_window_can_link_a_sweep_after_departure():
    links = associate_sweeps_to_zones(
        [
            _zone(
                "zone-visit",
                setup_id="setup-visit",
                visits=[
                    {
                        "visit_id": "zone-visit:visit-1",
                        "start_index": 15,
                        "end_index": 16,
                    }
                ],
            )
        ],
        _sweeps(_sweep(index=15)),
        atr_value=10,
    )

    assert links["zone-visit"].visit_id == "zone-visit:visit-1"
    assert links["zone-visit"].time_delta == 0


def test_link_time_window_is_inclusive_at_twenty_bars():
    valid = associate_sweeps_to_zones(
        [_zone("valid-window", formation_start_index=8, departure_end_index=28)],
        _sweeps(_sweep(index=28)),
        atr_value=10,
    )
    late = associate_sweeps_to_zones(
        [_zone("late-window", formation_start_index=8, departure_end_index=29)],
        _sweeps(_sweep(index=29)),
        atr_value=10,
    )

    assert "valid-window" in valid
    assert late == {}


def test_link_distance_gate_is_inclusive_at_quarter_atr():
    valid = associate_sweeps_to_zones(
        [_zone("distance-boundary")],
        _sweeps(_sweep(level=112.5)),
        atr_value=10,
    )
    invalid = associate_sweeps_to_zones(
        [_zone("distance-over")],
        _sweeps(_sweep(level=112.51)),
        atr_value=10,
    )

    assert "distance-boundary" in valid
    assert invalid == {}
