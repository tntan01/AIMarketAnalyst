"""Task 60 contracts for lifecycle reaction follow-through."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.market_models import Candle, candle_close_at, validate_smc_candles
from core.smc_lifecycle import analyze_zone_lifecycle


START = datetime(2026, 9, 11, tzinfo=timezone.utc)


def _candles(rows):
    values = [
        Candle(
            time=START + timedelta(hours=index),
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=100,
        )
        for index, (open_, high, low, close) in enumerate(rows)
    ]
    issues = validate_smc_candles(values, "H1")
    assert not issues, f"task60 fixture must contain valid OHLC: {issues}"
    return values


def _lifecycle(candles, *, side="buy", **kwargs):
    return analyze_zone_lifecycle(
        candles=candles,
        low=100,
        high=110,
        side=side,
        origin_index=0,
        departure_end_index=1,
        zone_id="smcz-task60",
        timeframe="H1",
        tf_minutes=60,
        atr_current=2.0,
        **kwargs,
    )


def _base_visit(*tail):
    return _candles([
        (112, 114, 111, 113),
        (112, 114, 111, 113),
        (105, 111, 105, 108),
        *tail,
    ])


def test_open_visit_is_not_reacted():
    result = _lifecycle(_base_visit())

    visit = result.visits[0]
    assert visit.visit_state == "open"
    assert visit.reacted_at is None


def test_exit_without_follow_through_is_completed_unreacted():
    result = _lifecycle(_base_visit((112, 113, 110.2, 110.2)))

    visit = result.visits[0]
    assert visit.visit_state == "completed_unreacted"
    assert visit.reacted_at is None


def test_buy_reaction_is_allowed_within_three_candles():
    candles = _base_visit(
        (112, 113, 110.2, 110.2),
        (111, 112, 110.3, 110.3),
        (112, 113, 110.5, 110.5),
    )
    result = _lifecycle(candles)

    visit = result.visits[0]
    assert visit.visit_state == "completed_reacted"
    assert visit.reacted_at == candle_close_at(candles[5].time, "H1").isoformat()


def test_sell_reaction_is_symmetric():
    candles = _candles([
        (88, 89, 86, 87),
        (88, 89, 86, 87),
        (101, 105, 99, 102),
        (98, 99.8, 97.5, 99.8),
        (99, 99.7, 98, 99.7),
        (98, 99.5, 97, 99.5),
    ])
    result = _lifecycle(candles, side="sell")

    visit = result.visits[0]
    assert visit.visit_state == "completed_reacted"
    assert visit.reacted_at == candle_close_at(candles[5].time, "H1").isoformat()


def test_same_exit_candle_can_emit_exit_then_reaction():
    candles = _base_visit((112, 113, 110.5, 110.5))
    result = _lifecycle(candles)

    visit = result.visits[0]
    assert visit.visit_state == "completed_reacted"
    assert visit.exited_at == visit.reacted_at == candle_close_at(
        candles[3].time, "H1"
    ).isoformat()


def test_follow_through_after_three_candles_does_not_react():
    candles = _base_visit(
        (112, 113, 110.2, 110.2),
        (112, 113, 110.3, 110.3),
        (112, 113, 110.4, 110.4),
        (112, 113, 110.4, 110.4),
        (112, 113, 110.5, 110.5),
    )
    result = _lifecycle(candles)

    assert result.visits[0].visit_state == "completed_unreacted"
    assert result.visits[0].reacted_at is None


def test_invalidation_before_reaction_has_priority():
    candles = _base_visit(
        (112, 113, 110.2, 110.2),
        (99, 100, 98, 99),
        (112, 113, 110.5, 110.5),
    )
    # F02/r1: explicit synthetic metadata at the call site (TL-approved);
    # buffer = max(0.1, 0.05*2) = 0.1 keeps the invalidation close below the threshold.
    result = _lifecycle(candles, tick_size=0.1)

    assert result.lifecycle_broken is True
    assert result.visits[0].visit_state == "completed_unreacted"
    assert result.visits[0].reacted_at is None


def test_invalidation_while_visit_open_closes_visit_without_reaction():
    candles = _base_visit(
        (99, 100, 98, 99),
    )
    # F02/r1: explicit synthetic metadata at the call site (TL-approved);
    # buffer = max(0.1, 0.05*2) = 0.1 keeps the invalidation close below the threshold.
    result = _lifecycle(candles, tick_size=0.1)

    assert result.lifecycle_broken is True
    assert result.visits[0].visit_state == "closed_by_invalidation"
    assert result.visits[0].reacted_at is None
