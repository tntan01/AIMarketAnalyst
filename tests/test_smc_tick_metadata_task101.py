"""D101-02 — the canonical tick size is a rule dependency, not a snapshot verdict.

The snapshot still carries ``trade_tick_size`` (or the labelled ``point``
fallback) and its provenance.  What changed is where a MISSING tick size is
reported: at the candidate/rule that quantizes price, never as a snapshot-wide
``DATA_UNAVAILABLE``.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone  # noqa: F401

from core.smc_geometry import GEOMETRY_TICK_SIZE_UNAVAILABLE
from core.smc_snapshot import (
    SNAPSHOT_CUTOFF_NAIVE,
    SNAPSHOT_TICK_SIZE_UNAVAILABLE,
    TICK_SIZE_SOURCE_BROKER,
    TICK_SIZE_SOURCE_POINT_FALLBACK,
    build_smc_snapshot,
    evaluate_smc_snapshot,
)

UTC = timezone.utc
NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)


def _empty_context(*_args, **_kwargs):
    """A canonical context with no zones: the core data was evaluated."""

    return {
        "domain_version": "smc-domain",
        "symbol": "XAUUSD",
        "D1": {"structure": "HH/HL", "bos": True, "displacement": "bullish"},
        "H4": {"structure": "HH/HL", "bos": True, "displacement": "bullish"},
        "H1": {"structure": "HH/HL", "bos": True, "displacement": "bullish"},
        "confluence": {"timeframe_evidence": {}},
    }


def _empty_technical(*_args, **_kwargs):
    return {"price": 1000.0, "atr_h4": 5.0, "atr_d1": 6.0}


def _snapshot(*, tick_size=None, tick_size_source=None, empty=False):
    """A frozen snapshot of the REAL Scanner fixture (or an empty context)."""

    from tests.test_scanner_release import _zoned_candles

    d1, h4, h1 = _zoned_candles()
    extra = {}
    if empty:
        extra = {
            "context_builder": _empty_context,
            "technical_builder": _empty_technical,
        }
    return build_smc_snapshot(
        {"D1": d1, "H4": h4, "H1": h1},
        symbol="XAUUSD",
        as_of=NOW,
        tick_size=tick_size,
        tick_size_source=tick_size_source,
        **extra,
    )


# ---------------------------------------------------------------------------
# The metadata itself
# ---------------------------------------------------------------------------


def test_broker_tick_size_is_carried_with_its_provenance():
    snapshot = _snapshot(tick_size=0.01, tick_size_source=TICK_SIZE_SOURCE_BROKER)
    assert snapshot.tick_size == 0.01
    assert snapshot.tick_size_source == TICK_SIZE_SOURCE_BROKER
    assert snapshot.provenance["tick_size_status"] == "available"


def test_point_fallback_is_carried_and_labelled():
    snapshot = _snapshot(
        tick_size=0.001, tick_size_source=TICK_SIZE_SOURCE_POINT_FALLBACK
    )
    assert snapshot.tick_size == 0.001
    assert snapshot.tick_size_source == TICK_SIZE_SOURCE_POINT_FALLBACK
    assert snapshot.provenance["tick_size_status"] == "available"


def test_a_missing_tick_size_is_provenance_not_a_core_reason():
    snapshot = _snapshot(tick_size=None)
    assert snapshot.tick_size is None
    assert snapshot.core_reason_codes == ()
    assert snapshot.provenance["tick_size_status"] == SNAPSHOT_TICK_SIZE_UNAVAILABLE


def test_symbol_data_quality_publishes_broker_tick_size_then_point(
    monkeypatch, tmp_path
):
    """The metadata source: ``trade_tick_size`` first, then a labelled point."""

    import services.mt5_service as mt5_service

    class _Info:
        def __init__(self, tick, point):
            self.trade_tick_size = tick
            self.point = point
            self.spread = 10
            self.trade_contract_size = 100_000.0
            self.volume_min = 0.01
            self.volume_max = 100.0
            self.volume_step = 0.01

    class _Fake:
        def __init__(self, info):
            self._info = info

        def symbol_info(self, _symbol):
            return self._info

        def symbol_info_tick(self, _symbol):
            return None

        def terminal_info(self):
            return None

        def account_info(self):
            return None

    profile_path = tmp_path / "symbol_profiles.json"
    profile_path.write_text("{}", encoding="utf-8")
    service = mt5_service.MT5Service(profile_path)
    monkeypatch.setattr(service, "connect", lambda: None)
    monkeypatch.setattr(
        service,
        "mt5_connection_status",
        lambda: mt5_service.MT5ConnectionStatus(
            initialized=True,
            terminal_connected=True,
            logged_in=True,
            trade_allowed=True,
            broker="test",
        ),
    )

    monkeypatch.setitem(sys.modules, "MetaTrader5", _Fake(_Info(0.01, 0.001)))
    direct = service.symbol_data_quality("XAUUSD", "XAUUSD")
    assert direct["tick_size"] == 0.01
    assert direct["tick_size_source"] == TICK_SIZE_SOURCE_BROKER

    monkeypatch.setitem(sys.modules, "MetaTrader5", _Fake(_Info(None, 0.001)))
    fallback = service.symbol_data_quality("XAUUSD", "XAUUSD")
    assert fallback["tick_size"] == 0.001
    assert fallback["tick_size_source"] == TICK_SIZE_SOURCE_POINT_FALLBACK

    monkeypatch.setitem(sys.modules, "MetaTrader5", _Fake(_Info(None, None)))
    missing = service.symbol_data_quality("XAUUSD", "XAUUSD")
    assert missing["tick_size"] is None
    assert missing["tick_size_source"] is None


# ---------------------------------------------------------------------------
# Where a missing tick size is reported
# ---------------------------------------------------------------------------


def test_a_snapshot_with_core_data_and_no_tick_is_not_globally_unavailable():
    """Core data is complete and no candidate needs tick: ``no_zone``."""

    from core.smc_models import SMC_QUALITY_STATE_NO_ZONE

    snapshot = _snapshot(tick_size=None, empty=True)
    assert snapshot.core_reason_codes == ()
    assert snapshot.usable is True

    evaluation = evaluate_smc_snapshot(snapshot)
    for side in ("buy", "sell"):
        candidate_set = evaluation.candidate_sets[side]
        assert candidate_set.state == SMC_QUALITY_STATE_NO_ZONE
        assert candidate_set.quality_raw == 0
        assert SNAPSHOT_TICK_SIZE_UNAVAILABLE not in candidate_set.reason_codes


def test_candidates_that_need_the_tick_fail_closed_with_the_tick_reason():
    """A real canonical snapshot without tick fails ITS candidates closed."""

    snapshot = _snapshot(tick_size=None)
    evaluation = evaluate_smc_snapshot(snapshot)
    tick_rejected = [
        candidate
        for side in ("buy", "sell")
        for candidate in evaluation.candidate_sets[side].candidates
        if GEOMETRY_TICK_SIZE_UNAVAILABLE in candidate.rejection_codes
    ]
    # The fixture does produce canonical candidates; each one that claims
    # canonical evidence fails closed on its own.
    assert tick_rejected or all(
        not evaluation.candidate_sets[side].candidates for side in ("buy", "sell")
    )
    for candidate in tick_rejected:
        assert candidate.mandatory_passed is False


def test_the_same_candidates_evaluate_when_the_tick_size_is_known():
    """The control: supplying the real tick size removes the tick rejection."""

    with_tick = evaluate_smc_snapshot(_snapshot(tick_size=0.01))
    without_tick = evaluate_smc_snapshot(_snapshot(tick_size=None))
    for side in ("buy", "sell"):
        with_codes = {
            code
            for candidate in with_tick.candidate_sets[side].candidates
            for code in candidate.rejection_codes
        }
        without_codes = {
            code
            for candidate in without_tick.candidate_sets[side].candidates
            for code in candidate.rejection_codes
        }
        assert GEOMETRY_TICK_SIZE_UNAVAILABLE not in with_codes
        assert GEOMETRY_TICK_SIZE_UNAVAILABLE in without_codes


def test_core_timeframes_are_still_the_only_snapshot_level_unavailable_reason():
    """A missing D1/H4/H1 window keeps failing the whole snapshot closed."""

    snapshot = build_smc_snapshot(
        {"D1": [], "H4": [], "H1": []},
        symbol="XAUUSD",
        as_of=NOW,
        tick_size=0.01,
        context_builder=lambda *a, **k: {},
        technical_builder=lambda *a, **k: {},
    )
    assert snapshot.core_reason_codes
    assert SNAPSHOT_TICK_SIZE_UNAVAILABLE not in snapshot.core_reason_codes

    naive = build_smc_snapshot(
        {},
        symbol="XAUUSD",
        as_of="2026-08-13T12:00:00",
        tick_size=0.01,
        context_builder=_empty_context,
        technical_builder=_empty_technical,
    )
    assert SNAPSHOT_CUTOFF_NAIVE in naive.core_reason_codes
