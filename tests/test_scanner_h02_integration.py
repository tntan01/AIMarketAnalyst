"""Task 30 (H02): targeted live-to-UI integration and non-order smoke checks."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from core.location_engine import (
    DEFAULT_LOCATION_CONFIG,
    build_location_context,
    score_location,
)
from core.scanner_features import TechnicalRawDerivationError, prepare_location_results
from core.scanner_live_producers import derive_live_analysis
from core.scanner_release import run_pair_from_live
from core.scanner_row import scanner_row_from_composition
from core.scanner_ui_adapter import pair_to_ui_row
from tests.test_location_engine import NOW as LOCATION_NOW, _score_context, _zone, _zone_history
from tests.test_scanner_features import _location_candles
from tests.test_scanner_live_producers import NOW as LIVE_NOW, _mk
from tests.test_scanner_release import _live_candles, _live_safety


def _reference_h1(cutoff=LOCATION_NOW):
    from core.market_models import Candle

    return [
        Candle(
            time=cutoff - timedelta(hours=80 - index),
            open=100.0,
            high=100.1,
            low=99.9,
            close=100.0,
        )
        for index in range(80)
    ]


def test_live_release_reaches_snapshot_row_and_ui_without_dispatch():
    d1, h4, h1 = _live_candles()
    analysis = derive_live_analysis(
        d1, h4, h1, symbol="XAUUSD", captured_at=LIVE_NOW
    )
    pair = run_pair_from_live(
        d1,
        h4,
        h1,
        "XAUUSD",
        _live_safety(),
        now=LIVE_NOW,
        captured_at=LIVE_NOW,
        analysis=analysis,
        macro_raw_buy=20,
        macro_raw_sell=14,
        macro_confidence=0.8,
    )

    row = scanner_row_from_composition(pair.composition)
    ui_row = pair_to_ui_row(
        pair,
        broker_symbol="XAUUSDc",
        technical=analysis["technical"],
    )

    assert {side.side for side in row.side_scores} == {"buy", "sell"}
    assert all(side.location_status == "NO_VALID_ANCHOR" for side in row.side_scores)
    assert all(
        item.get("location_detail", {}).get("status") == "NO_VALID_ANCHOR"
        for item in ui_row["side_scores"]
    )
    if pair.candidate is not None and pair.candidate.order_payload is not None:
        assert pair.candidate.order_payload.sends_real_order is False
    assert ui_row["candidate_order_payload"] is None or (
        ui_row["candidate_order_payload"]["sends_real_order"] is False
    )


def test_live_location_status_matrix_covers_evaluated_conflict_and_no_anchor():
    from core.market_models import Candle

    h4 = [Candle(**item) for item in _zone_history()]
    d1 = _mk(120, 0.08, 0.0, interval_hours=24.0)
    h1 = _reference_h1(LOCATION_NOW)
    analysis = derive_live_analysis(
        d1, h4, h1, symbol="EURUSD", captured_at=LOCATION_NOW
    )
    evaluated = analysis["raws"].per_side["buy"].location_detail

    conflict = score_location("buy", _score_context(100.0, (_zone("support"), _zone("resistance"))))
    no_anchor = score_location(
        "buy",
        _score_context(
            100.0,
            (replace(_zone("resistance"), low=103.0, high=104.0),),
        ),
    )

    assert evaluated is not None and evaluated.status == "EVALUATED"
    assert conflict.status == "CONFLICT" and conflict.raw == 0
    assert no_anchor.status == "NO_VALID_ANCHOR" and no_anchor.raw == 0


def test_live_location_unavailable_fails_closed_without_legacy_fallback():
    h4, h1 = _location_candles()
    flat_h4 = [
        bar.__class__(
            time=bar.time,
            open=100.0,
            high=100.0,
            low=100.0,
            close=100.0,
        )
        for bar in h4
    ]

    with pytest.raises(TechnicalRawDerivationError) as caught:
        prepare_location_results(flat_h4, h1, cutoff=LIVE_NOW)

    assert caught.value.reason_code == "LOCATION_INVALID_DATA"
    assert caught.value.field == "context.current_atr_h4"
    assert caught.value.cause is not None


def test_location_context_smoke_keeps_shared_reference_and_history_cutoff():
    context = build_location_context(
        _zone_history(), 100.0, LOCATION_NOW, DEFAULT_LOCATION_CONFIG
    )

    assert context.reference_price == 100.0
    assert context.reference_closed_at is None
    assert context.h4_bars_considered == 60
    assert all(zone.confirmed_at <= LOCATION_NOW for zone in context.zones)


def test_controller_packet_cutoff_survives_worker_delay_across_h1_h4_boundary(
    monkeypatch,
):
    """The packet cutoff, not worker time, reaches analysis and snapshot."""
    from core.location_engine import closed_candles_at_cutoff, reference_from_closed_h1
    from controllers import scanner_controller

    d1, h4, h1 = _live_candles()
    cutoff = datetime(2026, 8, 13, 11, 0, tzinfo=timezone.utc)

    # The final H1 opens exactly at the cutoff and the final H4 still closes
    # after it. Both must remain outside the Location input at this boundary;
    # the previous H1 may close exactly at the cutoff.
    assert reference_from_closed_h1(h1, cutoff).reference_closed_at <= cutoff
    assert h1[-1].time == datetime(2026, 8, 13, 11, 0, tzinfo=timezone.utc)
    assert h4[-1].time == datetime(2026, 8, 13, 8, 0, tzinfo=timezone.utc)
    assert closed_candles_at_cutoff(h4, "H4", cutoff)[-1].candle.time < h4[-1].time

    seen: dict[str, object] = {}
    real_run_pair = scanner_controller.run_pair_from_live

    def _run_pair_spy(*args, **kwargs):
        seen["run_now"] = kwargs["now"]
        seen["run_captured_at"] = kwargs["captured_at"]
        result = real_run_pair(*args, **kwargs)
        seen["snapshot_captured_at"] = result.composition.captured_at
        return result

    monkeypatch.setattr(scanner_controller, "run_pair_from_live", _run_pair_spy)
    packet = {
        "symbol": "XAUUSD",
        "broker_symbol": "XAUUSD",
        "candles": {"D1": d1, "H4": h4, "H1": h1},
        "macro_context": {},
        "input_timestamps": {},
        "v4_safety": _live_safety(),
        "v4_captured_at": cutoff,
        "location_cutoff": cutoff,
        "account": None,
        "portfolio": None,
        "journal": None,
    }

    row = scanner_controller._analyze_one_symbol(
        packet,
        correlation_context={},
        freshness_multiplier=1.0,
        contract_size_overrides={},
        analysis_input_kwargs={},
        closed_trades=[],
        account_guard_settings={},
    )

    assert row["candidate_status"] in {
        "READY_NOW",
        "WAITING_CONFIRMATION",
        "WATCH_ZONE",
        "BLOCKED",
        "DATA_UNAVAILABLE",
    }
    assert seen["run_captured_at"] == cutoff
    assert seen["snapshot_captured_at"] == cutoff
    assert isinstance(seen["run_now"], datetime)
    assert seen["run_now"] > cutoff
