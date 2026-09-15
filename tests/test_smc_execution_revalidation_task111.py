"""D111-01 — dispatch revalidation re-checks the approved SMC setup.

Task 111 was incomplete while ``smc_revalidation`` only travelled with the
proposal: no caller built a CURRENT comparison, so every dispatch blocked
unconditionally.  These tests cover both halves — the engine contract and the
real caller boundary that produces the fresh canonical snapshot.
"""

from __future__ import annotations

from datetime import datetime, timezone

from core.execution_revalidation_engine import (
    SMC_M15_UNAVAILABLE,
    SMC_NOT_READY,
    SMC_REVALIDATION_UNAVAILABLE,
    SMC_SETUP_CHANGED,
    SMC_ZONE_INVALID_OR_EXPIRED,
    revalidate_execution,
)
from tests.test_execution_revalidation import _proposal, _snapshot

UTC = timezone.utc
NOW = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)


def _approved(zone="smcz-approved", setup="smcs-approved") -> dict:
    return {"selected_zone_id": zone, "selected_setup_id": setup}


def _current(**overrides) -> dict:
    values = {
        "selected_zone_id": "smcz-approved",
        "selected_setup_id": "smcs-approved",
        "state": "evaluated",
        "readiness_status": "READY_NOW",
        "m15_status": "confirmed",
    }
    values.update(overrides)
    return values


def _validate(smc_revalidation, **overrides):
    return revalidate_execution(
        _proposal(),
        _snapshot(),
        news_blackout=False,
        account_allowed=True,
        portfolio_allowed=True,
        now=NOW,
        smc_revalidation=smc_revalidation,
        **overrides,
    )


# ---------------------------------------------------------------------------
# Engine contract
# ---------------------------------------------------------------------------


def test_a_matching_ready_setup_does_not_add_smc_block_codes():
    result = _validate({"approved": _approved(), "current": _current()})
    assert result.allowed is True
    assert result.block_codes == ()


def test_an_invalidated_or_expired_zone_blocks():
    result = _validate(
        {"approved": _approved(), "current": _current(state="out_of_strategy")}
    )
    assert result.allowed is False
    assert SMC_ZONE_INVALID_OR_EXPIRED in result.block_codes


def test_a_changed_setup_blocks():
    result = _validate(
        {
            "approved": _approved(),
            "current": _current(selected_zone_id="smcz-other"),
        }
    )
    assert result.allowed is False
    assert SMC_SETUP_CHANGED in result.block_codes


def test_a_changed_setup_id_blocks_even_when_the_zone_matches():
    result = _validate(
        {
            "approved": _approved(),
            "current": _current(selected_setup_id="smcs-other"),
        }
    )
    assert result.allowed is False
    assert SMC_SETUP_CHANGED in result.block_codes


def test_a_missing_or_invalidated_m15_blocks():
    missing = _validate(
        {"approved": _approved(), "current": _current(m15_status="missing")}
    )
    assert missing.allowed is False
    assert SMC_M15_UNAVAILABLE in missing.block_codes

    invalidated = _validate(
        {"approved": _approved(), "current": _current(m15_status="invalidated")}
    )
    assert invalidated.allowed is False
    assert SMC_M15_UNAVAILABLE in invalidated.block_codes

    expired = _validate(
        {"approved": _approved(), "current": _current(m15_status="expired")}
    )
    assert expired.allowed is False
    assert SMC_M15_UNAVAILABLE in expired.block_codes


def test_a_not_ready_side_blocks_even_when_the_zone_is_the_same():
    result = _validate(
        {
            "approved": _approved(),
            "current": _current(readiness_status="WAITING_CONFIRMATION"),
        }
    )
    assert result.allowed is False
    assert SMC_NOT_READY in result.block_codes


def test_no_fresh_comparison_blocks():
    for value in (None, {}, {"approved": _approved()}, {"current": _current()}):
        result = _validate(value)
        assert result.allowed is False
        assert SMC_REVALIDATION_UNAVAILABLE in result.block_codes


# ---------------------------------------------------------------------------
# Caller boundary
# ---------------------------------------------------------------------------


class _StubController:
    """Minimal surface the revalidation helper reads (mt5 + settings)."""

    def __init__(self, candles, data_quality):
        self._candles = candles
        self._data_quality = data_quality
        self.mt5 = self

    def load_primary_timeframes(self, _broker_symbol, _bars):
        return self._candles

    def symbol_data_quality(self, _symbol, _broker_symbol):
        return self._data_quality


class _Settings:
    class _Advanced:
        d1_bars = 120
        h4_bars = 120
        h1_bars = 120

    advanced = _Advanced()


def _call(order, *, candles=None, data_quality=None, side="buy"):
    from tests.test_scanner_release import _zoned_candles

    if candles is None:
        d1, h4, h1 = _zoned_candles()
        candles = {"D1": d1, "H4": h4, "H1": h1, "M15": []}
    if data_quality is None:
        data_quality = {"tick_size": 0.01, "tick_size_source": "trade_tick_size"}
    from controllers.scanner_controller import ScannerController

    return ScannerController._smc_revalidation_for_order(
        _StubController(candles, data_quality),
        order,
        broker_symbol="XAUUSD",
        side=side,
        settings=_Settings(),
    )


def test_the_caller_builds_a_fresh_canonical_comparison():
    order = {"symbol": "XAUUSD", "smc_zone_id": "smcz-approved", "setup": 1}
    order["smc_setup_id"] = "smcs-approved"
    comparison = _call(order)
    assert comparison is not None
    assert comparison["source"] == "fresh_canonical_snapshot"
    assert comparison["approved"] == {
        "selected_zone_id": "smcz-approved",
        "selected_setup_id": "smcs-approved",
    }
    current = comparison["current"]
    # The comparison reports the CURRENT verdict of a NEW snapshot — the
    # approved ids only appear on the approved side.
    assert set(current) == {
        "selected_zone_id",
        "selected_setup_id",
        "state",
        "readiness_status",
        "m15_status",
    }
    assert comparison["cutoff"]


def test_the_fresh_comparison_blocks_when_the_setup_changed():
    comparison = _call(
        {"symbol": "XAUUSD", "smc_zone_id": "smcz-gone", "smc_setup_id": "smcs-gone"}
    )
    result = revalidate_execution(
        _proposal(),
        _snapshot(),
        news_blackout=False,
        account_allowed=True,
        portfolio_allowed=True,
        now=NOW,
        smc_revalidation=comparison,
    )
    assert result.allowed is False
    assert SMC_SETUP_CHANGED in result.block_codes


def test_no_approved_identity_means_no_comparison():
    assert _call({"symbol": "XAUUSD"}) is None


def test_a_missing_fresh_snapshot_returns_no_comparison():
    assert (
        _call(
            {"symbol": "XAUUSD", "smc_zone_id": "smcz-approved"},
            candles={"D1": [], "H4": [], "H1": [], "M15": []},
        )
        is None
    )


def test_insufficient_fresh_history_returns_no_comparison():
    from tests.test_scanner_release import _zoned_candles

    d1, h4, h1 = _zoned_candles()
    assert (
        _call(
            {"symbol": "XAUUSD", "smc_zone_id": "smcz-approved"},
            candles={"D1": d1[:5], "H4": h4, "H1": h1, "M15": []},
        )
        is None
    )


def test_a_loader_failure_returns_no_comparison():
    class _Broken(_StubController):
        def load_primary_timeframes(self, _broker_symbol, _bars):
            raise RuntimeError("mt5 unavailable")

    from controllers.scanner_controller import ScannerController

    comparison = ScannerController._smc_revalidation_for_order(
        _Broken({}, {}),
        {"symbol": "XAUUSD", "smc_zone_id": "smcz-approved"},
        broker_symbol="XAUUSD",
        side="buy",
        settings=_Settings(),
    )
    assert comparison is None


# ---------------------------------------------------------------------------
# Caller boundary — the comparison is DERIVED from a fresh canonical snapshot
# ---------------------------------------------------------------------------

A_CUTOFF = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
ANOTHER_CUTOFF = datetime(2026, 8, 13, 16, 0, tzinfo=UTC)


def _fixture(name: str):
    from tests.test_scanner_release import _live_candles, _zoned_candles

    return _zoned_candles() if name == "zoned" else _live_candles()


def _fresh_call(
    order,
    *,
    fixture="zoned",
    m15=None,
    data_quality=None,
    cutoff=A_CUTOFF,
    side="buy",
):
    """Drive the caller with a REAL loader and a REAL canonical snapshot."""

    from controllers.scanner_controller import ScannerController

    d1, h4, h1 = _fixture(fixture)
    candles = {"D1": d1, "H4": h4, "H1": h1, "M15": m15 or []}
    calls: list[dict] = []
    stub = _StubController(candles, data_quality or {"tick_size": 0.01})
    real_loader = stub.load_primary_timeframes

    def loader(broker_symbol, bars):
        calls.append({"broker_symbol": broker_symbol, "bars": dict(bars)})
        return real_loader(broker_symbol, bars)

    stub.load_primary_timeframes = loader
    comparison = ScannerController._smc_revalidation_for_order(
        stub,
        order,
        broker_symbol="XAUUSD",
        side=side,
        settings=_Settings(),
        now=cutoff,
    )
    return comparison, calls


def _engine(comparison):
    return revalidate_execution(
        _proposal(),
        _snapshot(),
        news_blackout=False,
        account_allowed=True,
        portfolio_allowed=True,
        now=NOW,
        smc_revalidation=comparison,
    )


def test_the_comparison_comes_from_new_candles_and_a_new_cutoff():
    """Proof it is a NEW evaluation, not an echo of the approved proposal."""

    order = {
        "symbol": "XAUUSD",
        "smc_zone_id": "smcz-approved-earlier",
        "smc_setup_id": "smcs-approved-earlier",
    }
    comparison, calls = _fresh_call(order, cutoff=A_CUTOFF)

    assert calls and calls[0]["broker_symbol"] == "XAUUSD"
    # The cutoff is the ONE the dispatch boundary captured and passed on.
    assert comparison["cutoff"] == A_CUTOFF.isoformat()

    # The current side is the FRESH canonical verdict, not the approved ids.
    assert comparison["current"]["selected_zone_id"] != "smcz-approved-earlier"
    assert comparison["current"]["selected_setup_id"] != "smcs-approved-earlier"
    assert comparison["approved"] == {
        "selected_zone_id": "smcz-approved-earlier",
        "selected_setup_id": "smcs-approved-earlier",
    }

    # A different dispatch moment records a different cutoff, so the comparison
    # cannot be reusing a cached or previous snapshot.
    later, _ = _fresh_call(order, cutoff=ANOTHER_CUTOFF)
    assert later["cutoff"] == ANOTHER_CUTOFF.isoformat()
    assert later["cutoff"] != comparison["cutoff"]


def test_a_fresh_snapshot_without_a_usable_zone_blocks_as_invalid_or_expired():
    """The fresh chain could not certify a zone: the order is not dispatched."""

    comparison, _ = _fresh_call(
        {"symbol": "XAUUSD", "smc_zone_id": "smcz-approved"},
        fixture="smooth",
    )
    assert comparison is not None
    result = _engine(comparison)
    assert result.allowed is False
    assert SMC_ZONE_INVALID_OR_EXPIRED in result.block_codes


def test_a_fresh_snapshot_without_m15_blocks_as_m15_unavailable():
    """The real fixture carries no M15 window for this cutoff."""

    comparison, _ = _fresh_call({"symbol": "XAUUSD", "smc_zone_id": "smcz-approved"})
    # The loader delivered no M15 window for this cutoff, so the fresh verdict
    # cannot carry a confirmation.
    assert comparison["current"]["m15_status"] not in ("confirmed", "not_required")
    result = _engine(comparison)
    assert result.allowed is False
    assert SMC_M15_UNAVAILABLE in result.block_codes


def test_a_fresh_snapshot_whose_zone_changed_blocks_as_setup_changed():
    comparison, _ = _fresh_call({"symbol": "XAUUSD", "smc_zone_id": "smcz-approved"})
    assert comparison["current"]["selected_zone_id"] not in (None, "smcz-approved")
    result = _engine(comparison)
    assert result.allowed is False
    assert SMC_SETUP_CHANGED in result.block_codes


def test_an_approved_identity_matching_the_fresh_snapshot_does_not_block_on_setup():
    """Control: when the approved ids ARE the fresh ones, the setup is stable.

    The engine may still block on the honest M15/readiness state of this real
    fixture — that is the truthful verdict, not a fabricated confirmation.
    """

    fresh, _ = _fresh_call({"symbol": "XAUUSD", "smc_zone_id": "placeholder"})
    current = fresh["current"]
    approved = {
        "symbol": "XAUUSD",
        "smc_zone_id": current["selected_zone_id"],
        "smc_setup_id": current["selected_setup_id"],
    }
    comparison, _ = _fresh_call(approved)
    assert comparison["approved"] == {
        "selected_zone_id": current["selected_zone_id"],
        "selected_setup_id": current["selected_setup_id"],
    }
    assert SMC_SETUP_CHANGED not in _engine(comparison).block_codes


def test_a_missing_or_unusable_fresh_snapshot_blocks_as_unavailable():
    """cutoff/candle/metadata/evaluator problems never pass as an approval."""

    from controllers.scanner_controller import ScannerController

    without_identity = _fresh_call({"symbol": "XAUUSD"})[0]
    assert without_identity is None

    stub = _StubController(
        {"D1": [], "H4": [], "H1": [], "M15": []}, {"tick_size": 0.01}
    )
    missing = ScannerController._smc_revalidation_for_order(
        stub,
        {"symbol": "XAUUSD", "smc_zone_id": "smcz-approved"},
        broker_symbol="XAUUSD",
        side="buy",
        settings=_Settings(),
        now=A_CUTOFF,
    )
    assert missing is None

    class _Raises(_StubController):
        def load_primary_timeframes(self, _broker_symbol, _bars):
            raise RuntimeError("mt5 unavailable")

    failed = ScannerController._smc_revalidation_for_order(
        _Raises({}, {}),
        {"symbol": "XAUUSD", "smc_zone_id": "smcz-approved"},
        broker_symbol="XAUUSD",
        side="buy",
        settings=_Settings(),
        now=A_CUTOFF,
    )
    assert failed is None

    for unavailable in (without_identity, missing, failed):
        result = _engine(unavailable)
        assert result.allowed is False
        assert SMC_REVALIDATION_UNAVAILABLE in result.block_codes


def test_the_fresh_snapshot_is_built_once_with_the_injected_cutoff(monkeypatch):
    """The boundary builds ONE canonical snapshot per dispatch attempt."""

    from core import scanner_live_producers

    calls: list[dict] = []
    real = scanner_live_producers.derive_live_analysis

    def spy(*args, **kwargs):
        calls.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(scanner_live_producers, "derive_live_analysis", spy)
    comparison, _ = _fresh_call({"symbol": "XAUUSD", "smc_zone_id": "smcz-approved"})

    assert len(calls) == 1
    assert calls[0]["captured_at"] == A_CUTOFF
    assert calls[0]["m15_as_of"] == A_CUTOFF
    assert comparison["source"] == "fresh_canonical_snapshot"
