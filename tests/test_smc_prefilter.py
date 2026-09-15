"""Unit contracts for the Tier-1 canonical SMC prefilter predicate (task 104).

The prefilter consumes the SAME frozen snapshot and the SAME canonical
evaluation the full route produces.  It rejects only on a concluded canonical
verdict: an evaluated empty (no usable zone on either side) or core data that
could not be concluded.  A side merely waiting for its M15 confirmation is a
valid setup state and is never rejected.
"""

from __future__ import annotations

import importlib

import pytest

from core.smc_prefilter import (
    NO_ACTIONABLE_SMC_ZONE,
    SMC_CORE_DATA_UNAVAILABLE,
    SMC_PREFILTER_ERROR_FAIL_OPEN,
    SMC_PREFILTER_VERSION,
    SMC_SCORING_ERROR,
    evaluate_post_context_prefilter,
)
from core.smc_snapshot import build_smc_snapshot, evaluate_smc_snapshot

_QUALITY = importlib.import_module("tests.test_smc_quality_task88")
# The snapshot cutoff must match the candle fixture the seam filters, so the
# core-data verdict is the real one (and not an empty-history artefact).
_AS_OF = "2026-08-13T12:00:00+00:00"
_SHAPES = importlib.import_module("core.smc_models")

_FAMILY_KEYS = {
    "demand": "demand_zones",
    "supply": "supply_zones",
    "order_block": "order_blocks",
    "fvg": "fvg",
}


def _flat_timeframe(*, structure="HH/HL", bos=True, displacement="bullish"):
    return {
        "structure": structure,
        "bos": bos,
        "choch": False,
        "displacement": displacement,
        "demand_zones": [],
        "supply_zones": [],
        "order_blocks": [],
        "fvg": [],
        "zone_link_sweeps": {},
    }


def _context(*, zone=None, family="order_block", timeframe="H4"):
    """A canonical context; *zone* lands in the family list of its own family."""

    context = {
        "symbol": "EUR/USD",
        "D1": _flat_timeframe(),
        "H4": _flat_timeframe(),
        "H1": _flat_timeframe(),
        "confluence": {"timeframe_evidence": {}},
    }
    if zone is not None:
        context[timeframe][_FAMILY_KEYS[family]] = [zone]
    return context


def _candles():
    from tests.test_scanner_release import _zoned_candles

    return _zoned_candles()


def _snapshot(context, *, technical=None, candles=None):
    """Freeze a snapshot the way the runtime callers do."""

    d1, h4, h1 = candles if candles is not None else _candles()
    return build_smc_snapshot(
        {"D1": d1, "H4": h4, "H1": h1},
        symbol="EUR/USD",
        as_of=_AS_OF,
        tick_size=0.1,
        context_builder=lambda *a, **k: context,
        technical_builder=lambda *a, **k: (
            technical if technical is not None else _QUALITY._technical()
        ),
    )


def _zone(**overrides):
    zone = _QUALITY._zone()
    zone.update(overrides)
    return zone


@pytest.mark.parametrize("timeframe", ("H4", "H1"))
@pytest.mark.parametrize("family", tuple(_FAMILY_KEYS))
def test_canonical_prefilter_survives_each_raw_family_and_timeframe(
    timeframe: str,
    family: str,
) -> None:
    side = "buy" if family != "supply" else "sell"
    zone = _zone(
        family="supply_demand" if family in ("demand", "supply") else (
            "fvg" if family == "fvg" else "ob"
        ),
        direction=side,
        type=(
            "supply_zone" if family == "supply"
            else "demand_zone" if family == "demand"
            else "bullish_fvg" if family == "fvg"
            else "bullish_order_block"
        ),
    )
    if family == "fvg":
        # An FVG carries its measurement on the gap's middle candle, and the
        # remaining/original gap the family geometry feature needs.
        zone["middle_measurement"] = {
            "body_range": 0.8,
            "directional_close_location": 0.86,
            "atr_before_event": 2.0,
        }
        zone["remaining_low"] = 99.0
        zone["remaining_high"] = 99.8
    if family in ("demand", "supply"):
        # The S/D family feature is measured from the base compression.
        zone["base_measurement"] = {
            "base_low": 99.0,
            "base_high": 100.0,
            "average_range": 2.0,
            "compression_limit": 2.0,
        }
    context = _context(zone=zone, family=family, timeframe=timeframe)

    decision = evaluate_post_context_prefilter(snapshot=_snapshot(context), min_rr=2.0)

    assert decision["prefilter_version"] == SMC_PREFILTER_VERSION
    assert decision["fail_open"] is False
    assert decision["should_reject"] is False
    assert decision["reason_code"] == ""
    assert decision["precomputed_evaluation"] is not None
    assert decision["raw_counts"][timeframe][family] == 1
    assert decision["selected_zone_ids"][side] == zone["zone_id"]


def test_canonical_prefilter_rejects_only_when_both_sides_lack_selected_zones():
    decision = evaluate_post_context_prefilter(
        snapshot=_snapshot(_context()), min_rr=2.0
    )
    assert decision["should_reject"] is True
    assert decision["reason_code"] == NO_ACTIONABLE_SMC_ZONE
    assert decision["selected_zone_ids"] == {"buy": None, "sell": None}


def test_core_data_unavailable_is_not_reported_as_no_setup():
    """A snapshot the chain could not conclude is a DIFFERENT rejection."""

    snapshot = _snapshot(
        _context(),
        technical={"price": 100.0, "atr_h4": 10.0, "atr_d1": 12.0},
    )
    from dataclasses import replace

    snapshot = replace(
        snapshot, core_reason_codes=("SMC_H4_INSUFFICIENT_HISTORY",)
    )
    decision = evaluate_post_context_prefilter(snapshot=snapshot, min_rr=2.0)
    assert decision["reason_code"] == SMC_CORE_DATA_UNAVAILABLE
    assert decision["core_unavailable_sides"] == ["buy", "sell"]


def test_a_side_waiting_for_m15_is_never_rejected_for_that_reason():
    """M15 owns readiness only: a watch/evaluated side stays actionable."""

    zone = _zone()
    decision = evaluate_post_context_prefilter(
        snapshot=_snapshot(_context(zone=zone)), min_rr=2.0
    )
    assert decision["should_reject"] is False
    assert decision["selected_zone_ids"]["buy"] == zone["zone_id"]


@pytest.mark.parametrize("case", ("broken", "origin_index"))
def test_broken_or_invalid_zone_uses_canonical_reject(case: str) -> None:
    """A terminal zone cannot be selected; the side is refused, not invented."""

    if case == "broken":
        zone = _zone(broken=True, lifecycle_status="invalid", invalidated_at=_AS_OF)
    else:
        # An expired zone is terminal for the same reason: it cannot be
        # selected, and the side must not fall back to another zone.
        zone = _zone(lifecycle_status="expired", expired_at=_AS_OF)

    decision = evaluate_post_context_prefilter(
        snapshot=_snapshot(_context(zone=zone)), min_rr=2.0
    )
    # Either the side is not actionable (canonical reject) or the chain could
    # not conclude it — never a fabricated selected zone.
    assert decision["should_reject"] is True
    assert decision["reason_code"] in {
        NO_ACTIONABLE_SMC_ZONE,
        SMC_CORE_DATA_UNAVAILABLE,
    }
    assert decision["selected_zone_ids"]["buy"] is None


@pytest.mark.parametrize(
    ("family", "side"),
    (("demand", "buy"), ("supply", "sell")),
)
def test_buy_and_sell_selection_are_independent(family: str, side: str) -> None:
    zone = _zone(
        family="supply_demand",
        direction=side,
        zone_id=f"zone-{side}",
        setup_id=f"setup-{side}",
        type="demand_zone" if side == "buy" else "supply_zone",
        base_measurement={
            "base_low": 99.0,
            "base_high": 100.0,
            "average_range": 2.0,
            "compression_limit": 2.0,
        },
    )
    context = _context(zone=zone, family=family)

    evaluation = evaluate_smc_snapshot(
        _snapshot(context),
        min_rr=2.0,
    )
    other = "sell" if side == "buy" else "buy"
    assert evaluation.selection(side).selected_zone_id == f"zone-{side}"
    assert evaluation.selection(other).selected_zone_id is None


@pytest.mark.parametrize(
    "technical",
    (
        # No price at all.
        {"atr_h4": 10.0, "atr_d1": 12.0},
        # No usable ATR on either timeframe.
        {"price": 100.0},
        # Nothing measurable.
        {},
        # Non-positive references.
        {"price": 0.0, "atr_h4": 0.0, "atr_d1": 0.0},
    ),
)
def test_invalid_price_or_atr_fails_open(technical: dict) -> None:
    """Without the geometry reference the prefilter never claims "no setup"."""

    decision = evaluate_post_context_prefilter(
        snapshot=_snapshot(_context(), technical=technical), min_rr=2.0
    )
    assert decision["fail_open"] is True
    assert decision["reason_code"] == SMC_PREFILTER_ERROR_FAIL_OPEN
    assert decision["precomputed_evaluation"] is None


def test_malformed_context_fails_open():
    """A context missing a core timeframe is not a concluded empty."""

    context = _context()
    context.pop("H1")
    decision = evaluate_post_context_prefilter(
        snapshot=_snapshot(context), min_rr=2.0
    )
    assert decision["fail_open"] is True
    assert decision["reason_code"] == SMC_PREFILTER_ERROR_FAIL_OPEN


def test_unfrozen_snapshot_fails_open():
    assert evaluate_post_context_prefilter(snapshot=None)["fail_open"] is True
    assert (
        evaluate_post_context_prefilter(snapshot={"smc": {}})["fail_open"] is True
    )


def test_scorer_exception_fails_closed(monkeypatch):
    from core import smc_prefilter

    def _boom(*_args, **_kwargs):
        raise RuntimeError("chain unavailable")

    monkeypatch.setattr(smc_prefilter, "evaluate_smc_snapshot", _boom)
    decision = evaluate_post_context_prefilter(
        snapshot=_snapshot(_context(zone=_zone())), min_rr=2.0
    )
    assert decision["should_reject"] is True
    assert decision["fail_open"] is False
    assert decision["scorer_error"] is True
    assert decision["reason_code"] == SMC_SCORING_ERROR


def test_prefilter_preserves_context_and_reuses_canonical_result(monkeypatch):
    """The survivor's evaluation is REUSED — the chain runs exactly once."""

    from core import smc_prefilter

    calls: list[str] = []
    real = smc_prefilter.evaluate_smc_snapshot

    def spy(*args, **kwargs):
        calls.append("evaluate")
        return real(*args, **kwargs)

    monkeypatch.setattr(smc_prefilter, "evaluate_smc_snapshot", spy)
    snapshot = _snapshot(_context(zone=_zone()))
    decision = evaluate_post_context_prefilter(snapshot=snapshot, min_rr=2.0)

    assert calls == ["evaluate"]
    assert decision["precomputed_evaluation"].snapshot is snapshot
    assert decision["precomputed_smc"] is decision["precomputed_evaluation"].result
    assert decision["selected_zone_ids"]["buy"] == _zone()["zone_id"]
