"""Legacy golden characterization kept explicit (D103-03).

``tests/fixtures/smc_canonical/golden_cases.json`` injects a hand-built legacy
``case["smc"]`` context into ``AnalysisPipeline``.  Task103 moved Analyze onto
the canonical snapshot chain, so that payload is no longer a valid input for
Analyze and the file is NOT used as a canonical oracle any more.

It is still a useful characterization of the RETIRED scoring route, so this
module exercises it through the legacy scorer directly — it never calls
Analyze, and it never asserts canonical results.  The canonical golden lives in
``test_smc_canonical_golden.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.smc_scorer import score_smc

_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "smc_canonical"
    / "golden_cases.json"
)
_CHOCH_CAP = "choch_cap"
_FORBIDDEN_SHADOW_KEYS = frozenset(
    {
        "shadow_score",
        "shadow_sides",
        "shadow_scoring_version",
        "shadow_selected_zone",
        "shadow_selected_zone_id",
        "shadow_selected_zone_type",
    }
)


def _fixture() -> dict:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _case(name: str) -> dict:
    return next(case for case in _fixture()["cases"] if case["name"] == name)


def test_fixture_has_required_cases_and_scoring_version():
    fixture = _fixture()
    names = {case["name"] for case in fixture["cases"]}
    assert {
        "buy_selected_zone",
        "sell_selected_zone",
        "no_zone",
        "fvg_h1_only",
        "order_block",
        "broken_stale",
        "choch_cap",
        "missing_data_valid",
    }.issubset(names)
    for case in fixture["cases"]:
        for side in ("buy", "sell"):
            assert case["expected"]["sides"][side]["smc_scoring_version"] == "smc-v2"


def test_golden_expected_never_locks_shadow_payload():
    for case in _fixture()["cases"]:
        _assert_no_forbidden_keys(case["expected"], path=case["name"])


def test_choch_cap_characterizes_the_retired_cap_on_the_legacy_scorer():
    """The legacy CHOCH cap, asserted on the route that actually owned it.

    The canonical contribution carries no cap (Task106/112 removed it), so this
    expectation only ever holds for the retired ``score_smc`` pipeline — it is
    deliberately NOT part of the canonical golden.
    """

    case = _case(_CHOCH_CAP)
    legacy = score_smc(case["smc"], case["technical"], case["market_regime"])
    side = legacy.side("buy")
    expected = case["expected"]["sides"]["buy"]

    assert expected["smc_quality"] == 8
    assert side.score == expected["smc_quality"]
    assert side.breakdown.get("caps"), "the legacy cap must still be recorded"
    assert side.breakdown.get("applied_cap") is not None
    assert side.selected_zone_id == expected["selected_zone_id"]


def _assert_no_forbidden_keys(value: Any, *, path: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            assert key not in _FORBIDDEN_SHADOW_KEYS, f"{path}.{key}"
            _assert_no_forbidden_keys(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_forbidden_keys(item, path=f"{path}[{index}]")
