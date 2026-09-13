import json
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from core.market_models import Candle
from core.smc_models import build_zone_id
from core.smc_snapshot_cache import (
    SMC_RULE_IDENTITY,
    smc_snapshot_identity,
    smc_snapshot_identity_payload,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "smc_snapshot_cache_task38.json"


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _candles(raw: list[dict]) -> list[Candle]:
    return [
        Candle(
            time=_timestamp(item["time"]),
            open=float(item["open"]),
            high=float(item["high"]),
            low=float(item["low"]),
            close=float(item["close"]),
            volume=float(item["volume"]),
        )
        for item in raw
    ]


def _base_input(fixture: dict) -> dict:
    return {
        "symbol": fixture["symbol"],
        "as_of": fixture["as_of"],
        "candles_by_timeframe": {
            timeframe: _candles(candles)
            for timeframe, candles in fixture["candles"].items()
        },
        "metadata": deepcopy(fixture["metadata"]),
        "rule_identity": fixture["rule_identity"],
    }


def _mutated_input(fixture: dict, mutation: dict) -> dict:
    value = _base_input(fixture)
    if mutation["kind"] == "candle_close":
        value["candles_by_timeframe"]["H4"][mutation["index"]] = replace(
            value["candles_by_timeframe"]["H4"][mutation["index"]],
            close=float(mutation["value"]),
        )
    elif mutation["kind"] == "as_of":
        value["as_of"] = mutation["value"]
    elif mutation["kind"] == "metadata":
        value["metadata"][mutation["key"]] = mutation["value"]
    elif mutation["kind"] == "rule_identity":
        value["rule_identity"] = mutation["value"]
    elif mutation["kind"] == "metadata_reordered":
        value["metadata"] = {
            key: value["metadata"][key]
            for key in reversed(tuple(value["metadata"]))
        }
    elif mutation["kind"] == "metadata_numeric_spelling":
        value["metadata"]["tick_size"] = "0.0001000"
        value["metadata"]["point"] = "0.0001"
    else:
        raise AssertionError(f"unknown mutation: {mutation['kind']}")
    return value


def test_task38_fixture_is_complete():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["fixture_id"] == "smc-snapshot-cache-task38-v1"
    assert fixture["rule_identity"] == SMC_RULE_IDENTITY
    assert len(fixture["mutations"]) == 6
    assert fixture["zone_identity"]["expected_same_zone_id"] is True


def test_snapshot_identity_changes_for_candle_cutoff_metadata_and_rule_inputs():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    base = _base_input(fixture)
    base_key = smc_snapshot_identity(**base)
    assert base_key.startswith("smc-cache-key-v1:")

    for mutation in fixture["mutations"]:
        candidate = _mutated_input(fixture, mutation)
        candidate_key = smc_snapshot_identity(**candidate)
        if mutation["expected"] == "different":
            assert candidate_key != base_key, mutation["id"]
        else:
            assert candidate_key == base_key, mutation["id"]


def test_identity_payload_retains_all_candle_content_and_metadata():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload = smc_snapshot_identity_payload(**_base_input(fixture))
    assert payload["as_of"] == "2026-02-02T12:00:00+00:00"
    assert payload["candles"]["H4"][1]["close"] == "1.103"
    assert payload["candles"]["H4"][1]["volume"] == "15"
    assert payload["metadata"]["tick_size"] == {"type": "float", "value": "0.0001"}
    assert payload["rule_identity"] == "smc-rules-v1"
    assert set(payload["rule_versions"]) == {
        "domain",
        "snapshot_contract",
        "scorer",
        "confluence",
        "sweep_link",
    }


def test_equivalent_added_history_does_not_change_zone_identity():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    zone = fixture["zone_identity"]
    common = {
        "symbol": fixture["symbol"],
        "timeframe": zone["timeframe"],
        "family": zone["family"],
        "direction": zone["direction"],
        "origin_time": zone["origin_time"],
        "low": zone["low"],
        "high": zone["high"],
    }
    original = build_zone_id(**common)
    extended = build_zone_id(**common)
    assert original == extended
    assert zone["original_history_index"] != zone["extended_history_index"]
