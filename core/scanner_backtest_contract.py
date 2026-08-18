"""Scanner backtest parity contract and artifact versions (Bước 09; target-only).

This module exists because Bước 09's acceptance criteria are: *"cùng immutable
point-in-time input tạo cùng Technical/Setup/gate/status ở live và backtest"* and
the artifact policy push *"legacy ... only read-only audit, non-replayable; không
được calibrate"*.

9A (parity) is structurally guaranteed by Bước 07: both adapters
(``build_live_snapshot`` / ``build_backtest_snapshot``) feed the **single**
``compose_scanner`` API and differ only in ``capture_source`` provenance.
This module turns that structural fact into a *verifiable contract*: a live
composition result and a backtest composition result built from the same
immutable snapshot input must be byte-identical in snapshot id, technical and
setup scores, selected side, every gate status, and the candidate decision —
differing **only** in ``capture_source`` and the provenance lines it implies.

9C (artifacts) lives here too: the artifact/ledger version identity.  The legacy
backtest family keeps its own live versions (``phase0-backtest-safety-v1``,
``backtest-candidate-ledger-v1``, ...); the current build defines distinct locked
versions so no legacy artifact can ever be type-coerced into a current ledger,
frozen strategy, or replay.  A classifier marks every artifact as replayable,
legacy-audit-only, or incompatible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

from core.reason_codes import (
    SCANNER_BACKTEST_PARITY_VIOLATION,
    SCANNER_LEGACY_V3_AUDIT_ONLY,
    SCANNER_SCHEMA_INVALID,
    SCANNER_VERSION_MISSING,
    SCANNER_VERSION_MISMATCH,
)
from core.scanner_composition import (
    COMPOSITION_POLICY_VERSION,
    COMPOSITION_POLICY_LEGACY_VERSION,
    ScannerCompositionResult,
)
from core.scanner_candidate import ScannerV4CandidateDecision

# ---------------------------------------------------------------------------
# Artifact/ledger identity (9C).  Distinct from the legacy versions declared in
# core/backtest_contract.py / core/backtest_candidate_ledger.py / etc.
# ---------------------------------------------------------------------------

SCANNER_BACKTEST_CONTRACT_VERSION = "scanner-backtest-contract"
SCANNER_BACKTEST_CONTRACT_LEGACY_VERSION = "scanner-backtest-contract-v4"
SCANNER_CANDIDATE_LEDGER_VERSION = "scanner-candidate-ledger"
SCANNER_CANDIDATE_LEDGER_LEGACY_VERSION = "scanner-v4-candidate-ledger-v4"
SCANNER_CANDIDATE_REPLAY_VERSION = "scanner-candidate-replay"
SCANNER_CANDIDATE_REPLAY_LEGACY_VERSION = "scanner-v4-candidate-replay-v4"
SCANNER_FROZEN_STRATEGY_VERSION = "scanner-frozen-strategy"
SCANNER_FROZEN_STRATEGY_LEGACY_VERSION = "scanner-v4-frozen-strategy-v4"
SCANNER_BACKTEST_CONFIG_SCHEMA_VERSION = 10

# Legacy artifact versions that classify as read-only/audit-only (never replayable,
# never usable to calibrate or activate).
V3_LEGACY_ARTIFACT_VERSIONS: frozenset[str] = frozenset({
    "phase0-backtest-safety-v1",
    "backtest-candidate-ledger-v1",
    "candidate-replay-v1",
    "frozen-strategy-config-v1",
    "backtest-run-policy-v1",
    "backtest-v9-statistical-validation-v1",
    "system-backtest-v1.2-event-sequence-research",
    "system-backtest-v2-execution-parity",
    "scanner-v3",
    "scanner-features-v3",
})

REPLAYABLE_ARTIFACT_KIND = "replayable"
V3_AUDIT_ONLY_ARTIFACT_KIND = "v3_audit_only"
INCOMPATIBLE_ARTIFACT_KIND = "incompatible"

ArtifactKind: TypeAlias = Literal[
    "replayable",
    "v3_audit_only",
    "incompatible",
]


@dataclass(frozen=True, slots=True)
class ArtifactClassification:
    kind: ArtifactKind
    version_field: str
    version: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "version_field": self.version_field,
            "version": self.version,
            "reason_codes": list(self.reason_codes),
        }


def classify_backtest_artifact(value: Any) -> ArtifactClassification:
    """Classify an artifact by its version identity without reading scored fields.

    Bước 12 (§12.1) hardening: an artifact is ``v4_replayable`` ONLY when it is a
    COMPLETE, strict composition envelope — ``composition_version`` exactly
    ``COMPOSITION_POLICY_VERSION`` AND the whole envelope round-trips the
    canonical composition reader (it rejects missing/mismatched/unknown nested
    identity).  A bare single version field is NOT sufficient.  Rules:

    * any legacy version field value → ``v3_audit_only`` (read-only,
      non-replayable, never calibrates);
    * a full, strictly-parsed composition envelope → ``v4_replayable``;
    * a dict that is not a parseable composition envelope (missing version, wrong
      identity, non-string version) → ``incompatible``;
    * anything else (non-dict) → ``incompatible``.
    """
    if type(value) is not dict:
        return ArtifactClassification(
            kind=INCOMPATIBLE_ARTIFACT_KIND,
            version_field="",
            version="",
            reason_codes=(SCANNER_SCHEMA_INVALID,),
        )
    for version_field, version in value.items():
        if not str(version_field).endswith("_version"):
            continue
        if not isinstance(version, str):
            return ArtifactClassification(
                kind=INCOMPATIBLE_ARTIFACT_KIND,
                version_field=version_field,
                version="",
                reason_codes=(SCANNER_SCHEMA_INVALID,),
            )
        if version in V3_LEGACY_ARTIFACT_VERSIONS:
            return ArtifactClassification(
                kind=V3_AUDIT_ONLY_ARTIFACT_KIND,
                version_field=version_field,
                version=version,
                reason_codes=(SCANNER_LEGACY_V3_AUDIT_ONLY,),
            )

    # A replayable artifact must declare the exact canonical composition
    # identity — not merely carry one matching version-family field.
    if value.get("composition_version") not in (
        COMPOSITION_POLICY_VERSION,
        COMPOSITION_POLICY_LEGACY_VERSION,
    ):
        if "composition_version" in value:
            return ArtifactClassification(
                kind=INCOMPATIBLE_ARTIFACT_KIND,
                version_field="composition_version",
                version=str(value.get("composition_version")),
                reason_codes=(SCANNER_VERSION_MISMATCH,),
            )
        return ArtifactClassification(
            kind=INCOMPATIBLE_ARTIFACT_KIND,
            version_field="",
            version="",
            reason_codes=(SCANNER_VERSION_MISSING,),
        )
    try:
        ScannerCompositionResult.from_dict(value)
    except ValueError as exc:
        code = getattr(exc, "code", None)
        if code == SCANNER_LEGACY_V3_AUDIT_ONLY:
            return ArtifactClassification(
                kind=V3_AUDIT_ONLY_ARTIFACT_KIND,
                version_field="composition_version",
                version=str(value.get("composition_version")),
                reason_codes=(SCANNER_LEGACY_V3_AUDIT_ONLY,),
            )
        reason_code = code if code in (_INCOMPATIBLE_CODES) else SCANNER_SCHEMA_INVALID
        return ArtifactClassification(
            kind=INCOMPATIBLE_ARTIFACT_KIND,
            version_field="composition_version",
            version=str(value.get("composition_version")),
            reason_codes=(reason_code,),
        )
    return ArtifactClassification(
        kind=REPLAYABLE_ARTIFACT_KIND,
        version_field="composition_version",
        version=COMPOSITION_POLICY_VERSION,
        reason_codes=(),
    )


_INCOMPATIBLE_CODES = frozenset({
    SCANNER_VERSION_MISMATCH,
    SCANNER_VERSION_MISSING,
    SCANNER_SCHEMA_INVALID,
})


def require_replayable(value: dict[str, object]) -> dict[str, object]:
    """Return value unchanged when it is replayable; otherwise raise.

    Fail-closed: any legacy/missing/mismatched identity refuses replay before any
    candidate data is read.  This is the artifact-side twin of the strategy
    router's version fencing.
    """
    verdict = classify_backtest_artifact(value)
    if verdict.kind == REPLAYABLE_ARTIFACT_KIND:
        return value
    raise ScannerArtifactError(verdict)


class ScannerArtifactError(ValueError):
    """Typed refusal of a non-replayable / incompatible backtest artifact."""

    def __init__(self, verdict: ArtifactClassification) -> None:
        self.verdict = verdict
        self.reason_codes = verdict.reason_codes
        super().__init__(
            f"artifact {verdict.kind} ({verdict.version_field}= "
            f"{verdict.version!r}): cannot replay/calibrate Scanner V4"
        )


# ---------------------------------------------------------------------------
# 9A — parity contract
# ---------------------------------------------------------------------------

# Leaf paths that legitimately differ between a live and a backtest composition
# result built from the same immutable input.  Only capture_source provenance
# may differ (in both the top-level envelope and the canonical provenance); no
# score, side, gate or decision leaf may.
_PARITY_ALLOWED_DIFF_SUFFIXES = (
    "capture_source",
    "provenance.capture_source",
)


def _leaf_path_allowed_diff(path: str) -> bool:
    return any(path.endswith(suffix) for suffix in _PARITY_ALLOWED_DIFF_SUFFIXES)


@dataclass(frozen=True, slots=True)
class ParityDiff:
    path: str
    live: object
    backtest: object

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "live": self.live, "backtest": self.backtest}


@dataclass(frozen=True, slots=True)
class BacktestParityReport:
    contract_version: str
    passed: bool
    diffs: tuple[ParityDiff, ...] = ()

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return () if self.passed else (SCANNER_BACKTEST_PARITY_VIOLATION,)

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "passed": self.passed,
            "diffs": [d.to_dict() for d in self.diffs],
        }


def _walk_mapping(value: dict[str, object], path: str) -> list[tuple[str, object]]:
    found: list[tuple[str, object]] = []
    for key, item in value.items():
        child = f"{path}.{key}" if path else str(key)
        if isinstance(item, dict):
            found.extend(_walk_mapping(item, child))
        else:
            found.append((child, item))
    return found


def verify_composition_parity(
    live: ScannerCompositionResult,
    backtest: ScannerCompositionResult,
) -> BacktestParityReport:
    """Verify live/backtest byte-parity for the same immutable snapshot input.

    The comparison walks every leaf of the composition results (canonical
    snapshot, decision, gates, provenance).  Only ``capture_source`` leaves may
    differ and only between ``live`` / ``backtest``; any other difference is a
    parity violation.  ``passed`` is False as soon as one real difference exists.
    """
    diffs: list[ParityDiff] = []
    live_leaves = dict(_walk_mapping(live.to_dict(), ""))
    bt_leaves = dict(_walk_mapping(backtest.to_dict(), ""))

    for path, live_value in live_leaves.items():
        if path not in bt_leaves:
            diffs.append(ParityDiff(path, live_value, "<missing>"))
            continue
        bt_value = bt_leaves[path]
        if live_value == bt_value:
            continue
        allowed_source_labels = {("live", "backtest"), ("backtest", "live")}
        is_allowed_source = (
            _leaf_path_allowed_diff(path)
            and isinstance(live_value, str)
            and isinstance(bt_value, str)
            and (live_value, bt_value) in allowed_source_labels
        )
        if not is_allowed_source:
            diffs.append(ParityDiff(path, live_value, bt_value))

    return BacktestParityReport(
        contract_version=SCANNER_BACKTEST_CONTRACT_VERSION,
        passed=not diffs,
        diffs=tuple(diffs),
    )


def verify_candidate_parity(
    live: ScannerV4CandidateDecision,
    backtest: ScannerV4CandidateDecision,
) -> BacktestParityReport:
    """Verify the candidate decision layer is parity-identical too."""
    diffs: list[ParityDiff] = []
    live_leaves = dict(_walk_mapping(live.to_dict(), ""))
    bt_leaves = dict(_walk_mapping(backtest.to_dict(), ""))
    for path, live_value in live_leaves.items():
        if path not in bt_leaves:
            diffs.append(ParityDiff(path, live_value, "<missing>"))
            continue
        bt_value = bt_leaves[path]
        if live_value != bt_value:
            diffs.append(ParityDiff(path, live_value, bt_value))
    return BacktestParityReport(
        contract_version=SCANNER_BACKTEST_CONTRACT_VERSION,
        passed=not diffs,
        diffs=tuple(diffs),
    )