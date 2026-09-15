"""Task114 — Scanner / Analyze / replay parity on ONE snapshot input.

The three routes must reach the SAME canonical verdict for the same frozen
input, and the evaluator must run exactly once per route.  Nothing here
re-baselines a difference: every compared field is read from the route's own
public/consumer output, and any disagreement is a failure, not a new expected
value.

Task 114 also removed the second canonical chain: ``replay_canonical_snapshot``
now accepts the live ``SmcSnapshotInput`` and delegates to
``core.smc_snapshot.evaluate_smc_snapshot`` instead of calling the evaluator and
the coordinator itself.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from core.smc_scoring_result import SELECTION_STATE_DATA_UNAVAILABLE, smc_selection_of

_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "smc_canonical"
    / "golden_cases_canonical.json"
)
_FIXTURES = importlib.import_module("tests.scanner_fast_path_fixtures")
_BASELINE = importlib.import_module("tests.test_scanner_fast_path_baseline")

_CASES = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))["cases"]
_BY_NAME = {case["name"]: case for case in _CASES}
_CASE_NAMES = ["no_zone", "ob_confirmed_sell", "fvg_confirmed_buy", "sell_setup"]

_MIN_RR = 2.0


def _case(name: str) -> dict[str, Any]:
    return _BY_NAME[name]


def _candles(case: dict[str, Any]) -> dict[str, Any]:
    return _FIXTURES.make_candles({"recipe": case["recipe"], "name": case["name"]})


def _cutoff(candles: dict[str, Any]) -> Any:
    return _BASELINE._cutoff(candles)


def _tick(case: dict[str, Any]) -> float:
    return float(case["tick_size"])


def _scanner(case: dict[str, Any]) -> dict[str, Any]:
    from core.scanner_live_producers import derive_live_analysis

    candles = _candles(case)
    cutoff = _cutoff(candles)
    return derive_live_analysis(
        candles["D1"],
        candles["H4"],
        candles["H1"],
        symbol=str(case["symbol"]),
        captured_at=cutoff,
        m15_candles=candles["M15"],
        m15_as_of=cutoff,
        tick_size=_tick(case),
        min_rr=_MIN_RR,
    )


def _analyze(case: dict[str, Any]):
    from core.analysis_pipeline import AnalysisPipeline
    from core.risk_engine import AnalysisInput

    candles = _candles(case)
    cutoff = _cutoff(candles)
    pipeline = AnalysisPipeline()
    pipeline.execute(
        AnalysisInput(
            symbol=str(case["symbol"]),
            broker_symbol=str(case["symbol"]),
            account_balance=10_000.0,
            risk_percent=1.0,
        ),
        candles,
        m15_candles=candles["M15"],
        snapshot_as_of=cutoff,
        m15_as_of=cutoff,
        tick_size=_tick(case),
    )
    return pipeline


def _replay(snapshot: Any, **kwargs: Any) -> dict[str, Any]:
    from core.smc_validation import replay_canonical_snapshot

    return replay_canonical_snapshot(snapshot, min_rr=_MIN_RR, **kwargs)


def _side_view(selection: Any) -> dict[str, Any]:
    readiness = selection.readiness if isinstance(selection.readiness, Mapping) else {}
    return {
        "state": selection.state,
        "quality_raw": selection.quality_raw,
        "b": selection.b,
        "q": selection.q,
        "l": selection.l,
        "c": selection.c,
        "total": selection.total,
        "selected_zone_id": selection.selected_zone_id,
        "selected_setup_id": selection.selected_setup_id,
        "plan_available": selection.plan_available,
        "plan_zone_id": selection.plan_zone_id,
        "plan_setup_id": selection.plan_setup_id,
        "readiness_status": readiness.get("status"),
        "smc_state": readiness.get("smc_state"),
        "reason_codes": list(selection.selection_reason_codes),
    }


# ---------------------------------------------------------------------------
# Same snapshot input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", _CASE_NAMES)
def test_the_live_routes_freeze_the_same_snapshot_input(name: str):
    """Scanner and Analyze build one snapshot from the same candles/cutoff."""

    case = _case(name)
    scanner_snapshot = _scanner(case)["smc_snapshot"]
    pipeline = _analyze(case)
    analyze_snapshot = pipeline._smc_snapshot

    assert analyze_snapshot.as_of == scanner_snapshot.as_of == _cutoff(_candles(case))
    assert analyze_snapshot.core_reason_codes == scanner_snapshot.core_reason_codes
    assert analyze_snapshot.tick_size == scanner_snapshot.tick_size == _tick(case)
    assert analyze_snapshot.tick_size_source == scanner_snapshot.tick_size_source
    assert analyze_snapshot.m15_as_of == scanner_snapshot.m15_as_of
    assert len(analyze_snapshot.m15_candles or ()) == len(
        scanner_snapshot.m15_candles or ()
    )
    assert analyze_snapshot.symbol == scanner_snapshot.symbol


# ---------------------------------------------------------------------------
# Same verdict
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", _CASE_NAMES)
def test_scanner_and_analyze_agree_field_by_field(name: str):
    """Same input, same quality/state/identity/readiness/plan reference."""

    case = _case(name)
    scanner = _scanner(case)
    pipeline = _analyze(case)

    for side in ("buy", "sell"):
        left = _side_view(smc_selection_of(scanner["canonical_smc"].side(side)))
        right = _side_view(smc_selection_of(pipeline._smc_evaluation.result.side(side)))
        assert left == right, f"{name}/{side}"


@pytest.mark.parametrize("name", _CASE_NAMES)
def test_replay_agrees_with_the_live_verdict(name: str):
    """The replay of the SAME snapshot reports the live verdict."""

    case = _case(name)
    scanner = _scanner(case)
    replayed = _replay(scanner["smc_snapshot"])

    for side in ("buy", "sell"):
        live = _side_view(smc_selection_of(scanner["canonical_smc"].side(side)))
        observed = replayed["sides"][side]
        assert observed["state"] == live["state"]
        assert observed["quality_raw"] == live["quality_raw"]
        assert observed["selected_zone_id"] == live["selected_zone_id"]
        assert observed["selected_setup_id"] == live["selected_setup_id"]
        assert observed["plan_available"] == live["plan_available"]
        assert observed["readiness_status"] == live["readiness_status"]
        assert observed["smc_state"] == live["smc_state"]

    # The reported side/status is the live selection of that side.
    if replayed["side"] in ("buy", "sell"):
        live = _side_view(
            smc_selection_of(scanner["canonical_smc"].side(replayed["side"]))
        )
        assert replayed["status"] == live["readiness_status"]
        assert replayed["quality_raw"] == live["quality_raw"]


@pytest.mark.parametrize("name", ["ob_confirmed_sell", "sell_setup", "no_zone"])
def test_a_core_unavailable_snapshot_stays_unavailable_on_every_route(name: str):
    """A core-data verdict cannot be repaired by a different route."""

    case = _case(name)
    scanner = _scanner(case)
    unavailable = [
        side
        for side in ("buy", "sell")
        if smc_selection_of(scanner["canonical_smc"].side(side)).state
        == SELECTION_STATE_DATA_UNAVAILABLE
    ]

    pipeline = _analyze(case)
    replayed = _replay(scanner["smc_snapshot"])

    for side in ("buy", "sell"):
        live = smc_selection_of(scanner["canonical_smc"].side(side))
        analyze = smc_selection_of(pipeline._smc_evaluation.result.side(side))
        replay = replayed["sides"][side]
        # Whatever the state, the three routes agree on it and its raw.
        assert analyze.state == live.state
        assert replay["state"] == live.state
        assert analyze.quality_raw == live.quality_raw
        assert replay["quality_raw"] == live.quality_raw

    for side in unavailable:
        for selection in (
            smc_selection_of(scanner["canonical_smc"].side(side)),
            smc_selection_of(pipeline._smc_evaluation.result.side(side)),
        ):
            assert selection.state == SELECTION_STATE_DATA_UNAVAILABLE
            assert selection.quality_raw is None
            assert selection.plan_available is False
        assert replayed["sides"][side]["state"] == SELECTION_STATE_DATA_UNAVAILABLE
        assert replayed["sides"][side]["quality_raw"] is None


# ---------------------------------------------------------------------------
# The evaluator runs once per route, on one chain
# ---------------------------------------------------------------------------


def test_every_route_runs_the_evaluator_exactly_once(monkeypatch: pytest.MonkeyPatch):
    """No route may rebuild the chain for the same cutoff."""

    from core import smc_snapshot

    calls: list[Any] = []
    real = smc_snapshot.evaluate_candidate_sets

    def spy(smc, technical=None, **kwargs):
        calls.append(kwargs.get("as_of"))
        return real(smc, technical, **kwargs)

    monkeypatch.setattr(smc_snapshot, "evaluate_candidate_sets", spy)

    case = _case("ob_confirmed_sell")
    scanner = _scanner(case)
    assert len(calls) == 1, "Scanner must evaluate the snapshot once"

    pipeline = _analyze(case)
    assert len(calls) == 2, "Analyze must evaluate the snapshot once"

    _replay(scanner["smc_snapshot"])
    assert len(calls) == 3, "replay must evaluate the frozen snapshot once"


def test_replay_delegates_to_the_one_canonical_seam(monkeypatch: pytest.MonkeyPatch):
    """Replay is not a second evaluator/coordinator implementation."""

    from core import smc_snapshot, smc_validation

    seen: list[Any] = []
    real = smc_snapshot.evaluate_smc_snapshot

    def spy(snapshot, **kwargs):
        seen.append(snapshot)
        return real(snapshot, **kwargs)

    monkeypatch.setattr(smc_snapshot, "evaluate_smc_snapshot", spy)
    case = _case("sell_setup")
    scanner = _scanner(case)
    seen.clear()  # the live producer's own evaluation is not the replay's
    _replay(scanner["smc_snapshot"])

    assert seen == [scanner["smc_snapshot"]], "replay must reuse the frozen snapshot"

    # The duplicate chain is gone: the module no longer binds the evaluator or
    # the coordinator at all.
    source = Path(smc_validation.__file__).read_text(encoding="utf-8")
    for name in ("evaluate_candidate_sets", "select_canonical_sides"):
        assert f"import {name}" not in source
        assert f"{name}(" not in source


def test_replay_still_refuses_a_payload_that_is_not_a_snapshot():
    """The malformed guard survives the seam change (compat spec §3)."""

    from core.smc_validation import REPLAY_SNAPSHOT_MALFORMED, replay_canonical_snapshot

    for payload in (None, {}, [], "not-a-snapshot", {"status": "READY"}, {"smc": {}}):
        replayed = replay_canonical_snapshot(payload, min_rr=_MIN_RR)
        for side in ("buy", "sell"):
            assert replayed["sides"][side]["state"] == SELECTION_STATE_DATA_UNAVAILABLE
            assert (
                REPLAY_SNAPSHOT_MALFORMED
                in replayed["sides"][side]["quality_reason_codes"]
            )
        assert replayed["status"] != "READY_NOW"


def test_an_empty_but_valid_snapshot_stays_no_zone_not_unavailable():
    """A present context with no eligible zone is a zero, never unavailable."""

    from core.smc_validation import REPLAY_SNAPSHOT_MALFORMED, replay_canonical_snapshot

    case = _case("no_zone")
    scanner = _scanner(case)
    replayed = replay_canonical_snapshot(
        {
            "smc": dict(scanner["smc_snapshot"].smc or {}),
            "technical": dict(scanner["smc_snapshot"].technical or {}),
            "as_of": scanner["smc_snapshot"].as_of,
            "m15_as_of": scanner["smc_snapshot"].m15_as_of,
            "m15_candles": scanner["smc_snapshot"].m15_candles,
            "core_reason_codes": list(scanner["smc_snapshot"].core_reason_codes),
        },
        min_rr=_MIN_RR,
    )
    for side in ("buy", "sell"):
        assert replayed["sides"][side]["state"] == "no_zone"
        assert replayed["sides"][side]["quality_raw"] == 0
        assert (
            REPLAY_SNAPSHOT_MALFORMED
            not in replayed["sides"][side]["quality_reason_codes"]
        )
