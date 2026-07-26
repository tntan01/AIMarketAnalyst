from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from core.backtest_market_data import (
    DATA_MANIFEST_VERSION,
    _gap_overlaps_scope,
    _unexpected_gaps,
    prepare_backtest_data,
)
from core.market_models import Candle
from core.trading_session_calendar import (
    BROKER_MAINTENANCE,
    MARKET_HOLIDAY,
    TRADING_SESSION_POLICY_VERSION,
    UNEXPECTED_DATA_GAP,
    trading_session_calendar,
)


UTC = timezone.utc


def _candle(opened_at: datetime) -> Candle:
    return Candle(
        time=opened_at,
        open=1.0,
        high=1.1,
        low=0.9,
        close=1.0,
        volume=100,
    )


def test_forex_weekend_is_expected_in_new_york_standard_time() -> None:
    gaps = _unexpected_gaps(
        [
            _candle(datetime(2026, 1, 9, 21, tzinfo=UTC)),
            _candle(datetime(2026, 1, 11, 22, tzinfo=UTC)),
        ],
        timedelta(hours=1),
        symbol="EUR/USD",
        timeframe="H1",
    )

    assert gaps == []


def test_forex_weekend_is_expected_in_new_york_daylight_time() -> None:
    gaps = _unexpected_gaps(
        [
            _candle(datetime(2026, 7, 10, 20, tzinfo=UTC)),
            _candle(datetime(2026, 7, 12, 21, tzinfo=UTC)),
        ],
        timedelta(hours=1),
        symbol="EUR/USD",
        timeframe="H1",
    )

    assert gaps == []


def test_jpy_pair_uses_the_forex_session_policy() -> None:
    calendar = trading_session_calendar("USD/JPY")
    gaps = _unexpected_gaps(
        [
            _candle(datetime(2026, 1, 9, 21, tzinfo=UTC)),
            _candle(datetime(2026, 1, 11, 22, tzinfo=UTC)),
        ],
        timedelta(hours=1),
        symbol="USD/JPY",
        timeframe="H1",
    )

    assert calendar.policy.asset_class == "FOREX"
    assert gaps == []


def test_metal_daily_maintenance_is_not_an_unexpected_gap() -> None:
    gaps = _unexpected_gaps(
        [
            _candle(datetime(2026, 1, 5, 21, 45, tzinfo=UTC)),
            _candle(datetime(2026, 1, 5, 23, 0, tzinfo=UTC)),
        ],
        timedelta(minutes=15),
        symbol="XAU/USD",
        timeframe="M15",
    )
    classification = trading_session_calendar("XAU/USD").classify_missing_slot(
        datetime(2026, 1, 5, 22, 0, tzinfo=UTC),
        timedelta(minutes=15),
        timeframe="M15",
    )

    assert classification.classification == BROKER_MAINTENANCE
    assert gaps == []


def test_crypto_weekend_gap_remains_unexpected() -> None:
    gaps = _unexpected_gaps(
        [
            _candle(datetime(2026, 1, 9, 21, tzinfo=UTC)),
            _candle(datetime(2026, 1, 11, 22, tzinfo=UTC)),
        ],
        timedelta(hours=1),
        symbol="BTC/USD",
        timeframe="H1",
    )

    assert len(gaps) == 1
    assert gaps[0]["missing_intervals"] == 48
    assert gaps[0]["classifications"] == {UNEXPECTED_DATA_GAP: 48}


def test_real_weekday_gap_remains_a_validation_warning() -> None:
    monday = datetime(2026, 1, 5, tzinfo=UTC)
    rows = [_candle(monday), _candle(monday + timedelta(hours=2))]
    normalized, manifest = prepare_backtest_data(
        {
            "D1": [_candle(monday)],
            "H4": [_candle(monday)],
            "H1": rows,
        },
        symbol="EUR/USD",
    )

    issue = next(
        item for item in manifest.issues
        if item.code == UNEXPECTED_DATA_GAP and item.timeframe == "H1"
    )
    assert normalized["H1"] == rows
    assert "1 nến thiếu" in issue.message
    assert "2026-01-05T01:00:00+00:00" in issue.message
    assert manifest.validation_eligible is False


def test_versioned_holiday_policy_classifies_christmas() -> None:
    calendar = trading_session_calendar("EUR/USD")
    result = calendar.classify_missing_slot(
        datetime(2026, 12, 25, 12, tzinfo=UTC),
        timedelta(hours=1),
        timeframe="H1",
    )

    assert result.expected_candle is False
    assert result.classification == MARKET_HOLIDAY
    assert calendar.policy.version == TRADING_SESSION_POLICY_VERSION
    assert len(calendar.fingerprint) == 64


def test_holiday_closure_starts_at_previous_new_york_trading_day_boundary() -> None:
    calendar = trading_session_calendar("EUR/USD")
    christmas_eve_after_close = calendar.classify_missing_slot(
        datetime(2025, 12, 24, 22, tzinfo=UTC),
        timedelta(hours=1),
        timeframe="H1",
    )
    christmas_reopen = calendar.classify_missing_slot(
        datetime(2025, 12, 25, 22, tzinfo=UTC),
        timedelta(hours=1),
        timeframe="H1",
    )

    assert christmas_eve_after_close.classification == MARKET_HOLIDAY
    assert christmas_eve_after_close.expected_candle is False
    assert christmas_reopen.expected_candle is True


def test_weekly_open_grace_avoids_partial_first_m15_false_positive() -> None:
    gaps = _unexpected_gaps(
        [
            _candle(datetime(2026, 3, 6, 21, 45, tzinfo=UTC)),
            _candle(datetime(2026, 3, 8, 21, 15, tzinfo=UTC)),
        ],
        timedelta(minutes=15),
        symbol="EUR/USD",
        timeframe="M15",
    )

    assert gaps == []


@pytest.mark.parametrize(
    "closed_at",
    [
        datetime(2026, 1, 19, 19, 30, tzinfo=UTC),
        datetime(2026, 2, 16, 19, 30, tzinfo=UTC),
        datetime(2026, 5, 25, 18, 30, tzinfo=UTC),
        datetime(2026, 6, 19, 17, 0, tzinfo=UTC),
        datetime(2026, 7, 3, 17, 0, tzinfo=UTC),
    ],
)
def test_metal_holiday_early_closures_are_expected(closed_at: datetime) -> None:
    classification = trading_session_calendar("XAU/USD").classify_missing_slot(
        closed_at,
        timedelta(minutes=15),
        timeframe="M15",
    )

    assert classification.expected_candle is False
    assert classification.classification in {MARKET_HOLIDAY, BROKER_MAINTENANCE}


def test_recorded_86_weekend_slots_are_no_longer_false_positives() -> None:
    new_york = ZoneInfo("America/New_York")
    first_friday = datetime(2026, 1, 9, 16, tzinfo=new_york)
    false_positive_intervals = 0

    for week in range(43):
        friday_last_candle = first_friday + timedelta(weeks=week)
        sunday_first_candle = friday_last_candle + timedelta(days=2, hours=1)
        gaps = _unexpected_gaps(
            [
                _candle(friday_last_candle.astimezone(UTC)),
                _candle(sunday_first_candle.astimezone(UTC)),
            ],
            timedelta(hours=1),
            symbol="EUR/USD",
            timeframe="H1",
        )
        false_positive_intervals += len(gaps)

    # Baseline production message recorded 43 weekends x 2 false slots.
    assert 43 * 2 == 86
    assert false_positive_intervals == 0


def test_metal_daily_reopen_has_a_fifteen_minute_grace() -> None:
    result = trading_session_calendar("XAU/USD").classify_missing_slot(
        datetime(2026, 4, 1, 22, 0, tzinfo=UTC),
        timedelta(minutes=15),
        timeframe="M15",
    )

    assert result.expected_candle is False
    assert result.classification == BROKER_MAINTENANCE


def test_good_friday_is_a_metal_holiday() -> None:
    result = trading_session_calendar("XAG/USD").classify_missing_slot(
        datetime(2026, 4, 3, 12, tzinfo=UTC),
        timedelta(hours=1),
        timeframe="H1",
    )

    assert result.expected_candle is False
    assert result.classification == MARKET_HOLIDAY


def test_manifest_records_expected_closure_without_quality_issue() -> None:
    friday = datetime(2026, 1, 9, 21, tzinfo=UTC)
    sunday = datetime(2026, 1, 11, 22, tzinfo=UTC)
    _normalized, manifest = prepare_backtest_data(
        {
            "D1": [_candle(datetime(2026, 1, 9, tzinfo=UTC))],
            "H4": [_candle(datetime(2026, 1, 9, 20, tzinfo=UTC))],
            "H1": [_candle(friday), _candle(sunday)],
        },
        symbol="EUR/USD",
    )

    h1 = manifest.timeframes["H1"]
    assert manifest.version == DATA_MANIFEST_VERSION
    assert manifest.session_policy["version"] == TRADING_SESSION_POLICY_VERSION
    assert manifest.session_policy["asset_class"] == "FOREX"
    assert h1.gap_count == 0
    assert h1.expected_closure_count == 1
    assert h1.expected_closed_interval_count == 48
    assert not any(item.code == UNEXPECTED_DATA_GAP for item in manifest.issues)


def test_requested_coverage_is_checked_separately_from_internal_gaps() -> None:
    start = datetime(2026, 1, 5, 0, tzinfo=UTC)
    end = datetime(2026, 1, 5, 3, tzinfo=UTC)
    _normalized, manifest = prepare_backtest_data(
        {
            "D1": [_candle(start)],
            "H4": [_candle(start)],
            "H1": [
                _candle(start + timedelta(hours=1)),
                _candle(start + timedelta(hours=2)),
            ],
        },
        symbol="EUR/USD",
        requested_start=start,
        requested_end=end,
    )

    codes = {
        (issue.code, issue.timeframe)
        for issue in manifest.issues
    }
    assert ("DATA_COVERAGE_START_MISSING", "H1") in codes
    assert manifest.timeframes["H1"].coverage_start_missing_intervals == 1
    assert manifest.timeframes["H1"].coverage_end_missing_intervals == 0
    assert manifest.requested_start == start.isoformat()
    assert manifest.requested_end == end.isoformat()


def test_dataset_hash_includes_session_policy_identity() -> None:
    opened_at = datetime(2026, 1, 5, tzinfo=UTC)
    data = {
        "D1": [_candle(opened_at)],
        "H4": [_candle(opened_at)],
        "H1": [_candle(opened_at)],
    }

    _fx_rows, fx = prepare_backtest_data(data, symbol="EUR/USD")
    _crypto_rows, crypto = prepare_backtest_data(data, symbol="BTC/USD")

    assert fx.dataset_hash != crypto.dataset_hash
    assert fx.session_policy["fingerprint"] != crypto.session_policy["fingerprint"]


def test_gap_before_timeframe_quality_scope_remains_auditable_but_non_blocking() -> None:
    gap = {
        "first_missing": "2024-12-08T22:00:00+00:00",
        "last_missing": "2024-12-09T01:00:00+00:00",
    }

    assert _gap_overlaps_scope(
        gap,
        timedelta(hours=1),
        datetime(2025, 12, 26, tzinfo=UTC),
        datetime(2026, 7, 25, tzinfo=UTC),
    ) is False
    assert _gap_overlaps_scope(
        gap,
        timedelta(hours=1),
        datetime(2024, 12, 1, tzinfo=UTC),
        datetime(2025, 1, 1, tzinfo=UTC),
    ) is True
