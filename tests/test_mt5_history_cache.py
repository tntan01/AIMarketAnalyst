from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from types import SimpleNamespace

import pytest

from core.analysis_engine import analyze_symbol
from core.market_models import Candle
from core.risk_engine import AnalysisInput
from services.mt5_service import MT5HistoryCacheIdentity, MT5Service


_TIMEFRAME_IDS = {"D1": 1, "H4": 2, "H1": 3, "M15": 4}
_INTERVALS = {
    "D1": timedelta(days=1),
    "H4": timedelta(hours=4),
    "H1": timedelta(hours=1),
    "M15": timedelta(minutes=15),
}
_BARS = {"D1": 500, "H4": 500, "H1": 500, "M15": 100}


class _HistoryMT5:
    TIMEFRAME_D1 = _TIMEFRAME_IDS["D1"]
    TIMEFRAME_H4 = _TIMEFRAME_IDS["H4"]
    TIMEFRAME_H1 = _TIMEFRAME_IDS["H1"]
    TIMEFRAME_M15 = _TIMEFRAME_IDS["M15"]

    def __init__(self, *, sleep_seconds: float = 0.0) -> None:
        self.series: dict[str, list[dict[str, float | int]]] = {}
        self.requests: list[tuple[str, int]] = []
        self.fail_tail = False
        self.sleep_seconds = sleep_seconds
        self._active = 0
        self._active_lock = Lock()
        self.max_active = 0

    def symbol_select(self, _symbol: str, enabled: bool) -> bool:
        return bool(enabled)

    def copy_rates_from_pos(
        self,
        symbol: str,
        timeframe_id: int,
        _start_pos: int,
        count: int,
    ) -> list[dict[str, float | int]]:
        timeframe = next(
            name for name, value in _TIMEFRAME_IDS.items() if value == timeframe_id
        )
        self.requests.append((timeframe, count))
        if self.fail_tail and count == 3:
            raise RuntimeError("tail unavailable")
        with self._active_lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)
        try:
            if self.sleep_seconds:
                time.sleep(self.sleep_seconds)
            return [dict(item) for item in self.series[timeframe][-count:]]
        finally:
            with self._active_lock:
                self._active -= 1


def _raw_series(timeframe: str, count: int = 620) -> list[dict[str, float | int]]:
    interval = _INTERVALS[timeframe]
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    values: list[dict[str, float | int]] = []
    for index in range(count):
        timestamp = int((start + index * interval).timestamp())
        close = float(index) + 1.0
        values.append(
            {
                "time": timestamp,
                "open": close - 0.1,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "tick_volume": 100 + index,
            }
        )
    return values


def _service_and_fake(monkeypatch, tmp_path: Path, *, sleep_seconds: float = 0.0):
    fake = _HistoryMT5(sleep_seconds=sleep_seconds)
    for timeframe in _TIMEFRAME_IDS:
        fake.series[timeframe] = _raw_series(timeframe)
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    tmp_path.mkdir(parents=True, exist_ok=True)
    profile = tmp_path / "symbol_profiles.json"
    profile.write_text("{}", encoding="utf-8")
    return MT5Service(profile), fake


def _identity(
    *, server: str = "Broker-Demo", broker: str = "Example Broker", login: int = 7
) -> MT5HistoryCacheIdentity:
    return MT5HistoryCacheIdentity(server=server, broker=broker, login=login)


def test_incomplete_connection_status_disables_cache_identity_safely():
    legacy_status = SimpleNamespace(server="Fixture-Demo")

    assert MT5HistoryCacheIdentity.from_connection_status(legacy_status) is None


def test_cold_full_then_warm_tail_metrics_and_forming_replace(monkeypatch, tmp_path):
    service, fake = _service_and_fake(monkeypatch, tmp_path)
    identity = _identity()

    cold = service.load_primary_timeframes_cached("EURUSD", _BARS, identity)

    assert cold["cache_status"] == "cold_full"
    assert cold["fetch_metrics"] == {
        "copy_rates_calls": 4,
        "full_history_calls": 4,
        "tail_calls": 0,
        "bars_requested": 1600,
        "bars_received": 1600,
    }
    assert [count for _, count in fake.requests] == [500, 500, 500, 100]

    # Change every forming bar.  The warm path must replace by timestamp.
    for timeframe in _TIMEFRAME_IDS:
        fake.series[timeframe][-1]["close"] = 999.0
    fake.requests.clear()
    warm = service.load_primary_timeframes_cached("EURUSD", _BARS, identity)

    assert warm["cache_status"] == "warm_tail"
    assert warm["fetch_metrics"] == {
        "copy_rates_calls": 4,
        "full_history_calls": 0,
        "tail_calls": 4,
        "bars_requested": 12,
        "bars_received": 12,
    }
    assert [count for _, count in fake.requests] == [3, 3, 3, 3]
    for candles in warm["candles_by_timeframe"].values():
        assert len(candles) in {100, 500}
        assert candles[-1].close == 999.0
        assert len({candle.time for candle in candles}) == len(candles)


def test_new_and_multiple_contiguous_bars_append_without_full_reload(
    monkeypatch,
    tmp_path,
):
    service, fake = _service_and_fake(monkeypatch, tmp_path)
    identity = _identity()
    service.load_primary_timeframes_cached("EURUSD", _BARS, identity)

    for timeframe in _TIMEFRAME_IDS:
        interval = _INTERVALS[timeframe]
        previous = fake.series[timeframe][-1]
        previous_time = datetime.fromtimestamp(
            int(previous["time"]), tz=timezone.utc
        )
        for offset in (1, 2, 3):
            value = float(previous["close"]) + offset
            at = previous_time + offset * interval
            fake.series[timeframe].append(
                {
                    "time": int(at.timestamp()),
                    "open": value - 0.1,
                    "high": value + 0.2,
                    "low": value - 0.2,
                    "close": value,
                    "tick_volume": 200 + offset,
                }
            )

    result = service.load_primary_timeframes_cached("EURUSD", _BARS, identity)

    assert result["cache_status"] == "warm_tail"
    assert result["fetch_metrics"]["full_history_calls"] == 0
    assert result["fetch_metrics"]["tail_calls"] == 4
    for timeframe, candles in result["candles_by_timeframe"].items():
        assert candles[-1].close == float(fake.series[timeframe][-1]["close"])
        assert len({candle.time for candle in candles}) == len(candles)


def test_gap_falls_back_to_full_reload(monkeypatch, tmp_path):
    service, fake = _service_and_fake(monkeypatch, tmp_path)
    identity = _identity()
    service.load_primary_timeframes_cached("EURUSD", _BARS, identity)

    for timeframe in _TIMEFRAME_IDS:
        interval = _INTERVALS[timeframe]
        previous = fake.series[timeframe][-1]
        previous_time = datetime.fromtimestamp(
            int(previous["time"]), tz=timezone.utc
        )
        value = float(previous["close"]) + 2.0
        fake.series[timeframe].append(
            {
                "time": int((previous_time + 2 * interval).timestamp()),
                "open": value - 0.1,
                "high": value + 0.2,
                "low": value - 0.2,
                "close": value,
                "tick_volume": 500,
            }
        )

    fake.requests.clear()
    result = service.load_primary_timeframes_cached("EURUSD", _BARS, identity)

    assert result["cache_status"] == "full_reload_gap"
    assert result["fetch_metrics"]["tail_calls"] == 4
    assert result["fetch_metrics"]["full_history_calls"] == 4
    assert result["fetch_metrics"]["bars_requested"] == 1612
    assert [count for _, count in fake.requests] == [3, 3, 3, 3, 500, 500, 500, 100]


def test_identity_and_configuration_changes_force_full_reload(monkeypatch, tmp_path):
    service, fake = _service_and_fake(monkeypatch, tmp_path)
    identity = _identity()
    service.load_primary_timeframes_cached("EURUSD", _BARS, identity)

    fake.requests.clear()
    changed_account = service.load_primary_timeframes_cached(
        "EURUSD", _BARS, _identity(login=8)
    )
    assert changed_account["cache_status"] == "full_reload_identity_change"
    assert [count for _, count in fake.requests] == [500, 500, 500, 100]

    fake.requests.clear()
    changed_config = service.load_primary_timeframes_cached(
        "EURUSD", {**_BARS, "H1": 400}, _identity(login=8)
    )
    assert changed_config["cache_status"] == "full_reload_validation_failure"
    assert [count for _, count in fake.requests] == [500, 500, 400, 100]

    fake.requests.clear()
    changed_symbol = service.load_primary_timeframes_cached(
        "EURUSDm", _BARS, _identity(login=8)
    )
    assert changed_symbol["cache_status"] == "cold_full"
    assert [count for _, count in fake.requests] == [500, 500, 500, 100]


def test_tail_error_keeps_last_known_good_cache_and_is_not_fresh(
    monkeypatch,
    tmp_path,
):
    service, fake = _service_and_fake(monkeypatch, tmp_path)
    identity = _identity()
    initial = service.load_primary_timeframes_cached("EURUSD", _BARS, identity)
    original = initial["candles_by_timeframe"]

    fake.fail_tail = True
    with pytest.raises(RuntimeError, match="tail"):
        service.load_primary_timeframes_cached("EURUSD", _BARS, identity)

    fake.fail_tail = False
    recovered = service.load_primary_timeframes_cached("EURUSD", _BARS, identity)
    assert recovered["cache_status"] == "warm_tail"
    for timeframe, candles in original.items():
        assert len(recovered["candles_by_timeframe"][timeframe]) == len(candles)


def test_full_vs_cache_candle_and_analysis_input_parity(monkeypatch, tmp_path):
    service, fake = _service_and_fake(monkeypatch, tmp_path)
    identity = _identity()
    service.load_primary_timeframes_cached("EURUSD", _BARS, identity)

    # Frozen response change limited to the forming bar and one new bar.
    for timeframe in _TIMEFRAME_IDS:
        interval = _INTERVALS[timeframe]
        previous = fake.series[timeframe][-1]
        previous_time = datetime.fromtimestamp(
            int(previous["time"]), tz=timezone.utc
        )
        previous["close"] = 700.0
        value = 701.0
        at = previous_time + interval
        fake.series[timeframe].append(
            {
                "time": int(at.timestamp()),
                "open": value - 0.1,
                "high": value + 0.2,
                "low": value - 0.2,
                "close": value,
                "tick_volume": 777,
            }
        )

    # Both paths must consume the identical, frozen MT5 response snapshot.
    frozen_series = {
        timeframe: [dict(item) for item in values]
        for timeframe, values in fake.series.items()
    }
    rolling = service.load_primary_timeframes_cached("EURUSD", _BARS, identity)
    fresh_service, fresh_fake = _service_and_fake(monkeypatch, tmp_path / "fresh")
    fresh_fake.series = frozen_series
    fresh = fresh_service.load_primary_timeframes("EURUSD", _BARS)

    assert rolling["candles_by_timeframe"] == fresh
    # This is the analysis input contract used by the scanner: exact lengths,
    # timestamps, and OHLCV values are all equal before analysis runs.
    rolling_input = {
        timeframe: tuple(candles)
        for timeframe, candles in rolling["candles_by_timeframe"].items()
    }
    fresh_input = {timeframe: tuple(candles) for timeframe, candles in fresh.items()}
    assert rolling_input == fresh_input

    analysis_input = AnalysisInput(
        symbol="EUR/USD",
        broker_symbol="EURUSD",
        account_balance=10_000.0,
        risk_percent=1.0,
        account_currency="USD",
        lot_step=0.01,
        minimum_lot=0.01,
        contract_size_override=100_000.0,
        timezone_name="Asia/Ho_Chi_Minh",
    )
    rolling_analysis = analyze_symbol(
        analysis_input,
        rolling["candles_by_timeframe"],
        m15_candles=rolling["candles_by_timeframe"]["M15"],
    )
    fresh_analysis = analyze_symbol(
        analysis_input,
        fresh,
        m15_candles=fresh["M15"],
    )
    # ``timestamp`` is wall-clock metadata; all decision/score fields must
    # remain byte-for-byte equivalent for the frozen candle response.
    rolling_analysis.pop("timestamp", None)
    fresh_analysis.pop("timestamp", None)
    assert rolling_analysis == fresh_analysis


def test_cached_sdk_operations_are_serialized(monkeypatch, tmp_path):
    service, fake = _service_and_fake(
        monkeypatch,
        tmp_path,
        sleep_seconds=0.002,
    )
    identity = _identity()
    service.load_primary_timeframes_cached("EURUSD", _BARS, identity)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(
            executor.map(
                lambda _index: service.load_primary_timeframes_cached(
                    "EURUSD", _BARS, identity
                ),
                range(4),
            )
        )

    assert all(result["cache_status"] == "warm_tail" for result in results)
    assert fake.max_active == 1
