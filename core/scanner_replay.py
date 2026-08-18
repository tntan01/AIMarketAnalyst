"""Scanner strict snapshot replay (Bước 10; target-only).

10C — a snapshot is replayed **strictly and deterministically**:

* only a ``full`` envelope (which embeds the strict composition) is replayable;
  a compact envelope carries display/audit fields only and is *not* replayable;
* replay runs the single decision pipeline (composition validation ->
  candidate route) on the embedded payload and compares the outcome of the
  replay against the stored envelope fields — never rewrites the artifact;
* a legacy snapshot, a payload with missing/mismatched versions, or a forbidden
  legacy scored field is **non-replayable**: it is refused (audit-only) and
  is never routed through the decision path.

The comparison is byte-deterministic: the same embedded composition + same
threshold policy produce the same candidate/status/scores every run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.reason_codes import (
    SCANNER_SCHEMA_INVALID,
    SCANNER_VERSION_MISSING,
)
from core.scanner_composition import ScannerCompositionResult
from core.scanner_v4_models import BUY, SELL
from core.scanner_snapshot import (
    MODE_FULL,
    SCANNER_SNAPSHOT_ENVELOPE_VERSION,
    ScannerSnapshotEnvelope,
    snapshot_envelope_from_dict,
)
from core.scanner_v4_strategy_router import (
    ROUTE_ROUTED,
    RoutedCandidate,
    route_scanner,
)
from core.scanner_threshold_policy import ThresholdPolicy

SCANNER_REPLAY_VERSION = "scanner-replay"
SCANNER_REPLAY_LEGACY_VERSION = "scanner-v4-replay-v1"


class SnapshotReplayError(ValueError):
    """Fail-closed replay error carrying a reason code."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.detail = message
        super().__init__(f"{code} at {path}: {message}")


@dataclass(frozen=True, slots=True)
class SnapshotReplayOutcome:
    """Deterministic replay outcome over a full envelope."""

    replayable: bool
    route_status: str
    match: bool | None  # None when not replayable
    candidate_status: str | None
    selected_side: str | None
    selected_setup_score: int | None
    reason_codes: tuple[str, ...]
    comparisons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "replayable": self.replayable,
            "route_status": self.route_status,
            "match": self.match,
            "candidate_status": self.candidate_status,
            "selected_side": self.selected_side,
            "selected_setup_score": self.selected_setup_score,
            "reason_codes": list(self.reason_codes),
            "comparisons": list(self.comparisons),
        }


def classify_snapshot_envelope(value: object) -> str:
    """Classify a snapshot payload for replay: ``replayable``/``audit_only``/``invalid``.

    Reads only identity/schema markers — never scores.  Total: any input maps
    to one of the three buckets (a non-object is ``invalid``).
    """
    try:
        payload = _require_mapping(value)
    except SnapshotReplayError:
        return "invalid"
    if payload.get("envelope_schema_version") == SCANNER_SNAPSHOT_ENVELOPE_VERSION:
        # A full envelope: replayable only in full mode with an embedded composition
        # that itself passes the STRICT reader (exact nested identity — legacy/mixed/
        # unknown never replayable).  Compact is a valid display/audit artifact and
        # never replayed.
        if payload.get("mode") == MODE_FULL and isinstance(payload.get("composition"), dict):
            try:
                snapshot_envelope_from_dict(payload)
            except (SnapshotReplayError, ValueError):
                return "invalid"
            return "replayable"
        return "audit_only"
    if _looks_v3(payload):
        return "audit_only"
    return "invalid"


def _looks_v3(payload: Mapping[str, Any]) -> bool:
    known_v3 = {"scanner-v3", "scanner-features-v3", "smc-v2", "phase7-observability-v1"}
    for key in ("scoring_version", "feature_version", "scorer_version", "persistence_version"):
        if payload.get(key) in known_v3:
            return True
    for key in (
        "persistence_schema_version",
        "scanner_action",
        "scanner_group",
        "macro_score",
        "risk_condition",
        "macro_alignment",
    ):
        if key in payload:
            return True
    return False


def replay_snapshot_envelope(
    value: object,
    *,
    thresholds: ThresholdPolicy,
    entry_confirmation: str = "unconfirmed",
) -> SnapshotReplayOutcome:
    """Strict, deterministic replay of a full snapshot envelope.

    Refuses ``compact`` envelopes (display-only), legacy artifacts, missing or
    mismatched versions, and any forbidden legacy scored field.  When the
    envelope is replayable, the embedded composition is re-validated strictly
    and routed through the single decision path; the replayed candidate is
    then compared field-by-field against the stored envelope.  Nothing is
    rewritten.
    """
    # 1. Strict envelope read (fail-closed; legacy -> audit-only non-replayable).
    try:
        envelope = snapshot_envelope_from_dict(value)
    except SnapshotReplayError as exc:
        return _failed(exc.code, sort_comparisons=(), already_failed=True)
    except ValueError as exc:
        code = getattr(exc, "code", None) or SCANNER_SCHEMA_INVALID
        return _failed(code, already_failed=True)

    if not envelope.replayable:
        return SnapshotReplayOutcome(
            replayable=False,
            route_status="not_replayable",
            match=None,
            candidate_status=envelope.candidate_status,
            selected_side=envelope.selected_side,
            selected_setup_score=None,
            reason_codes=(SCANNER_SCHEMA_INVALID,),
            comparisons=(f"mode={envelope.mode}: compact envelopes are not replayable",),
        )
    composition_payload = envelope.composition
    if composition_payload is None:
        return SnapshotReplayOutcome(
            replayable=False,
            route_status="not_replayable",
            match=None,
            candidate_status=envelope.candidate_status,
            selected_side=envelope.selected_side,
            selected_setup_score=None,
            reason_codes=(SCANNER_VERSION_MISSING,),
            comparisons=("full envelope missing embedded composition",),
        )

    # 2. Strict composition re-validation, then single-path routing.
    try:
        composition = ScannerCompositionResult.from_dict(composition_payload)
    except ValueError as exc:
        return _failed(getattr(exc, "code", None) or SCANNER_SCHEMA_INVALID)

    router: RoutedCandidate = route_scanner(
        composition,
        thresholds=thresholds,
        entry_confirmation=entry_confirmation,
    )
    comparisons: list[str] = []
    if router.route_status == ROUTE_ROUTED and router.candidate is not None:
        candidate = router.candidate
        candidate_status = candidate.candidate_status
        selected_side = candidate.selected_side
        setup_score = candidate.setup_score
        mismatch_flags: list[str] = []
        if candidate_status != envelope.candidate_status:
            mismatch_flags.append(
                f"candidate_status {candidate_status!r} != stored {envelope.candidate_status!r}"
            )
        if selected_side != envelope.selected_side:
            mismatch_flags.append(
                f"selected_side {selected_side!r} != stored {envelope.selected_side!r}"
            )
        if candidate.snapshot_id != envelope.snapshot_id:
            mismatch_flags.append(
                f"snapshot_id {candidate.snapshot_id!r} != stored {envelope.snapshot_id!r}"
            )
        _selected_setup = _setup_for(composition_payload, envelope, candidate_status)
        if _selected_setup != setup_score:
            mismatch_flags.append(
                f"selected_setup_score {setup_score!r} != stored {_selected_setup!r}"
            )
        comparisons = tuple(mismatch_flags)
        match = not mismatch_flags
        return SnapshotReplayOutcome(
            replayable=True,
            route_status=ROUTE_ROUTED,
            match=match,
            candidate_status=candidate_status,
            selected_side=selected_side,
            selected_setup_score=setup_score,
            reason_codes=candidate.reason_codes,
            comparisons=comparisons,
        )

    # 3. Router refused the replay (should never happen on a strictly
    #    re-validated full envelope, but keep the contract fail-closed).
    return SnapshotReplayOutcome(
        replayable=True,
        route_status=router.route_status,
        match=False,
        candidate_status=None,
        selected_side=None,
        selected_setup_score=None,
        reason_codes=router.reason_codes,
        comparisons=(f"router refused replay: {router.route_status}",),
    )


def _setup_for(
    composition_payload: Mapping[str, Any],
    envelope: ScannerSnapshotEnvelope,
    candidate_status: str | None,
) -> int | None:
    """Read the stored selected-side setup_score from the embedded canonical."""
    selected = envelope.selected_side
    if selected not in (BUY, SELL):
        return None
    canonical = composition_payload.get("canonical")
    if not isinstance(canonical, Mapping):
        return None
    side_scores = canonical.get("side_scores")
    if not isinstance(side_scores, Mapping):
        return None
    score = side_scores.get(selected)
    if isinstance(score, Mapping):
        return score.get("setup_score")
    return None


def _failed(code: str, *, sort_comparisons: tuple[str, ...] = (), already_failed: bool = False) -> SnapshotReplayOutcome:
    return SnapshotReplayOutcome(
        replayable=False,
        route_status="refused",
        match=False,
        candidate_status=None,
        selected_side=None,
        selected_setup_score=None,
        reason_codes=(code,),
        comparisons=sort_comparisons,
    )


def _require_mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SnapshotReplayError(
            SCANNER_SCHEMA_INVALID, "snapshot_payload", "expected a JSON object"
        )
    return value