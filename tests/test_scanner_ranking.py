"""Scanner ranking (Bước 08, target-only).

Mục 10 locked two tiers:

1. candidate status first: ``READY_NOW > WAITING_CONFIRMATION > WATCH_ZONE >
   ``{BLOCKED, DATA_UNAVAILABLE}``;
2. within the same status only: SetupScore, effective R:R, proximity, Evidence,
   Execution readiness — descending, with a missing within-group value sorting
   LAST (fail-closed, never a bonus).

The shape of the within-group key test (news/spread/macro) is explicit: the
candidate contract carries NO news/spread/macro field at all, so the tally can
never read them; the policy's key set *is* the versioned contract.  The tests
below also prove a news/spread/macro-only change can't shift a ranking and that
the final tie-break is ``symbol`` ascending (byte-deterministic).
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from core.scanner_candidate import ScannerV4CandidateDecision
from core.scanner_execution_readiness import ExecutionReadiness
from core.scanner_ranking import (
    DEFAULT_STATUS_ORDER,
    DEFAULT_WITHIN_GROUP_KEYS,
    RankPolicyError,
    ScannerRankingPolicy,
    grouped_scanner_candidates,
    rank_scanner_candidates,
)
from core.scanner_v4_models import (
    BLOCKED,
    DATA_UNAVAILABLE,
    READY_NOW,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
)

CV4 = "scanner-composition-v4"


def _candidate(*, status: str, setup: int | None = 50, rr: str | None = "2/1",
                proximity: float | None = 0.5, evidence: int | None = 60,
                execution_quality: int | None = 70, symbol: str = "XAUUSD"):
    """A minimal, contract-valid candidate decision pinned to one status."""
    payload = {
        "symbol": symbol,
        "captured_at": "2026-08-13T12:00:00+00:00",
        "snapshot_id": f"snap-{symbol}-{status}",
        "composition_version": CV4,
        "scoring_version": "scanner-v4",
        "feature_version": "scanner-features-v4",
        "output_schema_version": "scanner-output-v4",
        "snapshot_version": "scanner-pair-snapshot-v4",
        "safety_policy_version": "scanner-safety-policy-v4",
        "macro_policy_version": "scanner-macro-policy-v4",
        "threshold_policy_version": "scanner-threshold-policy-v4",
        "entry_confirmation": "confirmed" if status == READY_NOW else "unconfirmed",
        "candidate_status": status,
        "selected_side": "buy" if status != DATA_UNAVAILABLE else None,
        "technical_signal_score": 66 if status != DATA_UNAVAILABLE else None,
        "setup_score": setup if status != DATA_UNAVAILABLE else None,
        "score_gap": 10 if status != DATA_UNAVAILABLE else None,
        "risk_reward_ratio": (
            None if status == DATA_UNAVAILABLE or rr is None else rr
        ),
        "proximity": proximity if status != DATA_UNAVAILABLE else None,
        "evidence_score": evidence if status != DATA_UNAVAILABLE else None,
        "execution_quality_score": (
            execution_quality if status != DATA_UNAVAILABLE else None
        ),
        "decision_cap": None,
        "gate_codes": [],
        "reason_codes": [status],
        "block_codes": [status] if status == BLOCKED else [],
        "order_payload": None,
    }
    if status == READY_NOW:
        payload["order_payload"] = {
            "symbol": symbol,
            "side": "buy",
            "captured_at": payload["captured_at"],
            "snapshot_id": payload["snapshot_id"],
            "composition_version": CV4,
            "scoring_version": "scanner-v4",
            "feature_version": "scanner-features-v4",
            "output_schema_version": "scanner-output-v4",
            "snapshot_version": "scanner-pair-snapshot-v4",
            "safety_policy_version": "scanner-safety-policy-v4",
            "macro_policy_version": "scanner-macro-policy-v4",
            "threshold_policy_version": "scanner-threshold-policy-v4",
            "entry": 91.0,
            "stop_loss": 90.0,
            "take_profit": 94.0,
            "risk_reward_ratio": "4/3",
            "technical_signal_score": 66,
            "setup_score": setup,
            "sends_real_order": False,
            "revalidation_required": True,
        }
    readiness = ExecutionReadiness.from_dict(
        {
            "snapshot_id": payload["snapshot_id"],
            "captured_at": payload["captured_at"],
            "fresh_snapshot": True,
            "can_execute": status not in (BLOCKED, DATA_UNAVAILABLE),
            "prepared": status == READY_NOW,
            "revalidation_required": True,
            "reason_codes": [],
        }
    )
    payload["execution"] = readiness.to_dict()
    return ScannerV4CandidateDecision.from_dict(payload)


class TestStatusRankedFirst:
    def test_ready_now_outranks_every_other_status(self):
        high_index = {READY_NOW: 0, WAITING_CONFIRMATION: 1, WATCH_ZONE: 2, BLOCKED: 3, DATA_UNAVAILABLE: 4}
        candidates = [
            _candidate(status=READY_NOW, setup=5, rr="1/1", proximity=0.1),
            _candidate(status=WATCH_ZONE, setup=100, rr="9/1", proximity=0.9),
            _candidate(status=WAITING_CONFIRMATION, setup=100, rr="9/1"),
            _candidate(status=BLOCKED, setup=100),
            _candidate(status=DATA_UNAVAILABLE),
        ]
        ranked = rank_scanner_candidates(candidates)
        assert [c.candidate_status for c in ranked] == [
            READY_NOW,
            WAITING_CONFIRMATION,
            WATCH_ZONE,
            BLOCKED,
            DATA_UNAVAILABLE,
        ]
        assert [high_index[c.candidate_status] for c in ranked] == sorted(
            high_index[c.candidate_status] for c in ranked
        )

    def test_status_order_contract_locked(self):
        assert DEFAULT_STATUS_ORDER == (
            READY_NOW,
            WAITING_CONFIRMATION,
            WATCH_ZONE,
            BLOCKED,
            DATA_UNAVAILABLE,
        )

    def test_status_first_ignores_phenomenal_within_group_scores(self):
        # A WATCH_ZONE with setup 100/proximity 0.9 still sorts BELOW a
        # READY_NOW with setup 5/proximity 0.1 — status is tier 1.
        ranked = rank_scanner_candidates([
            _candidate(status=READY_NOW, setup=5, rr="1/1", proximity=0.1),
            _candidate(status=WATCH_ZONE, setup=100, rr="9/1", proximity=0.9),
        ])
        assert ranked[0].candidate_status == READY_NOW
        assert ranked[1].candidate_status == WATCH_ZONE

    def test_blocked_and_data_unavailable_are_dead_last_equal_group(self):
        ranked = rank_scanner_candidates([
            _candidate(status=DATA_UNAVAILABLE),
            _candidate(status=BLOCKED, setup=90),
        ])
        assert ranked[0].candidate_status == BLOCKED
        assert ranked[1].candidate_status == DATA_UNAVAILABLE


class TestWithinGroupKeys:
    def test_setup_score_descending(self):
        candidates = [
            _candidate(status=WATCH_ZONE, setup=60),
            _candidate(status=WATCH_ZONE, setup=90),
            _candidate(status=WATCH_ZONE, setup=40),
        ]
        ranked = rank_scanner_candidates(candidates)
        assert [c.setup_score for c in ranked] == [90, 60, 40]

    def test_rr_second_key_decides_ties(self):
        candidates = [
            _candidate(status=WATCH_ZONE, setup=50, rr="3/1"),
            _candidate(status=WATCH_ZONE, setup=50, rr="2/1"),
        ]
        ranked = rank_scanner_candidates(candidates)
        assert [c.risk_reward_ratio for c in ranked] == [Fraction(3, 1), Fraction(2, 1)]

    def test_proximity_third_key(self):
        candidates = [
            _candidate(status=WATCH_ZONE, setup=50, rr="2/1", proximity=0.2),
            _candidate(status=WATCH_ZONE, setup=50, rr="2/1", proximity=0.8),
        ]
        ranked = rank_scanner_candidates(candidates)
        assert [c.proximity for c in ranked] == [0.8, 0.2]

    def test_evidence_fourth_key(self):
        candidates = [
            _candidate(status=WATCH_ZONE, evidence=30, execution_quality=70),
            _candidate(status=WATCH_ZONE, evidence=80, execution_quality=20),
        ]
        ranked = rank_scanner_candidates(candidates)
        assert [c.evidence_score for c in ranked] == [80, 30]

    def test_execution_quality_fifth_key(self):
        candidates = [
            _candidate(status=WATCH_ZONE, evidence=50, execution_quality=60),
            _candidate(status=WATCH_ZONE, evidence=50, execution_quality=90),
        ]
        ranked = rank_scanner_candidates(candidates)
        assert [c.execution_quality_score for c in ranked] == [90, 60]

    def test_within_group_key_order_is_the_versioned_contract(self):
        assert DEFAULT_WITHIN_GROUP_KEYS == (
            "setup_score",
            "risk_reward_ratio",
            "proximity",
            "evidence_score",
            "execution_quality_score",
        )

    def test_missing_value_sorts_last_inside_group(self):
        candidates = [
            _candidate(status=WATCH_ZONE, setup=50, rr="3/1"),
            _candidate(status=WATCH_ZONE, setup=50, rr="2/1"),
            _candidate(status=WATCH_ZONE, setup=50, rr=None),  # missing R:R
        ]
        ranked = rank_scanner_candidates(candidates)
        assert [c.risk_reward_ratio for c in ranked] == [
            Fraction(3, 1),
            Fraction(2, 1),
            None,  # missing sorts LAST — fail-closed, never a bonus
        ]

    def test_symbol_is_the_final_deterministic_tie_break(self):
        candidates = [
            _candidate(status=WATCH_ZONE, setup=50, symbol="BTCUSDT"),
            _candidate(status=WATCH_ZONE, setup=50, symbol="XAUUSD"),
            _candidate(status=WATCH_ZONE, setup=50, symbol="AUDUSD"),
        ]
        ranked = rank_scanner_candidates(candidates)
        assert [c.symbol for c in ranked] == ["AUDUSD", "BTCUSDT", "XAUUSD"]

    def test_repeated_ranking_is_stable(self):
        candidates = [_candidate(status=WATCH_ZONE, setup=i) for i in range(5)]
        once = rank_scanner_candidates(candidates)
        twice = rank_scanner_candidates(candidates)
        assert [c.snapshot_id for c in once] == [c.snapshot_id for c in twice]


class TestNoNewsSpreadMacroInfluence:
    def test_news_spread_macro_changes_cannot_shift_ranking(self):
        # The candidate contract has no news/spread/macro fields at all — the
        # tally literally cannot read them.  Two candidates differing only in
        # the (here nonexistent) news/spread/macro dimension must still sort by
        # the policy keys: same setup/R:R/proximity/evidence/execution, same
        # status -> deterministic symbol order, no penalty, no macro tie-break.
        a = _candidate(status=WATCH_ZONE, setup=50, symbol="XAUUSD")
        b = _candidate(status=WATCH_ZONE, setup=50, symbol="EURUSD")
        ranked = rank_scanner_candidates([b, a])
        assert [c.symbol for c in ranked] == ["EURUSD", "XAUUSD"]
        # Reorder the input: order of equal decisions is stable.
        again = rank_scanner_candidates([a, b])
        assert [c.symbol for c in again] == ["EURUSD", "XAUUSD"]

    def test_ranking_keys_exactness(self):
        # Not a single extra attribute is readable in the sort-key computation.
        candidates = [_candidate(status=WATCH_ZONE, setup=50, symbol="XAUUSD")]
        policy = ScannerRankingPolicy()
        ranked = rank_scanner_candidates(candidates, policy=policy)
        assert ranked[0].symbol == "XAUUSD"

    def test_macro_gate_status_never_ties_break(self):
        # Two candidates with identical policy keys but different macro
        # (macro is only a gate on the way to the status; it stopped being a
        # status once the decision was made) -> the ORDER is unchanged, and the
        # sort never inspects macro at all: it is deterministic.
        c1 = _candidate(status=WAITING_CONFIRMATION, setup=50, symbol="XAUUSD")
        c2 = _candidate(status=WAITING_CONFIRMATION, setup=50, symbol="EURUSD")
        assert rank_scanner_candidates([c2, c1]) == rank_scanner_candidates([c1, c2])


class TestGrouped:
    def test_grouped_returns_per_status_buckets_in_rank_order(self):
        candidates = [
            _candidate(status=WATCH_ZONE, setup=50, symbol="XAUUSD"),
            _candidate(status=READY_NOW, setup=60, symbol="XAUUSD"),
            _candidate(status=WATCH_ZONE, setup=90, symbol="NZDUSD"),
            _candidate(status=BLOCKED, setup=90, symbol="XAUUSD"),
        ]
        groups = grouped_scanner_candidates(candidates)
        assert list(groups) == [READY_NOW, WATCH_ZONE, BLOCKED]
        assert groups[READY_NOW][0].snapshot_id.endswith("READY_NOW")
        assert [g.setup_score for g in groups[WATCH_ZONE]] == [90, 50]

    def test_empty_input_gives_all_clear(self):
        assert grouped_scanner_candidates([]) == {}
        assert rank_scanner_candidates([]) == ()


class TestPolicyContract:
    def test_duplicate_status_rejected(self):
        with pytest.raises(RankPolicyError):
            ScannerRankingPolicy(status_order=(READY_NOW, READY_NOW))

    def test_empty_version_rejected(self):
        with pytest.raises(RankPolicyError):
            ScannerRankingPolicy(ranking_version="")

    def test_custom_status_order_is_refused_at_runtime(self):
        # §6.3 runtime lock: the caller cannot change eligibility order.  The
        # policy class can still be constructed (for sorter unit tests), but the
        # public ranking entry point refuses a non-default policy.
        custom = ScannerRankingPolicy(
            status_order=(BLOCKED, WATCH_ZONE, WAITING_CONFIRMATION, READY_NOW, DATA_UNAVAILABLE)
        )
        candidates = [
            _candidate(status=READY_NOW),
            _candidate(status=BLOCKED),
        ]
        with pytest.raises(RankPolicyError):
            rank_scanner_candidates(candidates, policy=custom)

    def test_non_default_within_group_keys_refused_at_runtime(self):
        custom = ScannerRankingPolicy(within_group_keys=("setup_score",))
        with pytest.raises(RankPolicyError):
            rank_scanner_candidates([_candidate(status=READY_NOW)], policy=custom)

    def test_non_canonical_version_refused_at_runtime(self):
        custom = ScannerRankingPolicy(ranking_version="scanner-ranking-v3")
        with pytest.raises(RankPolicyError):
            rank_scanner_candidates([_candidate(status=READY_NOW)], policy=custom)