"""Scanner feature derivation tests (Path B, Bước 2+4).

Proves the candle→raw port in :mod:`core.scanner_features`:

* **parity** — on a frozen fixture, the ported raw formulas equal legacy
  ``signal_engine.trend_alignment_score / momentum_alignment_score /
  location_quality_score`` for both sides (this is the legacy-deletion gate; the
  test is retired when legacy scoring is removed);
* **property** — raw ceilings in-bounds; deterministic fingerprint independent
  of metadata; deterministic across identical candle sets;
* **fail-closed** — insufficient D1/H4/H1 candles raise
  ``TechnicalRawDerivationError``, never fabricate numbers;
* **smc** — ``None`` (fail-closed) without a canonical result; optional
  ``canonical_smc`` projects the 0-15 raw through
  ``project_smc_technical_raw``.
"""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

import core.scanner_features as scanner_features
from core.market_models import Candle
from core.reason_codes import LOCATION_INVALID_DATA
from core.scanner_features import (
    FEATURES_VERSION,
    LOCATION_RAW_MAX,
    MOMENTUM_RAW_MAX,
    SMC_RAW_MAX,
    TREND_RAW_MAX,
    MIN_D1,
    MIN_H4,
    MIN_H1,
    SideFeatureRaws,
    TechnicalRaws,
    TechnicalRawDerivationError,
    derive_technical_raws_with_location,
    derive_technical_raws,
    prepare_location_results,
    trend_alignment_score_v4,
    momentum_alignment_score_v4,
    location_quality_score_v4,
)
from core.technical_context import build_technical_snapshot

NOW = datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc)
BASE = 1000.0


def _mk(n: int, step: float, phase: float) -> list[Candle]:
    out = []
    for i in range(n):
        o = BASE + math.sin((i + phase) / 3) * 0.5 + i * step
        c = BASE + math.sin((i + 1 + phase) / 3) * 0.5 + (i + 1) * step
        out.append(
            Candle(
                time=NOW - timedelta(seconds=int((n - i) * step * 3600)),
                open=o,
                high=max(o, c) + 0.1,
                low=min(o, c) - 0.1,
                close=c,
            )
        )
    return out


@pytest.fixture
def candles():
    return _mk(120, 0.02, 0.0), _mk(120, 0.01, 1.0), _mk(80, 0.005, 2.0)


def _t(d1, h4, h1):
    return build_technical_snapshot(d1, h4, h1)


def _location_candles() -> tuple[list[Candle], list[Candle]]:
    """Causally closed H4/H1 fixture for the Task 22 feature adapter."""
    h4: list[Candle] = []
    h1: list[Candle] = []
    for i in range(80):
        h4_open_time = NOW - timedelta(hours=(80 - i) * 4)
        h4_open = 100.0 + i * 0.03
        h4_close = h4_open + (0.02 if i % 2 else -0.01)
        h4.append(
            Candle(
                time=h4_open_time,
                open=h4_open,
                high=max(h4_open, h4_close) + 0.05,
                low=min(h4_open, h4_close) - 0.05,
                close=h4_close,
            )
        )

        h1_open_time = NOW - timedelta(hours=80 - i)
        h1_open = 100.5 + i * 0.01
        h1_close = h1_open + (0.01 if i % 2 else -0.005)
        h1.append(
            Candle(
                time=h1_open_time,
                open=h1_open,
                high=max(h1_open, h1_close) + 0.02,
                low=min(h1_open, h1_close) - 0.02,
                close=h1_close,
            )
        )
    return h4, h1


# ---------------------------------------------------------------------------
# Parity vs legacy signal_engine — FROZEN SNAPSHOT (deletion gate)
# ---------------------------------------------------------------------------
# The legacy raws (trend/momentum/location) were ported to scanner_features. On
# this DETERMINISTIC frozen fixture the legacy signal_engine produced exactly the
# values below (captured pre-deletion). We now assert the port against the
# frozen snapshot instead of importing the deleted legacy module.

_FROZEN_TREND = {"buy": 8, "sell": 10}
_FROZEN_MOMENTUM = {"buy": 3, "sell": 16}
_FROZEN_LOCATION = {"buy": 3, "sell": 3}


# ---------------------------------------------------------------------------
# Legacy Location counterexamples — Task 3 (A03)
# ---------------------------------------------------------------------------
# These cases intentionally lock the pre-upgrade formula.  They are historical
# references for the six documented counterexamples, not expectations for the
# target Location engine after H01.
def _legacy_zone(low: float, high: float, confluence: int = 1) -> dict[str, float | int]:
    return {"low": low, "high": high, "confluence_count": confluence}


def _legacy_location_score(
    price: float,
    supports: list[dict[str, float | int]],
    resistances: list[dict[str, float | int]],
) -> int:
    return location_quality_score_v4(
        "buy",
        {
            "price": price,
            "atr_h4": 1.0,
            "atr_d1": 2.0,
            "support_zones": supports,
            "resistance_zones": resistances,
        },
    )


@pytest.mark.parametrize(
    "case, price, supports, resistances, expected",
    [
        pytest.param("OLD-01", 99.8, [_legacy_zone(100, 101)], [], 10, id="OLD-01"),
        pytest.param(
            "OLD-02",
            100,
            [_legacy_zone(99, 101)],
            [_legacy_zone(99.5, 100.5)],
            15,
            id="OLD-02",
        ),
        pytest.param(
            "OLD-03",
            110,
            [_legacy_zone(99, 100, confluence=3)],
            [_legacy_zone(109, 111)],
            5,
            id="OLD-03",
        ),
        pytest.param("OLD-04", 100, [], [], 3, id="OLD-04"),
        pytest.param("OLD-05", 100.5, [_legacy_zone(99, 100)], [], 10, id="OLD-05"),
        pytest.param("OLD-06", 100.5001, [_legacy_zone(99, 100)], [], 3, id="OLD-06"),
    ],
)
def test_legacy_location_counterexamples(case, price, supports, resistances, expected):
    """Keep the documented pre-upgrade outputs visible as legacy fixtures."""
    assert _legacy_location_score(price, supports, resistances) == expected, case


@pytest.mark.parametrize("side", ["buy", "sell"])
class TestParityVsV3Frozen:
    def test_trend_parity(self, candles, side):
        d1, h4, h1 = candles
        t = _t(d1, h4, h1)
        assert trend_alignment_score_v4(side, t) == _FROZEN_TREND[side]

    def test_momentum_parity(self, candles, side):
        d1, h4, h1 = candles
        t = _t(d1, h4, h1)
        assert momentum_alignment_score_v4(side, t) == _FROZEN_MOMENTUM[side]

    def test_location_parity(self, candles, side):
        d1, h4, h1 = candles
        t = _t(d1, h4, h1)
        assert location_quality_score_v4(side, t) == _FROZEN_LOCATION[side]


# ---------------------------------------------------------------------------
# Property: ceilings, determinism
# ---------------------------------------------------------------------------

def test_ranges_in_bounds(candles):
    d1, h4, h1 = candles
    r = derive_technical_raws(d1, h4, h1, symbol="XAUUSD", captured_at=NOW)
    for side in ("buy", "sell"):
        s = r.per_side[side]
        assert 0 <= s.trend <= TREND_RAW_MAX
        assert 0 <= s.momentum <= MOMENTUM_RAW_MAX
        assert 0 <= s.location <= LOCATION_RAW_MAX
        assert s.smc is None  # no canonical_smc provided → fail-closed


def test_version_and_requirements(candles):
    d1, h4, h1 = candles
    r = derive_technical_raws(d1, h4, h1, captured_at=NOW)
    assert r.features_version == FEATURES_VERSION
    assert r.requirements == {"d1_min": MIN_D1, "h4_min": MIN_H4, "h1_min": MIN_H1}


def test_deterministic_same_input(candles):
    d1, h4, h1 = candles
    a = derive_technical_raws(d1, h4, h1, captured_at=NOW)
    b = derive_technical_raws(d1, h4, h1, captured_at=NOW)
    assert a.to_dict()["features"] == b.to_dict()["features"]
    assert a.deterministic_fingerprint == b.deterministic_fingerprint


def test_fingerprint_independent_of_metadata(candles):
    d1, h4, h1 = candles
    a = derive_technical_raws(d1, h4, h1, symbol="XAUUSD", captured_at=NOW)
    b = derive_technical_raws(d1, h4, h1, symbol="ANY", captured_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
    # Same candles ⇒ same fingerprint regardless of symbol/captured_at.
    assert a.deterministic_fingerprint == b.deterministic_fingerprint
    assert a.to_dict()["features"] == b.to_dict()["features"]


def test_cross_side_keys_are_exact(candles):
    d1, h4, h1 = candles
    r = derive_technical_raws(d1, h4, h1, captured_at=NOW)
    assert set(r.per_side) == {"buy", "sell"}
    for s in r.per_side.values():
        assert isinstance(s, SideFeatureRaws)
        assert s.side in ("buy", "sell")
        assert s.trend_source == "technical"


def test_location_feature_adapter_builds_one_context_for_both_sides(candles, monkeypatch):
    d1, _, _ = candles
    h4, h1 = _location_candles()
    calls = 0
    original = scanner_features.build_location_context

    def counted_context(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(scanner_features, "build_location_context", counted_context)
    raws = derive_technical_raws_with_location(
        d1,
        h4,
        h1,
        cutoff=NOW,
        symbol="EURUSD",
        captured_at=NOW,
    )

    assert calls == 1
    for side in ("buy", "sell"):
        feature = raws.per_side[side]
        assert feature.location_detail is not None
        assert feature.location == feature.location_detail.raw
        assert feature.location_detail.side == side
        assert feature.location_detail.reference_closed_at == NOW
        assert feature.location_source == feature.location_detail.model_version
    assert "location=location-geometry-v2" in raws.derivation
    assert "config=location-config-v1" in raws.derivation


def test_location_feature_detail_serializes_per_side_without_cross_mutation(candles):
    d1, _, _ = candles
    h4, h1 = _location_candles()
    raws = derive_technical_raws_with_location(
        d1,
        h4,
        h1,
        cutoff=NOW,
        captured_at=NOW,
    )

    payload = raws.to_dict()
    buy_detail = payload["features"]["buy"]["location_detail"]
    sell_detail = payload["features"]["sell"]["location_detail"]
    assert payload["features"]["buy"]["location"] == buy_detail["raw"]
    assert payload["features"]["sell"]["location"] == sell_detail["raw"]

    buy_detail["reason_codes"].append("TEST_ONLY")
    assert "TEST_ONLY" not in sell_detail["reason_codes"]
    assert "TEST_ONLY" not in raws.per_side["buy"].location_detail.reason_codes
    assert "TEST_ONLY" not in raws.per_side["sell"].location_detail.reason_codes


def test_location_fingerprint_includes_resolved_config_when_raw_is_unchanged(candles):
    d1, _, _ = candles
    h4, h1 = _location_candles()
    prepared = derive_technical_raws_with_location(
        d1, h4, h1, cutoff=NOW, captured_at=NOW
    )
    original_detail = prepared.per_side["buy"].location_detail
    assert original_detail is not None
    changed_config = replace(
        original_detail.config_used,
        zone_half_width_atr=original_detail.config_used.zone_half_width_atr + 0.05,
    )
    changed_detail = replace(original_detail, config_used=changed_config)
    changed_buy = replace(
        prepared.per_side["buy"], location_detail=changed_detail
    )
    changed = replace(
        prepared,
        per_side={
            "buy": changed_buy,
            "sell": prepared.per_side["sell"],
        },
    )

    assert changed.per_side["buy"].location == prepared.per_side["buy"].location
    assert changed.deterministic_fingerprint != prepared.deterministic_fingerprint


def test_location_unavailable_preserves_typed_reason_field_and_cause():
    h4, h1 = _location_candles()
    invalid_h4 = [
        replace(bar, open=100.0, high=100.0, low=100.0, close=100.0)
        for bar in h4
    ]

    with pytest.raises(TechnicalRawDerivationError) as caught:
        prepare_location_results(invalid_h4, h1, cutoff=NOW)

    error = caught.value
    assert error.reason_code == LOCATION_INVALID_DATA
    assert error.field == "context.current_atr_h4"
    assert error.cause is not None
    assert LOCATION_INVALID_DATA in str(error)


def test_no_valid_anchor_is_a_valid_zero_raw_not_an_unavailable_error(candles):
    d1, _unused_h4, _unused_h1 = candles
    source_h4, h1 = _location_candles()
    monotonic_h4 = []
    for index, bar in enumerate(source_h4):
        open_price = 100.0 + index * 0.1
        close_price = open_price + 0.03
        monotonic_h4.append(
            Candle(
                time=bar.time,
                open=open_price,
                high=close_price + 0.02,
                low=open_price - 0.02,
                close=close_price,
            )
        )

    raws = derive_technical_raws_with_location(
        d1,
        monotonic_h4,
        h1,
        cutoff=NOW,
        captured_at=NOW,
    )

    for feature in raws.per_side.values():
        assert feature.location == 0
        assert feature.location_detail is not None
        assert feature.location_detail.raw == 0
        assert feature.location_detail.status == "NO_VALID_ANCHOR"


def test_location_adapter_preserves_non_location_features_regime_and_legacy_zones(candles):
    """Task 27: Location preparation must not rewrite retained consumers."""
    d1, _unused_h4, _unused_h1 = candles
    h4, h1 = _location_candles()
    from core.scanner_live_producers import resolve_technical_regime
    from core.technical_context import build_technical_snapshot, detect_market_regime

    canonical = _real_canonical_smc(d1, h4, h1)
    canonical_before = deepcopy(canonical.to_dict())
    candles_before = (deepcopy(d1), deepcopy(h4), deepcopy(h1))
    technical_before = build_technical_snapshot(d1, h4, h1)
    baseline = derive_technical_raws(
        d1, h4, h1, canonical_smc=canonical, captured_at=NOW
    )

    prepared = derive_technical_raws_with_location(
        d1,
        h4,
        h1,
        canonical_smc=canonical,
        cutoff=NOW,
        captured_at=NOW,
    )
    technical_after = build_technical_snapshot(d1, h4, h1)

    for side in ("buy", "sell"):
        before = baseline.per_side[side]
        after = prepared.per_side[side]
        assert (after.trend, after.momentum, after.smc) == (
            before.trend,
            before.momentum,
            before.smc,
        )
        assert after.location_detail is not None

    assert detect_market_regime(technical_after, False) == detect_market_regime(
        technical_before, False
    )
    assert resolve_technical_regime(technical_after, False) == resolve_technical_regime(
        technical_before, False
    )
    assert technical_after["support_zones"] == technical_before["support_zones"]
    assert technical_after["resistance_zones"] == technical_before["resistance_zones"]
    assert canonical.to_dict() == canonical_before
    assert (d1, h4, h1) == candles_before


# ---------------------------------------------------------------------------
# Fail-closed: insufficient history
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("reduce,what", [
    (("d1",), "D1"),
    (("h4",), "H4"),
    (("h1",), "H1"),
    (("d1", "h4"), "D1/H4"),
])
def test_insufficient_data_fails_closed(candles, reduce, what):
    d1, h4, h1 = candles
    if "d1" in reduce:
        d1 = d1[: MIN_D1 - 1]
    if "h4" in reduce:
        h4 = h4[: MIN_H4 - 1]
    if "h1" in reduce:
        h1 = h1[: MIN_H1 - 1]
    with pytest.raises(TechnicalRawDerivationError):
        derive_technical_raws(d1, h4, h1, captured_at=NOW)


def test_boundary_meets_minimum(candles):
    d1, h4, h1 = candles
    r = derive_technical_raws(d1[: MIN_D1], h4[: MIN_H4], h1[: MIN_H1], captured_at=NOW)
    assert r is not None and set(r.per_side) == {"buy", "sell"}


def test_reject_forged_features_version(candles):
    d1, h4, h1 = candles
    r = derive_technical_raws(d1, h4, h1, captured_at=NOW)
    data = r.to_dict()
    data["features_version"] = "scanner-max"  # unknown identity pre-decision
    with pytest.raises(TechnicalRawDerivationError):
        TechnicalRaws(
            features_version=data["features_version"],
            symbol=data["symbol"],
            captured_at=NOW,
            per_side=r.per_side,
            requirements=r.requirements,
            derivation=r.derivation,
        )


# ---------------------------------------------------------------------------
# smc from the RETAINED canonical producer (decision §4-a)
# ---------------------------------------------------------------------------

def _real_canonical_smc(d1, h4, h1):
    """Build canonical SMC through the REAL retained producer (no fabrication).

    ``score_smc`` (``core.smc_scorer``, owner decision §4-a) is the canonical
    ``smc-v2`` source the contract mandates.  Feeding its real output into
    ``derive_technical_raws`` proves the projection path without inventing a
    canonical result.
    """
    from core.smc_context import build_smc_context
    from core.smc_scorer import score_smc
    from core.technical_context import build_technical_snapshot

    smc_ctx = build_smc_context(d1, h4, h1, symbol="XAUUSD")
    technical = build_technical_snapshot(d1, h4, h1)
    return score_smc(smc_ctx, technical)


def test_smc_projected_with_canonical(candles):
    d1, h4, h1 = candles
    canonical = _real_canonical_smc(d1, h4, h1)
    assert canonical.scoring_version == "smc-v2"
    assert canonical.contract_version == "smc-scoring-canonical-2026-08"
    r = derive_technical_raws(d1, h4, h1, canonical_smc=canonical, captured_at=NOW)
    # Outermost raw the scorer consumes must already be ≤15.
    for side in ("buy", "sell"):
        assert r.per_side[side].smc is not None
        assert 0 <= r.per_side[side].smc <= SMC_RAW_MAX
        assert r.per_side[side].smc_source is not None
        assert isinstance(r.per_side[side].smc, int)


def test_smc_none_without_canonical(candles):
    d1, h4, h1 = candles
    r = derive_technical_raws(d1, h4, h1, captured_at=NOW)
    assert r.per_side["buy"].smc is None
    assert r.per_side["sell"].smc is None
