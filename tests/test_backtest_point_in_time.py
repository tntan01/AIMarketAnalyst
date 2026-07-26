from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.backtest_contract import (
    BACKTEST_PURPOSE_RESEARCH,
    BACKTEST_PURPOSE_VALIDATION,
)
from core.backtest_market_data import (
    BACKTEST_INTERVAL_CONVENTION,
    TIMEFRAME_DURATIONS,
    candle_close_time,
    in_half_open_interval,
    prepare_backtest_data,
)
from core.market_models import Candle
from core.system_backtest_engine import (
    BacktestRequest,
    _future_execution_candles,
    _normalize_correlation_context,
    _slice_correlation_context,
    run_system_backtest,
    slice_candles_until,
    validate_backtest_input,
)


UTC = timezone.utc


def _candle(
    opened_at: datetime,
    *,
    close: float = 1.1,
    high: float = 1.2,
    low: float = 1.0,
) -> Candle:
    return Candle(
        time=opened_at,
        open=1.1,
        high=high,
        low=low,
        close=close,
        volume=100.0,
    )


def _request(*, purpose: str = BACKTEST_PURPOSE_RESEARCH) -> BacktestRequest:
    return BacktestRequest(
        symbol="EUR/USD",
        broker_symbol="EURUSD",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 2, 1, tzinfo=UTC),
        initial_balance=10_000.0,
        risk_percent=1.0,
        purpose=purpose,
    )


@pytest.mark.parametrize(
    ("timeframe", "duration"),
    list(TIMEFRAME_DURATIONS.items()),
)
def test_snapshot_never_exposes_a_forming_candle(
    timeframe: str,
    duration: timedelta,
) -> None:
    opened_at = datetime(2026, 1, 5, tzinfo=UTC)
    candle = _candle(opened_at)
    dataset = {timeframe: [candle]}

    before_close = slice_candles_until(
        dataset,
        opened_at + duration - timedelta(microseconds=1),
    )
    at_close = slice_candles_until(dataset, opened_at + duration)

    assert before_close[timeframe] == []
    assert at_close[timeframe] == [candle]
    assert candle_close_time(candle, timeframe) == opened_at + duration


def test_half_open_interval_assigns_boundary_only_to_oos() -> None:
    boundary = datetime(2026, 7, 1, tzinfo=UTC)
    is_start = datetime(2026, 1, 1, tzinfo=UTC)
    oos_end = datetime(2026, 10, 1, tzinfo=UTC)

    assert not in_half_open_interval(boundary, is_start, boundary)
    assert in_half_open_interval(boundary, boundary, oos_end)
    assert BACKTEST_INTERVAL_CONVENTION == "[start,end)"


def test_execution_data_starts_after_decision_and_stops_before_end() -> None:
    decision_time = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
    end = datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    m15 = [
        _candle(datetime(2026, 1, 5, 9, 45, tzinfo=UTC)),
        _candle(datetime(2026, 1, 5, 10, 0, tzinfo=UTC)),
        _candle(datetime(2026, 1, 5, 10, 15, tzinfo=UTC)),
        _candle(datetime(2026, 1, 5, 10, 45, tzinfo=UTC)),
    ]

    selected = _future_execution_candles(
        {"M15": m15},
        decision_time,
        end,
    )

    assert [candle.time for candle in selected] == [
        datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
        datetime(2026, 1, 5, 10, 15, tzinfo=UTC),
    ]


def test_normalization_is_deterministic_for_unsorted_duplicates() -> None:
    first = _candle(datetime(2026, 1, 5, 1, 0, tzinfo=UTC), close=1.10)
    duplicate_a = _candle(
        datetime(2026, 1, 5, 2, 0, tzinfo=UTC),
        close=1.11,
    )
    duplicate_b = _candle(
        datetime(2026, 1, 5, 2, 0, tzinfo=UTC),
        close=1.12,
    )
    third = _candle(datetime(2026, 1, 5, 3, 0, tzinfo=UTC), close=1.13)
    required = {
        "D1": [_candle(datetime(2026, 1, 5, tzinfo=UTC))],
        "H4": [_candle(datetime(2026, 1, 5, tzinfo=UTC))],
    }
    input_a = {
        **required,
        "H1": [third, duplicate_a, first, duplicate_b],
    }
    input_b = {
        **required,
        "H1": [duplicate_b, first, duplicate_a, third],
    }

    normalized_a, manifest_a = prepare_backtest_data(input_a)
    normalized_b, manifest_b = prepare_backtest_data(input_b)

    assert normalized_a == normalized_b
    assert manifest_a.dataset_hash == manifest_b.dataset_hash
    assert manifest_a.timeframes["H1"].duplicate_count == 1
    assert manifest_a.timeframes["H1"].conflicting_duplicate_count == 1


def test_backtest_result_is_independent_from_provider_input_order() -> None:
    d1 = [
        _candle(datetime(2026, 1, 1, tzinfo=UTC)),
        _candle(datetime(2026, 1, 2, tzinfo=UTC)),
    ]
    h4 = [
        _candle(datetime(2026, 1, 1, 0, tzinfo=UTC)),
        _candle(datetime(2026, 1, 1, 4, tzinfo=UTC)),
    ]
    h1 = [
        _candle(datetime(2026, 1, 1, 0, tzinfo=UTC)),
        _candle(datetime(2026, 1, 1, 1, tzinfo=UTC)),
    ]
    request = BacktestRequest(
        symbol="EUR/USD",
        broker_symbol="EURUSD",
        start=datetime(2026, 1, 10, tzinfo=UTC),
        end=datetime(2026, 1, 11, tzinfo=UTC),
        initial_balance=10_000.0,
        risk_percent=1.0,
    )

    forward = run_system_backtest(
        request,
        {"D1": d1, "H4": h4, "H1": h1},
    ).to_dict()
    reversed_input = run_system_backtest(
        request,
        {
            "D1": list(reversed(d1)),
            "H4": list(reversed(h4)),
            "H1": list(reversed(h1)),
        },
    ).to_dict()

    assert forward["summary"] == reversed_input["summary"]
    assert (
        forward["backtest_contract"]["data_manifest_version"]
        == forward["data_manifest"]["version"]
    )
    assert forward["backtest_contract"]["point_in_time_data"] is True
    assert (
        forward["data_manifest"]["dataset_hash"]
        == reversed_input["data_manifest"]["dataset_hash"]
    )


def test_manifest_reports_timezone_duplicate_and_unexpected_gap() -> None:
    monday = datetime(2026, 1, 5)
    data = {
        "D1": [_candle(datetime(2026, 1, 5, tzinfo=UTC))],
        "H4": [_candle(datetime(2026, 1, 5, tzinfo=UTC))],
        "H1": [
            _candle(monday),
            _candle(monday),
            _candle(monday + timedelta(hours=2)),
        ],
    }

    _normalized, manifest = prepare_backtest_data(data)
    codes = {issue.code for issue in manifest.issues}

    assert manifest.timezone == "UTC"
    assert manifest.quality_status == "WARNING"
    assert manifest.validation_eligible is False
    assert "TIMEZONE_ASSUMED_UTC" in codes
    assert "DUPLICATE_CANDLES_NORMALIZED" in codes
    assert "UNEXPECTED_DATA_GAP" in codes


def test_manifest_reports_invalid_timestamp_and_ohlc() -> None:
    invalid_time = Candle(  # type: ignore[arg-type]
        time="not-a-datetime",
        open=1.1,
        high=1.2,
        low=1.0,
        close=1.1,
    )
    invalid_ohlc = Candle(
        time=datetime(2026, 1, 5, tzinfo=UTC),
        open=1.1,
        high=1.0,
        low=1.2,
        close=1.1,
    )
    raw = {
        "D1": [_candle(datetime(2026, 1, 5, tzinfo=UTC))],
        "H4": [_candle(datetime(2026, 1, 5, tzinfo=UTC))],
        "H1": [invalid_time, invalid_ohlc],
    }

    normalized, manifest = prepare_backtest_data(raw)
    codes = {issue.code for issue in manifest.issues}

    assert normalized["H1"] == []
    assert manifest.quality_status == "INVALID"
    assert manifest.timeframes["H1"].invalid_timestamp_count == 1
    assert manifest.timeframes["H1"].invalid_ohlc_count == 1
    assert "INVALID_CANDLE_TIMESTAMP" in codes
    assert "INVALID_OHLC" in codes


def test_validation_fails_closed_when_manifest_has_quality_warning() -> None:
    naive = datetime(2026, 1, 5)
    raw = {
        "D1": [_candle(naive)],
        "H4": [_candle(naive)],
        "H1": [_candle(naive)],
    }
    normalized, manifest = prepare_backtest_data(raw)

    with pytest.raises(ValueError, match="Dữ liệu không đạt chuẩn VALIDATION"):
        validate_backtest_input(
            _request(purpose=BACKTEST_PURPOSE_VALIDATION),
            normalized,
            data_manifest=manifest,
        )

    # Research remains usable but carries the manifest warnings.
    validate_backtest_input(
        _request(purpose=BACKTEST_PURPOSE_RESEARCH),
        normalized,
        data_manifest=manifest,
    )


def test_validation_rejects_request_boundary_without_timezone() -> None:
    raw = {
        timeframe: [_candle(datetime(2026, 1, 5, tzinfo=UTC))]
        for timeframe in ("D1", "H4", "H1")
    }
    normalized, manifest = prepare_backtest_data(raw)
    request = BacktestRequest(
        symbol="EUR/USD",
        broker_symbol="EURUSD",
        start=datetime(2026, 1, 1),
        end=datetime(2026, 2, 1),
        initial_balance=10_000.0,
        risk_percent=1.0,
        purpose=BACKTEST_PURPOSE_VALIDATION,
        execution_mode="EXECUTION_PARITY",
        cost_model_configured=True,
    )

    with pytest.raises(ValueError, match="REQUEST_TIMEZONE_MISSING"):
        validate_backtest_input(
            request,
            normalized,
            data_manifest=manifest,
        )


def test_aware_non_utc_timestamps_are_normalized_to_utc() -> None:
    gmt7 = timezone(timedelta(hours=7))
    opened_at = datetime(2026, 1, 5, 7, 0, tzinfo=gmt7)
    raw = {
        timeframe: [_candle(opened_at)]
        for timeframe in ("D1", "H4", "H1")
    }

    normalized, manifest = prepare_backtest_data(raw)

    assert normalized["H1"][0].time == datetime(
        2026,
        1,
        5,
        tzinfo=UTC,
    )
    assert manifest.timeframes["H1"].timezone_converted_count == 1


def test_macro_context_is_sorted_and_sliced_at_daily_close() -> None:
    first = _candle(datetime(2026, 1, 5, tzinfo=UTC), close=1.10)
    future = _candle(datetime(2026, 1, 6, tzinfo=UTC), close=1.11)
    normalized = _normalize_correlation_context(
        {"dxy_candles": [future, first]}
    )

    snapshot = _slice_correlation_context(
        normalized,
        datetime(2026, 1, 6, 12, 0, tzinfo=UTC),
    )

    assert snapshot is not None
    assert snapshot["dxy_candles"] == [first]
