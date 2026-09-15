"""Canonical Analyze golden (D103-03).

The old ``golden_cases.json`` injected a hand-built legacy ``case["smc"]`` into
``AnalysisPipeline`` through a monkeypatched ``build_smc_context``.  Task103
moved Analyze onto the canonical snapshot chain, so that input is no longer a
valid runtime input and the legacy file is kept, unchanged, as a separate
characterization artifact (see ``test_smc_canonical_golden_legacy.py``).

Every case here is regenerated from CANDLES by
``tests/scanner_fast_path_fixtures.py``, frozen at the cutoff of its own data
with an explicit tick, and read through the real
façade -> snapshot -> evaluator -> coordinator -> finalizer chain.  Nothing is
injected and nothing is monkeypatched.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


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


def _fixture() -> dict:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _analyze(case: dict):
    """Run the REAL Analyze caller for one golden case.

    The canonical chain is reached the way production reaches it — through
    ``AnalysisPipeline.execute`` with the case's own candles, cutoff, tick and
    M15 window.  Nothing is monkeypatched and no evaluator is invoked directly,
    so a regression that stops Analyze forwarding any of those inputs (or that
    rebuilds the evaluation) fails the golden.
    """

    from core.analysis_pipeline import AnalysisPipeline
    from core.risk_engine import AnalysisInput

    candles = _FIXTURES.make_candles(
        {"recipe": case["recipe"], "name": case["name"]}
    )
    cutoff = _BASELINE._cutoff(candles)
    pipeline = AnalysisPipeline()
    result = pipeline.execute(
        AnalysisInput(
            symbol=str(case["symbol"]),
            broker_symbol="EURUSD",
            account_balance=10_000.0,
            risk_percent=1.0,
        ),
        candles,
        m15_candles=candles["M15"],
        snapshot_as_of=cutoff,
        m15_as_of=cutoff,
        tick_size=float(case["tick_size"]),
    )
    return result, pipeline, cutoff


def _observed(result: dict) -> dict:
    """Golden values, read from the Analyze CONSUMER result only."""

    consumer = result.get("smc_consumer") or {}
    sides: dict[str, dict] = {}
    for side in ("buy", "sell"):
        payload = (consumer.get("sides") or {}).get(side) or {}
        selection = payload.get("selection") or {}
        readiness = payload.get("readiness") or {}
        sides[side] = {
            "state": selection.get("state"),
            "quality_raw": selection.get("quality_raw"),
            "selected_zone_id": payload.get("selected_zone_id"),
            "selected_setup_id": selection.get("selected_setup_id"),
            "family": selection.get("family"),
            "lifecycle_status": selection.get("lifecycle_status"),
            "plan_available": bool(payload.get("plan_available")),
            "readiness_status": readiness.get("status"),
            "smc_state": readiness.get("smc_state"),
        }
    return {"sides": sides}


@pytest.mark.parametrize("case", _CASES, ids=lambda item: item["name"])
def test_golden_canonical_runtime_matches(case: dict) -> None:
    result, _pipeline, _cutoff = _analyze(case)
    assert _observed(result) == case["expected"]


@pytest.mark.parametrize("case", _CASES, ids=lambda item: item["name"])
def test_golden_canonical_is_deterministic(case: dict) -> None:
    first = _observed(_analyze(case)[0])
    second = _observed(_analyze(case)[0])
    assert first == second


def test_fixture_is_versioned_and_separate_from_the_legacy_artifact():
    fixture = _fixture()
    assert fixture["fixture_version"] == "smc-canonical-golden-v2"
    assert fixture["runtime_mode"] == "canonical-snapshot"
    # The legacy artifact is a different file and must stay untouched.
    legacy = _FIXTURE_PATH.parent / "golden_cases.json"
    legacy_doc = json.loads(legacy.read_text(encoding="utf-8"))
    assert legacy_doc["fixture_version"] == "smc-canonical-golden-v1"
    assert legacy_doc["runtime_mode"] == "v2-decision"
    assert {c["name"] for c in legacy_doc["cases"]} != {
        c["name"] for c in fixture["cases"]
    }
    # Every canonical case carries its own data provenance.
    for case in fixture["cases"]:
        assert case["recipe"] and case["symbol"] and case["tick_size"] > 0


def test_no_zone_zero_and_data_unavailable_null_are_different_contracts():
    """``0`` (evaluated, nothing found) and ``null`` (could not conclude)."""

    zero = _observed(_analyze(_BY_NAME["no_zone"])[0])["sides"]
    for side in ("buy", "sell"):
        assert zero[side]["state"] == "no_zone"
        assert zero[side]["quality_raw"] == 0

    unavailable = _observed(_analyze(_BY_NAME["ob_confirmed_sell"])[0])["sides"]["buy"]
    assert unavailable["state"] == "data_unavailable"
    assert unavailable["quality_raw"] is None
    assert unavailable["selected_zone_id"] is None
    assert unavailable["plan_available"] is False
    assert unavailable["readiness_status"] == "DATA_UNAVAILABLE"


def test_selected_cases_expose_a_consistent_identity_and_provenance():
    for name in ("ob_confirmed_sell", "fvg_confirmed_buy", "sell_setup"):
        observed = _observed(_analyze(_BY_NAME[name])[0])["sides"]
        for side, values in observed.items():
            if values["selected_zone_id"] is None:
                assert values["state"] in {
                    "no_zone",
                    "out_of_strategy",
                    "data_unavailable",
                }
                assert values["family"] is None
                assert values["lifecycle_status"] is None
                continue
            assert values["selected_setup_id"]
            assert values["family"] in {"ob", "fvg", "supply_demand"}
            assert values["lifecycle_status"] in {"confirmed", "usable"}
            assert values["quality_raw"] is not None
            assert values["readiness_status"] in {
                "WATCH_ZONE",
                "WAITING_CONFIRMATION",
                "READY_NOW",
            }


def test_a_side_that_could_not_be_concluded_does_not_cancel_the_other():
    """``ob_confirmed_sell`` pairs an unavailable buy side with a valid sell."""

    sides = _observed(_analyze(_BY_NAME["ob_confirmed_sell"])[0])["sides"]
    assert sides["buy"]["state"] == "data_unavailable"
    assert sides["sell"]["state"] in {"evaluated", "watch_zone"}
    assert sides["sell"]["selected_zone_id"]
    assert sides["sell"]["family"] == "ob"


# ---------------------------------------------------------------------------
# Analyze runtime contracts that used to live in this file's legacy form.
# They are re-expressed against the CANONICAL chain: the seam a batch caller
# invokes exactly once per symbol is ``evaluate_smc_snapshot``.
# ---------------------------------------------------------------------------


def _pipeline_run(monkeypatch, *, tier1: bool = False):
    """Run Analyze once over the canonical fixture, counting chain calls."""

    from core import analysis_pipeline as pipeline_module
    from core import smc_prefilter as prefilter_module
    from core.analysis_pipeline import AnalysisPipeline
    from core.risk_engine import AnalysisInput

    # The chain is invoked from two namespaces: the Tier-1 prefilter runs it
    # first and the full route then REUSES that evaluation, so counting only
    # one namespace would not prove "once per symbol".
    calls: list[str] = []
    real = pipeline_module.evaluate_smc_snapshot

    def spy(*args, **kwargs):
        calls.append("evaluate")
        return real(*args, **kwargs)

    monkeypatch.setattr(pipeline_module, "evaluate_smc_snapshot", spy)
    monkeypatch.setattr(prefilter_module, "evaluate_smc_snapshot", spy)
    case = _BY_NAME["fvg_confirmed_buy"]
    candles = _FIXTURES.make_candles(
        {"recipe": case["recipe"], "name": case["name"]}
    )
    cutoff = _BASELINE._cutoff(candles)
    result = AnalysisPipeline().execute(
        AnalysisInput(
            symbol="EUR/USD",
            broker_symbol="EURUSD",
            account_balance=10_000.0,
            risk_percent=1.0,
        ),
        candles,
        m15_candles=candles["M15"],
        snapshot_as_of=cutoff,
        m15_as_of=cutoff,
        tick_size=float(case["tick_size"]),
        scanner_fast_tier1=tier1,
    )
    return result, calls


def test_score_smc_is_called_exactly_once_per_symbol(monkeypatch):
    _result, calls = _pipeline_run(monkeypatch)
    assert len(calls) == 1


def test_tier1_survivor_total_score_smc_calls_is_one(monkeypatch):
    """A Tier-1 survivor must reuse the prefilter's evaluation, not rebuild it."""

    _result, calls = _pipeline_run(monkeypatch, tier1=True)
    assert len(calls) == 1


def test_tier1_scorer_error_fails_closed_without_retry(monkeypatch):
    from core import analysis_pipeline as pipeline_module
    from core import smc_prefilter as prefilter_module
    from core.analysis_pipeline import AnalysisPipeline
    from core.risk_engine import AnalysisInput

    calls: list[str] = []

    def explode(*_args, **_kwargs):
        calls.append("evaluate")
        raise RuntimeError("canonical chain unavailable")

    # Both namespaces fail, so there is no second route to fall back to.
    monkeypatch.setattr(pipeline_module, "evaluate_smc_snapshot", explode)
    monkeypatch.setattr(prefilter_module, "evaluate_smc_snapshot", explode)
    case = _BY_NAME["fvg_confirmed_buy"]
    candles = _FIXTURES.make_candles(
        {"recipe": case["recipe"], "name": case["name"]}
    )
    cutoff = _BASELINE._cutoff(candles)
    result = AnalysisPipeline().execute(
        AnalysisInput(
            symbol="EUR/USD",
            broker_symbol="EURUSD",
            account_balance=10_000.0,
            risk_percent=1.0,
        ),
        candles,
        m15_candles=candles["M15"],
        snapshot_as_of=cutoff,
        m15_as_of=cutoff,
        tick_size=float(case["tick_size"]),
        scanner_fast_tier1=True,
    )
    assert result["analysis_status"] == "structural_reject"
    assert "SMC_SCORING_ERROR" in result["block_codes"]
    # Fail-closed means exactly one attempt, never a retry or a legacy fallback.
    assert calls == ["evaluate"]


def test_full_route_scorer_error_fails_closed(monkeypatch):
    from core import analysis_pipeline as pipeline_module
    from core.analysis_pipeline import AnalysisPipeline
    from core.risk_engine import AnalysisInput

    calls: list[str] = []

    def explode(*_args, **_kwargs):
        calls.append("evaluate")
        raise RuntimeError("canonical chain unavailable")

    monkeypatch.setattr(pipeline_module, "evaluate_smc_snapshot", explode)
    case = _BY_NAME["fvg_confirmed_buy"]
    candles = _FIXTURES.make_candles(
        {"recipe": case["recipe"], "name": case["name"]}
    )
    cutoff = _BASELINE._cutoff(candles)
    result = AnalysisPipeline().execute(
        AnalysisInput(
            symbol="EUR/USD",
            broker_symbol="EURUSD",
            account_balance=10_000.0,
            risk_percent=1.0,
        ),
        candles,
        m15_candles=candles["M15"],
        snapshot_as_of=cutoff,
        m15_as_of=cutoff,
        tick_size=float(case["tick_size"]),
    )
    assert result["analysis_status"] == "structural_reject"
    assert "SMC_SCORING_ERROR" in result["block_codes"]
    assert calls == ["evaluate"]


# ---------------------------------------------------------------------------
# D103-04 — the golden must prove the ANALYZE CALLER did the work
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _CASES, ids=lambda item: item["name"])
def test_each_case_forwards_cutoff_tick_and_m15_to_the_snapshot(case: dict) -> None:
    """The case's own cutoff/tick/M15 must reach the Analyze snapshot."""

    _result, pipeline, cutoff = _analyze(case)
    snapshot = pipeline._smc_snapshot
    assert snapshot is not None
    assert snapshot.as_of == cutoff
    assert snapshot.m15_as_of == cutoff
    assert snapshot.tick_size == float(case["tick_size"])
    assert snapshot.core_reason_codes == ()
    # The window really travelled: the fixture always ships M15 candles.
    assert snapshot.m15_candles
    assert len(snapshot.m15_candles) == len(
        _FIXTURES.make_candles(
            {"recipe": case["recipe"], "name": case["name"]}
        )["M15"]
    )


@pytest.mark.parametrize("case", _CASES, ids=lambda item: item["name"])
def test_the_consumer_result_is_the_same_evaluation_analyze_ran(case: dict) -> None:
    """One evaluation per snapshot: the consumer reads THAT result.

    The comparison uses the pipeline's own internal evaluation purely to prove
    reuse; every golden expectation above still comes from the consumer result.
    """

    result, pipeline, _cutoff = _analyze(case)
    evaluation = pipeline._smc_evaluation
    assert evaluation is not None
    assert evaluation.snapshot is pipeline._smc_snapshot

    consumer = result["smc_consumer"]
    for side in ("buy", "sell"):
        payload = consumer["sides"][side]
        selection = evaluation.selection(side)
        assert payload["selection"]["state"] == selection.state
        assert payload["selected_zone_id"] == selection.selected_zone_id
        assert (
            payload["selection"]["selected_setup_id"] == selection.selected_setup_id
        )
        assert payload["readiness"]["status"] == selection.readiness.status
        # Provenance survives the consumer hop.
        assert payload["side"] == side
        assert payload["scoring_version"] == evaluation.result.scoring_version
        assert "plan" in payload and "plan_available" in payload


def test_no_case_loses_its_selection_through_the_consumer_contract():
    for case in _CASES:
        result, _pipeline, _cutoff = _analyze(case)
        observed = _observed(result)["sides"]
        consumer = result["smc_consumer"]["sides"]
        for side, values in observed.items():
            assert consumer[side]["selection"]["state"] == values["state"]
            if values["selected_zone_id"] is None:
                assert consumer[side]["selection"]["selected_zone_id"] is None
                continue
            assert consumer[side]["selection"]["selected_setup_id"]
            assert consumer[side]["selection"]["lifecycle_status"] in {
                "confirmed",
                "usable",
            }
            assert consumer[side]["selection"]["quality_raw"] is not None
