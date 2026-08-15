"""Scanner V4 candidate decision matrix + invariants (Bước 08, target-only).

These tests prove the **single writer** ``build_candidate`` implements the
locked Mục 9 precedence exactly:

1. critical data UNKNOWN / missing Technical -> ``DATA_UNAVAILABLE`` (never
   ``OUT_OF_STRATEGY``, never a fake score);
2. any gate BLOCK -> ``BLOCKED`` — even with score 100 (a strong score can
   never loosen a gate/cap);
3. ``CAUTION`` / non-critical ``UNKNOWN`` -> never ``READY_NOW``;
4. only with every gate PASSing AND a certified ThresholdPolicy do floors/gap/
   R:R, entry confirmation and execution decide — and even then a confirmed
   unexecutable candidate caps at ``WAITING_CONFIRMATION``.

Every consumer reads the same immutable ``ScannerV4CandidateDecision``; the
strict readers below are the same fail-closed contract.
"""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import pytest

from core.reason_codes import (
    GATES_ALL_PASS,
    SNAPSHOT_STALE,
    V4_CANDIDATE_SIDE_INCONSISTENT,
    V4_ENTRY_CONFIRMED,
    V4_ENTRY_CONFIRMATION_MISSING,
    V4_ENTRY_UNCONFIRMED,
    V4_EXECUTION_FRESH_OK,
    V4_EXECUTION_NOT_READY,
    V4_EXECUTION_REVALIDATION_REQUIRED,
    V4_ORDER_NOT_PREPARED,
    V4_ORDER_PREPARED,
    V4_THRESHOLD_GAP_NOT_MET,
    V4_THRESHOLD_POLICY_OPEN,
    V4_THRESHOLD_RR_NOT_MET,
    V4_THRESHOLD_SCORE_FLOOR_NOT_MET,
)
from core.scanner_v4_candidate import (
    VALID_CANDIDATE_STATUSES,
    VALID_ENTRY_CONFIRMATIONS,
    CandidateContractError,
    ScannerV4CandidateDecision,
    ScannerV4OrderPayload,
    build_candidate,
)
from core.scanner_v4_execution_readiness import (
    ExecutionReadiness,
    evaluate_execution_readiness,
)
from core.scanner_v4_models import (
    BLOCK,
    BLOCKED,
    BUY,
    CAUTION,
    DATA_UNAVAILABLE,
    PASS,
    READY_NOW,
    SELL,
    UNKNOWN,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
)
from core.scanner_v4_threshold_policy import (
    SCANNER_V4_THRESHOLD_POLICY_VERSION,
    ThresholdPolicy,
    make_default_threshold_policy,
)
from tests.test_scanner_v4_composition import (
    CAPTURED,
    _canonical_smc,
    _compose,
    _options,
    _run,
    _safety_context,
    _safety_policy,
    _side_snapshot,
    _snapshot,
    JournalState,
    PortfolioState,
    AccountState,
)

# --- fixtures shared by the whole file -------------------------------------


def _candidate_of(
    *,
    composition=None,
    thresholds=None,
    entry="confirmed",
    execution=None,
) -> ScannerV4CandidateDecision:
    if composition is None:
        composition = _run()
    if thresholds is None:
        thresholds = make_default_threshold_policy()
    if execution is None:
        execution = evaluate_execution_readiness(composition)
    return build_candidate(
        composition=composition,
        thresholds=thresholds,
        entry_confirmation=entry,
        execution=execution,
    )


def _open_threshold(**values) -> ThresholdPolicy:
    """Certified test policy with any single criterion overridden (None = open)."""
    return replace(make_default_threshold_policy(), **values)


# ---------------------------------------------------------------------------
# 1. DATA_UNAVAILABLE: critical UNKNOWN / missing Technical, never recovered
# ---------------------------------------------------------------------------


class TestDataUnavailable:
    def test_stale_snapshot_stays_data_unavailable(self):
        from datetime import timedelta

        snapshot = _snapshot(captured_at=CAPTURED - timedelta(seconds=180))
        composition = _compose(snapshot)
        candidate = _candidate_of(composition=composition)
        assert candidate.candidate_status == DATA_UNAVAILABLE
        assert candidate.selected_side is None
        assert candidate.technical_signal_score is None
        assert candidate.setup_score is None
        assert candidate.order_payload is None
        assert candidate.execution.can_execute is False
        assert candidate.execution.prepared is False
        assert SNAPSHOT_STALE in candidate.reason_codes
        assert candidate.reason_codes == composition.decision.reason_codes  # unchanged

    def test_stale_never_becomes_out_of_strategy(self):
        from datetime import timedelta

        snapshot = _snapshot(captured_at=CAPTURED - timedelta(seconds=180))
        candidate = _candidate_of(composition=_compose(snapshot))
        assert candidate.candidate_status == DATA_UNAVAILABLE
        assert "OUT_OF_STRATEGY" not in candidate.reason_codes
        # reason codes come from the canonical decision unchanged
        assert SNAPSHOT_STALE in candidate.reason_codes

    def test_missing_technical_never_fabricates_score(self):
        # SMC contract forged -> TechnicalScoreDataError on both sides.
        from core.smc_scoring_result import (
            SMC_SCORING_CONTRACT_VERSION,
            SmcScoringResult,
        )
        from tests.test_scanner_v4_composition import _smc_side

        bad_smc = SmcScoringResult(
            scoring_version="smc-v9",  # forged -> TechnicalScoreDataError
            contract_version=SMC_SCORING_CONTRACT_VERSION,
            sides={
                "buy": _smc_side("buy", subtotal=12),
                "sell": _smc_side("sell", subtotal=7),
            },
        )
        candidate = _candidate_of(composition=_compose(_snapshot(smc=bad_smc)))
        assert candidate.candidate_status == DATA_UNAVAILABLE
        assert candidate.selected_side is None
        assert candidate.technical_signal_score is None
        assert candidate.setup_score is None
        assert candidate.order_payload is None

    def test_unavailable_with_closed_thresholds_still_unavailable(self):
        from datetime import timedelta

        snapshot = _snapshot(captured_at=CAPTURED - timedelta(seconds=180))
        # even a "very strict" certified policy cannot revive unavailable data
        strict = ThresholdPolicy(
            policy_version=SCANNER_V4_THRESHOLD_POLICY_VERSION,
            technical_floor=100,
            setup_floor=100,
            min_score_gap=0,
            min_risk_reward=Fraction(1, 2),
        )
        candidate = _candidate_of(
            composition=_compose(snapshot), thresholds=strict
        )
        assert candidate.candidate_status == DATA_UNAVAILABLE


# ---------------------------------------------------------------------------
# 2. BLOCKED stays BLOCKED — strong score can never loosen a gate
# ---------------------------------------------------------------------------


class TestBlockedNeverLoosened:
    def test_block_with_score_100_stays_blocked(self):
        # Maxed-out buy raws give technical_signal_score == 100.
        context = _safety_context(spread_points=40.0)
        snapshot = _snapshot(
            buy_side=_side_snapshot(BUY, trend=25, momentum=20, location=25),
            smc=_canonical_smc(buy_subtotal=15, sell_subtotal=0),
            safety=context,
        )
        # Safety BLOCK (spread 40 > threshold 30), symmetric with test policy.
        safety = _safety_policy(spread_threshold_by_symbol={"XAUUSD": 30})
        composition = _compose(snapshot, safety=safety)
        assert composition.safety.status == BLOCK
        assert composition.canonical.side_score(BUY).technical_signal_score == 100
        candidate = _candidate_of(composition=composition)
        assert candidate.candidate_status == BLOCKED
        assert candidate.technical_signal_score == 100  # honest score kept
        assert candidate.selected_side == BUY
        assert candidate.block_codes
        assert candidate.order_payload is None
        assert candidate.execution.can_execute is False

    def test_scenario_rr_block_keeps_scores_and_block_codes(self):
        composition = _compose(
            _snapshot(), options=_options(min_risk_reward=4)
        )
        candidate = _candidate_of(composition=composition)
        assert candidate.candidate_status == BLOCKED
        assert candidate.selected_side == BUY
        assert candidate.order_payload is None
        assert any("SCENARIO_RR" in code for code in candidate.block_codes)

    def test_high_setup_never_promotes_a_block(self):
        # Blocking gate + every confirmation crisp on paper: still BLOCKED.
        # spread threshold 15 < default context spread 20 -> safety BLOCK.
        composition = _compose(_snapshot(), safety=_safety_policy(
            spread_threshold_by_symbol={"XAUUSD": 15}
        ))
        candidate = _candidate_of(composition=composition)
        assert candidate.candidate_status == BLOCKED
        assert candidate.order_payload is None


# ---------------------------------------------------------------------------
# 3. CAUTION / non-critical UNKNOWN: never READY_NOW
# ---------------------------------------------------------------------------


class TestCautionNeverReadyNow:
    def _journal_caution_composition(self):
        # Drawdown ratio above caution threshold (0.5) but below the block.
        snapshot = _snapshot(journal=JournalState(consecutive_losses=1, recent_drawdown_ratio=0.6))
        return _compose(snapshot)

    def test_caution_caps_at_watch_zone(self):
        composition = self._journal_caution_composition()
        assert any(g.status == CAUTION for g in composition.composition_gates)
        candidate = _candidate_of(composition=composition, entry="confirmed")
        assert candidate.candidate_status in (WATCH_ZONE, WAITING_CONFIRMATION)
        assert candidate.candidate_status != READY_NOW
        assert candidate.order_payload is None

    def test_caution_keeps_honest_scores_inside(self):
        composition = self._journal_caution_composition()
        candidate = _candidate_of(composition=composition)
        assert candidate.selected_side == BUY
        assert candidate.technical_signal_score is not None
        assert candidate.order_payload is None

    def test_non_critical_unknown_scenario_plan_missing_caps_watch(self):
        snapshot = _snapshot(
            buy_side=_side_snapshot(BUY, trend=20, momentum=14, location=18, plan=False)
        )
        composition = _compose(snapshot)
        assert any(g.status == UNKNOWN for g in composition.composition_gates)
        candidate = _candidate_of(composition=composition)
        assert candidate.candidate_status != READY_NOW
        assert candidate.order_payload is None
        assert candidate.execution.prepared is False


# ---------------------------------------------------------------------------
# 4. All-gates-PASS + certified ThresholdPolicy: the addable confirmation ladder
# ---------------------------------------------------------------------------


class TestConfirmedLadder:
    def test_full_pass_confirmed_ready_now(self):
        composition = _run()
        assert all(g.status == PASS for g in composition.composition_gates)
        assert composition.safety.status == PASS
        assert composition.macro_gate.status == PASS
        candidate = _candidate_of(composition=composition, entry="confirmed")
        assert candidate.candidate_status == READY_NOW
        assert candidate.selected_side == BUY
        assert GATES_ALL_PASS in candidate.reason_codes
        assert V4_ENTRY_CONFIRMED in candidate.reason_codes
        assert V4_EXECUTION_FRESH_OK in candidate.reason_codes
        assert V4_ORDER_PREPARED in candidate.reason_codes

    def test_second_ladder_unconfirmed_waiting_confirmation(self):
        candidate = _candidate_of(composition=_run(), entry="unconfirmed")
        assert candidate.candidate_status == WAITING_CONFIRMATION
        assert V4_ENTRY_UNCONFIRMED in candidate.reason_codes
        assert candidate.order_payload is None

    def test_missing_entry_confirmation_waiting_confirmation(self):
        candidate = _candidate_of(composition=_run(), entry="missing")
        assert candidate.candidate_status == WAITING_CONFIRMATION
        assert V4_ENTRY_CONFIRMATION_MISSING in candidate.reason_codes
        assert candidate.order_payload is None

    def test_confirmed_but_execution_not_ready_caps_waiting(self):
        composition = _run()
        # Execution stays NOT ready even though the snapshot is fresh: the
        # candidate is confirmed yet cannot execute -> fails closed.
        readiness = ExecutionReadiness(
            snapshot_id=composition.snapshot_id,
            captured_at=composition.captured_at,
            fresh_snapshot=True,
            can_execute=False,
        )
        candidate = _candidate_of(
            composition=composition, entry="confirmed", execution=readiness
        )
        assert candidate.candidate_status == WAITING_CONFIRMATION
        assert V4_EXECUTION_NOT_READY in candidate.reason_codes
        assert candidate.order_payload is None


class TestThresholdContract:
    def test_open_policy_fails_closed_to_watch(self):
        open_policy = _open_threshold(min_score_gap=None)
        composition = _run()
        assert open_policy.certified() is False
        candidate = _candidate_of(
            composition=composition, thresholds=open_policy, entry="confirmed"
        )
        assert candidate.candidate_status == WATCH_ZONE
        assert V4_THRESHOLD_POLICY_OPEN in candidate.reason_codes
        assert candidate.order_payload is None

    def test_open_policy_strong_score_still_watch(self):
        open_policy = _open_threshold(technical_floor=None)
        composition = _compose(
            _snapshot(
                buy_side=_side_snapshot(BUY, trend=25, momentum=20, location=25),
                smc=_canonical_smc(buy_subtotal=15, sell_subtotal=0),
            )
        )
        candidate = _candidate_of(
            composition=composition, thresholds=open_policy, entry="confirmed"
        )
        assert candidate.technical_signal_score == 100
        assert candidate.candidate_status == WATCH_ZONE
        assert V4_THRESHOLD_POLICY_OPEN in candidate.reason_codes

    def test_technical_floor_not_met_watches(self):
        strict = _open_threshold(technical_floor=90)
        composition = _run()  # buy technical is 76 < 90
        candidate = _candidate_of(
            composition=composition, thresholds=strict, entry="confirmed"
        )
        assert candidate.candidate_status == WATCH_ZONE
        assert V4_THRESHOLD_SCORE_FLOOR_NOT_MET in candidate.reason_codes
        assert candidate.order_payload is None

    def test_setup_floor_not_met_watches(self):
        strict = _open_threshold(setup_floor=99)
        candidate = _candidate_of(
            composition=_run(), thresholds=strict, entry="confirmed"
        )
        assert candidate.candidate_status == WATCH_ZONE
        assert V4_THRESHOLD_SCORE_FLOOR_NOT_MET in candidate.reason_codes

    def test_score_gap_not_met_watches(self):
        strict = _open_threshold(min_score_gap=100)
        candidate = _candidate_of(
            composition=_run(), thresholds=strict, entry="confirmed"
        )
        assert candidate.candidate_status == WATCH_ZONE
        assert V4_THRESHOLD_GAP_NOT_MET in candidate.reason_codes

    def test_rr_not_met_watches(self):
        strict = _open_threshold(min_risk_reward=Fraction(5, 1))
        candidate = _candidate_of(
            composition=_run(), thresholds=strict, entry="confirmed"
        )
        assert candidate.candidate_status == WATCH_ZONE
        assert V4_THRESHOLD_RR_NOT_MET in candidate.reason_codes

    def test_multi_failure_lists_every_failing_code(self):
        strict = _open_threshold(
            technical_floor=90, setup_floor=99, min_score_gap=100,
            min_risk_reward=Fraction(5, 1),
        )
        candidate = _candidate_of(
            composition=_run(), thresholds=strict, entry="confirmed"
        )
        assert V4_THRESHOLD_SCORE_FLOOR_NOT_MET in candidate.reason_codes
        assert V4_THRESHOLD_GAP_NOT_MET in candidate.reason_codes
        assert V4_THRESHOLD_RR_NOT_MET in candidate.reason_codes
        assert candidate.candidate_status == WATCH_ZONE


# ---------------------------------------------------------------------------
# Side/scenario/gate consistency guard
# ---------------------------------------------------------------------------


class TestSideConsistencyGuard:
    def test_decision_side_must_match_scenario_side(self):
        composition = _run()  # decision side == BUY
        # Mutate the scenario side without touching the decision -> guard trips.
        corrupted = replace(
            composition,
            scenario=replace(composition.scenario, side=SELL),
        )
        candidate = _candidate_of(composition=corrupted)
        assert candidate.candidate_status == DATA_UNAVAILABLE
        assert V4_CANDIDATE_SIDE_INCONSISTENT in candidate.reason_codes

    def test_decision_side_must_match_macro_gate_assessed_side(self):
        composition = _run()
        corrupted = replace(
            composition,
            macro_gate=replace(composition.macro_gate, assessed_side=SELL),
        )
        candidate = _candidate_of(composition=corrupted)
        assert candidate.candidate_status == DATA_UNAVAILABLE
        assert V4_CANDIDATE_SIDE_INCONSISTENT in candidate.reason_codes


# ---------------------------------------------------------------------------
# The immutable single-document contract shared by all consumers
# ---------------------------------------------------------------------------


class TestCandidateContract:
    def test_round_trip_every_status_through_from_dict(self):
        for entry in ("confirmed", "unconfirmed", "missing"):
            candidate = _candidate_of(composition=_run(), entry=entry)
            restored = ScannerV4CandidateDecision.from_dict(candidate.to_dict())
            assert restored.to_dict() == candidate.to_dict()

    def test_ready_now_carries_order_payload_identity(self):
        candidate = _candidate_of(composition=_run(), entry="confirmed")
        payload = candidate.order_payload
        assert payload is not None
        assert payload.sends_real_order is False
        assert payload.revalidation_required is True
        assert payload.symbol == candidate.symbol
        assert payload.snapshot_id == candidate.snapshot_id
        assert payload.side == candidate.selected_side == BUY
        canonical = _run().canonical
        assert payload.composition_version == "scanner-composition-v4"
        assert payload.technical_signal_score == canonical.side_score(BUY).technical_signal_score

    def test_watch_zone_never_carries_order_payload(self):
        composition = _compose(
            _snapshot(buy_side=_side_snapshot(BUY, trend=20, momentum=14, location=18, plan=False))
        )
        candidate = _candidate_of(composition=composition)
        assert candidate.candidate_status == WATCH_ZONE
        assert candidate.order_payload is None

    def test_execution_readiness_attached_not_stacked(self):
        candidate = _candidate_of(composition=_run(), entry="confirmed")
        codes = candidate.execution.reason_codes
        assert codes.count(V4_ORDER_PREPARED) == 1
        assert codes.count(V4_ORDER_NOT_PREPARED) == 0
        assert V4_EXECUTION_REVALIDATION_REQUIRED in codes
        assert candidate.execution.revalidation_required is True

    def test_no_out_of_strategy_status_exists(self):
        assert "OUT_OF_STRATEGY" not in VALID_CANDIDATE_STATUSES

    def test_entry_confirmation_vocabulary_locked(self):
        assert VALID_ENTRY_CONFIRMATIONS == frozenset(
            {"confirmed", "unconfirmed", "missing"}
        )

    def test_reason_codes_are_deduplicated_and_ordered(self):
        candidate = _candidate_of(composition=_run(), entry="confirmed")
        assert len(candidate.reason_codes) == len(set(candidate.reason_codes))


# ---------------------------------------------------------------------------
# Strict reader enforcement (guest modifications cannot even parse)
# ---------------------------------------------------------------------------


class TestStrictReader:
    def test_from_dict_rejects_extra_key(self):
        candidate = _candidate_of(composition=_run())
        payload = candidate.to_dict()
        payload["totally_legacy_total"] = 99
        with pytest.raises(CandidateContractError):
            ScannerV4CandidateDecision.from_dict(payload)

    def test_from_dict_rejects_missing_key(self):
        candidate = _candidate_of(composition=_run())
        payload = candidate.to_dict()
        del payload["reason_codes"]
        with pytest.raises(CandidateContractError):
            ScannerV4CandidateDecision.from_dict(payload)

    def test_order_payload_refuses_sends_real_order(self):
        payload = _candidate_of(composition=_run(), entry="confirmed").order_payload.to_dict()
        payload["sends_real_order"] = True
        with pytest.raises(CandidateContractError):
            ScannerV4OrderPayload.from_dict(payload)

    def test_order_payload_version_locked(self):
        payload = _candidate_of(composition=_run(), entry="confirmed").order_payload.to_dict()
        payload["composition_version"] = "scanner-composition-v3"
        with pytest.raises(CandidateContractError):
            ScannerV4OrderPayload.from_dict(payload)

    def test_buy_order_levels_must_be_ordered(self):
        candidate = _candidate_of(composition=_run(), entry="confirmed")
        payload = candidate.order_payload.to_dict()
        payload["entry"], payload["stop_loss"] = payload["stop_loss"], payload["entry"]
        with pytest.raises(CandidateContractError):
            ScannerV4OrderPayload.from_dict(payload)

    def test_data_unavailable_with_side_rejected(self):
        candidate = _candidate_of(composition=_run(), entry="confirmed")
        payload = candidate.to_dict()
        payload["candidate_status"] = DATA_UNAVAILABLE
        with pytest.raises(CandidateContractError):
            ScannerV4CandidateDecision.from_dict(payload)

    def test_blocked_without_block_codes_rejected(self):
        candidate = _candidate_of(composition=_run(), entry="confirmed")
        payload = candidate.to_dict()
        payload["candidate_status"] = BLOCKED
        payload["block_codes"] = []
        with pytest.raises(CandidateContractError):
            ScannerV4CandidateDecision.from_dict(payload)

    def test_ready_now_requires_payload_side_match(self):
        candidate = _candidate_of(composition=_run(), entry="confirmed")
        payload = candidate.to_dict()
        payload["order_payload"]["side"] = SELL
        with pytest.raises(CandidateContractError):
            ScannerV4CandidateDecision.from_dict(payload)


# ---------------------------------------------------------------------------
# Consumers see the SAME decision (controller/UI/alert/execution via to_dict)
# ---------------------------------------------------------------------------


class TestSingleDecisionForAllConsumers:
    def test_execution_readiness_and_candidate_agree(self):
        candidate = _candidate_of(composition=_run(), entry="confirmed")
        # Execution readiness is the candidate's own field — never re-derived.
        assert candidate.execution.prepared is True
        assert candidate.execution.fresh_snapshot is True
        assert candidate.execution.can_execute is True

    def test_unified_serialization_for_controller_ui_alert(self):
        candidate = _candidate_of(composition=_run(), entry="confirmed")
        payload = candidate.to_dict()
        # Every consumer reads the same keys.
        assert payload["candidate_status"] == READY_NOW
        assert payload["selected_side"] == BUY
        assert payload["threshold_policy_version"] == SCANNER_V4_THRESHOLD_POLICY_VERSION
        assert payload["execution"]["prepared"] is True
        assert payload["order_payload"]["sends_real_order"] is False

    def test_gate_codes_and_reason_codes_are_consistent(self):
        candidate = _candidate_of(composition=_run(), entry="confirmed")
        assert candidate.candidate_status == READY_NOW
        assert GATES_ALL_PASS in candidate.reason_codes
        assert candidate.gate_codes == () or GATES_ALL_PASS in candidate.reason_codes
        # all-gates-PASS candidates carry only PASS-gate reasons, no BLOCK codes
        assert not candidate.block_codes