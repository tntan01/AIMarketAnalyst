"""M15 entry confirmation at the selected SMC zone.

The evaluator rebuilds the M15 entry visits of the zone and only the current
visit or a just-completed one inside its trigger window can confirm an entry:
a micro break of a confirmed level with departure out of the zone, or a
rejection at the zone with follow-through out of it.  Every outcome maps to a
reason code, and M15 owns readiness only — it never adds or subtracts points
(R16-03, parameter table P10).

Contract sources for the expectations below: lifecycle spec §11 (R16-02),
parameter table P10 and the acceptance dossier row for tasks 73–79.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.analysis_engine import analyze_symbol
from core.market_models import Candle
from core.smc_m15_confirmation import (
    M15_CONFIRMATION_REASON,
    M15_DATA_UNAVAILABLE_REASON,
    M15_INSUFFICIENT_DATA_REASON,
    M15_NO_CONFIRMATION_REASON,
    M15_ZONE_NOT_TESTED_REASON,
    TRIGGER_EXPIRED_REASON,
    evaluate_m15_confirmation,
)
from core.smc_snapshot import build_smc_snapshot, evaluate_smc_snapshot
from core.smc_prefilter import (
    NO_ACTIONABLE_SMC_ZONE,
    evaluate_post_context_prefilter,
)
from core.smc_scorer import score_smc
from tests.test_analysis_pipeline_integration import (
    _build_candles_by_timeframe,
    _default_input,
)
from tests.test_smc_m15_confirmation_task79 import (
    _close_at,
    _mirror,
    _micro_break_candles,
    _rejection_candles,
    _unconfirmed_level_candles,
    _warmup,
)
from tests.test_smc_scorer import _smc, _technical


_REGIME = {"primary": "trend_up"}
_TIME0 = datetime(2026, 8, 6, tzinfo=timezone.utc)

# The shared scorer fixtures select the buy zone [90, 95] and the sell
# zone [105, 110].
_BUY_ZONE = (90.0, 95.0)
_SELL_ZONE = (105.0, 110.0)
_BUY_ZONE_ID = "smcz-module-buy"
_SELL_ZONE_ID = "smcz-module-sell"


def _as_of(candles) -> datetime:
    """Snapshot cutoff of a fixture window: the close of its last candle."""

    return _close_at(candles[-1])


def _confirmation(side, zone, candles, *, zone_id, **kwargs):
    """Run the dict adapter with the snapshot cutoff of the fixture window.

    Missing/empty candle input is passed through untouched: those states are
    decided before the cutoff so the caller keeps their own reason.
    """

    if isinstance(candles, (list, tuple)) and candles:
        kwargs.setdefault("as_of", _as_of(candles))
    return evaluate_m15_confirmation(
        side,
        zone[0],
        zone[1],
        candles,
        zone_id=zone_id,
        **kwargs,
    )


def _candle(index: int, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        time=_TIME0 + timedelta(minutes=15 * index),
        open=open_,
        high=high,
        low=low,
        close=close,
    )


def _stagnation_at_zone() -> list[Candle]:
    """Price drops into the demand zone and stalls without any reaction.

    The first overlap opens the entry visit; 48 bars later the trigger window
    is long past, so the outcome is an expired trigger rather than a
    confirmation from the first touch.
    """

    return _warmup(20) + [
        _candle(index, 95.40, 95.50, 94.90, 95.00) if index == 20
        else _candle(index, 94.90, 95.10, 94.80, 95.00)
        for index in range(20, 48)
    ]


def _stagnation_at_supply() -> list[Candle]:
    return _mirror(_stagnation_at_zone())


def _above_zone() -> list[Candle]:
    """Price stays well above the demand zone: the zone is never tested."""

    return _warmup(48, 105.0)


# -- Evaluator statuses ------------------------------------------------------


def test_insufficient_m15_data_is_warning_only():
    none_result = _confirmation("buy", _BUY_ZONE, None, zone_id=_BUY_ZONE_ID)
    # An empty window with a valid cutoff is "not enough candles"; without a
    # cutoff the snapshot boundary itself is missing, so the cutoff reason wins.
    empty_result = evaluate_m15_confirmation(
        "buy",
        *_BUY_ZONE,
        [],
        zone_id=_BUY_ZONE_ID,
        as_of=_as_of(_stagnation_at_zone()),
    )
    no_cutoff_empty = evaluate_m15_confirmation(
        "buy", *_BUY_ZONE, [], zone_id=_BUY_ZONE_ID
    )
    # Missing data and too little data are distinct states (readiness §5.1).
    assert none_result["status"] == "insufficient_data"
    assert none_result["penalty"] == 0
    assert none_result["reason_codes"] == [M15_DATA_UNAVAILABLE_REASON]
    assert none_result["m15_status"] == "missing"
    assert empty_result["status"] == "insufficient_data"
    assert empty_result["reason_codes"] == [M15_INSUFFICIENT_DATA_REASON]
    assert no_cutoff_empty["reason_codes"] == ["SMC_CUTOFF_MISSING"]

    short_result = _confirmation(
        "buy", _BUY_ZONE, _warmup(10), zone_id=_BUY_ZONE_ID
    )
    assert short_result["status"] == "insufficient_data"
    assert short_result["confirmed"] is False
    assert short_result["penalty"] == 0
    assert short_result["reason_codes"] == [M15_INSUFFICIENT_DATA_REASON]

    invalid_zone = _confirmation(
        "buy", (95.0, 90.0), _stagnation_at_zone(), zone_id=_BUY_ZONE_ID
    )
    assert invalid_zone["status"] == "insufficient_data"
    assert invalid_zone["reason_codes"] == [M15_INSUFFICIENT_DATA_REASON]
    invalid_side = _confirmation(
        "hold", _BUY_ZONE, _stagnation_at_zone(), zone_id=_BUY_ZONE_ID
    )
    assert invalid_side["status"] == "insufficient_data"
    assert invalid_side["reason_codes"] == [M15_DATA_UNAVAILABLE_REASON]


def test_zone_not_tested_traces_warning_without_penalty():
    result = _confirmation("buy", _BUY_ZONE, _above_zone(), zone_id=_BUY_ZONE_ID)

    assert result["status"] == "zone_not_tested"
    assert result["confirmed"] is False
    assert result["penalty"] == 0
    assert result["reason_codes"] == [M15_ZONE_NOT_TESTED_REASON]
    assert result["m15_status"] == "waiting"


def test_tested_zone_without_confirmation_keeps_quality():
    """Historical name: this node used to assert the removed 2-point penalty."""

    result = _confirmation(
        "buy", _BUY_ZONE, _stagnation_at_zone(), zone_id=_BUY_ZONE_ID
    )

    assert result["status"] == "expired"
    assert result["confirmed"] is False
    assert result["penalty"] == 0
    assert result["reason_codes"] == [
        M15_NO_CONFIRMATION_REASON,
        TRIGGER_EXPIRED_REASON,
    ]
    assert result["choch"] is False
    assert result["reaction"] is False


def test_rejection_at_zone_confirms():
    result = _confirmation(
        "buy", _BUY_ZONE, _rejection_candles(), zone_id=_BUY_ZONE_ID
    )

    assert result["status"] == "confirmed"
    assert result["confirmed"] is True
    assert result["penalty"] == 0
    assert result["reason_codes"] == [M15_CONFIRMATION_REASON]
    assert result["reaction"] is True
    assert result["choch"] is False
    assert result["confirmation_id"] == f"{_BUY_ZONE_ID}:m15-visit-1:confirm-1"
    assert result["trigger_event_id"] == f"{_BUY_ZONE_ID}:m15-visit-1:trigger-1"
    assert result["confirmed_at"] == "2026-08-06T07:45:00+00:00"
    assert result["expires_at"] == "2026-08-06T10:30:00+00:00"


def test_micro_break_after_zone_touch_confirms():
    """Historical name: the branch is a confirmed micro break, not an HL/LH pair."""

    result = _confirmation(
        "buy", _BUY_ZONE, _micro_break_candles(), zone_id=_BUY_ZONE_ID
    )

    assert result["status"] == "confirmed"
    assert result["choch"] is True
    assert result["reaction"] is False
    assert result["penalty"] == 0
    assert result["confirmed"] is True


def test_displacement_without_confirmed_break_does_not_confirm():
    """Historical name: a strong candle alone is no longer a confirmation.

    Design §5/§7: the break must be of a level that is confirmed, so a lone
    displacement body never confirms an entry.
    """

    result = _confirmation(
        "buy", _BUY_ZONE, _unconfirmed_level_candles(), zone_id=_BUY_ZONE_ID
    )

    assert result["status"] == "waiting"
    assert result["confirmed"] is False
    assert result["choch"] is False
    assert result["reaction"] is False
    assert M15_NO_CONFIRMATION_REASON in result["reason_codes"]


def test_sell_side_confirmation_is_mirrored():
    result = _confirmation(
        "sell", _SELL_ZONE, _mirror(_rejection_candles()), zone_id=_SELL_ZONE_ID
    )

    assert result["status"] == "confirmed"
    assert result["reaction"] is True
    assert result["confirmed"] is True

    unconfirmed = _confirmation(
        "sell", _SELL_ZONE, _stagnation_at_supply(), zone_id=_SELL_ZONE_ID
    )
    assert unconfirmed["status"] == "expired"
    assert unconfirmed["confirmed"] is False
    assert unconfirmed["penalty"] == 0


# -- Scorer integration ------------------------------------------------------


def test_score_smc_without_m15_is_unchanged():
    baseline = score_smc(_smc("buy"), _technical("buy"), _REGIME).side("buy")

    explicit_none = score_smc(
        _smc("buy"),
        _technical("buy"),
        _REGIME,
        m15_candles=None,
    ).side("buy")

    assert explicit_none.score == baseline.score
    assert explicit_none.breakdown == baseline.breakdown


def test_missing_m15_confirmation_does_not_deduct_points():
    """Historical name: a tested-but-unconfirmed zone used to lose 2 points."""

    baseline = score_smc(_smc("buy"), _technical("buy"), _REGIME).side("buy")

    side = score_smc(
        _smc("buy"),
        _technical("buy"),
        _REGIME,
        m15_candles=_stagnation_at_zone(),
        m15_as_of=_as_of(_stagnation_at_zone()),
    ).side("buy")

    assert side.score == baseline.score
    assert side.breakdown["subtotal"] == baseline.breakdown["subtotal"]
    assert side.breakdown["penalty_points"] == baseline.breakdown["penalty_points"]
    assert side.breakdown["penalties"] == baseline.breakdown["penalties"]
    assert M15_NO_CONFIRMATION_REASON in side.breakdown["reason_codes"]
    assert M15_NO_CONFIRMATION_REASON not in side.breakdown["penalties"]


def test_m15_confirmation_never_adds_points():
    baseline = score_smc(_smc("buy"), _technical("buy"), _REGIME).side("buy")

    side = score_smc(
        _smc("buy"),
        _technical("buy"),
        _REGIME,
        m15_candles=_micro_break_candles(),
        m15_as_of=_as_of(_micro_break_candles()),
    ).side("buy")

    assert side.score == baseline.score
    assert (
        side.breakdown["penalty_points"]
        == baseline.breakdown["penalty_points"]
    )
    assert M15_CONFIRMATION_REASON in side.breakdown["reason_codes"]
    assert M15_CONFIRMATION_REASON not in side.breakdown["penalties"]


def test_zone_not_tested_and_insufficient_trace_warning_only():
    baseline = score_smc(_smc("buy"), _technical("buy"), _REGIME).side("buy")

    cases = (
        (_above_zone(), M15_ZONE_NOT_TESTED_REASON),
        (_warmup(10), M15_INSUFFICIENT_DATA_REASON),
    )
    for candles, expected_code in cases:
        side = score_smc(
            _smc("buy"),
            _technical("buy"),
            _REGIME,
            m15_candles=candles,
            m15_as_of=_as_of(candles),
        ).side("buy")
        assert side.score == baseline.score
        assert (
            side.breakdown["penalty_points"]
            == baseline.breakdown["penalty_points"]
        )
        assert expected_code in side.breakdown["reason_codes"]
        assert expected_code not in side.breakdown["penalties"]


def test_sell_side_missing_confirmation_does_not_deduct_points():
    """Historical name: the sell side used to lose 2 points as well."""

    baseline = score_smc(_smc("sell"), _technical("sell"), _REGIME).side("sell")

    side = score_smc(
        _smc("sell"),
        _technical("sell"),
        _REGIME,
        m15_candles=_stagnation_at_supply(),
        m15_as_of=_as_of(_stagnation_at_supply()),
    ).side("sell")

    assert side.score == baseline.score
    assert M15_NO_CONFIRMATION_REASON in side.breakdown["reason_codes"]
    assert M15_NO_CONFIRMATION_REASON not in side.breakdown["penalties"]


def test_side_without_selected_zone_skips_m15():
    baseline = score_smc(_smc("buy"), _technical("buy"), _REGIME).side("sell")

    sell_side = score_smc(
        _smc("buy"),
        _technical("buy"),
        _REGIME,
        m15_candles=_stagnation_at_zone(),
        m15_as_of=_as_of(_stagnation_at_zone()),
    ).side("sell")

    assert sell_side.score == baseline.score
    assert sell_side.breakdown == baseline.breakdown
    assert M15_NO_CONFIRMATION_REASON not in sell_side.breakdown["reason_codes"]
    assert M15_CONFIRMATION_REASON not in sell_side.breakdown["reason_codes"]


def test_m15_evidence_keeps_existing_caps():
    """Historical name: the node used to assert the removed M15 penalty."""

    context = _smc("buy", h4_choch_against=True)
    baseline = score_smc(context, _technical("buy"), _REGIME).side("buy")

    side = score_smc(
        context,
        _technical("buy"),
        _REGIME,
        m15_candles=_stagnation_at_zone(),
        m15_as_of=_as_of(_stagnation_at_zone()),
    ).side("buy")

    assert baseline.breakdown["applied_cap"] == 4
    assert side.breakdown["applied_cap"] == 4
    assert side.score <= 4
    assert side.breakdown["penalty_points"] == baseline.breakdown["penalty_points"]
    assert M15_NO_CONFIRMATION_REASON in side.breakdown["reason_codes"]
    assert M15_NO_CONFIRMATION_REASON not in side.breakdown["penalties"]


# -- Wiring (prefilter + pipeline) -------------------------------------------


def _snapshot(*, smc, technical, m15_candles=None, m15_as_of=None):
    """Freeze the same snapshot the runtime callers hand the prefilter."""

    from tests.test_scanner_release import _zoned_candles

    from datetime import timedelta

    d1, h4, h1 = _zoned_candles()
    # The snapshot boundary must belong to the SAME data that feeds the core
    # verdict, so it is the newest close of these candles — not the boundary of
    # the separate M15 window under test.
    cutoff = max(
        candle.time + interval
        for candles, interval in (
            (d1, timedelta(days=1)),
            (h4, timedelta(hours=4)),
            (h1, timedelta(hours=1)),
        )
        for candle in candles
    )
    return build_smc_snapshot(
        {"D1": d1, "H4": h4, "H1": h1, "M15": m15_candles or ()},
        symbol="EUR/USD",
        as_of=cutoff,
        m15_as_of=m15_as_of or cutoff,
        tick_size=0.00001,
        context_builder=lambda *a, **k: smc,
        technical_builder=lambda *a, **k: technical,
    )


def test_prefilter_forwards_m15_candles_to_scorer():
    """Task 104: the prefilter evaluates ONE snapshot and hands it on.

    The M15 window travels inside the snapshot, so the verdict the Tier-1
    predicate publishes IS the canonical evaluation of exactly that window —
    there is no second scorer call to diverge from it.
    """

    candles = _stagnation_at_zone()
    snapshot = _snapshot(
        smc=_smc("buy"),
        technical=_technical("buy"),
        m15_candles=candles,
        m15_as_of=_as_of(candles),
    )

    decision = evaluate_post_context_prefilter(snapshot=snapshot)
    direct = evaluate_smc_snapshot(snapshot)

    assert decision["fail_open"] is False
    assert decision["precomputed_evaluation"] is not None
    assert decision["precomputed_smc"] == direct.result
    assert decision["selected_zone_ids"] == {
        side: direct.selection(side).selected_zone_id for side in ("buy", "sell")
    }
    assert snapshot.m15_candles == tuple(candles)


def test_prefilter_without_m15_matches_plain_scorer():
    """The no-M15 snapshot is evaluated on its own terms, not by a fallback."""

    snapshot = _snapshot(smc=_smc("buy"), technical=_technical("buy"))
    decision = evaluate_post_context_prefilter(snapshot=snapshot)
    direct = evaluate_smc_snapshot(snapshot)

    assert decision["precomputed_smc"] == direct.result
    assert snapshot.m15_available is False


def test_prefilter_reject_decision_ignores_m15():
    """An evaluated-empty snapshot is rejected whatever the M15 window says."""

    empty_smc = {"symbol": "TEST", "D1": {}, "H4": {}, "H1": {}, "confluence": {}}
    candles = _stagnation_at_zone()
    snapshot = _snapshot(
        smc=empty_smc,
        technical=_technical("buy"),
        m15_candles=candles,
        m15_as_of=_as_of(candles),
    )

    decision = evaluate_post_context_prefilter(snapshot=snapshot)

    assert decision["should_reject"] is True
    assert decision["fail_open"] is False
    assert decision["reason_code"] == NO_ACTIONABLE_SMC_ZONE


def test_pipeline_forwards_m15_candles_and_cutoff_to_scorer(monkeypatch):
    """The Analyze seam must keep the window and its snapshot cutoff together."""

    from core.analysis_pipeline import AnalysisPipeline

    candles = _build_candles_by_timeframe(regime="trending_up")
    # The fixture's timeframes end at different instants, so the snapshot
    # boundary is the newest close across them (the M15 window itself ends
    # earlier and must still travel inside the snapshot).
    cutoff = max(
        _close_at(candles[timeframe][-1])
        for timeframe in ("D1", "H4", "H1", "M15")
    )

    pipeline = AnalysisPipeline()
    result = pipeline.execute(
        _default_input(),
        candles,
        m15_candles=candles["M15"],
        m15_as_of=cutoff,
    )

    assert result["analysis_status"] == "completed"
    # Task 101/103: the window and its boundary travel INSIDE the frozen
    # snapshot the canonical chain consumes.
    snapshot = pipeline._smc_snapshot
    assert snapshot is not None
    assert snapshot.m15_as_of == cutoff
    assert tuple(snapshot.m15_candles or ()) == tuple(candles["M15"])


def test_pipeline_never_fabricates_a_cutoff_for_the_m15_step(monkeypatch):
    """No caller cutoff means no cutoff: the seam must not invent one.

    Fabricating a cutoff from the wall clock or from the last list element is
    what R73-01 forbids.  Data spec §1 makes the snapshot cutoff mandatory, so
    Analyze refuses the input outright instead of evaluating a window of
    unknown boundary.
    """

    import pytest as _pytest

    from core.analysis_pipeline import AnalysisPipeline

    candles = _build_candles_by_timeframe(regime="trending_up")

    with _pytest.raises(ValueError) as exc_info:
        AnalysisPipeline().execute(
            _default_input(),
            candles,
            m15_candles=candles["M15"],
        )

    assert "SMC snapshot cutoff" in str(exc_info.value)
    assert "SMC_CUTOFF_MISSING" in str(exc_info.value)
