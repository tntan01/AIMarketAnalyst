"""Offline full-route oracle for the Scanner fast-reject implementation.

This test intentionally keeps both fast flags absent. It is the baseline that
later Tier 1/Tier 2 A/B tests must compare against.
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import timedelta
from time import perf_counter
from typing import Any

import pytest

from core.analysis_engine import analyze_symbol
from core.scanner import scanner_row_from_analysis
from core.scanner_candidate_engine import evaluate_scanner_candidate
from core.smc_canonical_context import build_canonical_smc_context
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


_ELIGIBLE_LIFECYCLES = frozenset({"confirmed", "usable"})


def _zone_evidence(smc: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    """Provenance/eligibility lock per timeframe and family (D102-02).

    ``raw_counts`` alone cannot tell a fixture's raw zones apart from zones the
    canonical detector invented, so the oracle also pins what every counted
    zone actually carries: canonical bounds, an evidence measurement, the
    causal formation ATR when warm-up allows, its lifecycle and its direction.
    """

    evidence: dict[str, dict[str, dict[str, Any]]] = {}
    for timeframe in ("H4", "H1"):
        evidence[timeframe] = {}
        for family, key in _FAMILY_KEYS.items():
            zones = [
                zone
                for zone in (smc.get(timeframe, {}).get(key) or [])
                if isinstance(zone, dict)
            ]
            evidence[timeframe][family] = {
                "count": len(zones),
                "eligible": sum(
                    1
                    for zone in zones
                    if str(zone.get("lifecycle_status") or "") in _ELIGIBLE_LIFECYCLES
                ),
                "with_bounds": sum(
                    1 for zone in zones if zone.get("original_bounds")
                ),
                "with_measurement": sum(
                    1
                    for zone in zones
                    if isinstance(
                        zone.get("departure_measurement")
                        or zone.get("middle_measurement")
                        or zone.get("base_measurement"),
                        dict,
                    )
                ),
                "with_formation_atr": sum(
                    1
                    for zone in zones
                    if isinstance(zone.get("formation_atr"), (int, float))
                    and not isinstance(zone.get("formation_atr"), bool)
                ),
                "lifecycles": sorted(
                    {str(zone.get("lifecycle_status") or "") for zone in zones}
                ),
                "directions": sorted(
                    {str(zone.get("direction") or "") for zone in zones}
                ),
            }
    return evidence


def _raw_counts(smc: dict[str, Any]) -> dict[str, dict[str, int]]:
    return {
        timeframe: {
            family: len(smc.get(timeframe, {}).get(key, []))
            for family, key in _FAMILY_KEYS.items()
        }
        for timeframe in ("H4", "H1")
    }


# The corpus prices are quoted to 5 decimals (steps down to 0.000003), so one
# broker tick is 0.00001.  Fixture metadata for the snapshot seam (task 101),
# not a policy threshold.
_TICK_SIZE = 0.00001


def _cutoff(candles: dict[str, list[Any]]) -> Any:
    """The fixture's own snapshot boundary: its last closed candle."""

    latest = None
    for timeframe, interval in (
        ("D1", timedelta(days=1)),
        ("H4", timedelta(hours=4)),
        ("H1", timedelta(hours=1)),
        ("M15", timedelta(minutes=15)),
    ):
        for candle in candles.get(timeframe) or ():
            close_at = candle.time + interval
            if latest is None or close_at > latest:
                latest = close_at
    assert latest is not None
    return latest


def _full_signature(case: dict[str, Any]) -> tuple[dict[str, Any], float]:
    candles = make_candles(case)
    cutoff = _cutoff(candles)
    smc = build_canonical_smc_context(
        candles["D1"], candles["H4"], candles["H1"],
        symbol=str(case.get("symbol", "EUR/USD")),
        as_of=cutoff,
        tick_size=_TICK_SIZE,
    )
    started = perf_counter()
    result = analyze_symbol(
        make_request(case, _CORPUS["analysis_input"]),
        candles,
        m15_candles=candles["M15"],
        m15_as_of=cutoff,
        snapshot_as_of=cutoff,
        tick_size=_TICK_SIZE,
        thresholds=_CORPUS["thresholds"],
    )
    elapsed_ms = round((perf_counter() - started) * 1_000, 3)
    candidate = evaluate_scanner_candidate(scanner_row_from_analysis(result))
    smc_sides = result["smc_scoring"]["sides"]
    return {
        "raw_counts": _raw_counts(smc),
        "zone_evidence": _zone_evidence(smc),
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
    } == names
    assert all(
        "smc_scoring_mode" not in case
        for case in _CORPUS["cases"]
    )
    assert _ORACLES["h1_only_fvg_v2"]["raw_counts"]["H1"]["fvg"] > 0
    assert _ORACLES["h1_order_block_v2"]["raw_counts"]["H1"]["order_block"] > 0
    assert _ORACLES["broken_invalid_v2"]["selected_zone_ids"] == {
        "buy": None, "sell": None,
    }
    assert _ORACLES["buy_setup_v2"]["selected_zone_ids"]["buy"]
    assert _ORACLES["sell_setup_v2"]["selected_zone_ids"]["sell"]


# Per-case canonical expectations of the rebuilt corpus (D102-03).  ``side`` is
# the side the scenario must produce a selected identity for; ``None`` means the
# case is a NEGATIVE scenario and must not select anything.
_CANONICAL_SCENARIO = {
    "raw_empty_v2": None,
    "h1_only_fvg_v2": "buy",
    "h1_order_block_v2": "sell",
    "broken_invalid_v2": None,
    "buy_setup_v2": "buy",
    "sell_setup_v2": "sell",
}
_NEGATIVE_CASES = frozenset({"raw_empty_v2", "broken_invalid_v2"})


@pytest.mark.parametrize("case", _CORPUS["cases"], ids=lambda item: item["name"])
def test_canonical_zone_evidence_and_eligibility(case: dict[str, Any]) -> None:
    """The oracle locks provenance/eligibility, not just zone counts (D102-03).

    Every counted zone must carry the canonical evidence the evaluator measures
    (bounds, an evidence measurement, and — when warm-up allows — the causal
    formation ATR).  A positive scenario must additionally publish a selected
    identity on its own side; a negative scenario must publish none.
    """

    signature, _elapsed = _full_signature(case)
    evidence = signature["zone_evidence"]
    expected_side = _CANONICAL_SCENARIO[case["name"]]

    for timeframe in ("H4", "H1"):
        for family, values in evidence[timeframe].items():
            assert values["with_bounds"] == values["count"], (timeframe, family)
            assert values["with_measurement"] == values["count"], (timeframe, family)
            assert values["eligible"] <= values["count"], (timeframe, family)
            assert values["lifecycles"] or values["count"] == 0, (timeframe, family)

    if expected_side is None:
        assert signature["selected_zone_ids"] == {"buy": None, "sell": None}
        if case["name"] == "raw_empty_v2":
            # The plain run must stay free of canonical raw candidates.
            assert all(
                values["count"] == 0
                for timeframe in ("H4", "H1")
                for values in evidence[timeframe].values()
            )
        return

    selected = signature["selected_zone_ids"]
    other = "sell" if expected_side == "buy" else "buy"
    assert selected[expected_side], case["name"]
    assert selected[other] is None, case["name"]
    # The scenario the Analyzer published is the same side that got selected.
    assert [item["type"] for item in signature["scenario_types"]] == [expected_side]
    # At least one zone on that side is eligible (usable/confirmed).
    assert any(
        values["eligible"]
        for timeframe in ("H4", "H1")
        for values in evidence[timeframe].values()
        if values["directions"] == [expected_side]
    ), case["name"]


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
