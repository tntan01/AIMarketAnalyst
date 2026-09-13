"""Reviewer probes for gate72; run explicitly, not part of the old 854 baseline.

Expected behavior comes from the approved lifecycle/P7/P8/BQLC contracts.
No production edits, skip or xfail. Synthetic source records test timestamp
validation separately from the pivot detector. All review candle rows are valid.
"""

import copy
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.market_models import Candle, validate_smc_candles
from core.smc_context import (
    _attach_zone_sweep_links, detect_liquidity_pools,
    detect_liquidity_sweeps, enrich_zones,
)
from core.smc_lifecycle import analyze_zone_lifecycle
from core.smc_confluence import build_d1_reaction_evidence
from core.smc_sweep_linking import assign_sweep_ownership


START = datetime(2026, 9, 1, tzinfo=timezone.utc)


def stamp(hours):
    return (START + timedelta(hours=hours)).isoformat()


def candles(rows, side="buy", hours=1):
    if side == "sell":
        rows = [(210-o, 210-low, 210-high, 210-close)
                for o, high, low, close in rows]
    values = [Candle(time=START + timedelta(hours=i*hours), open=o,
                     high=high, low=low, close=close, volume=100)
              for i, (o, high, low, close) in enumerate(rows)]
    assert not validate_smc_candles(values, "D1" if hours == 24 else "H1")
    return values


def lifecycle(rows, side="buy", hours=24):
    return analyze_zone_lifecycle(
        candles=candles(rows, side, hours), low=100, high=110, side=side,
        origin_index=0, departure_end_index=0, zone_id="zone",
        timeframe="D1" if hours == 24 else "H1", tf_minutes=hours*60,
        tick_size=.1, atr_current=1,
    )


def claim(setup, zone, available_hour):
    return dict(sweep_id="sweep", setup_id=setup, zone_id=zone, side="buy",
                reclaimed_at=stamp(11), setup_available_at=stamp(available_hour))


def sweep():
    return {"swept_lows": [dict(sweep_id="sweep", side="buy", kind="swept_low",
                                index=10, level=105, time=stamp(10),
                                reclaimed_at=stamp(11))], "swept_highs": []}


def zone(zone_id, setup_id, available_hour, low, high):
    return dict(zone_id=zone_id, setup_id=setup_id, type="demand_zone",
                direction="buy", origin_index=8, formation_start_index=8,
                departure_end_index=available_hour-1, available_at=stamp(available_hour),
                low=low, high=high)


def attach(zones, sweeps):
    _attach_zone_sweep_links(
        (("demand", zones),), sweeps,
        candles=candles([(120, 121, 119, 120)]*20),
        symbol="EURUSD", timeframe="H1", tf_minutes=60,
    )


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_01_sweep_must_not_precede_source_confirmation(side):
    # Supplied source is confirmed at snapshot time but NOT at sweep close.
    rows = [(112, 114, 111, 113)]*8
    rows[2] = (110, 111, 99.5, 100.1)
    source = dict(level=100 if side == "buy" else 110, index=0,
                  swing_id="source", confirmed=True, usable=True,
                  provisional=False, pivot_time=stamp(0), confirmed_at=stamp(6))
    swings = {"highs": [] if side == "buy" else [source],
              "lows": [source] if side == "buy" else []}
    values = candles(rows, side)
    pools = detect_liquidity_pools(values, swings, tick_size=.1, atr_value=1)
    result = detect_liquidity_sweeps(
        values, swings, timeframe="H1", tick_size=.1, atr_value=1,
        causal_only=True, lookback_bars=8, liquidity_pools=pools,
    )
    events = result["swept_lows" if side == "buy" else "swept_highs"]
    assert not events, "Sweep closes at hour 3; source is usable only at hour 6"


def test_r72_02_context_must_consider_earliest_eligible_setup_before_distance_rank():
    early = zone("early-child", "early", 13, 105.2, 106)
    late = zone("late-child", "late", 15, 100, 110)
    sweeps = sweep()
    attach([early, late], sweeps)
    assert sweeps["swept_lows"][0]["owner_setup_id"] == "early"


def test_r72_03_nonowner_child_cannot_take_contribution_slot():
    result = assign_sweep_ownership([claim("early", "z-owner", 13),
                                    claim("late", "a-nonowner", 15)])
    assert result["assignments"]["sweep"]["owner_setup_id"] == "early"
    assert sum(c["contribution_applied"] for c in result["claims"]) == 1
    assert next(c for c in result["claims"] if c["contribution_applied"])["setup_id"] == "early"


def test_r72_04_context_must_not_reassign_already_consumed_sweep():
    sweeps = sweep()
    attach([zone("old-child", "original-owner", 13, 100, 110)], sweeps)
    prior = copy.deepcopy(sweeps["swept_lows"][0])
    assert prior["consumed"] is True
    attach([zone("new-child", "later-owner", 15, 100, 110)], sweeps)
    assert sweeps["swept_lows"][0]["owner_setup_id"] == prior["owner_setup_id"]
    assert sweeps["swept_lows"][0]["assignment_id"] == prior["assignment_id"]


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_05_broken_d1_lifecycle_cannot_supply_active_reaction(side):
    state = lifecycle([(112,114,111,113), (109,110,105,109),
                       (112,114,111,113), (100,101,98,99)], side)
    assert state.lifecycle_broken
    assert state.visits[0].visit_state == "completed_reacted"
    evidence = build_d1_reaction_evidence(
        {"zone_id": "zone", "direction": side}, state, as_of=stamp(4*24),
    )
    assert evidence["valid"] is False
    assert evidence["score"] == 0


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_06_expiry_candle_cannot_create_reaction_for_earlier_exit(side):
    rows = [(112,114,111,113)]*22
    rows[19] = (109,110,105,109)
    rows[20] = (110.2,110.22,110.15,110.2)  # exit, below .25 ATR threshold
    rows[21] = (112,114,111,113)  # first possible reaction, already expired
    prefix = lifecycle(rows[:21], side)
    assert prefix.visits[0].visit_state == "completed_unreacted"
    state = lifecycle(rows, side)
    assert state.lifecycle_expired and state.expiry_index == 21
    assert state.visits[0].reacted_at is None
    assert state.visits[0].visit_state == "completed_unreacted"


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_07_enrich_must_forward_explicit_tick_to_lifecycle(side):
    values = candles([(112,114,111,113), (100,101,99.95,99.98)], side)
    item = dict(zone_id="zone", type="bullish_ob" if side == "buy" else "bearish_ob",
                family="ob", direction=side, origin_index=0, departure_end_index=0,
                low=100, high=110, available_at=stamp(1), atr_current=1,
                lifecycle_status="confirmed", usable=True)
    result = enrich_zones([item], values, "ob", {}, {"status": "unknown"},
                          timeframe="H1", tick_size=.1)[0]
    assert result["invalidation_buffer"] == pytest.approx(.1)
    assert result["lifecycle_broken"] is False


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_08_invalidated_zone_must_not_keep_confirmed_usable_flags(side):
    values = candles([(112,114,111,113), (100,101,98,99)], side)
    item = dict(zone_id="zone", type="bullish_ob" if side == "buy" else "bearish_ob",
                family="ob", direction=side, origin_index=0, departure_end_index=0,
                low=100, high=110, available_at=stamp(1), atr_current=1, tick_size=.1,
                lifecycle_status="confirmed", usable=True)
    result = enrich_zones([item], values, "ob", {}, {"status": "unknown"},
                          timeframe="H1")[0]
    assert result["lifecycle_broken"] is True
    assert result["usable"] is False
    assert result["lifecycle_status"] == "invalid"


def test_r72_09_existing_task60_positive_fixture_must_have_valid_ohlc(monkeypatch):
    path = Path(__file__).resolve().parents[3] / "tests/test_smc_zone_lifecycle_task60.py"
    spec = importlib.util.spec_from_file_location("task60_review_source", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    factory = module._candles

    def validated_factory(rows):
        values = factory(rows)
        assert not validate_smc_candles(values, "H1"), "Task60 golden positive contains invalid OHLC"
        return values

    monkeypatch.setattr(module, "_candles", validated_factory)
    module.test_buy_reaction_is_allowed_within_three_candles()


def test_control_live_d1_reaction_still_accepted():
    state = lifecycle([(112,114,111,113), (109,110,105,109), (112,114,111,113)])
    assert build_d1_reaction_evidence({"zone_id": "zone"}, state, as_of=stamp(72))["valid"]


def test_control_owner_children_share_exactly_one_contribution():
    result = assign_sweep_ownership([claim("owner", "child-b", 13),
                                    claim("owner", "child-a", 13)])
    assert len(result["assignments"]) == 1
    assert sum(c["contribution_applied"] for c in result["claims"]) == 1
