"""Scanner V4 ranking (Bước 08; target-only, not live-wired yet).

Two tiers exactly per Mục 10:

1. candidate status first: ``READY_NOW`` > ``WAITING_CONFIRMATION`` >
   ``WATCH_ZONE`` > ``{BLOCKED, DATA_UNAVAILABLE}``;
2. within the same status group only: SetupScore, effective R:R, proximity,
   Evidence and Execution readiness (descending, per the versioned contract).

Edge rules:

* the tally NEVER reads news/spread/macro — there is no penalty and no Macro
  tie-break, and no legacy ``opportunity_score`` concept exists in V4;
* a missing within-group value sorts LAST inside the group (fail-closed, never
  a bonus);
* final tie-break is ``symbol`` ascending so the order is byte-deterministic.

The engine is a pure sorter: it never promotes/caps a candidate decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from core.scanner_v4_candidate import ScannerV4CandidateDecision
from core.scanner_v4_models import (
    BLOCKED,
    DATA_UNAVAILABLE,
    READY_NOW,
    SCANNER_V4_RANKING_VERSION,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
)

_NEG_INF = float("-inf")

DEFAULT_STATUS_ORDER = (
    READY_NOW,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
    BLOCKED,
    DATA_UNAVAILABLE,
)

# Within-group tie-break keys (higher is better).  The order itself is the
# versioned contract; Mục 10 locked this exact sequence.
DEFAULT_WITHIN_GROUP_KEYS = (
    "setup_score",
    "risk_reward_ratio",
    "proximity",
    "evidence_score",
    "execution_quality_score",
)


class RankPolicyError(ValueError):
    """Typed misuse of a ranking policy."""


@dataclass(frozen=True, slots=True)
class ScannerV4RankingPolicy:
    """Versioned ranking contract (test policy: values are Bước 09's to calibrate)."""

    ranking_version: str = SCANNER_V4_RANKING_VERSION
    status_order: tuple[str, ...] = DEFAULT_STATUS_ORDER
    within_group_keys: tuple[str, ...] = DEFAULT_WITHIN_GROUP_KEYS

    def __post_init__(self) -> None:
        if type(self.ranking_version) is not str or self.ranking_version == "":
            raise RankPolicyError(
                "ranking_version must be a non-empty string"
            )
        if len(set(self.status_order)) != len(self.status_order):
            raise RankPolicyError("status_order must not contain duplicates")


def _attribute(candidate: ScannerV4CandidateDecision, key: str) -> Any:
    value = getattr(candidate, key, None)
    if value is None:
        return _NEG_INF
    if isinstance(value, Fraction):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        raise RankPolicyError(f"candidate field {key!r} is not orderable") from None


def _require_runtime_policy(policy: ScannerV4RankingPolicy) -> ScannerV4RankingPolicy:
    """Runtime lock (§6.3): the caller cannot change eligibility order/version.

    The live ranking path MUST run the single locked default policy.  A caller
    that supplies a non-default ``status_order`` / ``within_group_keys`` or a
    non-canonical ``ranking_version`` is a contract violation and is refused —
    not silently honoured.
    """
    if policy.ranking_version != SCANNER_V4_RANKING_VERSION:
        raise RankPolicyError(
            f"ranking_version lock broken: expected {SCANNER_V4_RANKING_VERSION!r}, "
            f"got {policy.ranking_version!r}"
        )
    if policy.status_order != DEFAULT_STATUS_ORDER:
        raise RankPolicyError("custom status_order is not allowed at runtime (§6.3)")
    if policy.within_group_keys != DEFAULT_WITHIN_GROUP_KEYS:
        raise RankPolicyError("custom within-group keys are not allowed at runtime (§6.3)")
    return policy


def rank_scanner_v4_candidates(
    candidates: list[ScannerV4CandidateDecision],
    *,
    policy: ScannerV4RankingPolicy | None = None,
) -> tuple[ScannerV4CandidateDecision, ...]:
    """Sort candidates status-first, then within-group keys, then symbol.

    Deterministic and stable for identical decisions: inputs of the same
    candidate yield the same ranking.  The function reads only status, the
    within-group keys and ``symbol`` — never news/spread/macro.  The runtime
    ranking policy is locked (§6.3); a non-default policy is refused.
    """
    if policy is None:
        policy = ScannerV4RankingPolicy()
    _require_runtime_policy(policy)
    status_index = {status: index for index, status in enumerate(policy.status_order)}
    known_keys = tuple(policy.within_group_keys)

    def sort_key(candidate: ScannerV4CandidateDecision) -> tuple[Any, ...]:
        status_key = status_index.get(candidate.candidate_status, len(status_index))
        within = tuple(
            -_attribute(candidate, key) for key in known_keys
        )
        return (status_key, *within, candidate.symbol)

    return tuple(sorted(candidates, key=sort_key))


def grouped_scanner_v4_candidates(
    candidates: list[ScannerV4CandidateDecision],
    *,
    policy: ScannerV4RankingPolicy | None = None,
) -> dict[str, tuple[ScannerV4CandidateDecision, ...]]:
    """Rank and group by candidate status (for controller/UI presentation)."""
    ranked = rank_scanner_v4_candidates(candidates, policy=policy)
    groups: dict[str, list[ScannerV4CandidateDecision]] = {}
    for candidate in ranked:
        groups.setdefault(candidate.candidate_status, []).append(candidate)
    return {status: tuple(items) for status, items in groups.items()}