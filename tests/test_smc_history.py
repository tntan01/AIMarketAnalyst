from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.smc_history import (
    SMC_ATR_WARMUP_CANDLES,
    assess_smc_history,
    required_history_for_lifetime,
)


def candles(start: datetime, count: int, timeframe: str = "H1") -> tuple[Candle, ...]:
    intervals = {"D1": timedelta(days=1), "H4": timedelta(hours=4), "H1": timedelta(hours=1), "M15": timedelta(minutes=15)}
    interval = intervals[timeframe]
    return tuple(
        Candle(
            time=start + index * interval,
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
        )
        for index in range(count)
    )


def test_warmup_boundary_is_14_true_ranges_plus_first_candle():
    start = datetime(2026, 1, 5, tzinfo=timezone.utc)

    before = assess_smc_history(candles(start, SMC_ATR_WARMUP_CANDLES - 1), "H1", minimum_candles=1)
    at = assess_smc_history(candles(start, SMC_ATR_WARMUP_CANDLES), "H1", minimum_candles=1)

    assert before.warmup_ready is False
    assert "SMC_ATR_REFERENCE_UNAVAILABLE" in before.reason_codes
    assert at.warmup_ready is True
    assert "SMC_ATR_REFERENCE_UNAVAILABLE" not in at.reason_codes


def test_valid_weekend_closure_is_not_reported_as_coverage_gap():
    friday = Candle(
        time=datetime(2026, 1, 2, 16, 0, tzinfo=timezone.utc),
        open=100,
        high=101,
        low=99,
        close=100.5,
    )
    monday = Candle(
        time=datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc),
        open=101,
        high=102,
        low=100,
        close=101.5,
    )

    result = assess_smc_history((friday, monday), "D1", symbol="EURUSD", minimum_candles=2)

    assert result.status == "insufficient"  # warm-up remains independently required
    assert result.missing_slots == ()
    assert result.closed_session_slots > 0
    assert "SMC_COVERAGE_GAP" not in result.reason_codes
    assert result.session_coverage_status == "known"


def test_unexpected_in_session_gap_is_incomplete_and_not_filled():
    samples = candles(datetime(2026, 1, 6, 0, tzinfo=timezone.utc), 16, "H1")
    gap_samples = samples[:7] + samples[8:]

    result = assess_smc_history(gap_samples, "H1", symbol="EURUSD", minimum_candles=1)

    assert result.status == "partial"
    assert "SMC_COVERAGE_GAP" in result.reason_codes
    assert len(result.missing_slots) == 1
    assert result.raw_count == 15


def test_unknown_session_metadata_stays_unknown_for_a_gap():
    samples = candles(datetime(2026, 1, 6, 0, tzinfo=timezone.utc), 16, "H1")

    result = assess_smc_history(samples[:7] + samples[8:], "H1", minimum_candles=1)

    assert result.status == "partial"
    assert result.session_coverage_status == "unknown"
    assert "SMC_SESSION_COVERAGE_UNKNOWN" in result.reason_codes
    assert "SMC_COVERAGE_GAP" in result.reason_codes


def test_missing_zone_origin_cannot_be_fresh():
    start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    result = assess_smc_history(
        candles(start, 15),
        "H1",
        symbol="EURUSD",
        origin_time=start - timedelta(hours=1),
        minimum_candles=1,
    )

    assert result.origin_covered is False
    assert result.freshness_eligible is False
    assert result.status == "partial"
    assert "SMC_COVERAGE_GAP" in result.reason_codes


def test_without_origin_freshness_is_never_assumed():
    start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    result = assess_smc_history(candles(start, 15), "H1", symbol="EURUSD", minimum_candles=1)

    assert result.origin_covered is None
    assert result.freshness_eligible is False
    assert result.status == "complete"


def test_lifetime_requirement_has_an_explicit_count_boundary():
    start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    required = required_history_for_lifetime("H1")

    below = assess_smc_history(
        candles(start, required - 1),
        "H1",
        symbol="EURUSD",
        origin_time=start,
        require_lifetime=True,
    )
    at = assess_smc_history(
        candles(start, required),
        "H1",
        symbol="EURUSD",
        origin_time=start,
        require_lifetime=True,
    )

    assert below.status == "insufficient"
    assert "SMC_H1_INSUFFICIENT_HISTORY" in below.reason_codes
    assert at.status == "complete"
    assert at.freshness_eligible is True


def test_lifetime_history_budget_is_explicit_and_m15_keeps_its_48_bar_lag():
    assert required_history_for_lifetime("D1") == 60
    assert required_history_for_lifetime("H4") == 60
    assert required_history_for_lifetime("H1") == 69
    assert required_history_for_lifetime("M15") == 147
