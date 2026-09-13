import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.market_models import Candle
from core.smc_history import assess_smc_history
from core.smc_models import SmcDataQualityState
from core.smc_snapshot_cache import smc_snapshot_identity
from core.smc_structure_replay import replay_smc_structure


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "smc_snapshot_cache_task39.json"
TASK38_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "smc_snapshot_cache_task38.json"
GATE40_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "smc_gate40_structure_replay.json"


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _h1_candles(start: datetime, count: int) -> tuple[Candle, ...]:
    gate40 = json.loads(GATE40_FIXTURE_PATH.read_text(encoding="utf-8"))
    rows = list(gate40["cases"][0]["candles"])
    rows.extend([[100.0, 100.5, 99.5, 100.0]] * max(0, count - len(rows)))
    rows = rows[:count]
    return tuple(
        Candle(
            time=start + timedelta(hours=index),
            open=float(row[0]),
            high=float(row[1]),
            low=float(row[2]),
            close=float(row[3]),
            volume=1000.0 + index,
        )
        for index, row in enumerate(rows)
    )


def _task38_input() -> dict:
    fixture = json.loads(TASK38_FIXTURE_PATH.read_text(encoding="utf-8"))
    candles = fixture["candles"]["H4"]
    return {
        "symbol": fixture["symbol"],
        "as_of": fixture["as_of"],
        "candles_by_timeframe": {
            "H4": tuple(
                Candle(
                    time=_timestamp(item["time"]),
                    open=float(item["open"]),
                    high=float(item["high"]),
                    low=float(item["low"]),
                    close=float(item["close"]),
                    volume=float(item["volume"]),
                )
                for item in candles
            )
        },
        "metadata": dict(fixture["metadata"]),
        "rule_identity": fixture["rule_identity"],
    }


def _result_for(input_value: dict) -> dict:
    h1 = input_value["candles_by_timeframe"]["H1"]
    coverage = assess_smc_history(
        h1,
        "H1",
        symbol=input_value["symbol"],
        origin_time=h1[0].time if h1 else None,
        require_lifetime=True,
    )
    structure = replay_smc_structure(
        h1,
        symbol=input_value["symbol"],
        timeframe="H1",
        as_of=input_value["as_of"],
        tick_size=0.01,
        pivot_width=5,
    )
    return {
        "identity": smc_snapshot_identity(**input_value),
        "history_status": coverage.status,
        "reason_codes": coverage.reason_codes,
        "raw_count": coverage.raw_count,
        "structure_events": tuple(
            (event["event_id"], event["event_type"], event["confirmed_at"])
            for event in structure["events"]
        ),
        "structure_state": tuple(
            structure["structure_state"].get(key)
            for key in (
                "state",
                "direction",
                "protected_swing_id",
                "protected_swing_level",
            )
        ),
    }


def _available_input(count: int = 69) -> dict:
    start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    candles = _h1_candles(start, count)
    value = _task38_input()
    value["as_of"] = (candles[-1].time + timedelta(hours=1)).isoformat()
    value["candles_by_timeframe"] = {"H1": candles}
    return value


def test_task39_fixture_is_complete():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["fixture_id"] == "smc-snapshot-cache-task39-v1"
    assert len(fixture["cases"]) == 4
    assert {case["id"] for case in fixture["cases"]} == {
        "restart-same-input",
        "broker-correction",
        "rolling-history-extension",
        "missing-origin-history",
    }


def test_restart_and_empty_cache_recompute_same_identity_and_result():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    expected = fixture["cases"][0]["expected"]
    source = _available_input()
    first = _result_for(source)
    assert bool(first["structure_events"]) is expected["structure_events_nonempty"]
    assert (first["structure_state"][2] is not None) is expected["protected_level_nonnull"]

    empty_cache: dict[str, dict] = {}
    assert first["identity"] not in empty_cache
    empty_cache[first["identity"]] = first

    # Reconstruct the input as a fresh process would from persisted candles.
    restarted_input = {
        **source,
        "candles_by_timeframe": {
            "H1": tuple(source["candles_by_timeframe"]["H1"])
        },
        "metadata": dict(source["metadata"]),
    }
    second = _result_for(restarted_input)
    assert expected["cold_cache_first_lookup"] == "miss"
    assert first["identity"] == second["identity"]
    assert first == second
    assert expected["identity_equal"] is True
    assert expected["result_equal"] is True


def test_broker_correction_misses_old_cache_entry():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    expected = fixture["cases"][1]["expected"]
    source = _available_input()
    old_result = _result_for(source)
    original_candle = source["candles_by_timeframe"]["H1"][30]
    corrected_candle = replace(
        original_candle,
        high=max(original_candle.high, 130.75),
        close=130.75,
    )
    corrected = {
        **source,
        "candles_by_timeframe": {
            "H1": source["candles_by_timeframe"]["H1"][:30]
            + (corrected_candle,)
            + source["candles_by_timeframe"]["H1"][31:]
        },
    }
    corrected_result = _result_for(corrected)
    cache = {old_result["identity"]: old_result}
    assert corrected_result["identity"] != old_result["identity"]
    assert corrected_result["identity"] not in cache
    assert expected["identity_equal"] is False
    assert expected["old_cache_reused"] is False
    assert expected["reason"] == "candle_content_changed"


def test_rolling_history_extension_changes_identity_but_keeps_complete_coverage():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    expected = fixture["cases"][2]["expected"]
    full = _available_input(69)
    start = full["candles_by_timeframe"]["H1"][0].time
    extended = {
        **full,
        "candles_by_timeframe": {
            "H1": _h1_candles(start - timedelta(hours=1), 70)
        },
    }
    full_result = _result_for(full)
    extended_result = _result_for(extended)
    assert full_result["identity"] != extended_result["identity"]
    assert full_result["history_status"] == expected["full_window_status"]
    assert extended_result["history_status"] == expected["extended_window_status"]
    assert expected["reason"] == "input_history_changed"


def test_missing_history_is_data_unavailable_with_explicit_reason_and_no_cache_reuse():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    expected = fixture["cases"][3]["expected"]
    complete = _available_input(69)
    missing = {
        **complete,
        "candles_by_timeframe": {
            "H1": complete["candles_by_timeframe"]["H1"][1:]
        },
    }
    complete_result = _result_for(complete)
    missing_result = _result_for(missing)
    coverage = assess_smc_history(
        missing["candles_by_timeframe"]["H1"],
        "H1",
        symbol=missing["symbol"],
        origin_time=complete["candles_by_timeframe"]["H1"][0].time,
        require_lifetime=True,
    )
    quality = SmcDataQualityState(
        status=coverage.status,
        reason_codes=coverage.reason_codes,
        missing_timeframes=("H1",),
    )
    consumer_status = "DATA_UNAVAILABLE" if quality.status != "complete" else "AVAILABLE"

    assert missing_result["identity"] != complete_result["identity"]
    assert coverage.status == expected["smc_quality_status"]
    assert consumer_status == expected["status"]
    assert set(expected["required_reasons"]).issubset(set(coverage.reason_codes))
    assert missing_result["identity"] != complete_result["identity"]
    assert missing_result["raw_count"] == 68
    assert expected["cache_result_reused"] is False
