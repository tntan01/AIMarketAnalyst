"""Scanner live producers tests (Bước 3 — production builders).

Proves the production adapters in :mod:`core.scanner_live_producers` build the
inputs from live app/MT5 state without fabricating anything:

* ``resolve_technical_regime`` — parity vs legacy ``_resolve_regime_key`` over every
  primary, and that it only ever returns the VALID regime vocabulary;
* ``build_side_snapshot`` — maps derived raws, enforces the source contract;
* ``build_live_market_safety_context`` — stamps availability from the ACTUAL
  live state; the ``MarketSafetyGate`` then yields PASS under a healthy,
  configured policy and a typed fail-closed UNKNOWN/BLOCK for every missing /
  stale / unreliable source (the default ``None`` policy thresholds are NEVER
  invented — only an explicit age limit marks a probe STALE);
* ``derive_live_analysis`` — the production candle→analysis path (regime in the
  valid set, canonical SMC v2, deterministic fingerprint).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from core.market_models import Candle
from core.market_safety_gate import MarketSafetyGate, SafetyPolicy
from core.scanner_composition import CompositionInputError, SideSnapshot
from core.scanner_live_producers import (
    PRODUCER_VERSION,
    build_live_market_safety_context,
    build_side_snapshot,
    derive_live_analysis,
    resolve_technical_regime,
)
from core.scanner_v4_models import SCANNER_SAFETY_POLICY_VERSION
from core.signal_engine import _resolve_regime_key
from core.technical_signal_scorer import VALID_TECHNICAL_REGIMES

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
    return _mk(120, 0.08, 0.0), _mk(120, 0.04, 1.0), _mk(80, 0.02, 2.0)


# ---------------------------------------------------------------------------
# resolve_technical_regime (parity vs legacy port)
# ---------------------------------------------------------------------------

regime_cases = [
    {"primary": "trend_up", "secondary": []},
    {"primary": "trend_down", "secondary": []},
    {"primary": "range", "secondary": []},
    {"primary": "volatile", "secondary": []},
    {"primary": "unknown", "secondary": []},
    {"primary": "trend_up", "secondary": ["volatile"]},
    {"primary": "range", "secondary": ["news_sensitive"]},
]


@pytest.mark.parametrize("case", regime_cases)
def test_regime_mapping_parity(case, monkeypatch):
    monkeypatch.setattr(
        "core.scanner_live_producers.detect_market_regime",
        lambda technical, news_in_3h: case,
    )
    got = resolve_technical_regime({}, False)
    assert got == _resolve_regime_key(case)
    assert got in VALID_TECHNICAL_REGIMES


def test_regime_is_always_in_valid_vocabulary(candles, monkeypatch):
    for primary in ("trend_up", "trend_down", "range", "volatile", "unknown"):
        for secondary in ([], ["volatile"], ["news_sensitive"]):
            monkeypatch.setattr(
                "core.scanner_live_producers.detect_market_regime",
                lambda technical, news_in_3h, p=primary, s=secondary: {"primary": p, "secondary": s},
            )
            assert resolve_technical_regime({}, False) in VALID_TECHNICAL_REGIMES


# ---------------------------------------------------------------------------
# build_side_snapshot
# ---------------------------------------------------------------------------

def test_side_snapshot_maps_derived_raws():
    s = build_side_snapshot("buy", trend=20, momentum=14, location=18)
    assert isinstance(s, SideSnapshot)
    assert s.technical_raws == {"trend": 20, "momentum": 14, "location": 18}
    # No evidence/execution supplied → None (composition falls back to neutral-50,
    # never fabricated here).
    assert s.evidence_score is None and s.execution_quality_score is None


@pytest.mark.parametrize("side,trend,momentum,location", [
    ("buy", 26, 14, 18),   # trend over ceiling
    ("buy", 20, 21, 18),   # momentum over ceiling
    ("buy", 20, 14, 26),   # location over ceiling
    ("buy", -1, 0, 0),     # negative
])
def test_side_snapshot_rejects_out_of_ceiling(side, trend, momentum, location):
    with pytest.raises(CompositionInputError):
        build_side_snapshot(side, trend=trend, momentum=momentum, location=location)


def test_side_snapshot_source_contract_not_fabricated():
    # A score with an empty source is contradictory → rejected by SideSnapshot.
    with pytest.raises(CompositionInputError):
        build_side_snapshot(
            "buy", trend=20, momentum=14, location=18,
            evidence_score=60, evidence_source="",
        )


def test_side_snapshot_rejects_bad_side():
    with pytest.raises(ValueError):
        build_side_snapshot("sideways", trend=20, momentum=14, location=18)


# ---------------------------------------------------------------------------
# build_live_market_safety_context → MarketSafetyGate
# ---------------------------------------------------------------------------

POLICY = SafetyPolicy(
    policy_version=SCANNER_SAFETY_POLICY_VERSION,
    max_candle_age_minutes=5,
    spread_threshold_by_symbol={"XAUUSD": 50},
    connectivity_max_age_minutes=10,
    volatility_calibrated=True,
    volatility_upper_ratio=1.5,
)
GATE = MarketSafetyGate()


def _ctx(**kw):
    base = dict(
        symbol="XAUUSD", captured_at=NOW,
        terminal_connected=True, broker_logged_in=True,
        connectivity_checked_at=NOW - timedelta(seconds=30),
        last_candle_time_utc=NOW - timedelta(seconds=30),
        spread_points=20.0, spread_checked_at=NOW,
        news_source_verified=True, news_checked_at=NOW,
        volatility_ratio=1.0, volatility_checked_at=NOW,
    )
    base.update(kw)
    return build_live_market_safety_context(**base)


def _status(**kw):
    r = GATE.evaluate(_ctx(**kw), now=NOW, policy=POLICY)
    return r.status, r.reason_codes


def test_healthy_passes_under_configured_policy():
    status, codes = _status()
    assert status == "PASS"
    assert codes == ()


@pytest.mark.parametrize("kw,expected_code", [
    ({"terminal_connected": False, "broker_logged_in": False}, "SAFETY_MT5_STATE_UNKNOWN"),
    ({"connectivity_checked_at": NOW - timedelta(minutes=99), "connectivity_max_age_minutes": 10},
     "SAFETY_MT5_STATE_UNKNOWN"),
    ({"last_candle_time_utc": NOW - timedelta(minutes=99), "max_candle_age_minutes": 5},
     "SAFETY_DATA_FRESHNESS_UNKNOWN"),
    ({"spread_points": None, "spread_checked_at": None}, "SAFETY_SPREAD_UNKNOWN"),
    ({"volatility_ratio": None, "volatility_checked_at": None}, "SAFETY_VOLATILITY_UNKNOWN"),
    ({"news_source_verified": False}, "SAFETY_NEWS_SOURCE_UNAVAILABLE"),
])
def test_missing_or_stale_source_fails_closed(kw, expected_code):
    status, codes = _status(**kw)
    assert status == "UNKNOWN"
    assert expected_code in codes


def test_spread_abnormal_blocks():
    status, codes = _status(spread_points=99.0)
    assert status == "BLOCK"
    assert "SAFETY_SPREAD_ABNORMAL" in codes


def test_no_age_limit_invented():
    # Default policy has connectivity_max_age_minutes=None; without an explicit
    # limit the producer must NOT mark a probe stale merely by age.
    c = _ctx(connectivity_checked_at=NOW - timedelta(hours=5))
    assert c.connectivity.availability == "valid"


def test_producer_disconnected_is_never_valid():
    from core.market_safety_gate import AVAILABILITY_MISSING

    c = _ctx(terminal_connected=False, broker_logged_in=False)
    assert c.connectivity.availability == AVAILABILITY_MISSING
    assert c.connectivity.availability != "valid"


def test_tick_time_flows_into_freshness_source():
    tick = NOW - timedelta(seconds=5)
    c = _ctx(last_tick_time_utc=tick)
    assert c.data.last_tick_time_utc == tick


def test_missing_tick_defaults_to_none():
    c = _ctx()
    assert c.data.last_tick_time_utc is None


def test_fresh_tick_rescues_stale_candle_open():
    # An M15 candle OPEN time (10 min old) exceeds the 5-min SLA, but a fresh
    # broker tick proves the feed is alive: the gate must PASS on the tick
    # reference instead of blocking on candle age.
    status, codes = _status(
        last_candle_time_utc=NOW - timedelta(minutes=10),
        data_checked_at=NOW,
        last_tick_time_utc=NOW - timedelta(seconds=5),
    )
    assert status == "PASS"
    assert codes == ()


def test_stale_tick_blocks_like_a_dead_feed():
    # Weekend / dead feed: the last tick is old, so the tick reference itself
    # is stale and must BLOCK even though a candle exists.
    status, codes = _status(
        last_candle_time_utc=NOW - timedelta(minutes=10),
        data_checked_at=NOW,
        last_tick_time_utc=NOW - timedelta(minutes=99),
    )
    assert status == "BLOCK"
    assert "SAFETY_DATA_STALE" in codes


# ---------------------------------------------------------------------------
# derive_live_analysis — production candle→analysis path
# ---------------------------------------------------------------------------

def test_derive_live_analysis_produces_valid_inputs(candles):
    d1, h4, h1 = candles
    a = derive_live_analysis(d1, h4, h1, symbol="XAUUSD", captured_at=NOW)
    assert a["regime"] in VALID_TECHNICAL_REGIMES
    assert a["canonical_smc"].scoring_version == "smc-v2"
    assert a["canonical_smc"].contract_version == "smc-scoring-canonical-2026-08"
    raws = a["raws"]
    assert raws.features_version == "scanner-features"
    assert set(raws.per_side) == {"buy", "sell"}
    for side in ("buy", "sell"):
        assert 0 <= raws.per_side[side].smc <= 15
    assert len(raws.deterministic_fingerprint) == 64


def test_derive_live_analysis_deterministic(candles):
    d1, h4, h1 = candles
    a = derive_live_analysis(d1, h4, h1, symbol="XAUUSD", captured_at=NOW)
    b = derive_live_analysis(d1, h4, h1, symbol="XAUUSD", captured_at=NOW)
    assert a["raws"].deterministic_fingerprint == b["raws"].deterministic_fingerprint
    assert a["regime"] == b["regime"]


def test_producer_version_is_locked():
    assert PRODUCER_VERSION == "scanner-live-producer"

# ---------------------------------------------------------------------------
# compute_live_volatility_ratio (locked atr14 semantics, fail-closed)
# ---------------------------------------------------------------------------


class TestComputeLiveVolatilityRatio:
    def test_ratio_matches_technical_snapshot_readings(self, candles):
        d1, h4, _ = candles
        from core.scanner_live_producers import compute_live_volatility_ratio
        from core.technical_context import atr_volatility_readings

        readings = atr_volatility_readings(d1, h4)
        expected = readings["atr_h4"] / readings["atr_avg_14d"]
        ratio = compute_live_volatility_ratio(d1, h4)
        assert ratio is not None
        assert math.isfinite(ratio)
        assert ratio > 0
        assert ratio == pytest.approx(expected)

    def test_ratio_consistent_with_technical_snapshot_fields(self, candles):
        d1, h4, h1 = candles
        from core.scanner_live_producers import compute_live_volatility_ratio
        from core.technical_context import build_technical_snapshot

        snap = build_technical_snapshot(d1, h4, h1)
        expected = snap["atr_h4"] / snap["atr_avg_14d"]
        assert compute_live_volatility_ratio(d1, h4) == pytest.approx(expected)

    @pytest.mark.parametrize("n", [0, 1, 14])
    def test_insufficient_history_returns_none(self, n):
        from core.scanner_live_producers import compute_live_volatility_ratio

        short = _mk(n, 0.08, 0.0) if n else []
        enough = _mk(60, 0.04, 1.0)
        assert compute_live_volatility_ratio(short, enough) is None
        assert compute_live_volatility_ratio(enough, short) is None

    def test_empty_or_none_inputs_return_none(self):
        from core.scanner_live_producers import compute_live_volatility_ratio

        assert compute_live_volatility_ratio(None, None) is None
        assert compute_live_volatility_ratio([], []) is None

    def test_flat_candles_zero_atr_returns_none(self):
        from core.scanner_live_producers import compute_live_volatility_ratio

        flat = [
            Candle(
                time=NOW - timedelta(hours=i),
                open=BASE,
                high=BASE,
                low=BASE,
                close=BASE,
            )
            for i in range(60)
        ]
        assert compute_live_volatility_ratio(flat, flat) is None
