"""Offline full-route oracle for the Scanner fast-reject implementation.

This test intentionally keeps both fast flags absent. It is the baseline that
later Tier 1/Tier 2 A/B tests must compare against.
"""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Any

import pytest

from core.analysis_engine import analyze_symbol
from core.scanner import scanner_row_from_analysis
from core.scanner_candidate_engine import evaluate_scanner_candidate
from core.smc_context import build_smc_context
from tests.scanner_fast_path_fixtures import make_candles, make_request


_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "scanner_fast_path"
_CORPUS = json.loads((_FIXTURE_DIR / "corpus.json").read_text(encoding="utf-8"))
_ORACLES = json.loads((_FIXTURE_DIR / "full-oracles.json").read_text(encoding="utf-8"))["cases"]
_FAMILY_KEYS = {
    "demand": "demand_zones",
    "supply": "supply_zones",
    "order_block": "order_blocks",
    "fvg": "fvg",
}


def _raw_counts(smc: dict[str, Any]) -> dict[str, dict[str, int]]:
    return {
        timeframe: {
            family: len(smc.get(timeframe, {}).get(key, []))
            for family, key in _FAMILY_KEYS.items()
        }
        for timeframe in ("H4", "H1")
    }


def _full_signature(case: dict[str, Any]) -> tuple[dict[str, Any], float]:
    candles = make_candles(case)
    smc = build_smc_context(
        candles["D1"], candles["H4"], candles["H1"],
        symbol=str(case.get("symbol", "EUR/USD")),
    )
    started = perf_counter()
    result = analyze_symbol(
        make_request(case, _CORPUS["analysis_input"]),
        candles,
        m15_candles=candles["M15"],
        thresholds=_CORPUS["thresholds"],
        smc_scoring_mode=str(case["smc_scoring_mode"]),
    )
    elapsed_ms = round((perf_counter() - started) * 1_000, 3)
    candidate = evaluate_scanner_candidate(scanner_row_from_analysis(result))
    smc_sides = result["smc_scoring"]["sides"]
    return {
        "raw_counts": _raw_counts(smc),
        "selected_zone_ids": {
            side: smc_sides[side]["selected_zone_id"]
            for side in ("buy", "sell")
        },
        "scenario_types": [
            {"type": item["type"], "entry_status": item.get("entry_status")}
            for item in result["scenarios"]
        ],
        "candidate_status": candidate.status,
        "candidate_selected_side": candidate.selected_side,
        "scoring_version": result["smc_scoring"]["scoring_version"],
    }, elapsed_ms


def test_corpus_covers_required_fast_path_edge_groups() -> None:
    names = {case["name"] for case in _CORPUS["cases"]}
    assert {
        "raw_empty_v2", "h1_only_fvg_v2", "h1_order_block_v2",
        "broken_invalid_v2", "buy_setup_v2", "sell_setup_v2",
        "mode_legacy", "mode_shadow",
    } <= names
    assert {case["smc_scoring_mode"] for case in _CORPUS["cases"]} == {
        "legacy", "shadow", "v2",
    }
    assert _ORACLES["h1_only_fvg_v2"]["raw_counts"]["H1"]["fvg"] > 0
    assert _ORACLES["h1_order_block_v2"]["raw_counts"]["H1"]["order_block"] > 0
    assert _ORACLES["broken_invalid_v2"]["selected_zone_ids"] == {
        "buy": None, "sell": None,
    }
    assert _ORACLES["buy_setup_v2"]["selected_zone_ids"]["buy"]
    assert _ORACLES["sell_setup_v2"]["selected_zone_ids"]["sell"]


@pytest.mark.parametrize("case", _CORPUS["cases"], ids=lambda item: item["name"])
def test_full_route_matches_normalized_offline_oracle(case: dict[str, Any]) -> None:
    """Lock baseline output while ignoring only result timestamps/scan IDs."""

    signature, elapsed_ms = _full_signature(case)
    expected = _ORACLES[case["name"]]
    assert signature == {
        key: value for key, value in expected.items()
        if key != "baseline_elapsed_ms"
    }
    assert elapsed_ms >= 0

    # Explicitly guard the Tier-2 raw-presence partition without depending on
    # detector count details alone.
    for timeframe, expected_presence in case["expected_raw_presence"].items():
        assert any(signature["raw_counts"][timeframe].values()) is expected_presence


@pytest.mark.parametrize("case", _CORPUS["cases"], ids=lambda item: item["name"])
def test_offline_corpus_is_repeatable_without_external_services(case: dict[str, Any]) -> None:
    """The normalized full result must be stable across repeat local runs."""

    first, _ = _full_signature(case)
    second, _ = _full_signature(case)
    assert second == first
