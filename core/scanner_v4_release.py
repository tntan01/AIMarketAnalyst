"""Scanner V4 release wiring (Bước 12; target-only cutover entry).

This is the SINGLE application wiring for the live runtime.  It exposes the V4
composition API (``compose_scanner_v4``) as the only scoring/decision/ranking
entry point and binds the owner's locked defaults:

* **threshold policy** — the single-owner DEFAULT policy
  (``make_default_threshold_policy()`` → technical 40 / setup 35 / gap 5 /
  R:R 2/1, ``scanner-threshold-policy-v4``).  This is a *default*, NOT a
  fabricated or V3-copied calibration; ``None`` policy still fails closed.
* **ranking policy** — the locked default (§6.3): the runtime cannot supply a
  custom status/within-group order.  ``rank_scanner_v4_candidates`` enforces it.
* **identity** — every row/snapshot/compact/ledger/journal reader and the config
  reader reject V3/mixed/unknown identity before the decision path.

Order dispatch contract (non-bypassable, §12.1 / §11): every real order is the
controller's ``execute_order_candidate`` → fresh ``revalidate_execution`` PASS →
``place_market_order``.  The router/candidate here only build an *intent*
``ScannerV4OrderPayload`` (``sends_real_order=False``); they never dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.scanner_v4_candidate import ScannerV4CandidateDecision
from core.scanner_v4_composition import (
    ScannerV4CompositionResult,
    compose_scanner_v4,
)
from core.scanner_v4_config_invalidation import filter_by_selected_side_setup
from core.scanner_v4_order_policy import (
    DEFAULT_RUNTIME_ORDER_POLICY,
    RuntimeOrderPolicy,
)
from core.scanner_v4_ranking import (
    grouped_scanner_v4_candidates,
    rank_scanner_v4_candidates,
)
from core.scanner_v4_row import ScannerV4Row, scanner_v4_row_from_composition
from core.scanner_v4_strategy_router import (
    ROUTE_ROUTED,
    RoutedCandidate,
    route_scanner_v4,
)
from core.scanner_v4_threshold_policy import (
    ThresholdPolicy,
    make_default_threshold_policy,
)

# Single-owner default threshold policy (technical 40 / setup 35 / gap 5 / R:R
# 2/1, scanner-threshold-policy-v4).  Locked once at import so the whole runtime
# shares one policy object.
DEFAULT_THRESHOLD_POLICY: ThresholdPolicy = make_default_threshold_policy()

SCANNER_V4_RELEASE_VERSION = "scanner-v4-release-v1"


@dataclass(frozen=True, slots=True)
class V4ReleasePair:
    """The V4 artefact set for ONE symbol produced by the release path."""

    composition: ScannerV4CompositionResult
    row: ScannerV4Row
    route_status: str
    candidate: ScannerV4CandidateDecision | None

    def to_dict(self) -> dict[str, object]:
        return {
            "composition_version": self.composition.to_dict().get("composition_version"),
            "snapshot_id": self.composition.snapshot_id,
            "symbol": self.composition.symbol,
            "route_status": self.route_status,
            "row": self.row.to_dict(),
            "candidate": None if self.candidate is None else self.candidate.to_dict(),
        }


def run_v4_pair(
    snapshot: object,
    *,
    now: object,
    entry_confirmation: str = "confirmed",
    proximity: float | None = None,
    order_policy: RuntimeOrderPolicy | None = None,
) -> V4ReleasePair:
    """Compose + route one snapshot through the single V4 decision path.

    ``compose_scanner_v4`` is the only entry; candidate routing uses the locked
    DEFAULT threshold policy.  ``order_policy`` binds the safety/macro/composition
    policies into the composition: its default (``DEFAULT_RUNTIME_ORDER_POLICY``)
    keeps every safety/macro/portfolio/journal value open, so candidates fail
    closed and no real order ever materializes until the owner fills the values
    (``order_policy.order_enabled`` becomes True only then).  The result carries
    the canonical composition, the exact-identity row, and the routed candidate
    (intent only — never dispatched here).
    """
    policy = DEFAULT_RUNTIME_ORDER_POLICY if order_policy is None else order_policy
    composition = compose_scanner_v4(
        snapshot,
        now=now,
        safety_policy=policy.safety,
        macro_policy=policy.macro,
        options=policy.to_compose_options(),
    )
    row = scanner_v4_row_from_composition(composition)
    routed: RoutedCandidate = route_scanner_v4(
        composition,
        thresholds=DEFAULT_THRESHOLD_POLICY,
        entry_confirmation=entry_confirmation,
        proximity=proximity,
    )
    return V4ReleasePair(
        composition=composition,
        row=row,
        route_status=routed.route_status,
        candidate=routed.candidate,
    )


def run_v4_pair_from_live(
    d1: list[object],
    h4: list[object],
    h1: list[object],
    symbol: str,
    safety,
    *,
    now: object,
    captured_at: object | None = None,
    news_in_3h: bool = False,
    entry_confirmation: str = "confirmed",
    proximity: float | None = None,
    macro_raw_buy: int | None = None,
    macro_raw_sell: int | None = None,
    macro_confidence: float | None = None,
    account=None,
    portfolio=None,
    journal=None,
    order_policy: RuntimeOrderPolicy | None = None,
) -> V4ReleasePair:
    """Drive the release path from live candles + live safety/macro/account state.

    Bước 3 convenience on top of the single entry: it builds the technical
    analysis layer + canonical SMC + regime via ``derive_live_analysis``, the
    per-side raws via ``build_side_snapshot``, assembles a ``ScannerV4Snapshot``
    from the supplied live state, and runs it through ``run_v4_pair``.  The
    routed candidate remains INTENT ONLY (``sends_real_order=False``); nothing
    here dispatches.
    """
    from core.scanner_v4_composition import build_live_snapshot
    from core.scanner_v4_live_producers import (
        build_side_snapshot,
        derive_live_analysis,
    )

    analysis = derive_live_analysis(
        d1, h4, h1, symbol=symbol,
        captured_at=captured_at if captured_at is not None else now,
        news_in_3h=news_in_3h,
    )
    snapshot = build_live_snapshot(
        symbol=symbol,
        captured_at=analysis["captured_at"],
        regime=analysis["regime"],
        canonical_smc=analysis["canonical_smc"],
        buy=build_side_snapshot(
            "buy",
            trend=analysis["raws"].per_side["buy"].trend,
            momentum=analysis["raws"].per_side["buy"].momentum,
            location=analysis["raws"].per_side["buy"].location,
        ),
        sell=build_side_snapshot(
            "sell",
            trend=analysis["raws"].per_side["sell"].trend,
            momentum=analysis["raws"].per_side["sell"].momentum,
            location=analysis["raws"].per_side["sell"].location,
        ),
        safety_context=safety,
        macro_raw_buy=macro_raw_buy,
        macro_raw_sell=macro_raw_sell,
        macro_confidence=macro_confidence,
        account=account,
        portfolio=portfolio,
        journal=journal,
    )
    return run_v4_pair(
        snapshot,
        now=now,
        entry_confirmation=entry_confirmation,
        proximity=proximity,
        order_policy=order_policy,
    )


def rank_pairs(pairs: list[V4ReleasePair]) -> tuple[V4ReleasePair, ...]:
    """Rank pairs with the LOCKED default ranking policy (§6.3)."""
    candidates = [pair.candidate for pair in pairs if pair.candidate is not None]
    ranked = rank_scanner_v4_candidates(candidates)  # default policy enforced
    by_candidate_id = {
        id(candidate): pair for pair, candidate in _candidate_index(pairs)
    }
    ordered: list[V4ReleasePair] = []
    for candidate in ranked:
        pair = by_candidate_id.get(id(candidate))
        if pair is not None:
            ordered.append(pair)
    return tuple(ordered)


def grouped_pairs(pairs: list[V4ReleasePair]) -> dict[str, tuple[V4ReleasePair, ...]]:
    """Group ranked pairs by candidate status (locked default ranking)."""
    ranked = rank_pairs(pairs)
    groups: dict[str, list[V4ReleasePair]] = {}
    for pair in ranked:
        groups.setdefault(pair.candidate.candidate_status if pair.candidate else "none", []).append(pair)
    return {status: tuple(items) for status, items in groups.items()}


def ready_pairs_above_setup(pairs: list[V4ReleasePair], min_setup_score: int | None = None) -> list[V4ReleasePair]:
    """Keep pairs whose selected-side setup meets the bar (fail-closed filter).

    ``min_setup_score`` defaults to the locked DEFAULT setup floor (35).  The
    filter reads ONLY the selected side's setup score — never V3 scored fields.
    """
    floor = int(min_setup_score) if min_setup_score is not None else int(DEFAULT_THRESHOLD_POLICY.setup_floor)
    rows = [
        {
            "selected_side": pair.row.selected_side,
            "setup_score": pair.row.selected_setup_score,
        }
        for pair in pairs
    ]
    kept = filter_by_selected_side_setup(rows, min_setup_score=floor)
    kept_pairs = [pair for pair, row in zip(pairs, rows) if row in kept]
    return kept_pairs


def _candidate_index(pairs: list[V4ReleasePair]) -> list[tuple[V4ReleasePair, ScannerV4CandidateDecision]]:
    result: list[tuple[V4ReleasePair, ScannerV4CandidateDecision]] = []
    for pair in pairs:
        if pair.candidate is not None:
            result.append((pair, pair.candidate))
    return result


__all__ = [
    "DEFAULT_THRESHOLD_POLICY",
    "ROUTE_ROUTED",
    "SCANNER_V4_RELEASE_VERSION",
    "V4ReleasePair",
    "grouped_pairs",
    "rank_pairs",
    "ready_pairs_above_setup",
    "run_v4_pair",
    "run_v4_pair_from_live",
]