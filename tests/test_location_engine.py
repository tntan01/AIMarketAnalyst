"""Task B01 tests for the Location engine configuration boundary."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import ast
import inspect
import json
import math

import pytest
import core.location_engine as location_engine_module

from core.indicators import atr
from core.location_engine import (
    DEFAULT_LOCATION_CONFIG,
    LOCATION_CONFIG_VERSION,
    LOCATION_DETAIL_SCHEMA_VERSION,
    LOCATION_MODEL_VERSION,
    LOCATION_ROUNDING_MODE,
    LocationConfig,
    LocationContext,
    LocationDataError,
    LocationObstacleSelection,
    LocationReference,
    LocationResult,
    LocationSwing,
    LocationZone,
    MIN_LOCATION_H4_BARS,
    build_location_context,
    build_location_zones,
    closed_candles_at_cutoff,
    closed_h4_history_at_cutoff,
    deduplicate_location_zones,
    distance_to_interval,
    location_swing_points,
    reference_from_closed_h1,
    resolve_location_config,
    score_location,
    score_location_safe,
    select_location_anchor,
    select_location_obstacle,
    update_location_zone_lifecycle,
    _width_exceeds_max,
    validate_location_config,
    validate_location_inputs,
    validate_location_side,
    validate_location_zone,
)


NOW = datetime(2026, 9, 9, 12, tzinfo=timezone.utc)


def _candles(count=MIN_LOCATION_H4_BARS):
    return [
        {
            "time": NOW - timedelta(hours=4 * (count - index)),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
        }
        for index in range(count)
    ]


def test_default_location_config_matches_plan_and_is_versioned():
    config = DEFAULT_LOCATION_CONFIG

    assert isinstance(config, LocationConfig)
    assert config.config_version == LOCATION_CONFIG_VERSION == "location-config-v1"
    assert config.model_version == LOCATION_MODEL_VERSION == "location-geometry-v2"
    assert config.rounding_mode == LOCATION_ROUNDING_MODE == "ROUND_HALF_UP"
    assert config.raw_max == 25
    assert config.swing_lookback == 2
    assert config.history_h4_bars == 240
    assert config.zone_half_width_atr == 0.15
    assert config.zone_max_width_atr == 1.0
    assert config.invalidation_close_count == 2
    assert config.invalidation_buffer_atr == 0.10
    assert config.zone_max_age_h4_bars == 120
    assert config.proximity_zero_at_atr == 1.0
    assert config.clearance_full_at_atr == 1.0
    assert config.unknown_clearance_factor == 0.5


def test_valid_config_round_trips_without_relabeling_version():
    restored = LocationConfig.from_dict(DEFAULT_LOCATION_CONFIG.to_dict())

    assert restored == DEFAULT_LOCATION_CONFIG


@pytest.mark.parametrize(
    "field, value",
    [
        ("config_version", "location-config-v0"),
        ("config_version", ""),
        ("model_version", "location-geometry-v1"),
        ("model_version", ""),
    ],
)
def test_unsupported_or_empty_config_versions_fail_at_validation(field, value):
    config = resolve_location_config({field: value})

    with pytest.raises(LocationDataError) as error:
        validate_location_config(config)
    assert error.value.code == "UNSUPPORTED_VERSION"
    assert error.value.field == f"config.{field}"


def test_history_config_requires_minimum_but_allows_less_than_desired_window():
    with pytest.raises(LocationDataError) as error:
        validate_location_config(
            resolve_location_config({"history_h4_bars": MIN_LOCATION_H4_BARS - 1})
        )
    assert error.value.field == "config.history_h4_bars"

    validate_location_config(
        resolve_location_config({"history_h4_bars": MIN_LOCATION_H4_BARS})
    )
    validate_location_config(
        resolve_location_config({"history_h4_bars": 240})
    )


def test_location_config_is_immutable():
    with pytest.raises(FrozenInstanceError):
        DEFAULT_LOCATION_CONFIG.raw_max = 20


def test_partial_config_inherits_only_missing_keys():
    resolved = resolve_location_config({"history_h4_bars": 120})

    assert resolved.history_h4_bars == 120
    assert resolved.swing_lookback == DEFAULT_LOCATION_CONFIG.swing_lookback
    assert resolved.model_version == DEFAULT_LOCATION_CONFIG.model_version


def test_explicit_invalid_value_is_not_replaced_by_default():
    resolved = resolve_location_config({"unknown_clearance_factor": 2.0})

    assert resolved.unknown_clearance_factor == 2.0


def test_unknown_config_key_is_rejected_at_resolution_boundary():
    with pytest.raises(KeyError):
        resolve_location_config({"not_a_location_setting": 1})


@pytest.mark.parametrize(
    "field, value",
    [
        ("swing_lookback", None),
        ("swing_lookback", True),
        ("zone_half_width_atr", math.nan),
        ("proximity_zero_at_atr", math.inf),
        ("history_h4_bars", -1),
        ("unknown_clearance_factor", 1.0),
    ],
)
def test_invalid_config_values_raise_typed_error(field, value):
    config = resolve_location_config({field: value})

    with pytest.raises(LocationDataError) as error:
        validate_location_config(config)
    assert error.value.field == f"config.{field}"


def test_short_history_below_minimum_is_rejected_but_less_than_desired_is_allowed():
    validate_location_inputs(
        _candles(MIN_LOCATION_H4_BARS),
        100.0,
        NOW,
        DEFAULT_LOCATION_CONFIG,
    )
    with pytest.raises(LocationDataError) as error:
        validate_location_inputs(
            _candles(MIN_LOCATION_H4_BARS - 1),
            100.0,
            NOW,
            DEFAULT_LOCATION_CONFIG,
        )
    assert error.value.code == "INSUFFICIENT_HISTORY"


def test_h4_history_filters_by_closed_at_before_applying_history_limit():
    candles = _candles(300)
    candles.append(_candle_at(NOW, 999.0))  # open at cutoff; still forming
    config = resolve_location_config({"history_h4_bars": 240})

    history = closed_h4_history_at_cutoff(candles, NOW, config)

    assert len(history) == 240
    assert history[0].open_time == NOW - timedelta(hours=4 * 240)
    assert history[-1].closed_at == NOW
    assert all(item.closed_at <= NOW for item in history)


def test_h4_history_accepts_minimum_closed_bars_plus_forming_bar():
    candles = _candles(MIN_LOCATION_H4_BARS)
    candles.append(_candle_at(NOW, 999.0))

    history = closed_h4_history_at_cutoff(candles, NOW, DEFAULT_LOCATION_CONFIG)

    assert len(history) == MIN_LOCATION_H4_BARS
    assert history[-1].closed_at == NOW


def test_h4_history_rejects_when_minimum_is_missing_after_cutoff_filter():
    candles = _candles(MIN_LOCATION_H4_BARS - 1)
    candles.append(_candle_at(NOW, 999.0))

    with pytest.raises(LocationDataError) as error:
        closed_h4_history_at_cutoff(candles, NOW, DEFAULT_LOCATION_CONFIG)

    assert error.value.code == "INSUFFICIENT_HISTORY"


def test_h4_history_future_ohlc_is_not_consumed_but_order_is_still_checked():
    candles = _candles(MIN_LOCATION_H4_BARS)
    future = _candle_at(NOW, 999.0)
    future["low"] = 1000.0
    future["high"] = 999.0
    candles.append(future)

    history = closed_h4_history_at_cutoff(candles, NOW, DEFAULT_LOCATION_CONFIG)

    assert len(history) == MIN_LOCATION_H4_BARS

    out_of_order = candles[:-1] + [_candle_at(NOW + timedelta(hours=4), 1000.0), candles[-1]]
    with pytest.raises(LocationDataError) as error:
        closed_h4_history_at_cutoff(out_of_order, NOW, DEFAULT_LOCATION_CONFIG)
    assert error.value.code == "INVALID_TIMESTAMP"


def test_closed_candle_limit_is_applied_after_cutoff_filter():
    candles = [
        _candle_at(NOW - timedelta(hours=12), 101.0),
        _candle_at(NOW - timedelta(hours=8), 102.0),
        _candle_at(NOW - timedelta(hours=4), 103.0),
        _candle_at(NOW, 104.0),
    ]

    selected = closed_candles_at_cutoff(candles, "H4", NOW, max_bars=2)

    assert [item.candle["close"] for item in selected] == [102.0, 103.0]


def _swing_candles():
    start = NOW - timedelta(hours=24)
    values = [
        (10.0, 8.0),
        (11.0, 9.0),
        (20.0, 1.0),  # unique swing high and low
        (12.0, 8.0),
        (13.0, 9.0),  # second right candle confirms index 2
        (14.0, 10.0),
    ]
    return [
        {
            "time": start + timedelta(hours=4 * index),
            "open": (high + low) / 2,
            "high": high,
            "low": low,
            "close": (high + low) / 2,
        }
        for index, (high, low) in enumerate(values)
    ]


def test_location_swing_uses_unique_extremum_and_second_right_close():
    candles = _swing_candles()
    cutoff = candles[4]["time"] + timedelta(hours=4)

    swings = location_swing_points(
        candles,
        cutoff,
        resolve_location_config({"history_h4_bars": 60}),
    )

    assert {s.role for s in swings} == {"support", "resistance"}
    assert all(isinstance(s, LocationSwing) for s in swings)
    for swing in swings:
        assert swing.formed_at == candles[2]["time"]
        assert swing.confirmed_at == candles[4]["time"] + timedelta(hours=4)
        assert swing.id == f"{swing.role}:{candles[2]['time'].isoformat()}"


def test_location_swing_rejects_duplicate_extremum_and_missing_right_confirmation():
    duplicate = _swing_candles()
    duplicate[3]["high"] = duplicate[2]["high"]
    duplicate[3]["low"] = duplicate[2]["low"]
    duplicate_swings = location_swing_points(duplicate, NOW, DEFAULT_LOCATION_CONFIG)
    assert not any(s.formed_at == duplicate[2]["time"] for s in duplicate_swings)

    incomplete = _swing_candles()[:4]
    incomplete_swings = location_swing_points(incomplete, NOW, DEFAULT_LOCATION_CONFIG)
    assert incomplete_swings == ()


def test_location_swing_is_not_created_when_second_right_candle_is_after_cutoff():
    candles = _swing_candles()
    cutoff = candles[4]["time"] + timedelta(hours=3)

    swings = location_swing_points(candles, cutoff, DEFAULT_LOCATION_CONFIG)

    assert swings == ()


def test_location_swing_id_is_stable_when_window_prefix_shifts():
    candles = _swing_candles()
    shifted = [
        {
            **candles[0],
            "time": candles[0]["time"] - timedelta(hours=4),
        },
        *candles,
    ]

    original = location_swing_points(candles, NOW, DEFAULT_LOCATION_CONFIG)
    moved = location_swing_points(shifted, NOW, DEFAULT_LOCATION_CONFIG)

    assert {(s.role, s.id) for s in moved} == {(s.role, s.id) for s in original}


@pytest.mark.parametrize("price", [None, math.nan, -1.0])
def test_invalid_reference_price_raises_typed_error(price):
    with pytest.raises(LocationDataError):
        validate_location_inputs(_candles(), price, NOW, DEFAULT_LOCATION_CONFIG)


def test_invalid_side_never_falls_through_to_sell():
    with pytest.raises(LocationDataError) as error:
        validate_location_side("hold")
    assert error.value.code == "INVALID_SIDE"


def test_invalid_timestamps_and_reversed_zone_raise_typed_error():
    candles = _candles()
    candles[5]["time"] = candles[4]["time"]
    with pytest.raises(LocationDataError):
        validate_location_inputs(candles, 100.0, NOW, DEFAULT_LOCATION_CONFIG)

    with pytest.raises(LocationDataError) as error:
        validate_location_zone({"low": 101.0, "high": 99.0})
    assert error.value.code == "INVALID_ZONE"


def test_naive_cutoff_is_rejected_without_timezone_fabrication():
    with pytest.raises(LocationDataError) as error:
        validate_location_inputs(
            _candles(),
            100.0,
            NOW.replace(tzinfo=None),
            DEFAULT_LOCATION_CONFIG,
        )
    assert error.value.code == "INVALID_TIMESTAMP"


def test_build_context_validates_before_placeholder_implementation():
    with pytest.raises(LocationDataError):
        build_location_context(_candles(), 100.0, NOW, DEFAULT_LOCATION_CONFIG, tick_size=0)


def _zone(role="support", status="ACTIVE"):
    return LocationZone(
        id=f"{role}:2026-09-08T00:00:00+00:00",
        role=role,
        low=99.0,
        high=100.0,
        formed_at=NOW - timedelta(days=2),
        confirmed_at=NOW - timedelta(days=1),
        formation_atr=1.0,
        status=status,
    )


def _result(side, status, raw, **overrides):
    values = {
        "side": side,
        "raw": raw,
        "status": status,
        "reason_codes": ("fixture",),
        "reference_price": 100.0,
        "reference_closed_at": NOW,
        "anchor": _zone("support"),
        "obstacle": None,
        "distance_atr": 0.0 if raw is not None else None,
        "clearance_atr": 1.0 if raw is not None else None,
        "proximity_factor": 1.0 if raw is not None else None,
        "clearance_factor": 1.0 if raw is not None else None,
        "model_version": DEFAULT_LOCATION_CONFIG.model_version,
        "config_used": DEFAULT_LOCATION_CONFIG,
    }
    values.update(overrides)
    return LocationResult(**values)


def test_location_context_and_buy_sell_results_are_immutable_and_valid():
    context = LocationContext(
        reference_price=100.0,
        reference_closed_at=NOW,
        cutoff=NOW,
        current_atr_h4=1.0,
        zones=[_zone()],
        h4_bars_considered=MIN_LOCATION_H4_BARS,
        config=DEFAULT_LOCATION_CONFIG,
    )
    buy = _result("buy", "EVALUATED", 25)
    sell = _result("sell", "LIMITED_CONTEXT", 13)
    unavailable = _result(
        "buy",
        "UNAVAILABLE",
        None,
        anchor=None,
        distance_atr=None,
        clearance_atr=None,
        proximity_factor=None,
        clearance_factor=None,
    )

    assert isinstance(context.zones, tuple)
    assert context.zones[0].role == "support"
    assert buy.raw == 25 and sell.raw == 13
    assert unavailable.raw is None
    with pytest.raises(FrozenInstanceError):
        buy.raw = 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": "EVALUATED", "raw": None},
        {"status": "EVALUATED", "raw": True},
        {"status": "LIMITED_CONTEXT", "raw": 26},
        {"status": "UNAVAILABLE", "raw": 0},
        {"status": "UNAVAILABLE", "raw": None, "proximity_factor": 0.5},
    ],
)
def test_location_result_rejects_status_raw_contradictions(kwargs):
    with pytest.raises(LocationDataError):
        _result("buy", kwargs.pop("status"), kwargs.pop("raw"), **kwargs)


@pytest.mark.parametrize("status", ["CONFLICT", "NO_VALID_ANCHOR"])
def test_conflict_and_no_anchor_require_raw_zero_in_constructor_and_parser(status):
    with pytest.raises(LocationDataError):
        _result("buy", status, 25)

    payload = _result("buy", "EVALUATED", 25).to_dict()
    payload["status"] = status
    with pytest.raises(LocationDataError):
        LocationResult.from_dict(payload)


def _candle_at(open_time, close):
    return {
        "time": open_time,
        "open": close - 0.25,
        "high": close + 0.25,
        "low": close - 0.5,
        "close": close,
    }


def test_closed_candle_seam_uses_open_time_boundaries_and_explicit_cutoff():
    h1 = [
        _candle_at(NOW - timedelta(hours=3), 101.0),
        _candle_at(NOW - timedelta(hours=2), 102.0),
        _candle_at(NOW - timedelta(hours=1), 103.0),  # closes exactly at cutoff
        _candle_at(NOW, 104.0),  # open at cutoff: still forming, must be excluded
    ]
    h4 = [
        _candle_at(NOW - timedelta(hours=8), 201.0),
        _candle_at(NOW - timedelta(hours=4), 202.0),  # closes exactly at cutoff
        _candle_at(NOW, 203.0),  # open at cutoff: still forming
    ]

    closed_h1 = closed_candles_at_cutoff(h1, "H1", NOW)
    closed_h4 = closed_candles_at_cutoff(h4, "H4", NOW)
    reference = reference_from_closed_h1(h1, NOW)

    assert [item.open_time for item in closed_h1] == [
        NOW - timedelta(hours=3),
        NOW - timedelta(hours=2),
        NOW - timedelta(hours=1),
    ]
    assert closed_h1[-1].closed_at == NOW
    assert [item.open_time for item in closed_h4] == [
        NOW - timedelta(hours=8),
        NOW - timedelta(hours=4),
    ]
    assert closed_h4[-1].closed_at == NOW
    assert reference.reference_price == 103.0
    assert reference.reference_closed_at == NOW

    future_h1 = h1 + [_candle_at(NOW + timedelta(hours=1), 105.0)]
    future_h4 = h4 + [_candle_at(NOW + timedelta(hours=4), 204.0)]
    assert closed_candles_at_cutoff(future_h1, "H1", NOW) == closed_h1
    assert closed_candles_at_cutoff(future_h4, "H4", NOW) == closed_h4
    assert reference_from_closed_h1(future_h1, NOW) == reference


def test_zone_rejects_invalid_lifecycle_geometry():
    with pytest.raises(LocationDataError):
        LocationZone(
            id="bad",
            role="support",
            low=101.0,
            high=99.0,
            formed_at=NOW,
            confirmed_at=NOW,
            formation_atr=1.0,
            status="ACTIVE",
        )


def test_location_detail_round_trip_preserves_zero_null_reason_time_version_and_config():
    conflict = _result(
        "buy",
        "CONFLICT",
        0,
        reason_codes=("LOCATION_CONFLICT",),
        obstacle=_zone("resistance"),
    )
    unavailable = _result(
        "sell",
        "UNAVAILABLE",
        None,
        reason_codes=("LOCATION_INVALID_DATA",),
        anchor=None,
        distance_atr=None,
        clearance_atr=None,
        proximity_factor=None,
        clearance_factor=None,
    )

    for original in (conflict, unavailable):
        payload = original.to_dict()
        assert payload["schema_version"] == LOCATION_DETAIL_SCHEMA_VERSION
        assert json.dumps(payload, allow_nan=False)
        restored = LocationResult.from_dict(payload)
        assert restored == original
        assert restored.raw == original.raw
        assert restored.reference_closed_at == original.reference_closed_at
        assert restored.config_used == DEFAULT_LOCATION_CONFIG


def test_context_round_trip_keeps_zones_and_cutoff_without_candles():
    context = LocationContext(
        reference_price=100.0,
        reference_closed_at=NOW,
        cutoff=NOW,
        current_atr_h4=1.0,
        zones=(_zone(),),
        h4_bars_considered=MIN_LOCATION_H4_BARS,
        config=DEFAULT_LOCATION_CONFIG,
    )

    restored = LocationContext.from_dict(context.to_dict())

    assert restored == context
    assert "closed_h4" not in context.to_dict()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update(model_version="location-geometry-v1"),
        lambda payload: payload.pop("model_version"),
        lambda payload: payload.update(schema_version="location-detail-v0"),
    ],
)
def test_location_parser_rejects_unknown_or_missing_version(mutate):
    payload = _result("buy", "EVALUATED", 0).to_dict()
    mutate(payload)

    with pytest.raises(LocationDataError) as error:
        LocationResult.from_dict(payload)
    assert error.value.code == "UNSUPPORTED_VERSION"


def test_location_detail_rejects_non_json_finite_values():
    payload = _result("buy", "EVALUATED", 0).to_dict()
    payload["distance_atr"] = math.inf

    with pytest.raises(ValueError):
        json.dumps(payload, allow_nan=False)
    with pytest.raises(LocationDataError):
        LocationResult.from_dict(payload)


@pytest.mark.parametrize("field", ["config_version", "model_version"])
def test_config_parser_rejects_missing_or_unknown_version(field):
    payload = DEFAULT_LOCATION_CONFIG.to_dict()
    payload[field] = "location-unknown-v0"
    with pytest.raises(LocationDataError) as error:
        LocationConfig.from_dict(payload)
    assert error.value.code == "UNSUPPORTED_VERSION"
    assert error.value.field == f"config.{field}"

    payload.pop(field)
    with pytest.raises(LocationDataError) as error:
        LocationConfig.from_dict(payload)
    assert error.value.code == "UNSUPPORTED_VERSION"
    assert error.value.field == f"config.{field}"


def _zone_history(*, swing_index=20):
    start = NOW - timedelta(hours=4 * 60)
    candles = []
    for index in range(60):
        high, low = 101.0, 99.0
        if index == swing_index:
            high, low = 105.0, 95.0
        candles.append(
            {
                "time": start + timedelta(hours=4 * index),
                "open": 100.0,
                "high": high,
                "low": low,
                "close": 100.0,
            }
        )
    return candles


def test_location_zones_use_atr_at_confirmation_and_persist_formation_atr():
    candles = _zone_history()
    config = resolve_location_config({"history_h4_bars": 240})
    zones = build_location_zones(candles, NOW, config)

    highs = [item["high"] for item in candles]
    lows = [item["low"] for item in candles]
    closes = [item["close"] for item in candles]
    atr_values = atr(highs, lows, closes, 14)
    formation_atr = atr_values[22]
    assert formation_atr is not None

    assert {zone.role for zone in zones} == {"support", "resistance"}
    for zone in zones:
        assert zone.confirmed_at == candles[22]["time"] + timedelta(hours=4)
        assert zone.formation_atr == formation_atr
        assert zone.high - zone.low == pytest.approx(
            config.zone_half_width_atr * formation_atr * 2
        )


def test_location_zones_round_tick_outward_and_reject_invalid_tick():
    candles = _zone_history()
    config = resolve_location_config({"history_h4_bars": 240})
    zones = build_location_zones(candles, NOW, config, tick_size=1.0)

    assert zones
    for zone in zones:
        assert zone.low == pytest.approx(round(zone.low))
        assert zone.high == pytest.approx(round(zone.high))
        assert zone.high > zone.low
        assert zone.high - zone.low >= 1.0

    with pytest.raises(LocationDataError) as error:
        build_location_zones(candles, NOW, config, tick_size=0)
    assert error.value.field == "tick_size"


def test_location_zones_skip_swing_without_atr_at_confirmation():
    candles = _zone_history(swing_index=2)

    zones = build_location_zones(candles, NOW, DEFAULT_LOCATION_CONFIG)

    assert zones == ()


def test_location_zones_check_max_width_after_tick_rounding():
    candles = _zone_history()
    config = resolve_location_config({"zone_max_width_atr": 0.1})

    zones = build_location_zones(candles, NOW, config)

    assert zones == ()


def test_location_zone_boundary_does_not_change_when_later_atr_changes():
    candles = _zone_history()
    initial = build_location_zones(candles, NOW, DEFAULT_LOCATION_CONFIG)

    later = list(candles)
    last_time = later[-1]["time"]
    for index in range(10):
        later.append(
            {
                "time": last_time + timedelta(hours=4 * (index + 1)),
                "open": 100.0,
                "high": 140.0,
                "low": 60.0,
                "close": 100.0,
            }
        )
    later_cutoff = later[-1]["time"] + timedelta(hours=4)
    rebuilt = build_location_zones(later, later_cutoff, DEFAULT_LOCATION_CONFIG)

    initial_by_id = {zone.id: zone for zone in initial}
    rebuilt_by_id = {zone.id: zone for zone in rebuilt}
    assert initial_by_id
    for zone_id, zone in initial_by_id.items():
        assert rebuilt_by_id[zone_id].low == zone.low
        assert rebuilt_by_id[zone_id].high == zone.high
        assert rebuilt_by_id[zone_id].formation_atr == zone.formation_atr


def test_location_zone_dedup_keeps_exact_duplicates_once_and_sorts_stably():
    support = _zone("support")
    resistance = _zone("resistance")

    forward = deduplicate_location_zones((resistance, support, support))
    reverse = deduplicate_location_zones((support, resistance))

    assert forward == reverse
    assert [zone.role for zone in forward] == ["support", "resistance"]


def test_location_zone_dedup_rejects_conflicting_same_id_and_keeps_nearby_ids():
    support = _zone("support")
    conflicting = replace(support, low=98.5)
    nearby = replace(support, id="support:nearby", low=99.1, high=100.1)

    with pytest.raises(LocationDataError) as error:
        deduplicate_location_zones((support, conflicting))
    assert error.value.code == "CONFLICTING_ZONE_ID"

    result = deduplicate_location_zones((support, nearby))
    assert len(result) == 2
    assert {zone.id for zone in result} == {support.id, nearby.id}


def test_location_context_is_causal_when_future_candles_are_appended():
    candles = _zone_history()
    prefix_context = build_location_context(
        candles,
        100.0,
        NOW,
        DEFAULT_LOCATION_CONFIG,
    )

    with_future = [*candles, {
        "time": NOW,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.0,
    }]
    future_context = build_location_context(
        with_future,
        100.0,
        NOW,
        DEFAULT_LOCATION_CONFIG,
    )

    assert future_context == prefix_context
    assert future_context.h4_bars_considered == len(candles)
    assert all(zone.confirmed_at <= NOW for zone in future_context.zones)


def test_location_context_is_side_neutral_and_can_be_shared_for_both_sides():
    context = build_location_context(
        _zone_history(),
        100.0,
        NOW,
        DEFAULT_LOCATION_CONFIG,
    )

    buy_context = context
    sell_context = context

    assert buy_context is sell_context
    assert buy_context.zones == sell_context.zones
    assert buy_context.cutoff == sell_context.cutoff == NOW
    assert buy_context.reference_price == sell_context.reference_price == 100.0


def test_location_context_records_actual_filtered_history_and_fixed_atr():
    candles = _zone_history()
    context = build_location_context(
        candles,
        100.0,
        NOW,
        resolve_location_config({"history_h4_bars": 60}),
    )

    assert context.h4_bars_considered == 60
    expected_atr = atr(
        [item["high"] for item in candles],
        [item["low"] for item in candles],
        [item["close"] for item in candles],
        14,
    )[-1]
    assert context.current_atr_h4 == pytest.approx(expected_atr)
    assert context.reference_closed_at is None


@pytest.mark.parametrize(
    "half_width_atr, expected_zone_count",
    [
        (0.499999, 2),  # just below max width: 2 * half_width < 1 ATR
        (0.5, 2),       # exactly max width: must survive float noise
        (0.500001, 0),  # materially over max width: must be rejected
    ],
)
def test_location_zone_max_width_handles_equal_below_and_real_overflow(
    half_width_atr,
    expected_zone_count,
):
    config = resolve_location_config({"zone_half_width_atr": half_width_atr})

    zones = build_location_zones(_zone_history(), NOW, config)

    assert len(zones) == expected_zone_count


def test_location_zone_max_width_handles_tick_subtraction_at_01_tick():
    # This keeps the rounded width within the configured limit while still
    # exercising the price-level subtraction at a decimal tick.
    config = resolve_location_config({
        "zone_half_width_atr": 0.5,
        "zone_max_width_atr": 1.01,
    })

    zones = build_location_zones(_zone_history(), NOW, config, tick_size=0.01)

    assert len(zones) == 2


@pytest.mark.parametrize(
    "low, high",
    [
        (100.27, 100.28),
        (2000.32, 2000.33),
    ],
)
def test_width_max_tolerance_accounts_for_price_operand_subtraction(low, high):
    assert not _width_exceeds_max(
        low,
        high,
        0.01,
        1.0,
        raw_low=low,
        raw_high=high,
        tick_size=0.01,
    )
    assert _width_exceeds_max(
        low,
        high + 0.0001,
        0.01,
        1.0,
        raw_low=low,
        raw_high=high + 0.0001,
        tick_size=0.01,
    )


def test_location_context_keeps_h1_reference_time_and_ignores_future_h1():
    h4 = _zone_history()
    h1 = [
        _candle_at(NOW - timedelta(hours=3), 101.0),
        _candle_at(NOW - timedelta(hours=2), 102.0),
        _candle_at(NOW - timedelta(hours=1), 103.0),
        _candle_at(NOW, 104.0),
    ]
    reference = reference_from_closed_h1(h1, NOW)
    context = build_location_context(
        h4,
        reference,
        NOW,
        DEFAULT_LOCATION_CONFIG,
    )

    future_h1 = [*h1, _candle_at(NOW + timedelta(hours=1), 105.0)]
    future_reference = reference_from_closed_h1(future_h1, NOW)
    future_context = build_location_context(
        h4,
        future_reference,
        NOW,
        DEFAULT_LOCATION_CONFIG,
    )

    assert context.reference_price == 103.0
    assert context.reference_closed_at == NOW
    assert future_reference == reference
    assert future_context == context


def test_location_context_rejects_reference_close_after_cutoff():
    reference = LocationReference(
        reference_price=100.0,
        reference_closed_at=NOW + timedelta(hours=1),
    )

    with pytest.raises(LocationDataError) as error:
        build_location_context(
            _zone_history(),
            reference,
            NOW,
            DEFAULT_LOCATION_CONFIG,
        )

    assert error.value.code == "FUTURE_DATA"


@pytest.mark.parametrize(
    "price, low, high, expected",
    [
        (100.0, 99.0, 101.0, 0.0),
        (99.0, 99.0, 101.0, 0.0),
        (101.0, 99.0, 101.0, 0.0),
        (98.5, 99.0, 101.0, 0.5),
        (101.5, 99.0, 101.0, 0.5),
    ],
)
def test_distance_to_interval_uses_nearest_edge(price, low, high, expected):
    assert distance_to_interval(price, low, high) == expected


def _context_for_anchor(reference_price, zones):
    return LocationContext(
        reference_price=reference_price,
        reference_closed_at=NOW,
        cutoff=NOW,
        current_atr_h4=1.0,
        zones=tuple(zones),
        h4_bars_considered=MIN_LOCATION_H4_BARS,
        config=DEFAULT_LOCATION_CONFIG,
    )


@pytest.mark.parametrize("side, role", [("buy", "support"), ("sell", "resistance")])
def test_anchor_requires_directional_role_active_status_and_correct_side(side, role):
    valid = _zone(role)
    wrong_side = replace(
        valid,
        id=f"{role}:wrong-side",
        low=101.0,
        high=102.0,
    )
    suspect = replace(valid, id=f"{role}:suspect", status="SUSPECT")
    expired = replace(valid, id=f"{role}:expired", status="EXPIRED")
    invalidated = replace(valid, id=f"{role}:invalidated", status="INVALIDATED")
    unconfirmed = replace(
        valid,
        id=f"{role}:unconfirmed",
        confirmed_at=NOW + timedelta(hours=1),
    )
    context = _context_for_anchor(
        100.0,
        (wrong_side, suspect, expired, invalidated, unconfirmed, valid),
    )

    assert select_location_anchor(side, context) == valid


@pytest.mark.parametrize("side, role", [("buy", "support"), ("sell", "resistance")])
def test_anchor_tie_break_is_independent_of_input_order(side, role):
    base = _zone(role)
    wide = replace(base, id=f"{role}:wide", low=98.0, high=102.0)
    narrow = replace(base, id=f"{role}:narrow", low=99.0, high=101.0)
    newer = replace(
        narrow,
        id=f"{role}:newer",
        confirmed_at=NOW - timedelta(hours=1),
        formed_at=NOW - timedelta(hours=2),
    )
    same_time_a = replace(
        newer,
        id=f"{role}:a",
        confirmed_at=NOW - timedelta(hours=2),
    )
    same_time_b = replace(
        newer,
        id=f"{role}:b",
        confirmed_at=NOW - timedelta(hours=2),
    )
    context_a = _context_for_anchor(
        100.0,
        (same_time_b, wide, same_time_a, newer, narrow),
    )
    context_b = _context_for_anchor(
        100.0,
        (narrow, newer, same_time_a, wide, same_time_b),
    )

    assert select_location_anchor(side, context_a) == select_location_anchor(side, context_b)
    assert select_location_anchor(side, context_a) == newer
    lexical_context = _context_for_anchor(100.0, (same_time_b, same_time_a))
    assert select_location_anchor(side, lexical_context) == same_time_a


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_anchor_returns_none_when_no_valid_directional_anchor_exists(side):
    role = "support" if side == "buy" else "resistance"
    zone = _zone(role, status="SUSPECT")

    assert select_location_anchor(side, _context_for_anchor(100.0, (zone,))) is None


@pytest.mark.parametrize("side, role", [("buy", "resistance"), ("sell", "support")])
def test_obstacle_conflict_has_priority_and_includes_both_interval_edges(side, role):
    containing = _zone(role)
    edge_context = _context_for_anchor(99.0, (containing,))
    conflict = select_location_obstacle(side, edge_context)

    assert isinstance(conflict, LocationObstacleSelection)
    assert conflict.conflict is True
    assert conflict.obstacle == containing
    assert conflict.clearance_distance == 0.0


@pytest.mark.parametrize("side, role", [("buy", "resistance"), ("sell", "support")])
def test_obstacle_selects_nearest_forward_edge_and_accepts_suspect(side, role):
    forward_near = replace(
        _zone(role),
        id=f"{role}:near",
        low=103.0,
        high=104.0,
        status="SUSPECT",
    )
    forward_far = replace(
        forward_near,
        id=f"{role}:far",
        low=105.0,
        high=106.0,
        status="ACTIVE",
    )
    if side == "sell":
        forward_near = replace(forward_near, low=96.0, high=97.0)
        forward_far = replace(forward_far, low=94.0, high=95.0)

    selected = select_location_obstacle(
        side,
        _context_for_anchor(100.0, (forward_far, forward_near)),
    )

    assert selected.conflict is False
    assert selected.obstacle == forward_near
    assert selected.clearance_distance == 3.0


@pytest.mark.parametrize("side, role", [("buy", "resistance"), ("sell", "support")])
def test_obstacle_ignores_behind_invalidated_expired_and_unconfirmed_zones(side, role):
    behind = replace(
        _zone(role),
        id=f"{role}:behind",
        low=90.0 if side == "buy" else 101.0,
        high=95.0 if side == "buy" else 102.0,
    )
    invalidated = replace(
        behind,
        id=f"{role}:invalidated",
        status="INVALIDATED",
        low=103.0 if side == "buy" else 96.0,
        high=104.0 if side == "buy" else 97.0,
    )
    expired = replace(
        invalidated,
        id=f"{role}:expired",
        status="EXPIRED",
    )
    unconfirmed = replace(
        invalidated,
        id=f"{role}:unconfirmed",
        status="ACTIVE",
        confirmed_at=NOW + timedelta(hours=1),
    )

    selected = select_location_obstacle(
        side,
        _context_for_anchor(100.0, (behind, invalidated, expired, unconfirmed)),
    )

    assert selected.obstacle is None
    assert selected.conflict is False
    assert selected.clearance_distance is None


def test_obstacle_conflict_is_reported_even_without_an_anchor():
    obstacle = replace(
        _zone("resistance"),
        id="resistance:conflict-only",
        low=99.0,
        high=101.0,
    )
    context = _context_for_anchor(100.0, (obstacle,))

    assert select_location_anchor("buy", context) is None
    result = select_location_obstacle("buy", context)
    assert result.conflict is True
    assert result.obstacle == obstacle


def _score_context(reference_price, zones, *, atr_value=1.0, config=None):
    return LocationContext(
        reference_price=reference_price,
        reference_closed_at=NOW,
        cutoff=NOW,
        current_atr_h4=atr_value,
        zones=tuple(zones),
        h4_bars_considered=MIN_LOCATION_H4_BARS,
        config=config or DEFAULT_LOCATION_CONFIG,
    )


def test_score_location_returns_25_inside_anchor_with_full_clearance():
    anchor = replace(_zone("support"), low=99.0, high=100.0)
    obstacle = replace(
        _zone("resistance"),
        id="resistance:far",
        low=103.0,
        high=104.0,
    )

    result = score_location("buy", _score_context(100.0, (anchor, obstacle)))

    assert result.raw == 25
    assert result.raw_exact == pytest.approx(25.0)
    assert result.proximity_factor == pytest.approx(1.0)
    assert result.clearance_factor == pytest.approx(1.0)
    assert result.distance_atr == pytest.approx(0.0)
    assert result.clearance_atr == pytest.approx(3.0)


def test_score_location_uses_continuous_proximity_and_half_up_rounding():
    anchor = replace(_zone("support"), low=99.0, high=99.5)
    obstacle = replace(
        _zone("resistance"),
        id="resistance:far",
        low=103.0,
        high=104.0,
    )
    context = _score_context(100.0, (anchor, obstacle))

    result = score_location("buy", context)

    assert result.distance_atr == pytest.approx(0.5)
    assert result.raw_exact == pytest.approx(12.5)
    assert result.raw == 13

    closer = replace(anchor, low=99.0, high=99.4999)
    closer_result = score_location("buy", _score_context(100.0, (closer, obstacle)))
    assert closer_result.raw_exact == pytest.approx(12.4975)
    assert closer_result.raw == 12


@pytest.mark.parametrize(
    "side, anchor, obstacle",
    [
        (
            "buy",
            replace(_zone("support"), low=1.0990, high=1.0995),
            replace(
                _zone("resistance"),
                id="resistance:fx-buy",
                low=1.1020,
                high=1.1030,
            ),
        ),
        (
            "sell",
            replace(
                _zone("resistance"),
                id="resistance:fx-sell",
                low=1.1005,
                high=1.1010,
            ),
            replace(
                _zone("support"),
                id="support:fx-sell",
                low=1.0970,
                high=1.0980,
            ),
        ),
    ],
)
def test_score_location_rounds_fx_half_atr_up_for_both_sides(side, anchor, obstacle):
    result = score_location(
        side,
        _score_context(1.1, (anchor, obstacle), atr_value=0.001),
    )

    assert result.distance_atr == pytest.approx(0.5)
    assert result.clearance_factor == pytest.approx(1.0)
    assert result.raw_exact == pytest.approx(12.5)
    assert result.raw == 13


def test_score_location_uses_clearance_to_obstacle_edge():
    anchor = replace(_zone("support"), low=99.0, high=100.0)
    obstacle = replace(
        _zone("resistance"),
        id="resistance:near",
        low=100.2,
        high=101.0,
    )

    result = score_location("buy", _score_context(100.0, (anchor, obstacle)))

    assert result.clearance_atr == pytest.approx(0.2)
    assert result.clearance_factor == pytest.approx(0.2)
    assert result.raw_exact == pytest.approx(5.0)
    assert result.raw == 5


def test_score_location_uses_unknown_clearance_factor_without_obstacle():
    anchor = replace(_zone("support"), low=99.0, high=100.0)

    result = score_location("buy", _score_context(100.0, (anchor,)))

    assert result.status == "LIMITED_CONTEXT"
    assert result.reason_codes == ("LOCATION_LIMITED_CONTEXT",)
    assert result.obstacle is None
    assert result.clearance_atr is None
    assert result.clearance_factor == pytest.approx(0.5)
    assert result.raw_exact == pytest.approx(12.5)
    assert result.raw == 13


def test_score_location_prioritizes_conflict_and_no_anchor():
    anchor = replace(_zone("support"), low=99.0, high=100.0)
    obstacle = replace(
        _zone("resistance"),
        id="resistance:conflict",
        low=99.5,
        high=100.5,
    )
    conflict = score_location("buy", _score_context(100.0, (anchor, obstacle)))
    no_anchor = score_location("buy", _score_context(100.0, (obstacle,)))

    assert conflict.status == "CONFLICT"
    assert conflict.raw == 0
    assert conflict.reason_codes == ("LOCATION_CONFLICT",)
    assert no_anchor.status == "CONFLICT"
    assert no_anchor.raw == 0


def test_score_location_returns_zero_for_missing_or_too_far_anchor():
    obstacle = replace(
        _zone("resistance"),
        id="resistance:far",
        low=103.0,
        high=104.0,
    )
    no_anchor = score_location("buy", _score_context(100.0, (obstacle,)))
    far_anchor = replace(_zone("support"), low=98.0, high=99.0)
    too_far = score_location("buy", _score_context(100.0, (far_anchor, obstacle)))

    assert no_anchor.status == "NO_VALID_ANCHOR"
    assert no_anchor.raw == 0
    assert too_far.reason_codes == ("LOCATION_ANCHOR_TOO_FAR",)
    assert too_far.raw == 0


def test_score_location_keeps_limited_context_when_far_anchor_has_no_obstacle():
    far_anchor = replace(_zone("support"), low=98.0, high=99.0)

    result = score_location("buy", _score_context(100.0, (far_anchor,)))

    assert result.status == "LIMITED_CONTEXT"
    assert result.raw == 0
    assert result.reason_codes == (
        "LOCATION_ANCHOR_TOO_FAR",
        "LOCATION_LIMITED_CONTEXT",
    )


@pytest.mark.parametrize(
    "reference_price, expected_status",
    [
        (100.0, "LIMITED_CONTEXT"),
        (100.25, "LIMITED_CONTEXT"),
        (100.5, "LIMITED_CONTEXT"),
        (100.75, "LIMITED_CONTEXT"),
        (101.0, "LIMITED_CONTEXT"),
    ],
)
def test_score_location_is_monotone_when_only_anchor_distance_increases(
    reference_price, expected_status
):
    anchor = replace(_zone("support"), low=99.0, high=100.0)
    result = score_location("buy", _score_context(reference_price, (anchor,)))

    assert result.status == expected_status


def test_score_location_anchor_proximity_is_non_increasing_without_reimplementing_formula():
    anchor = replace(_zone("support"), low=99.0, high=100.0)
    results = [
        score_location("buy", _score_context(price, (anchor,)))
        for price in (100.0, 100.25, 100.5, 100.75, 101.0)
    ]

    assert [result.distance_atr for result in results] == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert all(
        earlier.raw >= later.raw
        for earlier, later in zip(results, results[1:])
    )
    assert all(
        earlier.proximity_factor >= later.proximity_factor
        for earlier, later in zip(results, results[1:])
    )


def test_score_location_clearance_is_non_decreasing_when_only_obstacle_moves_forward():
    anchor = replace(_zone("support"), low=99.0, high=100.0)
    results = []
    for index, low in enumerate((100.2, 100.5, 101.0)):
        obstacle = replace(
            _zone("resistance"),
            id=f"resistance:clearance-{index}",
            low=low,
            high=low + 1.0,
        )
        results.append(score_location("buy", _score_context(100.0, (anchor, obstacle))))

    assert [result.distance_atr for result in results] == [0.0, 0.0, 0.0]
    assert [result.clearance_atr for result in results] == pytest.approx([0.2, 0.5, 1.0])
    assert all(
        earlier.raw <= later.raw
        for earlier, later in zip(results, results[1:])
    )
    assert [result.raw for result in results] == [5, 13, 25]


def test_score_location_reflects_buy_and_sell_geometry():
    buy_anchor = replace(_zone("support"), low=99.0, high=100.0)
    buy_obstacle = replace(
        _zone("resistance"),
        id="resistance:forward",
        low=102.0,
        high=103.0,
    )
    sell_anchor = replace(
        _zone("resistance"),
        id="resistance:reflected-anchor",
        low=100.0,
        high=101.0,
    )
    sell_obstacle = replace(
        _zone("support"),
        id="support:reflected-obstacle",
        low=97.0,
        high=98.0,
    )

    buy = score_location("buy", _score_context(100.0, (buy_anchor, buy_obstacle)))
    sell = score_location("sell", _score_context(100.0, (sell_anchor, sell_obstacle)))

    assert sell.raw == buy.raw
    assert sell.raw_exact == pytest.approx(buy.raw_exact)
    assert sell.distance_atr == pytest.approx(buy.distance_atr)
    assert sell.clearance_atr == pytest.approx(buy.clearance_atr)
    assert sell.proximity_factor == pytest.approx(buy.proximity_factor)
    assert sell.clearance_factor == pytest.approx(buy.clearance_factor)
    assert sell.status == buy.status == "EVALUATED"
    assert sell.anchor.low == pytest.approx(200.0 - buy.anchor.high)
    assert sell.anchor.high == pytest.approx(200.0 - buy.anchor.low)
    assert sell.obstacle.low == pytest.approx(200.0 - buy.obstacle.high)
    assert sell.obstacle.high == pytest.approx(200.0 - buy.obstacle.low)


def test_score_location_is_invariant_to_zone_input_order_and_future_append():
    anchor = replace(_zone("support"), low=99.0, high=100.0)
    obstacle = replace(
        _zone("resistance"),
        id="resistance:forward",
        low=102.0,
        high=103.0,
    )
    ordered = _score_context(100.0, (anchor, obstacle))
    reversed_zones = _score_context(100.0, (obstacle, anchor))

    assert score_location("buy", ordered) == score_location("buy", reversed_zones)

    base_candles = _zone_history()
    base_context = build_location_context(base_candles, 100.0, NOW, DEFAULT_LOCATION_CONFIG)
    future_context = build_location_context(
        [
            *base_candles,
            {
                "time": NOW,
                "open": 100.0,
                "high": 140.0,
                "low": 60.0,
                "close": 100.0,
            },
        ],
        100.0,
        NOW,
        DEFAULT_LOCATION_CONFIG,
    )
    assert score_location("buy", base_context) == score_location("buy", future_context)


def test_location_engine_import_scope_excludes_non_location_dependencies():
    tree = ast.parse(inspect.getsource(location_engine_module))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )

    forbidden_prefixes = (
        "news",
        "order",
        "ai",
        "smc",
        "scenario",
        "risk_reward",
    )
    assert not any(
        module.lower().startswith(forbidden_prefixes)
        for module in imported_modules
    )
    assert imported_modules == {
        "__future__",
        "dataclasses",
        "datetime",
        "decimal",
        "math",
        "numbers",
        "typing",
        "core.indicators",
    }


def test_score_location_safe_distinguishes_unavailable_from_zero_scores():
    obstacle = replace(
        _zone("resistance"),
        id="resistance:far",
        low=103.0,
        high=104.0,
    )
    no_anchor = score_location("buy", _score_context(100.0, (obstacle,)))
    unavailable_context = replace(
        _score_context(100.0, (obstacle,)),
        current_atr_h4=None,
    )

    with pytest.raises(LocationDataError) as error:
        score_location("buy", unavailable_context)
    assert error.value.field == "context.current_atr_h4"

    unavailable = score_location_safe("buy", unavailable_context)

    assert no_anchor.status == "NO_VALID_ANCHOR"
    assert no_anchor.raw == 0
    assert no_anchor.reason_codes == ("LOCATION_NO_VALID_ANCHOR",)
    assert unavailable.status == "UNAVAILABLE"
    assert unavailable.raw is None
    assert unavailable.reason_codes == ("LOCATION_INVALID_DATA",)
    assert unavailable.reference_price == 100.0
    assert unavailable.reference_closed_at == NOW
    assert unavailable.config_used == DEFAULT_LOCATION_CONFIG
    assert unavailable.distance_atr is None
    assert unavailable.clearance_atr is None
    assert unavailable.proximity_factor is None
    assert unavailable.clearance_factor is None
    assert LocationResult.from_dict(unavailable.to_dict()) == unavailable


def test_score_location_safe_does_not_swallow_programming_errors(monkeypatch):
    context = _score_context(100.0, (_zone("support"),))

    def broken_selector(*args, **kwargs):
        raise RuntimeError("programming failure")

    monkeypatch.setattr("core.location_engine.select_location_obstacle", broken_selector)

    with pytest.raises(RuntimeError, match="programming failure"):
        score_location_safe("buy", context)


def _lifecycle_zone(candles, role="support", *, status="ACTIVE", confirmation_index=22):
    confirmed_at = candles[confirmation_index]["time"] + timedelta(hours=4)
    return LocationZone(
        id=f"{role}:lifecycle",
        role=role,
        low=99.0,
        high=101.0,
        formed_at=candles[confirmation_index - 2]["time"],
        confirmed_at=confirmed_at,
        formation_atr=1.0,
        status=status,
    )


def _set_close(candle, close, *, high=None, low=None):
    candle["close"] = close
    candle["open"] = close
    candle["high"] = close if high is None else high
    candle["low"] = close if low is None else low


@pytest.mark.parametrize("role", ["support", "resistance"])
def test_lifecycle_wick_and_close_on_break_line_are_not_breaches(role):
    candles = _zone_history()
    zone = _lifecycle_zone(candles, role)
    if role == "support":
        _set_close(candles[23], 100.0, low=98.0)
        _set_close(candles[24], 98.9)
    else:
        _set_close(candles[23], 100.0, high=102.0)
        _set_close(candles[24], 101.1)

    updated = update_location_zone_lifecycle(
        (zone,), candles, NOW, DEFAULT_LOCATION_CONFIG
    )

    assert updated[0].status == "ACTIVE"


@pytest.mark.parametrize("role", ["support", "resistance"])
def test_lifecycle_one_close_is_suspect_and_two_consecutive_closes_invalidate(role):
    candles = _zone_history()
    zone = _lifecycle_zone(candles, role)
    if role == "support":
        _set_close(candles[-1], 98.0)
        one_breach = [dict(candle) for candle in candles]
        _set_close(candles[-2], 98.0)
    else:
        _set_close(candles[-1], 102.0)
        one_breach = [dict(candle) for candle in candles]
        _set_close(candles[-2], 102.0)

    suspect = update_location_zone_lifecycle(
        (zone,), one_breach, NOW, DEFAULT_LOCATION_CONFIG
    )
    invalidated = update_location_zone_lifecycle(
        (zone,), candles, NOW, DEFAULT_LOCATION_CONFIG
    )

    assert suspect[0].status == "SUSPECT"
    assert invalidated[0].status == "INVALIDATED"


@pytest.mark.parametrize("role", ["support", "resistance"])
def test_lifecycle_recovery_resets_streak_and_invalidated_is_terminal(role):
    candles = _zone_history()
    zone = _lifecycle_zone(candles, role)
    if role == "support":
        _set_close(candles[23], 98.0)
        _set_close(candles[24], 100.0)
    else:
        _set_close(candles[23], 102.0)
        _set_close(candles[24], 100.0)

    recovered = update_location_zone_lifecycle(
        (zone,), candles, NOW, DEFAULT_LOCATION_CONFIG
    )
    terminal = update_location_zone_lifecycle(
        (replace(recovered[0], status="INVALIDATED"),),
        candles,
        NOW,
        DEFAULT_LOCATION_CONFIG,
    )

    assert recovered[0].status == "ACTIVE"
    assert terminal[0].status == "INVALIDATED"


@pytest.mark.parametrize("role", ["support", "resistance"])
def test_lifecycle_checks_confirmation_close_and_age_boundary(role):
    candles = _zone_history()
    zone = _lifecycle_zone(candles, role, confirmation_index=22)
    if role == "support":
        _set_close(candles[22], 98.0)
    else:
        _set_close(candles[22], 102.0)

    confirmation_config = resolve_location_config({"invalidation_close_count": 1})
    invalidated = update_location_zone_lifecycle(
        (zone,), candles, NOW, confirmation_config
    )
    assert invalidated[0].status == "INVALIDATED"

    age_candles = _zone_history()
    age_zone = _lifecycle_zone(age_candles, role, confirmation_index=57)
    at_max = resolve_location_config({"zone_max_age_h4_bars": 2})
    not_expired = update_location_zone_lifecycle(
        (age_zone,), age_candles, NOW, at_max
    )
    extra = dict(age_candles[-1])
    extra["time"] = extra["time"] + timedelta(hours=4)
    age_candles.append(extra)
    expired = update_location_zone_lifecycle(
        (age_zone,), age_candles, extra["time"] + timedelta(hours=4), at_max
    )

    assert not_expired[0].status == "ACTIVE"
    assert expired[0].status == "EXPIRED"
