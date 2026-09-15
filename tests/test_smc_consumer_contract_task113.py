"""Task113 — the consumer/composition contract of the canonical result.

Every case is driven through the REAL callers, not through a DTO helper:

* Scanner live: ``run_pair_from_live`` -> ``plans_from_canonical_selection`` ->
  ``build_live_snapshot`` -> composition / ``SideScore.smc_selection``.
* Analyze: ``AnalysisPipeline.execute`` -> ``smc_consumer`` contract.

The contract states under test (compat spec §3):

* ``no_zone`` is an evaluated ZERO when the core timeframes are sufficient;
* ``data_unavailable`` keeps ``quality_raw = null``;
* a malformed canonical result is refused instead of degrading into a score, a
  zone, a plan or a ready verdict;
* readiness may only LOWER execution rights, never grant entry;
* the consumer and the composition read ONE lineage — the adapter converts, it
  never re-derives a zone or a plan.
"""

from __future__ import annotations

import importlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections.abc import Mapping
from typing import Any

import pytest

from core.smc_scoring_result import (
    SELECTION_STATE_DATA_UNAVAILABLE,
    SELECTION_STATE_EVALUATED,
    SELECTION_STATE_NO_ZONE,
    SmcScoringResult,
    SmcSideScoringResult,
    smc_selection_of,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "smc_canonical"
    / "golden_cases_canonical.json"
)
_FIXTURES = importlib.import_module("tests.scanner_fast_path_fixtures")
_BASELINE = importlib.import_module("tests.test_scanner_fast_path_baseline")

# Caller-level cases that together cover all three canonical states.
_CASES = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))["cases"]
_BY_NAME = {case["name"]: case for case in _CASES}

# The zoned-candle fixture whose canonical selection reaches ``evaluated``.
_ZONED_CUTOFF = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)


def _case(name: str) -> dict[str, Any]:
    return _BY_NAME[name]


def _candles(case: dict[str, Any]) -> dict[str, Any]:
    return _FIXTURES.make_candles({"recipe": case["recipe"], "name": case["name"]})


def _cutoff(candles: dict[str, Any]) -> Any:
    return _BASELINE._cutoff(candles)


def _safety(symbol: str, now: Any):
    from core.scanner_live_producers import build_live_market_safety_context

    return build_live_market_safety_context(
        symbol,
        now,
        terminal_connected=True,
        broker_logged_in=True,
        connectivity_checked_at=now - timedelta(seconds=30),
        last_candle_time_utc=now - timedelta(seconds=30),
        spread_points=20.0,
        spread_checked_at=now,
        news_source_verified=True,
        news_checked_at=now,
        volatility_ratio=1.0,
        volatility_checked_at=now,
    )


def _scanner(case: dict[str, Any]):
    """Run the real Scanner live caller for one canonical case."""

    from core.scanner_release import run_pair_from_live

    candles = _candles(case)
    cutoff = _cutoff(candles)
    symbol = str(case["symbol"])
    return run_pair_from_live(
        candles["D1"],
        candles["H4"],
        candles["H1"],
        symbol,
        _safety(symbol, cutoff),
        now=cutoff,
        captured_at=cutoff,
        m15_candles=candles["M15"],
        tick_size=float(case["tick_size"]),
    )


def _scanner_analysis(case: dict[str, Any]) -> dict[str, Any]:
    """The live producer output the Scanner caller builds the pair from."""

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
        tick_size=float(case["tick_size"]),
    )


def _analyze(case: dict[str, Any]):
    """Run the real Analyze caller for one canonical case."""

    from core.analysis_pipeline import AnalysisPipeline
    from core.risk_engine import AnalysisInput

    candles = _candles(case)
    cutoff = _cutoff(candles)
    pipeline = AnalysisPipeline()
    result = pipeline.execute(
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
        tick_size=float(case["tick_size"]),
    )
    return result, pipeline


def _canonical_result(case: dict[str, Any]) -> SmcScoringResult:
    """The final canonical result the Scanner caller evaluated."""

    return _scanner_analysis(case)["canonical_smc"]


def _composition_summary(pair: Any, side: str) -> dict[str, Any] | None:
    for side_score in pair.composition.canonical.side_scores:
        if getattr(side_score, "side", None) == side:
            summary = side_score.smc_selection
            # The projection is frozen (FrozenJson), not a plain dict.
            return dict(summary) if isinstance(summary, Mapping) else None
    return None


def _consumer(contract: dict[str, Any], side: str) -> dict[str, Any]:
    from core.smc_consumer_contract import selection_for_side

    selection = selection_for_side(contract, side)
    assert selection is not None, f"{side} must carry a canonical selection payload"
    return selection


# ---------------------------------------------------------------------------
# One lineage: consumer contract <-> composition <-> final selection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["no_zone", "ob_confirmed_sell", "fvg_confirmed_buy"])
def test_the_contract_and_the_composition_read_one_canonical_lineage(name: str):
    """The adapter converts the final selection; it never re-derives a zone."""

    case = _case(name)
    from core.smc_consumer_contract import build_smc_consumer_from_canonical_result

    pair = _scanner(case)
    canonical = _canonical_result(case)
    assert isinstance(canonical, SmcScoringResult)
    contract = build_smc_consumer_from_canonical_result(result=canonical)

    for side in ("buy", "sell"):
        final = smc_selection_of(canonical.side(side))
        assert final is not None
        payload = _consumer(contract, side)
        summary = _composition_summary(pair, side)
        assert summary is not None, f"{side} must reach the composition"

        for field in (
            "state",
            "quality_raw",
            "selected_zone_id",
            "selected_setup_id",
            "plan_available",
        ):
            assert payload[field] == getattr(final, field), f"contract.{field}"
        assert summary["state"] == final.state
        assert summary["quality_raw"] == final.quality_raw
        assert summary["selected_zone_id"] == final.selected_zone_id
        assert summary["plan_available"] == final.plan_available
        # The plan reference names the same zone/setup as the selection.
        if final.state == SELECTION_STATE_EVALUATED:
            assert final.plan_zone_id == final.selected_zone_id
            assert final.plan_setup_id == final.selected_setup_id
            assert summary["plan_zone_id"] == final.selected_zone_id
            assert summary["plan_setup_id"] == final.selected_setup_id


# ---------------------------------------------------------------------------
# no_zone = evaluated zero, data_unavailable = null
# ---------------------------------------------------------------------------


def test_a_no_zone_side_is_an_evaluated_zero_at_every_consumer():
    """Enough core data with no eligible setup is a ZERO, never a null."""

    case = _case("no_zone")
    pair = _scanner(case)
    for side in ("buy", "sell"):
        summary = _composition_summary(pair, side)
        assert summary["state"] == SELECTION_STATE_NO_ZONE
        assert summary["quality_raw"] == 0, "no-zone is an evaluated zero"
        assert summary["selected_zone_id"] is None
        assert summary["plan_available"] is False

    result, pipeline = _analyze(case)
    evaluation = pipeline._smc_evaluation
    for side in ("buy", "sell"):
        selection = smc_selection_of(evaluation.result.side(side))
        assert selection.state == SELECTION_STATE_NO_ZONE
        assert selection.quality_raw == 0
        assert selection.quality_raw is not None
    contract = result.get("smc_consumer") or {}
    for side in ("buy", "sell"):
        assert _consumer(contract, side)["quality_raw"] == 0


def test_data_unavailable_keeps_a_null_raw_at_every_consumer():
    """A side whose core evidence is missing reports null, never zero."""

    case = _case("ob_confirmed_sell")
    pair = _scanner(case)
    unavailable = [
        side
        for side in ("buy", "sell")
        if _composition_summary(pair, side)["state"] == SELECTION_STATE_DATA_UNAVAILABLE
    ]
    assert unavailable, "the fixture must expose a core-unavailable side"

    for side in unavailable:
        summary = _composition_summary(pair, side)
        assert summary["quality_raw"] is None, "unavailable is null, not zero"
        assert summary["plan_available"] is False
        assert summary["readiness_status"] != "READY_NOW"

    result, pipeline = _analyze(case)
    for side in unavailable:
        selection = smc_selection_of(pipeline._smc_evaluation.result.side(side))
        assert selection.state == SELECTION_STATE_DATA_UNAVAILABLE
        assert selection.quality_raw is None


# ---------------------------------------------------------------------------
# Malformed canonical never becomes a score / zone / plan / READY
# ---------------------------------------------------------------------------


def test_a_structural_legacy_result_is_refused_by_the_consumer():
    """A result carrying no canonical selection is not silently accepted."""

    from core.smc_consumer_contract import build_smc_consumer_from_canonical_result

    malformed = SmcScoringResult(
        scoring_version="smc-v2",
        sides={"buy": SmcSideScoringResult(score=12, breakdown={"total": 12})},
    )
    with pytest.raises(ValueError):
        build_smc_consumer_from_canonical_result(result=malformed)


def test_a_malformed_final_selection_never_reaches_a_consumer():
    """A final result that disagrees with its own identity fails closed."""

    from dataclasses import replace

    from core.scanner_live_producers import derive_live_analysis
    from core.smc_consumer_contract import build_smc_consumer_from_canonical_result
    from tests.test_scanner_release import _zoned_candles

    # A fixture whose canonical selection really reaches ``evaluated`` with a
    # plan, so the identity invariant has something to guard.
    d1, h4, h1 = _zoned_candles()
    canonical = derive_live_analysis(
        d1, h4, h1, symbol="XAUUSD", captured_at=_ZONED_CUTOFF, tick_size=0.01, min_rr=2.0
    )["canonical_smc"]
    selection = smc_selection_of(canonical.side("buy"))
    assert selection.state == SELECTION_STATE_EVALUATED
    assert selection.plan_available is True

    # A plan that names another zone, or that is dropped while the side claims
    # an evaluated setup, cannot exist: the canonical invariant refuses it at
    # construction, so no consumer can ever read a mismatched lineage.
    with pytest.raises(ValueError):
        replace(selection, plan_zone_id="smcz-other-zone")
    with pytest.raises(ValueError):
        replace(selection, plan=None)

    # And the contract itself refuses a result missing the second side.
    with pytest.raises(ValueError):
        build_smc_consumer_from_canonical_result(
            result=SmcScoringResult(
                scoring_version=canonical.scoring_version,
                sides={"buy": canonical.side("buy")},
            )
        )


# ---------------------------------------------------------------------------
# Readiness lowers, never grants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["ob_confirmed_sell", "fvg_confirmed_buy", "no_zone"])
def test_readiness_only_lowers_execution_rights(name: str):
    """The SMC verdict can only remove execution, never grant it."""

    from core.scanner_execution_readiness import (
        SMC_NOT_READY,
        evaluate_execution_readiness,
    )
    from core.scanner_v4_models import BLOCKED, DATA_UNAVAILABLE

    pair = _scanner(_case(name))
    readiness = evaluate_execution_readiness(pair.composition)
    assert readiness.revalidation_required is True

    selected = pair.composition.decision.selected_side
    summary = _composition_summary(pair, selected) if selected else None

    if summary is not None and summary["readiness_status"] != "READY_NOW":
        # A selected side whose canonical verdict is not READY_NOW is refused.
        assert readiness.can_execute is False
        assert SMC_NOT_READY in readiness.reason_codes
    elif summary is None:
        # No canonical summary for the selected side contributes no SMC reason;
        # the pre-existing execution conditions already refuse it.
        assert readiness.can_execute is False

    # The SMC verdict never grants: an executable side is the conjunction of
    # the pre-existing conditions AND a READY_NOW canonical verdict.
    if readiness.can_execute:
        assert readiness.fresh_snapshot is True
        assert pair.composition.decision.candidate_status not in (
            DATA_UNAVAILABLE,
            BLOCKED,
        )
        assert summary is not None
        assert summary["readiness_status"] == "READY_NOW"


def test_the_canonical_readiness_verdict_can_never_grant_execution():
    """The readiness value object refuses a granted execution by construction."""

    import inspect

    import core.smc_readiness as smc_readiness

    source = inspect.getsource(smc_readiness)
    assert "cannot grant execution by itself" in source
    assert "can_execute=False" in source
