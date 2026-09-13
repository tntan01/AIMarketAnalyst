"""Task 17 tests for the typed SMC snapshot/data-quality contract."""

from __future__ import annotations

import pytest

from core.smc_models import (
    SMC_SNAPSHOT_CONTRACT_VERSION,
    SmcDataQualityState,
    SmcSnapshot,
    SmcTimeframeSnapshot,
    validate_smc_snapshot,
)


def _timeframe_payload(timeframe: str = "H4") -> dict:
    return {
        "timeframe": timeframe,
        "interval_seconds": 14_400,
        "first_eligible_close_at": "2026-09-10T00:00:00Z",
        "last_eligible_close_at": "2026-09-10T04:00:00Z",
        "raw_count": 3,
        "eligible_count": 2,
        "cutoff_filtered": 1,
        "session_coverage_status": "known",
        "atr_period": 14,
        "atr_reference": 1.25,
        "atr_reference_time": "2026-09-09T20:00:00Z",
        "atr_reference_source": "formation_prefix",
        "reason_codes": [],
    }


def _partial_snapshot_payload() -> dict:
    return {
        "contract_version": SMC_SNAPSHOT_CONTRACT_VERSION,
        "symbol": "XAUUSD",
        "as_of": "2026-09-10T04:00:00Z",
        "observed_at": "2026-09-10T04:01:00Z",
        "broker_symbol": "XAUUSD.",
        "tick_size": 0.01,
        "point": 0.01,
        "digits": 2,
        "tick_size_source": "point_fallback",
        "timeframes": [_timeframe_payload()],
        "data_quality": {
            "status": "partial",
            "reason_codes": ["SMC_D1_MISSING", "M15_DATA_UNAVAILABLE"],
            "missing_timeframes": ["D1", "M15"],
        },
    }


def test_snapshot_round_trip_preserves_provenance_and_quality_state():
    snapshot = SmcSnapshot.from_dict(_partial_snapshot_payload())

    assert validate_smc_snapshot(snapshot)
    assert snapshot.symbol == "XAUUSD"
    assert snapshot.timeframes[0].timeframe == "H4"
    assert snapshot.timeframes[0].atr_reference_source == "formation_prefix"
    assert snapshot.data_quality.status == "partial"
    assert snapshot.data_quality.missing_timeframes == ("D1", "M15")
    assert SmcSnapshot.from_dict(snapshot.to_dict()) == snapshot


def test_missing_metadata_is_not_fabricated_for_data_unavailable_snapshot():
    quality = SmcDataQualityState(
        status="insufficient",
        reason_codes=("SMC_H4_MISSING", "SMC_ATR_REFERENCE_UNAVAILABLE"),
        missing_timeframes=("H4",),
    )
    snapshot = SmcSnapshot(
        symbol="EURUSD",
        as_of="2026-09-10T04:00:00+00:00",
        timeframes=(),
        data_quality=quality,
    )

    payload = snapshot.to_dict()
    assert payload["timeframes"] == []
    assert payload["observed_at"] is None
    assert payload["tick_size"] is None
    assert payload["tick_size_source"] is None
    assert payload["data_quality"]["missing_timeframes"] == ["H4"]


def test_snapshot_rejects_naive_or_future_eligible_timestamps():
    payload = _partial_snapshot_payload()
    payload["as_of"] = "2026-09-10T04:00:00"
    with pytest.raises(ValueError, match="UTC"):
        SmcSnapshot.from_dict(payload)

    payload = _partial_snapshot_payload()
    payload["timeframes"][0]["last_eligible_close_at"] = "2026-09-10T05:00:00Z"
    with pytest.raises(ValueError, match="after snapshot as_of"):
        SmcSnapshot.from_dict(payload)


def test_snapshot_rejects_missing_required_schema_fields():
    payload = _partial_snapshot_payload()
    del payload["as_of"]
    with pytest.raises(ValueError, match="as_of"):
        SmcSnapshot.from_dict(payload)

    timeframe = _timeframe_payload()
    del timeframe["atr_reference_source"]
    payload = _partial_snapshot_payload()
    payload["timeframes"] = [timeframe]
    with pytest.raises(ValueError, match="atr_reference_source"):
        SmcSnapshot.from_dict(payload)


def test_tick_size_provenance_must_match_the_value_used():
    payload = _partial_snapshot_payload()
    payload["tick_size_source"] = "point_fallback"
    payload["tick_size"] = 0.1
    with pytest.raises(ValueError, match="point_fallback"):
        SmcSnapshot.from_dict(payload)


def test_complete_snapshot_requires_all_canonical_timeframes():
    frames = tuple(
        SmcTimeframeSnapshot.from_dict(_timeframe_payload(timeframe))
        for timeframe in ("D1", "H4", "H1")
    )
    with pytest.raises(ValueError, match="all canonical timeframes"):
        SmcSnapshot(
            symbol="EURUSD",
            as_of="2026-09-10T04:00:00Z",
            timeframes=frames,
            data_quality=SmcDataQualityState(status="complete"),
        )
