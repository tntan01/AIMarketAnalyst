from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from services.candle_history_cache import (
    CacheFallbackReason,
    CacheIdentity,
    CandleHistoryCache,
)


H1 = timedelta(hours=1)


def _identity(
    *,
    server: str = "Broker-Demo",
    account: str = "login:12345",
    symbol: str = "EURUSD.a",
    timeframe: str = "H1",
) -> CacheIdentity:
    return CacheIdentity(
        server=server,
        account_fingerprint=account,
        broker_symbol=symbol,
        timeframe=timeframe,
    )


def _candle(index: int, *, close: float | None = None) -> Candle:
    opened_at = datetime(2026, 7, 20, tzinfo=timezone.utc) + index * H1
    value = float(index + 1)
    return Candle(
        time=opened_at,
        open=value,
        high=value + 0.5,
        low=value - 0.5,
        close=value if close is None else close,
        volume=100.0 + index,
    )


def _store(
    cache: CandleHistoryCache,
    identity: CacheIdentity,
    candles: list[Candle],
    *,
    max_count: int = 10,
) -> None:
    result = cache.store_full(
        identity,
        candles,
        expected_interval=H1,
        max_count=max_count,
    )
    assert result.usable


def test_cold_lookup_then_full_store_trims_and_returns_defensive_copy() -> None:
    cache = CandleHistoryCache()
    identity = _identity(timeframe="h1")

    cold = cache.lookup(identity, expected_interval=H1, max_count=3)

    assert cold.requires_full_reload
    assert cold.fallback_reason is CacheFallbackReason.CACHE_MISSING
    assert cold.candles == []

    stored = cache.store_full(
        identity,
        [_candle(index) for index in range(5)],
        expected_interval=H1,
        max_count=3,
    )

    assert stored.usable
    assert stored.trimmed_count == 2
    assert stored.candles == [_candle(2), _candle(3), _candle(4)]
    stored.candles.clear()
    assert cache.lookup(
        identity,
        expected_interval=H1,
        max_count=3,
    ).candles == [_candle(2), _candle(3), _candle(4)]


def test_full_store_normalizes_aware_timestamps_to_utc() -> None:
    cache = CandleHistoryCache()
    identity = _identity()
    ict = timezone(timedelta(hours=7))
    utc_candle = _candle(0)
    local_candle = replace(utc_candle, time=utc_candle.time.astimezone(ict))

    result = cache.store_full(
        identity,
        [local_candle],
        expected_interval=H1,
        max_count=10,
    )

    assert result.usable
    assert result.candles[0].time.tzinfo is timezone.utc
    assert result.candles[0] == utc_candle


def test_same_forming_bar_is_replaced_without_duplicate() -> None:
    cache = CandleHistoryCache()
    identity = _identity()
    _store(cache, identity, [_candle(0), _candle(1), _candle(2)])
    forming_update = replace(
        _candle(2),
        high=9.0,
        close=8.5,
        volume=999.0,
    )

    merged = cache.merge_tail(
        identity,
        [forming_update],
        expected_interval=H1,
        max_count=10,
    )

    assert merged.usable
    assert merged.replaced_count == 1
    assert merged.appended_count == 0
    assert len(merged.candles) == 3
    assert [item.time for item in merged.candles].count(forming_update.time) == 1
    assert merged.candles[-1] == forming_update


def test_new_bar_appends_after_replacing_forming_bar() -> None:
    cache = CandleHistoryCache()
    identity = _identity()
    _store(cache, identity, [_candle(0), _candle(1), _candle(2)])
    forming_update = replace(_candle(2), close=22.0)

    merged = cache.merge_tail(
        identity,
        [forming_update, _candle(3)],
        expected_interval=H1,
        max_count=10,
    )

    assert merged.usable
    assert merged.replaced_count == 1
    assert merged.appended_count == 1
    assert merged.candles == [
        _candle(0),
        _candle(1),
        forming_update,
        _candle(3),
    ]


def test_multiple_new_bars_append_and_trim_to_configured_count() -> None:
    cache = CandleHistoryCache()
    identity = _identity()
    _store(
        cache,
        identity,
        [_candle(0), _candle(1), _candle(2)],
        max_count=4,
    )

    merged = cache.merge_tail(
        identity,
        [_candle(2), _candle(3), _candle(4)],
        expected_interval=H1,
        max_count=4,
    )

    assert merged.usable
    assert merged.replaced_count == 1
    assert merged.appended_count == 2
    assert merged.trimmed_count == 1
    assert merged.candles == [
        _candle(1),
        _candle(2),
        _candle(3),
        _candle(4),
    ]


def test_gap_requests_full_reload_without_overwriting_last_known_good() -> None:
    cache = CandleHistoryCache()
    identity = _identity()
    original = [_candle(0), _candle(1), _candle(2)]
    _store(cache, identity, original)

    result = cache.merge_tail(
        identity,
        [_candle(2), _candle(4)],
        expected_interval=H1,
        max_count=10,
    )

    assert result.requires_full_reload
    assert result.fallback_reason is CacheFallbackReason.GAP_DETECTED
    assert result.candles == original
    still_cached = cache.lookup(
        identity,
        expected_interval=H1,
        max_count=10,
    )
    assert still_cached.usable
    assert still_cached.candles == original


def test_known_market_closure_can_be_exempted_from_gap_fallback() -> None:
    cache = CandleHistoryCache()
    identity = _identity()
    _store(cache, identity, [_candle(0), _candle(1)])

    result = cache.merge_tail(
        identity,
        [_candle(1), _candle(4)],
        expected_interval=H1,
        max_count=10,
        gap_allowed=lambda previous, current, interval: (
            previous == _candle(1).time
            and current == _candle(4).time
            and interval == H1
        ),
    )

    assert result.usable
    assert result.appended_count == 1
    assert result.candles == [_candle(0), _candle(1), _candle(4)]


def test_unknown_old_timestamp_invalidates_entry() -> None:
    cache = CandleHistoryCache()
    identity = _identity()
    _store(cache, identity, [_candle(1), _candle(2), _candle(3)])

    regressed = cache.merge_tail(
        identity,
        [_candle(0), _candle(2)],
        expected_interval=H1,
        max_count=10,
    )

    assert regressed.fallback_reason is (
        CacheFallbackReason.TIMESTAMP_REGRESSION
    )
    assert cache.lookup(
        identity,
        expected_interval=H1,
        max_count=10,
    ).fallback_reason is CacheFallbackReason.CACHE_MISSING


def test_server_or_account_change_clears_active_connection_cache() -> None:
    cache = CandleHistoryCache()
    original_identity = _identity()
    _store(cache, original_identity, [_candle(0)])
    changed_identity = _identity(server="Broker-Live", account="login:999")

    changed = cache.lookup(
        changed_identity,
        expected_interval=H1,
        max_count=10,
    )

    assert changed.fallback_reason is CacheFallbackReason.IDENTITY_CHANGED
    assert len(cache) == 0


def test_broker_suffix_is_part_of_key_and_cannot_reuse_other_series() -> None:
    cache = CandleHistoryCache()
    suffix_a = _identity(symbol="EURUSD.a")
    suffix_b = _identity(symbol="EURUSD.b")
    _store(cache, suffix_a, [_candle(0)])

    other = cache.lookup(suffix_b, expected_interval=H1, max_count=10)

    assert other.fallback_reason is CacheFallbackReason.CACHE_MISSING
    assert cache.lookup(
        suffix_a,
        expected_interval=H1,
        max_count=10,
    ).usable


def test_timeframe_configuration_change_invalidates_entry() -> None:
    cache = CandleHistoryCache()
    identity = _identity()
    _store(cache, identity, [_candle(0)], max_count=10)

    changed = cache.lookup(identity, expected_interval=H1, max_count=20)

    assert changed.fallback_reason is (
        CacheFallbackReason.CONFIGURATION_CHANGED
    )
    assert cache.lookup(
        identity,
        expected_interval=H1,
        max_count=10,
    ).fallback_reason is CacheFallbackReason.CACHE_MISSING


def test_cache_corruption_is_detected_and_invalidated() -> None:
    cache = CandleHistoryCache()
    identity = _identity()
    _store(cache, identity, [_candle(0), _candle(1)])
    entry = cache._entries[identity]
    cache._entries[identity] = replace(
        entry,
        candles=(entry.candles[1], entry.candles[0]),
    )

    corrupt = cache.lookup(identity, expected_interval=H1, max_count=10)

    assert corrupt.fallback_reason is CacheFallbackReason.CACHE_CORRUPT
    assert len(cache) == 0


def test_invalid_tail_keeps_cache_but_is_not_reported_as_fresh() -> None:
    cache = CandleHistoryCache()
    identity = _identity()
    original = [_candle(0), _candle(1)]
    _store(cache, identity, original)
    duplicate_tail = [_candle(1), replace(_candle(1), close=50.0)]

    invalid = cache.merge_tail(
        identity,
        duplicate_tail,
        expected_interval=H1,
        max_count=10,
    )

    assert invalid.requires_full_reload
    assert invalid.fallback_reason is CacheFallbackReason.TAIL_INVALID
    assert invalid.candles == original
    assert cache.lookup(
        identity,
        expected_interval=H1,
        max_count=10,
    ).candles == original


def test_invalid_full_response_does_not_overwrite_last_known_good() -> None:
    cache = CandleHistoryCache()
    identity = _identity()
    original = [_candle(0), _candle(1)]
    _store(cache, identity, original)

    invalid = cache.store_full(
        identity,
        [],
        expected_interval=H1,
        max_count=10,
    )

    assert invalid.fallback_reason is (
        CacheFallbackReason.FULL_HISTORY_INVALID
    )
    assert invalid.candles == original
    assert cache.lookup(
        identity,
        expected_interval=H1,
        max_count=10,
    ).candles == original


def test_warm_merge_output_matches_equivalent_full_reload() -> None:
    identity = _identity()
    full_history = [_candle(index) for index in range(10)]
    forming_update = replace(full_history[7], high=99.0, close=88.0)
    frozen_full_response = [
        *full_history[:7],
        forming_update,
        full_history[8],
        full_history[9],
    ]

    rolling_cache = CandleHistoryCache()
    _store(rolling_cache, identity, full_history[:8], max_count=10)
    warm = rolling_cache.merge_tail(
        identity,
        frozen_full_response[-3:],
        expected_interval=H1,
        max_count=10,
    )

    full_cache = CandleHistoryCache()
    cold = full_cache.store_full(
        identity,
        frozen_full_response,
        expected_interval=H1,
        max_count=10,
    )

    assert warm.usable
    assert cold.usable
    assert warm.candles == cold.candles == frozen_full_response
    assert len({candle.time for candle in warm.candles}) == len(
        warm.candles
    )
    assert all(
        before.time < after.time
        for before, after in zip(warm.candles, warm.candles[1:])
    )
