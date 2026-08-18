"""Scanner — target-only integration chain (Bước 11).

Drives the single path end-to-end from one immutable composition through
every consumer (row → snapshot/engagement → router → candidate → ranking →
presenter), plus live/backtest parity and the fail-closed rejection paths.

Chain exercised (all target-only, nothing wired into the legacy runtime):

1. ``compose`` produces one canonical composition; live and backtest adapters
   are byte-parity-identical (only ``capture_source`` may differ);
2. the scanner **row** reads only the canonical artifact and carries identity +
   selected-side scores + gate statuses;
3. the **snapshot envelope** (full) round-trips through the strict reader and
   **replays** to the same candidate; compact envelopes are display-only
   (never replayable) and a legacy artifact is audit-only;
4. the **router** fail-closes on any shape/version/legacy doubt
   (``version_mismatch`` / structural reject) and otherwise routes to the single
   candidate writer;
5. the **candidate** only reaches ``READY_NOW`` when every gate PASSes, the
   certified thresholds are met AND entry is confirmed AND execution is fresh —
   otherwise it caps at ``WAITING_CONFIRMATION`` (execution revalidation);
6. **ranking** orders status-first (READY_NOW > WAITING > WATCH > BLOCKED >
   DATA_UNAVAILABLE) and never reads news/spread/macro;
7. the **presenter** renders exactly four scored components and never renders a
   gate UNKNOWN as PASS.

Every fixture uses the Bước 04–08 test policies; no production threshold is
invented here.
"""

from __future__ import annotations

from core.scanner_backtest_contract import verify_composition_parity
from core.scanner_candidate import build_candidate
from core.scanner_execution_readiness import (
    ExecutionReadiness,
    evaluate_execution_readiness,
)
from core.scanner_ranking import (
    grouped_scanner_candidates,
    rank_scanner_candidates,
)
from core.scanner_replay import (
    classify_snapshot_envelope,
    replay_snapshot_envelope,
)
from core.scanner_row import (
    scanner_row_from_composition,
    scanner_row_from_dict,
)
from core.scanner_snapshot import (
    MODE_COMPACT,
    MODE_FULL,
    build_snapshot_envelope,
)
from core.scanner_v4_strategy_router import (
    ROUTE_ROUTED,
    ROUTE_VERSION_MISMATCH,
    route_scanner,
)
from core.scanner_v4_models import (
    BLOCKED,
    BUY,
    DATA_UNAVAILABLE,
    READY_NOW,
    SELL,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
)
from ui.scanner_v4_presentation import (
    TECHNICAL_COMPONENT_NAMES,
    build_scanner_presentation,
)

from tests.scanner_testkit import (
    DEFAULT_THRESHOLD_POLICY,
    build_snapshot,
    compose,
    options,
)

# ---------------------------------------------------------------------------
# 1. Composition → parity (live == backtest for the same immutable input)
# ---------------------------------------------------------------------------


class TestCompositionParity:
    def test_live_and_backtest_compositions_are_byte_parity(self) -> None:
        live = compose(build_snapshot(source="live"))
        backtest = compose(build_snapshot(source="backtest"))
        report = verify_composition_parity(live, backtest)
        assert report.passed, report.diffs
        assert live.snapshot_id == backtest.snapshot_id
        assert live.decision.candidate_status == backtest.decision.candidate_status


# ---------------------------------------------------------------------------
# 2. Composition → row
# ---------------------------------------------------------------------------


class TestCompositionToRow:
    def test_row_carries_identity_scores_and_gates(self) -> None:
        composition = compose(build_snapshot())
        row = scanner_row_from_composition(composition)
        assert row.snapshot_id == composition.snapshot_id
        assert row.candidate_status == composition.decision.candidate_status
        assert row.selected_side == composition.decision.selected_side
        # Selected-side scores are the canonical side score, never re-scored.
        buy = [s for s in row.side_scores if s.side == BUY][0]
        assert row.selected_technical_signal_score == buy.technical_signal_score
        assert row.selected_setup_score == buy.setup_score
        # Round-trips through the strict row reader unchanged.
        assert scanner_row_from_dict(row.to_dict()).to_dict() == row.to_dict()


# ---------------------------------------------------------------------------
# 3. Composition → snapshot envelope → replay
# ---------------------------------------------------------------------------


class TestSnapshotAndReplay:
    def test_full_envelope_round_trips_and_replays_matching(self) -> None:
        composition = compose(build_snapshot())
        envelope = build_snapshot_envelope(composition, mode=MODE_FULL)
        assert envelope.replayable
        # The embedded composition crosses a from_dict strict boundary.
        from core.scanner_composition import ScannerCompositionResult

        revalidated = ScannerCompositionResult.from_dict(envelope.to_dict()["composition"])
        assert revalidated.snapshot_id == composition.snapshot_id
        outcome = replay_snapshot_envelope(
            envelope.to_dict(),
            thresholds=DEFAULT_THRESHOLD_POLICY,
            entry_confirmation="unconfirmed",
        )
        assert outcome.replayable is True
        assert outcome.match is True
        assert outcome.candidate_status == composition.decision.candidate_status
        assert outcome.selected_side == composition.decision.selected_side
        assert classify_snapshot_envelope(envelope.to_dict()) == "replayable"

    def test_compact_envelope_is_display_only_never_replayable(self) -> None:
        composition = compose(build_snapshot())
        envelope = build_snapshot_envelope(composition, mode=MODE_COMPACT)
        assert envelope.replayable is False
        assert classify_snapshot_envelope(envelope.to_dict()) == "audit_only"
        outcome = replay_snapshot_envelope(envelope.to_dict(), thresholds=DEFAULT_THRESHOLD_POLICY)
        assert outcome.replayable is False
        assert outcome.match is None

    def test_v3_artifact_is_audit_only(self) -> None:
        v3 = {
            "envelope_schema_version": "scanner-v3-envelope",
            "scanner_action": "buy",
            "risk_condition": "high",
            "composition_version": "v3",
        }
        assert classify_snapshot_envelope(v3) == "audit_only"
        outcome = replay_snapshot_envelope(v3, thresholds=DEFAULT_THRESHOLD_POLICY)
        assert outcome.replayable is False
        # A legacy artifact is refused for replay, never improvised into a candidate.
        assert outcome.route_status == "refused"
        assert outcome.match is not True


# ---------------------------------------------------------------------------
# 4. Router (structural reject) + 5. candidate (execution revalidation)
# ---------------------------------------------------------------------------


class TestRouterAndCandidate:
    def test_default_unconfirmed_routes_to_waiting_confirmation(self) -> None:
        composition = compose(build_snapshot())
        routed = route_scanner(
            composition,
            thresholds=DEFAULT_THRESHOLD_POLICY,
            entry_confirmation="unconfirmed",
        )
        assert routed.route_status == ROUTE_ROUTED
        assert routed.candidate.candidate_status == WAITING_CONFIRMATION

    def test_readiness_only_ready_now_for_confirmed_executable(self) -> None:
        composition = compose(build_snapshot())

        # Non-bypassable (Bước 12 §12.1): the router has NO `execution` override.
        refused = False
        try:
            route_scanner(
                composition,
                thresholds=DEFAULT_THRESHOLD_POLICY,
                entry_confirmation="confirmed",
                execution=evaluate_execution_readiness(composition),  # type: ignore[call-arg]
            )
        except TypeError:
            refused = True
        assert refused is True

        # Fresh evaluation: confirmed + executable -> READY_NOW with a prepared
        # (never auto-sent) payload that always requires revalidation at dispatch.
        routed = route_scanner(
            composition,
            thresholds=DEFAULT_THRESHOLD_POLICY,
            entry_confirmation="confirmed",
        )
        assert routed.candidate.candidate_status == READY_NOW
        payload = routed.candidate.order_payload
        assert payload is not None
        assert payload.sends_real_order is False
        assert payload.revalidation_required is True

        # Dispatch freshness is owned by the controller/order layer
        # (revalidate_execution right before a real order), never injectable at
        # the router — the router alone cannot mark a snapshot "fresh".
        readiness = evaluate_execution_readiness(composition)
        assert readiness.revalidation_required is True

    def test_structural_reject_forbidden_legacy_keys(self) -> None:
        # A legacy-shaped payload with forbidden legacy scored fields must fail
        # closed at the router, never improvised into a candidate.
        payload = {
            "composition_version": "some-version",
            "canonical": {},
            "scanner_action": "buy",
            "risk_condition": "high",
        }
        routed = route_scanner(payload, thresholds=DEFAULT_THRESHOLD_POLICY, entry_confirmation="confirmed")
        assert routed.route_status == ROUTE_VERSION_MISMATCH
        assert routed.candidate is None


# ---------------------------------------------------------------------------
# 6. Ranking (status-first; never reads news/spread/macro)
# ---------------------------------------------------------------------------


class TestRankingChain:
    def test_status_first_order_integrated(self) -> None:
        ready = compose(build_snapshot())  # -> WAITING (gates PASS)
        # Confirm + fresh execution -> READY_NOW (same snapshot geometry).
        ready_composition = compose(build_snapshot())
        ready_candidate = build_candidate(
            composition=ready_composition,
            thresholds=DEFAULT_THRESHOLD_POLICY,
            entry_confirmation="confirmed",
            execution=evaluate_execution_readiness(ready_composition),
        )
        assert ready_candidate.candidate_status == READY_NOW

        waiting_candidate = build_candidate(
            composition=compose(build_snapshot()),
            thresholds=DEFAULT_THRESHOLD_POLICY,
            entry_confirmation="unconfirmed",
            execution=evaluate_execution_readiness(compose(build_snapshot())),
        )
        assert waiting_candidate.candidate_status == WAITING_CONFIRMATION

        blocked = compose(build_snapshot(macro_raw_buy=10, macro_raw_sell=20))
        blocked_candidate = build_candidate(
            composition=blocked,
            thresholds=DEFAULT_THRESHOLD_POLICY,
            entry_confirmation="confirmed",
            execution=evaluate_execution_readiness(blocked),
        )
        assert blocked_candidate.candidate_status == BLOCKED

        candidates = [
            blocked_candidate,
            ready_candidate,
            waiting_candidate,
        ]
        ranked = rank_scanner_candidates(candidates)
        assert [c.candidate_status for c in ranked] == [
            READY_NOW,
            WAITING_CONFIRMATION,
            BLOCKED,
        ]
        groups = grouped_scanner_candidates(candidates)
        assert set(groups) == {READY_NOW, WAITING_CONFIRMATION, BLOCKED}
        assert [c for c in groups[READY_NOW]] == [ready_candidate]


# ---------------------------------------------------------------------------
# 7. Presenter (four scored components; UNKNOWN never rendered PASS)
# ---------------------------------------------------------------------------


class TestPresenterChain:
    def test_presentation_exactly_four_components_and_gate_statuses(self) -> None:
        composition = compose(build_snapshot())
        presentation = build_scanner_presentation(composition)
        assert presentation.candidate_status == composition.decision.candidate_status
        assert presentation.snapshot_id == composition.snapshot_id
        for view in presentation.side_scores:
            names = tuple(c.name for c in view.components)
            assert names == TECHNICAL_COMPONENT_NAMES
        # Gate statuses mirror the canonical gates exactly.
        assert presentation.safety_status == composition.canonical.market_safety.status
        assert presentation.macro_status == composition.canonical.macro_gate.status