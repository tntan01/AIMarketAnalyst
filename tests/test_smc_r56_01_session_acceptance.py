"""Tech Lead-owned RED acceptance suite; no implementation or runtime oracle.

Contract: docs/plans/smc-r56-01-session-contract.md.
Golden cases are hand-labelled in the fixture, not derived from detector output.
An absent new diagnostic seam is an assertion failure, not a collection error.
"""

import copy
import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import core.smc_context as smc
from core.market_models import Candle, candle_close_at
from core.smc_models import SmcZone


FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "smc_r56_01_session_acceptance.json").read_text(encoding="utf-8"))
CASES = FIXTURE["cases"]
POSITIVE = [case for case in CASES if case["confirmed"]]
SIDES = ["buy", "sell"]


def _candles(case, side="buy"):
    rows = case["rows"]
    if side == "sell":
        # Exact decimal reflection avoids creating float-rounding threshold cases.
        p = Decimal(str(FIXTURE["mirror_price"]))
        rows = [[float(p - Decimal(str(v))) for v in (o, low, high, close)]
                for o, high, low, close in rows]
    return [Candle(time=datetime.fromisoformat(t), open=o, high=high, low=low, close=close, volume=100)
            for t, (o, high, low, close) in zip(FIXTURE["times"][case["times"]], rows)]


def _bounds(case, side):
    low, high = case["gap"]
    if side == "sell":
        p = Decimal(str(FIXTURE["mirror_price"]))
        low, high = float(p - Decimal(str(high))), float(p - Decimal(str(low)))
    return {"low": low, "high": high}


def _detect(case, side, candles=None, **overrides):
    args = dict(symbol=case.get("symbol", FIXTURE["symbol"]), timeframe="H1",
                tick_size=FIXTURE["tick_size"], atr_before_event=FIXTURE["atr_before_event"])
    args.update(overrides)
    return smc.detect_fvg_candidates(_candles(case, side) if candles is None else candles, **args)


def _origin(case, side):
    classifier = getattr(smc, "classify_fvg_session_origin", None)
    assert callable(classifier), "R56-01 contract requires classify_fvg_session_origin; implementation intentionally pending"
    return classifier(_candles(case, side), timeframe="H1", symbol=case.get("symbol", FIXTURE["symbol"]))


@pytest.mark.parametrize("side", SIDES)
@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_fixture_is_valid_and_does_not_hide_a_quality_failure(case, side):
    """Sanity only, not a classifier: check raw data and pre-existing P5 gates."""
    candles = _candles(case, side)
    assert len(candles) == 3
    assert candles[0].time < candles[1].time < candles[2].time
    for candle in candles:
        assert candle.low <= min(candle.open, candle.close) <= max(candle.open, candle.close) <= candle.high
    gap = smc.measure_fvg_gap(*candles, tick_size=.1, atr_before_event=5)
    assert gap["accepted"] is True
    assert {"low": gap["gap_low"], "high": gap["gap_high"]} == _bounds(case, side)
    assert smc.measure_fvg_middle_candle(candles[1], direction=side)["accepted"] is True


@pytest.mark.parametrize("side", SIDES)
@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_origin_contract_has_auditable_status_and_reason(case, side):
    result = _origin(case, side)
    assert result["status"] == case["origin_status"]
    assert result["accepted"] is case["confirmed"]  # Matrix has no quality failures.
    assert case["origin_reason"] in result["reason_codes"]
    assert result["gap_bounds"] == _bounds(case, side)


@pytest.mark.parametrize("side", SIDES)
@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_public_detector_and_confirmation_follow_golden_matrix(case, side):
    candles = _candles(case, side)
    candidates = _detect(case, side)
    if not case["confirmed"]:
        assert candidates == [], "Session-only/unknown/invalid source must not enter confirmed-zone pipeline"
        return
    assert len(candidates) == 1, case["why"]
    raw = candidates[0]
    assert raw["lifecycle_status"] == "candidate"
    assert raw["available_at"] is None
    close_at = candle_close_at(candles[2].time, "H1")
    confirmed = smc.confirm_fvg_candidate(raw, candles, timeframe="H1", as_of=close_at)
    assert confirmed["lifecycle_status"] == "confirmed"
    assert confirmed["direction"] == side
    assert confirmed["available_at"] == close_at.isoformat()
    assert confirmed["confirmed_at"] == close_at.isoformat()
    assert confirmed["entry_eligible"] is False
    assert confirmed["zone_id"] == raw["zone_id"]
    assert confirmed["original_bounds"] == _bounds(case, side)


@pytest.mark.parametrize("side", SIDES)
def test_origin_diagnostic_is_preserved_through_typed_evidence(side):
    case = next(c for c in CASES if c["id"] == "reopen_inside")
    raw = _detect(case, side)[0]
    evidence = raw.get("evidence", {}).get("session_origin")
    assert isinstance(evidence, dict), "Keep session_origin diagnosis even after raw detector fields are dropped"
    assert evidence == _origin(case, side)
    restored = SmcZone.from_dict(SmcZone.from_dict(raw).to_dict())
    assert restored.evidence["session_origin"] == evidence


@pytest.mark.parametrize("side", SIDES)
def test_cutoff_incremental_idempotent_and_terminal_guards(side):
    case = next(c for c in CASES if c["id"] == "reopen_inside")
    candles = _candles(case, side)
    assert _detect(case, side, candles=candles[:2]) == []
    raw = _detect(case, side)[0]
    original = copy.deepcopy(raw)
    close_at = candle_close_at(candles[2].time, "H1")
    early = smc.confirm_fvg_candidate(raw, candles, timeframe="H1", as_of=close_at - timedelta(microseconds=1))
    assert early["lifecycle_status"] == "candidate"
    assert early["available_at"] is None
    cold = smc.confirm_fvg_candidate(raw, candles, timeframe="H1", as_of=close_at)
    assert smc.confirm_fvg_candidate(early, candles, timeframe="H1", as_of=close_at) == cold
    assert smc.confirm_fvg_candidate(cold, candles, timeframe="H1", as_of=close_at) == cold
    assert raw == original
    for status in ("invalid", "expired"):
        terminal = {**cold, "lifecycle_status": status}
        assert smc.confirm_fvg_candidate(terminal, candles, timeframe="H1", as_of=close_at) == terminal


@pytest.mark.parametrize("side", SIDES)
def test_future_candle_does_not_rewrite_original_identity_or_availability(side):
    case = next(c for c in CASES if c["id"] == "reopen_inside")
    candles = _candles(case, side)
    raw = _detect(case, side)[0]
    last = candles[-1]
    extended = candles + [Candle(time=last.time + timedelta(hours=1), open=last.close,
                                high=last.high, low=last.low, close=last.close, volume=100)]
    same = next(z for z in _detect(case, side, candles=extended) if z["zone_id"] == raw["zone_id"])
    assert same["original_bounds"] == raw["original_bounds"]
    assert same["setup_id"] == raw["setup_id"]
    cutoff = candle_close_at(last.time, "H1")
    assert smc.confirm_fvg_candidate(same, extended, timeframe="H1", as_of=cutoff) == smc.confirm_fvg_candidate(raw, candles, timeframe="H1", as_of=cutoff)


@pytest.mark.parametrize("side", SIDES)
@pytest.mark.parametrize("middle", [
    [100,103,99.5,100.2],  # weak body
    [102,103,99.5,100],    # wrong direction
    [100,100,100,100],     # zero range
], ids=["weak", "wrong_direction", "zero_range"])
def test_origin_policy_cannot_bypass_middle_quality(side, middle):
    case = copy.deepcopy(next(c for c in CASES if c["id"] == "reopen_inside"))
    case["rows"][1] = middle
    candles = _candles(case, side)
    for raw in _detect(case, side):  # Retaining raw weak candidates remains allowed.
        assert smc.confirm_fvg_candidate(raw, candles, timeframe="H1")["lifecycle_status"] == "candidate"


@pytest.mark.parametrize("side", SIDES)
@pytest.mark.parametrize("overrides", [
    {"tick_size": None}, {"tick_size": 0}, {"atr_before_event": 0},
    {"atr_before_event": None}, {"tick_size": 1},
], ids=["missing_tick", "zero_tick", "zero_atr", "missing_atr", "gap_below_tick_minimum"])
def test_session_policy_cannot_replace_required_tick_atr_or_gap_minimum(side, overrides):
    case = next(c for c in CASES if c["id"] == "reopen_inside")
    assert _detect(case, side, **overrides) == []


@pytest.mark.parametrize("side", SIDES)
@pytest.mark.parametrize("low,expected", [(100.25, False), (100.5, True), (100.75, True)], ids=["below", "equal", "above"])
def test_gap_minimum_boundary_is_unchanged(side, low, expected):
    case = copy.deepcopy(next(c for c in CASES if c["id"] == "reopen_inside"))
    case["rows"][2] = [102,104,low,103]
    candidates = _detect(case, side, tick_size=.25)
    assert bool(candidates) is expected


@pytest.mark.parametrize("side", SIDES)
def test_confirmation_does_not_trust_legacy_eligible_boolean_over_origin_evidence(side):
    case = next(c for c in CASES if c["id"] == "reopen_inside")
    raw = copy.deepcopy(_detect(case, side)[0])
    # An inconsistent restored mapping is not authority to turn unknown into confirmed.
    raw.setdefault("evidence", {})["session_origin"] = {
        "status": "unknown", "accepted": False,
        "reason_codes": ["FVG_SESSION_ORIGIN_AMBIGUOUS"], "gap_bounds": _bounds(case, side),
    }
    raw["session_displacement_eligible"] = True
    result = smc.confirm_fvg_candidate(raw, _candles(case, side), timeframe="H1")
    assert result["lifecycle_status"] != "confirmed"
    assert "FVG_SESSION_ORIGIN_AMBIGUOUS" in result["reason_codes"]
