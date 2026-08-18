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
from datetime import datetime, timedelta, timezone

import pytest

from core.market_models import Candle
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
    derive_technical_raws,
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