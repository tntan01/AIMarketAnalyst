"""Unit tests for the pure candle merge utility."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.market_models import (
    Candle,
    candles_from_dicts,
    candles_to_dicts,
    merge_candles,
    normalize_candles,
)


def _candle(time: datetime, open_: float, close: float) -> Candle:
    return Candle(time=time, open=open_, high=max(open_, close), low=min(open_, close), close=close)


def _t(offset: int) -> datetime:
    return datetime(2026, 8, 3, 12, 0) + timedelta(minutes=60 * offset)


def test_merge_replaces_duplicate_times_with_new():
    old = [_candle(_t(0), 1.0, 1.1), _candle(_t(1), 1.1, 1.2)]
    new = [_candle(_t(1), 2.0, 2.1), _candle(_t(2), 2.1, 2.2)]
    merged = merge_candles(old, new)
    assert [c.time for c in merged] == [_t(0), _t(1), _t(2)]
    by_time = {c.time: c for c in merged}
    assert by_time[_t(0)].close == 1.1
    assert by_time[_t(1)].close == 2.1
    assert by_time[_t(2)].close == 2.2


def test_merge_updates_still_forming_last_candle():
    old = [_candle(_t(0), 1.0, 1.1), _candle(_t(1), 1.1, 1.2)]
    new = [_candle(_t(1), 1.3, 1.4)]
    merged = merge_candles(old, new)
    assert [c.time for c in merged] == [_t(0), _t(1)]
    assert merged[-1].close == 1.4


def test_merge_appends_new_candles_in_time_order():
    old = [_candle(_t(0), 1.0, 1.1), _candle(_t(1), 1.1, 1.2)]
    new = [_candle(_t(2), 1.2, 1.3), _candle(_t(3), 1.3, 1.4)]
    merged = merge_candles(old, new)
    assert [c.time for c in merged] == [_t(0), _t(1), _t(2), _t(3)]
    assert [c.close for c in merged] == [1.1, 1.2, 1.3, 1.4]


def test_merge_with_empty_new_data_keeps_old():
    old = [_candle(_t(0), 1.0, 1.1), _candle(_t(1), 1.1, 1.2)]
    merged = merge_candles(old, [])
    assert merged == old
    assert [c.time for c in merged] == [old[0].time, old[1].time]


def test_merge_with_empty_old_data_keeps_new():
    new = [_candle(_t(0), 1.0, 1.1), _candle(_t(1), 1.1, 1.2)]
    merged = merge_candles([], new)
    assert merged == new
    assert [c.time for c in merged] == [new[0].time, new[1].time]


def test_merge_both_empty_returns_empty():
    assert merge_candles([], []) == []


def test_merge_does_not_create_duplicates_or_lose_closed():
    old = [_candle(_t(0), 1.0, 1.1), _candle(_t(1), 1.1, 1.2), _candle(_t(2), 1.2, 1.3)]
    new = [_candle(_t(1), 9.0, 9.1), _candle(_t(2), 9.1, 9.2), _candle(_t(3), 9.2, 9.3)]
    merged = merge_candles(old, new)
    times = [c.time for c in merged]
    assert times == sorted(times)
    assert len(times) == len(set(times))
    assert len(merged) == 4
    assert merged[0].close == 1.1
    assert merged[1].close == 9.1
    assert merged[2].close == 9.2
    assert merged[3].close == 9.3


def _candle_dict(time: datetime, open_: float, close: float) -> dict:
    return {
        "time": time.isoformat(),
        "open": open_,
        "high": max(open_, close),
        "low": min(open_, close),
        "close": close,
        "volume": 100.0,
    }


def test_candles_from_dicts_parses_naive_and_aware_to_utc():
    naive = _candle_dict(datetime(2026, 8, 3, 12, 0), 1.0, 1.1)
    aware = _candle_dict(datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc) + timedelta(hours=1), 1.1, 1.2)
    parsed = candles_from_dicts([naive, aware])
    assert len(parsed) == 2
    assert all(c.time.tzinfo is not None for c in parsed)
    assert parsed[0].time == datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    assert parsed[1].time == datetime(2026, 8, 3, 13, 0, tzinfo=timezone.utc)


def test_candles_to_dicts_roundtrips_time_format():
    candle = _candle(datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc), 1.0, 1.1)
    out = candles_to_dicts([candle])
    assert out[0]["time"] == datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc).isoformat()
    assert out[0]["open"] == 1.0
    assert out[0]["close"] == 1.1
    assert "volume" in out[0]


def test_normalize_candles_makes_naive_candles_aware_utc():
    naive = _candle(datetime(2026, 8, 3, 12, 0), 1.0, 1.1)
    aware = _candle(datetime(2026, 8, 3, 13, 0, tzinfo=timezone.utc), 1.1, 1.2)
    normalized = normalize_candles([naive, aware])
    assert all(c.time.tzinfo is not None for c in normalized)
    assert normalized[0].time == datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    assert normalized[1].time == datetime(2026, 8, 3, 13, 0, tzinfo=timezone.utc)


def test_merge_handles_mixed_timezone_sources_without_error():
    # Old snapshot dicts are naive; new provider candles are aware UTC.
    old_dicts = [_candle_dict(datetime(2026, 8, 3, 12, 0), 1.0, 1.1)]
    new_candles = [
        _candle(datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc), 1.2, 1.3),
        _candle(datetime(2026, 8, 3, 13, 0, tzinfo=timezone.utc), 1.3, 1.4),
    ]
    old = normalize_candles(candles_from_dicts(old_dicts))
    merged = merge_candles(old, normalize_candles(new_candles))
    assert [c.time for c in merged] == [
        datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc),
        datetime(2026, 8, 3, 13, 0, tzinfo=timezone.utc),
    ]
    assert merged[0].close == 1.3
    assert merged[1].close == 1.4