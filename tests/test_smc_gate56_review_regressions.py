"""Gate 56 regressions for the Tech Lead CHANGES_REQUESTED findings."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.market_models import Candle, candle_close_at
from core.smc_context import (
    apply_zone_availability,
    confirm_fvg_candidate,
    confirm_order_block_candidate,
    confirm_supply_demand_candidate,
    detect_fvg_candidates,
    detect_order_block_candidates,
    detect_supply_demand_candidates,
    group_smc_zones_into_setups,
)
from core.smc_history import required_history_for_lifetime
from core.smc_models import SmcSetup, SmcZone
from core.smc_structure_replay import replay_smc_structure


FIXTURE = json.loads(Path("tests/fixtures/smc_gate56_zone_pipeline.json").read_text())
START = datetime(2026, 9, 7, tzinfo=timezone.utc)


def _fixture_rows():
    return FIXTURE["buy_rows"] + FIXTURE["history_extension_rows"]


def _integrated_rows():
    return FIXTURE["integrated_rows"] + FIXTURE["integrated_history_tail_rows"]


def _candles(rows, *, mirror=False, step=timedelta(hours=1), start=START):
    result = []
    for index, (open_, high, low, close) in enumerate(rows):
        if mirror:
            open_, high, low, close = 200 - open_, 200 - low, 200 - high, 200 - close
        result.append(Candle(
            time=start + step * index,
            open=open_, high=high, low=low, close=close, volume=100,
        ))
    return result


def _event(candles, index, *, direction="bullish", invalidated=False, **overrides):
    occurred = candle_close_at(candles[index].time, "H1").isoformat()
    event = {
        "event_id": f"bos-{direction}-{index}",
        "broken_level_id": f"level-{direction}-{index}",
        "event_type": "BOS",
        "direction": direction,
        "timeframe": "H1",
        "occurred_index": index,
        "occurred_at": occurred,
        "confirmed_at": occurred,
        "confirmed": True,
    }
    if invalidated:
        event.update({"invalidated": True, "invalidated_at": occurred})
    event.update(overrides)
    return event


def test_r56_01_fvg_confirmed_available_at_third_close_buy_and_sell():
    for mirror, direction in ((False, "buy"), (True, "sell")):
        candles = _candles(_fixture_rows(), mirror=mirror)
        candidates = detect_fvg_candidates(
            candles, symbol="EUR/USD", timeframe="H1",
            tick_size=0.1, atr_before_event=5.0,
        )
        candidate = next(item for item in candidates if item["formation_end_index"] == 17)
        confirmed = confirm_fvg_candidate(
            candidate, candles, timeframe="H1",
            as_of=candle_close_at(candles[17].time, "H1"),
        )
        assert confirmed["direction"] == direction
        assert confirmed["lifecycle_status"] == "confirmed"
        assert confirmed["available_at"] == candle_close_at(candles[17].time, "H1").isoformat()
        assert confirmed["entry_eligible"] is False

        early = confirm_fvg_candidate(
            candidate, candles, timeframe="H1",
            as_of=candle_close_at(candles[16].time, "H1"),
        )
        assert early["lifecycle_status"] == "candidate"
        assert "FVG_THIRD_CANDLE_NOT_CLOSED" in early["reason_codes"]
        incremental = confirm_fvg_candidate(
            early, candles, timeframe="H1",
            as_of=candle_close_at(candles[17].time, "H1"),
        )
        assert incremental["lifecycle_status"] == "confirmed"
        assert incremental["available_at"] == confirmed["available_at"]
        assert incremental["reason_codes"] == confirmed["reason_codes"]
        weak = dict(candidate)
        weak["middle_quality_eligible"] = False
        weak_result = confirm_fvg_candidate(weak, candles, timeframe="H1")
        assert weak_result["lifecycle_status"] == "candidate"
        assert "FVG_MIDDLE_CANDLE_WEAK" in weak_result["reason_codes"]


def test_r56_01_fvg_terminal_invalid_and_expired_are_idempotent_buy_and_sell():
    for mirror in (False, True):
        candles = _candles(_fixture_rows(), mirror=mirror)
        candidate = next(item for item in detect_fvg_candidates(
            candles, symbol="EUR/USD", timeframe="H1",
            tick_size=0.1, atr_before_event=5.0,
        ) if item["formation_end_index"] == 17)
        confirmed = confirm_fvg_candidate(
            candidate, candles, timeframe="H1",
            as_of=candle_close_at(candles[17].time, "H1"),
        )
        invalid = {
            **confirmed,
            "lifecycle_status": "invalid",
            "invalidated_at": candle_close_at(candles[18].time, "H1").isoformat(),
        }
        assert confirm_fvg_candidate(invalid, candles, timeframe="H1") == invalid
        expired = {**confirmed, "lifecycle_status": "expired"}
        assert confirm_fvg_candidate(expired, candles, timeframe="H1") == expired


def test_r56_02_ob_requires_atr_ids_validity_and_causal_close_provenance():
    candles = _candles(_fixture_rows())
    candidate = next(item for item in detect_order_block_candidates(
        candles, symbol="EUR/USD", timeframe="H1",
    ) if item["departure_end_index"] == 16)
    event = _event(candles, 17)
    confirmed = confirm_order_block_candidate(
        candidate, [event], candles=candles,
        as_of=candle_close_at(candles[17].time, "H1"),
    )
    assert confirmed["lifecycle_status"] == "confirmed"
    assert confirmed["confirmation_event_id"] == event["event_id"]
    assert confirmed["broken_level_id"] == event["broken_level_id"]

    bad_measurement = {**candidate, "departure_measurement": {
        **candidate["departure_measurement"], "status": "unavailable",
    }}
    assert confirm_order_block_candidate(
        bad_measurement, [event], candles=candles,
    )["lifecycle_status"] == "candidate"
    for missing in (
        {"event_id": ""},
        {"broken_level_id": ""},
    ):
        bad_event = {**event, **missing}
        assert confirm_order_block_candidate(
            candidate, [bad_event], candles=candles,
        )["lifecycle_status"] == "candidate"

    assert confirm_order_block_candidate(
        candidate, [_event(candles, 17, invalidated=True)], candles=candles,
    )["lifecycle_status"] == "candidate"
    assert confirm_order_block_candidate(
        candidate, [dict(event, occurred_at=candles[16].time.isoformat())], candles=candles,
    )["lifecycle_status"] == "candidate"
    late = dict(event)
    late.pop("occurred_index")
    late["occurred_at"] = candle_close_at(candles[16].time, "H1") + timedelta(hours=24)
    late["confirmed_at"] = late["occurred_at"]
    assert confirm_order_block_candidate(candidate, [late], candles=candles)["lifecycle_status"] == "candidate"

    sell_candles = _candles(_fixture_rows(), mirror=True)
    sell_candidate = next(item for item in detect_order_block_candidates(
        sell_candles, symbol="EUR/USD", timeframe="H1",
    ) if item["departure_end_index"] == 16)
    sell_event = _event(sell_candles, 17, direction="bearish")
    sell_confirmed = confirm_order_block_candidate(
        sell_candidate, [sell_event], candles=sell_candles,
        as_of=candle_close_at(sell_candles[17].time, "H1"),
    )
    assert sell_confirmed["lifecycle_status"] == "confirmed"

    weak_rows = [(100, 100.5, 99.5, 100.1)] * 15
    weak_rows += [(100.1, 101, 99, 100), (100, 110, 99.8, 101.1), (101, 112, 100, 111)]
    weak_candles = _candles(weak_rows)
    weak_candidate = next(item for item in detect_order_block_candidates(
        weak_candles, symbol="EUR/USD", timeframe="H1",
    ) if item["departure_end_index"] == 16)
    weak_confirmed = confirm_order_block_candidate(
        weak_candidate, [_event(weak_candles, 17)], candles=weak_candles,
    )
    assert weak_confirmed["lifecycle_status"] == "candidate"
    assert "OB_DEPARTURE_BODY_WEAK" in weak_confirmed["reason_codes"]


def test_r56_02_genuine_canonical_bos_from_gate40_replay_promotes_ob():
    gate40 = json.loads(Path("tests/fixtures/smc_gate40_structure_replay.json").read_text())
    rows = list(gate40["cases"][0]["candles"])
    rows[23] = [105.5, 106, 104, 105]
    rows[24] = [105, 108, 104.5, 107]
    rows[25] = [105, 115, 105, 113]
    candles = _candles(
        rows, step=timedelta(hours=4),
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    cutoff = candle_close_at(candles[25].time, "H4")
    replay = replay_smc_structure(
        candles, symbol="EURUSD", timeframe="H4", tick_size=0.01,
        pivot_width=5, as_of=cutoff,
    )
    event = next(item for item in replay["events"] if item["event_type"] == "BOS")
    expected = FIXTURE["canonical_gate40_provenance"]
    assert event["status"] == expected["status"]
    assert event["event_id"] == expected["event_id"]
    assert event["broken_level_id"] == expected["broken_level_id"]
    assert event["occurred_at"] == expected["occurred_at"]
    assert event["confirmed_at"] == expected["confirmed_at"]
    assert event.get("confirmed") is None
    candidate = next(item for item in detect_order_block_candidates(
        candles, symbol="EURUSD", timeframe="H4",
    ) if item["departure_end_index"] == 24)
    confirmed = confirm_order_block_candidate(
        candidate, [event], candles=candles, as_of=cutoff,
    )
    assert confirmed["lifecycle_status"] == "confirmed"
    assert confirmed["confirmation_event_id"] == event["event_id"]


def test_r56_02_timestamp_only_canonical_bos_uses_closed_candle_lineage_across_weekend():
    gate40 = json.loads(Path("tests/fixtures/smc_gate40_structure_replay.json").read_text())
    rows = list(gate40["cases"][0]["candles"][:26])
    rows[23] = [105.5, 106, 104, 105]
    rows[24] = [105, 108, 104.5, 107]
    rows[25] = [105, 115, 105, 113]
    for mirror, direction in ((False, "buy"), (True, "sell")):
        for weekend in (False, True):
            start = datetime(2026, 9, 10, 20, tzinfo=timezone.utc)
            times = [start + timedelta(hours=index) for index in range(len(rows))]
            if weekend:
                times[25] = datetime(2026, 9, 13, 21, tzinfo=timezone.utc)
            candles = []
            for index, (open_, high, low, close) in enumerate(rows):
                if mirror:
                    open_, high, low, close = 200 - open_, 200 - low, 200 - high, 200 - close
                candles.append(Candle(
                    time=times[index], open=open_, high=high, low=low, close=close, volume=100,
                ))
            cutoff = candle_close_at(candles[25].time, "H1")
            replay = replay_smc_structure(
                candles, symbol="EUR/USD", timeframe="H1", tick_size=0.1,
                pivot_width=5, as_of=cutoff,
            )
            event = next(item for item in replay["events"] if item["event_type"] == "BOS")
            assert event["direction"] == ("bearish" if mirror else "bullish")
            event = dict(event)
            event.pop("occurred_index", None)
            event.pop("index", None)
            candidate = next(item for item in detect_order_block_candidates(
                candles, symbol="EUR/USD", timeframe="H1",
            ) if item["departure_end_index"] == 24 and item["direction"] == direction)
            confirmed = confirm_order_block_candidate(
                candidate, [event], candles=candles, as_of=cutoff,
            )
            assert confirmed["lifecycle_status"] == "confirmed"

        # A genuine OB five closed candles before the same genuine BOS must
        # remain a candidate: the rejection is based on actual candle count.
        late_rows = list(gate40["cases"][0]["candles"][:26])
        late_rows[19] = [100.1, 100.5, 99.5, 100]
        late_rows[20] = [100, 106, 99, 102]
        late_rows[23] = [105.5, 106, 104, 105]
        late_rows[24] = [105, 108, 104.5, 107]
        late_rows[25] = [105, 115, 105, 113]
        late_candles = _candles(
            late_rows, mirror=mirror,
            start=datetime(2026, 9, 10, 20, tzinfo=timezone.utc),
        )
        late_cutoff = candle_close_at(late_candles[25].time, "H1")
        late_replay = replay_smc_structure(
            late_candles, symbol="EUR/USD", timeframe="H1", tick_size=0.1,
            pivot_width=5, as_of=late_cutoff,
        )
        late_event = dict(next(
            item for item in late_replay["events"] if item["event_type"] == "BOS"
        ))
        late_event.pop("occurred_index", None)
        late_event.pop("index", None)
        late_candidate = next(item for item in detect_order_block_candidates(
            late_candles, symbol="EUR/USD", timeframe="H1",
        ) if item["departure_end_index"] == 20 and item["direction"] == direction)
        late_result = confirm_order_block_candidate(
            late_candidate, [late_event], candles=late_candles, as_of=late_cutoff,
        )
        assert late_result["lifecycle_status"] == "candidate"


def test_r56_03_sd_directional_close_location_is_required():
    base = [
        (100, 100.4, 99.8, 100.1),
        (100.1, 100.5, 99.9, 100.2),
        (100.2, 100.3, 99.9, 100.0),
    ]
    for mirror, expected in ((False, "buy"), (True, "sell")):
        candles = _candles(base + [(100, 103, 100, 101.8)], mirror=mirror)
        candidate = next(item for item in detect_supply_demand_candidates(
            candles, symbol="EUR/USD", timeframe="H1",
            average_range_before_departure={3: 0.6},
        ) if item["direction"] == expected)
        result = confirm_supply_demand_candidate(
            candidate, candles, timeframe="H1", atr_before_event=2.0,
        )
        assert result["lifecycle_status"] == "candidate"
        assert "SD_DEPARTURE_CLOSE_LOCATION_WEAK" in result["reason_codes"]


def test_r56_04_sd_selects_one_canonical_base_per_impulse_and_typed_setup_is_safe():
    rows = [(100, 100.5, 99.5, 100.1)] * 10 + [(100, 103, 100, 102.8)]
    candles = _candles(rows)
    candidates = detect_supply_demand_candidates(
        candles, symbol="EUR/USD", timeframe="H1",
        average_range_before_departure={10: 1.0},
    )
    at_impulse = [item for item in candidates if item["departure_end_index"] == 10]
    assert len(at_impulse) == 1
    assert at_impulse[0]["consolidation_bars"] == 3
    confirmed = [confirm_supply_demand_candidate(
        item, candles, timeframe="H1", atr_before_event=2.0,
    ) for item in at_impulse]
    setup = SmcSetup.from_zones(confirmed, symbol="EUR/USD", timeframe="H1")
    assert len(setup.children) == 1


def test_r56_05_actual_ob_fvg_sd_lineage_groups_one_setup_for_buy_and_sell():
    for mirror, direction in ((False, "buy"), (True, "sell")):
        candles = _candles(
            _integrated_rows(), mirror=mirror,
            start=datetime(2026, 9, 10, 20, tzinfo=timezone.utc),
        )
        fvg = next(item for item in detect_fvg_candidates(
            candles, symbol="EUR/USD", timeframe="H1", tick_size=0.1,
            atr_before_event=5.0,
        ) if item["formation_end_index"] == 25)
        ob = next(item for item in detect_order_block_candidates(
            candles, symbol="EUR/USD", timeframe="H1",
        ) if item["departure_end_index"] == 24)
        sd = next(item for item in detect_supply_demand_candidates(
            candles, symbol="EUR/USD", timeframe="H1",
            average_range_before_departure={24: 2.0},
        ) if item["departure_end_index"] == 24)
        cutoff = candle_close_at(candles[69].time, "H1")
        replay = replay_smc_structure(
            candles, symbol="EUR/USD", timeframe="H1", tick_size=0.1,
            pivot_width=5, as_of=cutoff,
        )
        event = next(item for item in replay["events"] if item["event_type"] == "BOS")
        assert event["event_id"] == FIXTURE["integrated_structure_provenance"][direction]["event_id"]
        assert event["broken_level_id"] == FIXTURE["integrated_structure_provenance"][direction]["broken_level_id"]
        assert event["status"] == "confirmed"
        assert event.get("confirmed") is None
        confirmed = [
            confirm_fvg_candidate(fvg, candles, timeframe="H1", as_of=candle_close_at(candles[25].time, "H1")),
            confirm_order_block_candidate(ob, [event], candles=candles, as_of=cutoff),
            confirm_supply_demand_candidate(
                sd, candles, timeframe="H1", atr_before_event=2.0, as_of=cutoff,
            ),
        ]
        available = apply_zone_availability(
            confirmed, candles, timeframe="H1", symbol="EUR/USD", as_of=cutoff,
        )
        assert all(item["usable"] for item in available)
        zones = [SmcZone.from_dict(item).to_dict() for item in available]
        assert len(group_smc_zones_into_setups(zones, symbol="EUR/USD", timeframe="H1")) == 1
        assert {item["direction"] for item in zones} == {direction}


def test_r56_06_availability_is_invariant_to_future_valid_or_invalid_candles():
    candles = _candles([(100, 101, 99, 100.5)] * 70)
    zone = {
        "zone_id": "zone-1", "family": "ob", "direction": "buy",
        "low": 99, "high": 101, "origin_time": candles[0].time.isoformat(),
        "lifecycle_status": "confirmed",
        "confirmed_at": candle_close_at(candles[5].time, "H1").isoformat(),
        "available_at": candle_close_at(candles[5].time, "H1").isoformat(),
    }
    cutoff = candle_close_at(candles[19].time, "H1")
    prefix = apply_zone_availability([zone], candles[:20], timeframe="H1", symbol="EUR/USD", as_of=cutoff)[0]
    extended = apply_zone_availability([zone], candles, timeframe="H1", symbol="EUR/USD", as_of=cutoff)[0]
    invalid_future = candles + [Candle(
        time=candles[-1].time + timedelta(hours=1), open=1, high=0, low=2, close=1,
    )]
    extended_invalid = apply_zone_availability([zone], invalid_future, timeframe="H1", symbol="EUR/USD", as_of=cutoff)[0]
    assert prefix["history_coverage"]["raw_count"] == 20
    assert extended["history_coverage"] == prefix["history_coverage"]
    assert extended_invalid["history_coverage"] == prefix["history_coverage"]
    assert extended["usable"] == prefix["usable"] == extended_invalid["usable"]


def test_r56_07_actual_detector_evidence_survives_zone_and_setup_round_trip():
    candles = _candles(_fixture_rows())
    raw = next(item for item in detect_order_block_candidates(
        candles, symbol="EUR/USD", timeframe="H1",
    ) if item["departure_end_index"] == 16)
    zone = SmcZone.from_dict(raw, symbol="EUR/USD", timeframe="H1")
    restored = SmcZone.from_dict(zone.to_dict())
    assert restored.evidence["departure_measurement"] == raw["departure_measurement"]
    setup = SmcSetup.from_zones([raw], symbol="EUR/USD", timeframe="H1")
    assert setup.children[0].evidence["departure_measurement"] == raw["departure_measurement"]
    assert SmcSetup.from_dict(setup.to_dict()).children[0].evidence == setup.children[0].evidence


def test_r56_08_m15_cold_rebuild_keeps_zone_at_l_minus_one_l_and_l_plus_one():
    assert required_history_for_lifetime("M15") == 147
    rows = [(100, 100.5, 99.5, 100.1)] * 20
    rows += [(101, 102, 99, 100), (100, 106, 99.8, 105.5)]
    rows += [(105, 106, 104, 105)] * 82
    candles = _candles(rows, step=timedelta(minutes=15))
    for length in (102, 103, 104):
        rebuilt = detect_order_block_candidates(
            candles[:length], symbol="EUR/USD", timeframe="M15",
        )
        candidate = next(item for item in rebuilt if item["origin_index"] == 20)
        event_time = candle_close_at(candles[22].time, "M15").isoformat()
        event = {
            "event_id": "bos-m15-cold-replay",
            "broken_level_id": "m15-level-1",
            "event_type": "BOS",
            "direction": "bullish",
            "timeframe": "M15",
            "occurred_index": 22,
            "occurred_at": event_time,
            "confirmed_at": event_time,
            "confirmed": True,
        }
        confirmed = confirm_order_block_candidate(
            candidate, [event], candles=candles[:length],
            as_of=candle_close_at(candles[length - 1].time, "M15"),
        )
        assert confirmed["lifecycle_status"] == "confirmed"
