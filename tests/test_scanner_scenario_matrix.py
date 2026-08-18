"""Scanner — Mục 13 scenario matrix (Bước 11; target-only).

Locks the cross-gate decision ladder (Bước 07) as a *matrix*, independent of any
single module.  It drives each gate to a canonical status through the testkit's
real inputs (safety spread policy, macro conflict cap, scenario R:R, account
margin, portfolio limits, journal policy) and asserts the composed
``candidate_status`` matches a reference precedence model:

    DATA_UNAVAILABLE  <- freshness/technical absence only
    BLOCKED           <- any gate BLOCK, or any CRITICAL gate UNKNOWN
    WATCH_ZONE        <- any CAUTION, or any non-critical gate UNKNOWN,
                         or an open/too-high score floor
    WAITING_CONFIRMATION <- every gate PASS and floors met

Precedence is strict: BLOCK > UNKNOWN > CAUTION > PASS.  A critical-gate
UNKNOWN is as hard as a BLOCK (missing safety/macro/account/portfolio data can
never confirm), while a non-critical UNKNOWN (scenario/journal) only downgrades
to WATCH_ZONE.

The reference model and the constructible gate-status combinations are both
declared explicitly here so the matrix is auditable.  No production threshold
is invented — every fixture uses the Bước 04–08 test policies.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from core.scanner_composition import (
    AccountState,
    JournalState,
    PortfolioState,
    ScenarioPlan,
    SideSnapshot,
)
from core.scanner_v4_models import (
    BLOCK,
    BLOCKED,
    BUY,
    CAUTION,
    DATA_UNAVAILABLE,
    PASS,
    SELL,
    UNKNOWN,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
)

from tests.scanner_testkit import (
    build_snapshot,
    canonical_smc,
    compose,
    macro_policy,
    options,
    safety_context,
    safety_policy,
    side_snapshot,
)

# These gates are read by the decision as *critical*: a UNKNOWN on any of them
# is BLOCK-equivalent (missing data that could have blocked auto-entry).
CRITICAL_GATES = frozenset({"market_safety", "macro", "account", "portfolio"})


def expected_decision(gate_statuses: dict[str, str]) -> str:
    """Reference Mục 07 ladder for a full gate-status row (module independent)."""
    if BLOCK in gate_statuses.values():
        return BLOCKED
    if any(gate_statuses.get(g) == UNKNOWN for g in CRITICAL_GATES):
        return BLOCKED
    noncritical_unknown = any(
        status == UNKNOWN for gate, status in gate_statuses.items()
        if gate not in CRITICAL_GATES
    )
    if CAUTION in gate_statuses.values() or noncritical_unknown:
        return WATCH_ZONE
    return WAITING_CONFIRMATION


def _observed_statuses(result) -> dict[str, str]:
    """Read the canonical per-gate statuses straight from a composition result."""
    statuses = {
        "market_safety": result.canonical.market_safety.status,
        "macro": result.canonical.macro_gate.status,
    }
    for gate in result.composition_gates:
        statuses[gate.name] = gate.status
    return statuses


def _strong_buy_side(*, plan: bool = True, poor_rr: bool = False) -> SideSnapshot:
    """A strong buy side (technical 76) with a configurable scenario plan."""
    if poor_rr:
        plan_obj = ScenarioPlan(BUY, 91.0, 90.0, 91.5, source="plan")  # R:R 0.5
    elif plan:
        plan_obj = ScenarioPlan(BUY, 91.0, 90.0, 94.0, source="plan")  # R:R 3
    else:
        plan_obj = None
    return SideSnapshot(
        technical_raws={"trend": 20, "momentum": 14, "location": 18},
        evidence_score=60,
        evidence_source="evidence_feed",
        execution_quality_score=70,
        execution_quality_source="exec_feed",
        scenario_plan=plan_obj,
    )


def _compose_with(gate_statuses: dict[str, str]):
    """Build a full composition that reaches exactly the requested gate statuses.

    Every gate starts PASS and is pushed to a target non-PASS status using the
    real input knobs.  Only constructible combinations are expected to be used
    (a policy-open UNKNOWN on portfolio and on journal share the options object,
    so those two UNKNOWNs are not combined together).
    """
    ctx = safety_context()
    safety = safety_policy()
    macro = macro_policy()
    opts = options()
    acct = AccountState(free_margin=10000.0, required_margin=500.0)
    port = PortfolioState(open_positions=2, exposure_ratio=0.8)
    jour = JournalState(consecutive_losses=1, recent_drawdown_ratio=0.2)
    snap: dict = {}

    for gate, status in gate_statuses.items():
        if gate == "market_safety":
            if status == BLOCK:
                ctx = safety_context(spread_points=40.0)
                safety = safety_policy(spread_threshold_by_symbol={"XAUUSD": 10})
            elif status == UNKNOWN:
                safety = safety_policy(volatility_calibrated=False)
            elif status != PASS:
                raise AssertionError(f"market_safety status {status!r} not reachable")
        elif gate == "macro":
            if status in {BLOCK, CAUTION, UNKNOWN}:
                snap.update(macro_raw_buy=10, macro_raw_sell=20)  # buy conflict
                if status == BLOCK:
                    macro = macro_policy(conflict_cap="BLOCK")
                elif status == CAUTION:
                    # A real decision cap (not BLOCK) gates the conflict CAUTION.
                    macro = macro_policy(conflict_cap="WATCH_ZONE")
                # UNKNOWN: conflict_cap stays None -> MACRO_CONFLICT_CAP_UNSET
            elif status != PASS:
                raise AssertionError(f"macro status {status!r} not reachable")
        elif gate == "scenario":
            if status == BLOCK:
                snap["buy_side"] = _strong_buy_side(poor_rr=True)
            elif status == UNKNOWN:
                snap["buy_side"] = _strong_buy_side(plan=False)
            elif status != PASS:
                raise AssertionError(f"scenario status {status!r} not reachable")
        elif gate == "account":
            if status == BLOCK:
                acct = AccountState(free_margin=100.0, required_margin=500.0)
            elif status == UNKNOWN:
                acct = AccountState(free_margin=None, required_margin=None)
            elif status != PASS:
                raise AssertionError(f"account status {status!r} not reachable")
        elif gate == "portfolio":
            if status == BLOCK:
                port = PortfolioState(open_positions=6, exposure_ratio=0.5)
            elif status == UNKNOWN:
                opts = options(portfolio_position_limit=None, portfolio_exposure_limit=None)
            elif status != PASS:
                raise AssertionError(f"portfolio status {status!r} not reachable")
        elif gate == "journal":
            if status == BLOCK:
                jour = JournalState(consecutive_losses=5, recent_drawdown_ratio=0.1)
            elif status == CAUTION:
                jour = JournalState(consecutive_losses=1, recent_drawdown_ratio=0.9)
            elif status == UNKNOWN:
                opts = options(journal_max_consecutive_losses=None, journal_drawdown_caution_ratio=None)
            elif status != PASS:
                raise AssertionError(f"journal status {status!r} not reachable")
        else:
            raise AssertionError(f"unknown gate {gate!r}")

    snapshot = build_snapshot(
        **snap,
        safety=ctx,
        account=acct,
        portfolio=port,
        journal=jour,
    )
    return compose(snapshot, safety=safety, macro=macro, opts=opts)


# ---------------------------------------------------------------------------
# Reachability: every candidate_status is reachable through real inputs
# ---------------------------------------------------------------------------

class TestStatusReachability:
    def test_waiting_confirmation_default(self) -> None:
        result = compose(build_snapshot())
        assert result.decision.candidate_status == WAITING_CONFIRMATION
        assert all(status == PASS for status in _observed_statuses(result).values())

    def test_watch_zone_via_noncritical_unknown(self) -> None:
        # Journal policy OPEN -> journal UNKNOWN (non-critical) -> WATCH_ZONE.
        result = _compose_with({"journal": UNKNOWN})
        assert result.decision.candidate_status == WATCH_ZONE
        journal = [g for g in result.composition_gates if g.name == "journal"][0]
        assert journal.status == UNKNOWN

    def test_blocked_via_macro_block(self) -> None:
        result = _compose_with({"macro": BLOCK})
        assert result.decision.candidate_status == BLOCKED
        assert result.decision.block_codes

    def test_data_unavailable_via_future_skew(self) -> None:
        snapshot = build_snapshot(captured_at=snapshot_captured_in_future())
        result = compose(snapshot)
        assert result.decision.candidate_status == DATA_UNAVAILABLE
        assert result.decision.selected_side is None


def snapshot_captured_in_future():
    from datetime import timezone
    from tests.scanner_testkit import NOW

    return NOW + timedelta(minutes=5)


# ---------------------------------------------------------------------------
# Single-gate matrix: each reachable status correctly classified
# ---------------------------------------------------------------------------

SINGLE_GATE_CASES = [
    ({"market_safety": BLOCK}, BLOCKED),
    ({"market_safety": UNKNOWN}, BLOCKED),
    ({"macro": BLOCK}, BLOCKED),
    ({"macro": UNKNOWN}, BLOCKED),
    ({"macro": CAUTION}, WATCH_ZONE),
    ({"scenario": BLOCK}, BLOCKED),
    ({"scenario": UNKNOWN}, WATCH_ZONE),
    ({"account": BLOCK}, BLOCKED),
    ({"account": UNKNOWN}, BLOCKED),
    ({"portfolio": BLOCK}, BLOCKED),
    ({"portfolio": UNKNOWN}, BLOCKED),
    ({"journal": BLOCK}, BLOCKED),
    ({"journal": UNKNOWN}, WATCH_ZONE),
    ({"journal": CAUTION}, WATCH_ZONE),
]


class TestSingleGateClassification:
    @pytest.mark.parametrize("statuses,expected", SINGLE_GATE_CASES)
    def test_single_gate(self, statuses, expected) -> None:
        result = _compose_with(statuses)
        observed = _observed_statuses(result)
        # Every non-PASS declared gate must actually reach its requested status.
        for gate, status in statuses.items():
            if status == BLOCK or status == CAUTION or status == UNKNOWN:
                assert observed[gate] == status, f"{gate} did not reach {status}: {observed}"
        assert result.decision.candidate_status == expected
        assert expected_decision(observed) == expected


# ---------------------------------------------------------------------------
# Pairwise / cross-coupling precedence (BLOCK > UNKNOWN > CAUTION > PASS)
# ---------------------------------------------------------------------------

MULTI_GATE_CASES = [
    # BLOCK dominates any CAUTION / non-critical UNKNOWN.
    ({"macro": BLOCK, "journal": CAUTION}, BLOCKED),
    ({"market_safety": BLOCK, "journal": UNKNOWN}, BLOCKED),
    ({"portfolio": BLOCK, "scenario": UNKNOWN}, BLOCKED),
    # Critical UNKNOWN is BLOCK-equivalent, dominating CAUTION.
    ({"macro": UNKNOWN, "journal": CAUTION}, BLOCKED),
    ({"account": UNKNOWN, "journal": CAUTION}, BLOCKED),
    ({"market_safety": BLOCK, "macro": CAUTION, "journal": CAUTION}, BLOCKED),
    # CAUTION / non-critical UNKNOWN coexist -> WATCH_ZONE (never looser).
    ({"macro": CAUTION, "journal": CAUTION}, WATCH_ZONE),
    ({"journal": CAUTION, "scenario": UNKNOWN}, WATCH_ZONE),
    ({"journal": UNKNOWN, "scenario": UNKNOWN}, WATCH_ZONE),
    ({"macro": CAUTION, "journal": UNKNOWN, "scenario": UNKNOWN}, WATCH_ZONE),
    # A CAUTION plus an otherwise clean row stays WATCH_ZONE, not WAITING.
    ({"journal": CAUTION}, WATCH_ZONE),
    # Two independent BLOCKs still BLOCKED (no double-counting).
    ({"macro": BLOCK, "market_safety": BLOCK}, BLOCKED),
]


class TestCrossGatePrecedence:
    @pytest.mark.parametrize("statuses,expected", MULTI_GATE_CASES)
    def test_multi_gate(self, statuses, expected) -> None:
        result = _compose_with(statuses)
        observed = _observed_statuses(result)
        assert expected_decision(observed) == expected
        assert result.decision.candidate_status == expected

    def test_block_outranks_unknown_outranks_caution(self) -> None:
        # Explicit ordering check with a single row carrying all four severity
        # levels across different gates.
        cases = [
            ({"macro": CAUTION, "scenario": UNKNOWN}, WATCH_ZONE),
            ({"macro": UNKNOWN, "journal": CAUTION}, BLOCKED),
            ({"market_safety": BLOCK, "macro": UNKNOWN, "journal": CAUTION}, BLOCKED),
        ]
        for statuses, expected in cases:
            result = _compose_with(statuses)
            assert result.decision.candidate_status == expected


# ---------------------------------------------------------------------------
# Score floors: strong score never reaches WAITING when floors are unmet; the
# gate list must stay identical once a gate BLOCKs (score never loosens it).
# ---------------------------------------------------------------------------

class TestScoreFloorsAndGateIsolation:
    def test_strong_score_with_open_floor_stays_watch_zone(self) -> None:
        # All gates PASS but floors are open -> can never certify a confirmation.
        result = compose(build_snapshot(), opts=options(technical_floor=None, setup_floor=None))
        assert result.decision.candidate_status == WATCH_ZONE

    def test_strong_score_below_floor_stays_watch_zone(self) -> None:
        # Selected buy technical is 76; raise the floor above it.
        result = compose(build_snapshot(), opts=options(technical_floor=80))
        assert result.decision.candidate_status == WATCH_ZONE

    def test_gate_block_does_not_mutate_scores(self) -> None:
        # BLOCKing macro must leave technical/setup/gap exactly as PASSed.
        base = compose(build_snapshot())
        blocked = _compose_with({"macro": BLOCK})
        assert blocked.decision.candidate_status == BLOCKED
        assert (
            blocked.canonical.side_scores[0].technical_signal_score
            == base.canonical.side_scores[0].technical_signal_score
        )
        assert blocked.canonical.side_scores[0].setup_score == base.canonical.side_scores[0].setup_score
        assert blocked.decision.score_gap == base.decision.score_gap


# ---------------------------------------------------------------------------
# Eligibility-axis matrix: technical floor, Evidence/Execution presence, side.
#
# Completes the remaining acceptance rows of the Bước 11 (Mục 13) matrix that are
# reachable through real decision inputs.  No production threshold is invented —
# floors are the Bước 04–08 test floors, and a MISSING Evidence/Execution maps to
# the single fail-safe neutral-50 fallback (``fallback_neutral_50``), because the
# model has no separate "rejected" state distinct from absence.
# ---------------------------------------------------------------------------


TECHNICAL_AXIS_CASES = [
    # technical floor unset/missing -> cannot certify -> WATCH_ZONE
    (dict(technical_floor=None), WATCH_ZONE),
    # technical BELOW floor (strong buy tech 76 < floor 80) -> WATCH_ZONE
    (dict(technical_floor=80), WATCH_ZONE),
    # technical AT floor (76 == 76) -> floor passes
    (dict(technical_floor=76), WAITING_CONFIRMATION),
    # technical ABOVE floor (76 > 40) -> floor passes
    (dict(technical_floor=40), WAITING_CONFIRMATION),
]


class TestTechnicalAxisMatrix:
    @pytest.mark.parametrize("overrides,expected", TECHNICAL_AXIS_CASES)
    def test_technical_floor_axis(self, overrides, expected) -> None:
        result = compose(build_snapshot(), opts=options(**overrides))
        assert result.decision.candidate_status == expected


def _strong_buy(evidence: int | None, execution: int | None):
    return side_snapshot(
        BUY, trend=20, momentum=14, location=18,
        evidence=evidence, execution=execution,
    )


EVIDENCE_EXECUTION_AXIS_CASES = [
    # both present (valid/valid) -> setup 72, passes
    (60, 70, {}, WAITING_CONFIRMATION),
    # Evidence missing -> neutral-50 fallback, setup 70, passes floor 35
    (None, 70, {}, WAITING_CONFIRMATION),
    # Execution missing -> neutral-50 fallback, setup 69, passes floor 35
    (60, None, {}, WAITING_CONFIRMATION),
    # Evidence fallback pushes setup (70) below a raised floor (72) -> WATCH_ZONE
    (None, 70, {"setup_floor": 72}, WATCH_ZONE),
    # Execution fallback pushes setup (69) below a raised floor (70) -> WATCH_ZONE
    (60, None, {"setup_floor": 70}, WATCH_ZONE),
]


class TestEvidenceExecutionAxisMatrix:
    @pytest.mark.parametrize(
        "evidence,execution,overrides,expected", EVIDENCE_EXECUTION_AXIS_CASES
    )
    def test_evidence_execution_axis(self, evidence, execution, overrides, expected) -> None:
        result = compose(
            build_snapshot(buy_side=_strong_buy(evidence, execution)),
            opts=options(**overrides),
        )
        assert result.decision.candidate_status == expected

    def test_missing_evidence_uses_neutral_50_not_technical(self) -> None:
        result = compose(build_snapshot(buy_side=_strong_buy(None, 70)))
        side = result.canonical.side_scores[0]
        assert side.evidence_source == "fallback_neutral_50"
        assert side.setup_score == 70  # 0.65*76 + 0.20*50 + 0.15*70

    def test_missing_execution_uses_neutral_50_not_technical(self) -> None:
        result = compose(build_snapshot(buy_side=_strong_buy(60, None)))
        side = result.canonical.side_scores[0]
        assert side.execution_quality_source == "fallback_neutral_50"
        assert side.setup_score == 69  # 0.65*76 + 0.20*60 + 0.15*50


class TestSideAxisMatrix:
    def test_buy_dominant_side_is_selected_at_default(self) -> None:
        result = compose(build_snapshot())
        assert result.decision.selected_side == BUY
        assert result.decision.candidate_status == WAITING_CONFIRMATION

    def test_sell_dominant_side_is_selected_when_macro_aligned(self) -> None:
        # Flip SMC + macro to the sell side so the selected tail is clean.
        sell_strong = side_snapshot(SELL, trend=20, momentum=14, location=18, evidence=60, execution=70)
        buy_weak = side_snapshot(BUY, trend=8, momentum=5, location=6, evidence=60, execution=70)
        result = compose(build_snapshot(
            buy_side=buy_weak,
            sell_side=sell_strong,
            smc=canonical_smc(buy_subtotal=12, sell_subtotal=7),
            macro_raw_buy=14, macro_raw_sell=20,  # sell-aligned macro
        ))
        assert result.decision.selected_side == SELL
        assert result.decision.candidate_status == WAITING_CONFIRMATION
        buy, sell = result.canonical.side_scores
        assert sell.side == SELL and buy.side == BUY
        assert sell.setup_score > buy.setup_score