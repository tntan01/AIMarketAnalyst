"""Task115 — gate / scenario verification and the technical-fallback boundary.

D107-01: the canonical final selection is the ONLY source for the canonical
readiness/entry plan.  ``technical_zone`` / ``_protective_zone`` stay as the
historical reader the old callers use, and they may never raise
``invalid`` / ``no_zone`` / ``data_unavailable`` into a canonical ready or
selected state.

The gates are checked through the callers that own them — the Scanner release
pair for the safety/macro/account gates, the Analyze scenario builder for the
risk gate, and ``check_trade_gates`` for the structural-conflict cap.  Nothing
here loosens a gate: every test asserts that a blocking signal still blocks
even when the canonical side carries a real accepted plan.

Source-age freshness is CHARACTERIZED, not changed: the only freshness owners
today are the composition SLA and the market-safety data-freshness source.  The
canonical SMC snapshot itself carries no source-age SLA, which is the deferred
decision recorded in the progress log.
"""

from __future__ import annotations

import importlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from core.smc_consumer_contract import selected_zone_for_side
from core.smc_scoring_result import SELECTION_STATE_EVALUATED, smc_selection_of

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
_ALL_CASES = ["no_zone", "ob_confirmed_sell", "fvg_confirmed_buy", "sell_setup"]

UTC = timezone.utc
NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)


def _case(name: str) -> dict[str, Any]:
    return _BY_NAME[name]


def _candles(case: dict[str, Any]) -> dict[str, Any]:
    return _FIXTURES.make_candles({"recipe": case["recipe"], "name": case["name"]})


def _live_analysis(case: dict[str, Any]) -> dict[str, Any]:
    from core.scanner_live_producers import derive_live_analysis

    candles = _candles(case)
    cutoff = _BASELINE._cutoff(candles)
    return derive_live_analysis(
        candles["D1"],
        candles["H4"],
        candles["H1"],
        symbol=str(case["symbol"]),
        captured_at=cutoff,
        m15_candles=candles["M15"],
        m15_as_of=cutoff,
        tick_size=float(case["tick_size"]),
        min_rr=2.0,
    )


def _safety(terminal_connected: bool = True):
    from core.scanner_live_producers import build_live_market_safety_context

    return build_live_market_safety_context(
        "XAUUSD",
        NOW,
        terminal_connected=terminal_connected,
        broker_logged_in=True,
        connectivity_checked_at=NOW - timedelta(seconds=30),
        last_candle_time_utc=NOW - timedelta(seconds=30),
        spread_points=20.0,
        spread_checked_at=NOW,
        news_source_verified=True,
        news_checked_at=NOW,
        volatility_ratio=1.0,
        volatility_checked_at=NOW,
    )


def _zoned_pair(*, safety=None, order_policy: Any = "default", **macro: Any):
    from core.scanner_order_policy import load_runtime_order_policy
    from core.scanner_release import run_pair_from_live
    from tests.test_scanner_release import _zoned_candles

    d1, h4, h1 = _zoned_candles()
    policy = load_runtime_order_policy() if order_policy == "default" else order_policy
    kwargs = {"macro_raw_buy": 20, "macro_raw_sell": 14, "macro_confidence": 0.8}
    kwargs.update(macro)
    return run_pair_from_live(
        d1,
        h4,
        h1,
        "XAUUSD",
        safety if safety is not None else _safety(),
        now=NOW,
        captured_at=NOW,
        tick_size=0.01,
        order_policy=policy,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# D107-01 — the technical fallback is not on the canonical route
# ---------------------------------------------------------------------------


def test_the_legacy_plan_producers_have_no_production_caller():
    """The technical-fallback producers are reader-only by construction."""

    root = Path(__file__).resolve().parent.parent
    offenders: list[str] = []
    for package in ("core", "controllers", "services", "ui", "workers", "scripts"):
        for path in (root / package).rglob("*.py"):
            if path.name == "scanner_scenario_producers.py":
                continue
            source = path.read_text(encoding="utf-8")
            for name in ("produce_scenario_plans", "produce_scenario_plans_from_zones"):
                if name in source:
                    offenders.append(f"{path.relative_to(root)}: {name}")
    assert offenders == [], f"live modules must not call the legacy producers: {offenders}"


def test_the_live_planner_asks_only_the_coordinator_for_a_plan():
    """``plan_for_candidate`` never reaches the protective-zone fallback."""

    import core.scanner_scenario_producers as producers

    source = Path(producers.__file__).read_text(encoding="utf-8")
    live = source.split("def plan_for_candidate", 1)[1].split(
        "\ndef ", 1
    )[0]
    assert "canonical=True" in live
    assert "_protective_zone" not in live
    assert "_SOURCE_TECHNICAL" not in live

    # And the historical fallback really is a different function, still present
    # for the reader that owns it.
    assert "_protective_zone" in source
    assert "HISTORICAL reader" in source


@pytest.mark.parametrize("name", _ALL_CASES)
def test_a_canonical_result_never_offers_a_legacy_zone(name: str):
    """The finalizer leaves the legacy ``selected_zone`` seam empty."""

    analysis = _live_analysis(_case(name))
    for side in ("buy", "sell"):
        from core.smc_consumer_contract import build_smc_consumer_from_canonical_result

        contract = build_smc_consumer_from_canonical_result(
            result=analysis["canonical_smc"]
        )
        assert selected_zone_for_side(contract, side) is None


def test_no_canonical_state_is_upgraded_to_a_plan():
    """Only an ``evaluated`` side carries a plan; nothing else is promoted."""

    from core.scanner_scenario_producers import plans_from_canonical_selection

    for name in _ALL_CASES:
        analysis = _live_analysis(_case(name))
        plans = plans_from_canonical_selection(analysis["canonical_smc"])
        for side in ("buy", "sell"):
            selection = smc_selection_of(analysis["canonical_smc"].side(side))
            if selection.state == SELECTION_STATE_EVALUATED:
                assert selection.plan_available is True
                assert plans[side] is not None, f"{name}/{side} lost its plan"
            else:
                assert plans[side] is None, f"{name}/{side} was upgraded to a plan"
                assert selection.plan_available is False


def test_the_reader_only_producer_cannot_invent_a_zone_from_a_canonical_result():
    """Even called directly, the historical producer finds no zone to fall back on."""

    from core.scanner_scenario_producers import produce_scenario_plans

    for name in _ALL_CASES:
        analysis = _live_analysis(_case(name))
        legacy = produce_scenario_plans(
            dict(analysis["technical"]), analysis["canonical_smc"], min_rr=None
        )
        for side in ("buy", "sell"):
            assert legacy[side] is None, f"{name}/{side} produced a fallback plan"


# ---------------------------------------------------------------------------
# The gates still block a real canonical plan
# ---------------------------------------------------------------------------


def test_a_real_canonical_plan_does_not_make_the_candidate_ready():
    """The scenario gate passes, and the other gates still block."""

    pair = _zoned_pair()
    composition = pair.composition
    assert composition.scenario.plan is not None
    assert composition.scenario.gate.status == "PASS"
    assert pair.candidate is not None
    assert pair.candidate.candidate_status != "READY_NOW"
    payload = pair.candidate.order_payload
    assert payload is None or payload.sends_real_order is False
    # The blocking signals come from the gates that own them, not from SMC.
    assert set(composition.decision.gate_codes) & {
        "GATE_ACCOUNT_DATA_MISSING",
        "GATE_PORTFOLIO_DATA_MISSING",
        "GATE_JOURNAL_DATA_MISSING",
    }


def test_the_safety_gate_still_blocks_a_canonical_plan():
    pair = _zoned_pair(safety=_safety(terminal_connected=False))
    composition = pair.composition
    assert "SAFETY_MT5_STATE_UNKNOWN" in composition.decision.gate_codes
    assert composition.scenario.plan is not None, "the plan itself is not the gate"
    assert pair.candidate is not None
    assert pair.candidate.candidate_status != "READY_NOW"


def test_the_macro_gate_still_blocks_a_canonical_plan():
    pair = _zoned_pair(macro_raw_buy=None, macro_raw_sell=None, macro_confidence=None)
    composition = pair.composition
    assert "MACRO_DATA_UNAVAILABLE" in composition.decision.gate_codes
    assert pair.candidate is None or pair.candidate.candidate_status != "READY_NOW"


def test_the_scenario_gate_still_fails_closed_without_an_owner_rr_floor():
    """No order policy means no plan — the gate is never loosened to pass."""

    pair = _zoned_pair(order_policy=None)
    composition = pair.composition
    assert composition.scenario.plan is None
    assert composition.scenario.gate.status == "UNKNOWN"
    assert "GATE_SCENARIO_PLAN_MISSING" in composition.decision.gate_codes


def test_the_risk_gate_still_refuses_a_blocked_permission():
    """A blocked trade permission yields no scenario, plan or not."""

    from core.risk_engine import AnalysisInput, build_scenarios
    from tests.scanner_testkit import canonical_smc

    scored = _live_analysis(_case("sell_setup"))
    technical = dict(scored["technical"])
    scores = {
        "buy": {"signal_score": 80, "total": 80},
        "sell": {"signal_score": 80, "total": 80},
    }
    canonical = canonical_smc(buy_subtotal=12, sell_subtotal=12)
    preferred = {"buy": {"low": 1.0, "high": 1.1}, "sell": {"low": 1.0, "high": 1.1}}
    common = dict(
        h1_candles=[],
        preferred_zones=preferred,
        strict_preferred_zones=True,
        require_preferred_zones=False,
    )
    blocked = build_scenarios(
        AnalysisInput(
            symbol="XAUUSD",
            broker_symbol="XAUUSD",
            account_balance=10_000.0,
            risk_percent=1.0,
        ),
        technical,
        dict(scored["smc_snapshot"].smc or {}),
        scores,
        {"status": "blocked"},
        **common,
    )
    assert blocked == []
    assert canonical is not None


def test_the_structural_conflict_gate_still_caps_to_watch_only():
    """An opposing confirmed H4 CHOCH keeps its WATCH_ONLY cap."""

    from core.trade_gate_engine import check_trade_gates

    from core.reason_codes import CHOCH_AGAINST_DIRECTION

    conflicted = check_trade_gates({"h4_confirmed_choch_against_direction": True})
    clear = check_trade_gates({"h4_confirmed_choch_against_direction": False})
    # The conflict adds its own code and caps the decision; without it the code
    # is absent.  The cap lowers eligibility, it does not block the gate.
    assert CHOCH_AGAINST_DIRECTION in conflicted["warning_codes"]
    assert CHOCH_AGAINST_DIRECTION not in clear["warning_codes"]
    assert conflicted["decision_cap"] == "WATCH_ONLY"
    assert conflicted["allowed"] is True


def test_the_analyze_gate_context_carries_the_structural_conflict_key():
    """The Analyze route still feeds the structural gate its owner input."""

    source = (
        Path(__file__).resolve().parent.parent / "core" / "analysis_pipeline.py"
    ).read_text(encoding="utf-8")
    assert "h4_confirmed_choch_against_direction" in source
    assert "WATCH_ONLY" in source


# ---------------------------------------------------------------------------
# Source-age freshness — characterization only (DEFERRED decision)
# ---------------------------------------------------------------------------


def test_the_only_freshness_owners_are_the_existing_slas():
    """Characterize the real freshness metadata; no new SLA is introduced."""

    from core import scanner_composition
    from core.market_safety_gate import AVAILABILITY_VALID, DataFreshnessSource

    assert scanner_composition.SNAPSHOT_MAX_AGE_SECONDS == 120
    assert scanner_composition.SNAPSHOT_MAX_FUTURE_SKEW_SECONDS == 30

    freshness = DataFreshnessSource(
        availability=AVAILABILITY_VALID,
        source="broker",
        checked_at=NOW,
        provenance={"feed": "mt5"},
        last_candle_time_utc=NOW - timedelta(minutes=15),
        last_tick_time_utc=NOW - timedelta(seconds=5),
    )
    # The broker tick is the preferred age reference; the candle is the
    # documented baseline/fallback.
    assert freshness.last_tick_time_utc is not None
    assert freshness.last_candle_time_utc is not None


def test_the_canonical_snapshot_carries_no_source_age_sla():
    """The DEFERRED gap, locked as a fact rather than guessed at.

    The canonical seam freezes the cutoff and its provenance, but nothing in it
    asserts how old the *source* data is; that decision (which owner and which
    threshold) is still open, so this test records the current contract instead
    of inventing a policy.
    """

    from core.smc_snapshot import SMC_SNAPSHOT_INPUT_VERSION, SmcSnapshotInput

    analysis = _live_analysis(_case("sell_setup"))
    snapshot = analysis["smc_snapshot"]
    assert isinstance(snapshot, SmcSnapshotInput)
    assert snapshot.contract_version == SMC_SNAPSHOT_INPUT_VERSION

    fields = set(snapshot.to_dict())
    for forbidden in ("max_age", "max_age_seconds", "source_age", "stale", "sla"):
        assert not any(forbidden in field for field in fields), forbidden

    # Freshness is asserted by the composition SLA over the capture time, which
    # is exactly what the readiness layer reads.
    from core.reason_codes import SNAPSHOT_FRESHNESS_UNKNOWN, SNAPSHOT_STALE

    assert SNAPSHOT_STALE and SNAPSHOT_FRESHNESS_UNKNOWN
