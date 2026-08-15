"""Pure, target-only Scanner V4 MacroGate and MacroAssessment semantics.

Step 05 of the Scanner V4 migration builds the *decision* contract for macro:
it owns (1) the versioned ``MacroPolicy``, (2) the deterministic raw deadband
classification, (3) the single canonical construction of ``MacroAssessment``
(data only — raw BUY/SELL, confidence, status, correlation/event/AI provenance)
and (4) the ``MacroGate`` that turns an assessment into a fail-closed
``MacroGateResult`` (status PASS|CAUTION|BLOCK|UNKNOWN, assessed side,
decision cap, reason codes, policy version).

This module is intentionally NOT wired into the executable scanner. Macro
influence is confined to gate/cap: nothing here creates a contribution, bonus,
numeric adjustment, tie-break, promotion, or any mutation of
``TechnicalSignalScore``/ranking. The V3 numeric paths that do mutate scores are
ledgered in the architecture doc (Mục 7.2) for removal at Bước 07/12.

Fail-closed rules (never infer optimistic defaults):
  * policy version must equal ``scanner-macro-policy-v4``.
  * OPEN/uncalibrated policy values default to None -> the affected dimension
    returns ``UNKNOWN`` with a dedicated reason code, never coerced to PASS or
    neutral:
      - deadband_points None        -> MACRO_DEADBAND_UNSET
      - confidence_threshold None   -> MACRO_CONFIDENCE_THRESHOLD_UNSET
      - conflict_cap None           -> MACRO_CONFLICT_CAP_UNSET
      - unknown_cap None            -> UNKNOWN decision stays uncapped
      - ai_conviction_threshold None + veto present -> MACRO_AI_VETO_UNVERIFIED
  * missing raw/confidence/side data is ``UNKNOWN`` (MACRO_DATA_UNAVAILABLE /
    MACRO_SIDE_MISSING), never converted to neutral or PASS.
  * provider/AI error (verdict source fallback/fatal) is REPRESENTED with
    MACRO_AI_VERDICT_UNAVAILABLE and prevents a PASS gate — the absence of a
    veto cannot be certified, so the error is never silently skipped to pass.
    Intentional skips (disabled / below threshold / no cache) are recorded as
    MACRO_AI_VERDICT_SKIPPED without blocking the deterministic side.
  * The AI verdict is asymmetric (veto/cap only; never improves a setup) and is
    interpreted only here — a single owner for AI veto/cap.
  * Aggregate precedence: BLOCK > UNKNOWN > CAUTION > PASS.
  * Macro never touches TechnicalSignalScore; a BLOCK may coexist with a
    technical score of 100, but auto-entry must not proceed.

The gate is decisional: an evaluation re-derives the classification from the
policy and rejects an assessment whose status disagrees (``MacroGateError``),
so no consumer can inject an arbitrary status and the gate stays the owner.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any

from core.reason_codes import (
    MACRO_AI_VERDICT_SKIPPED,
    MACRO_AI_VERDICT_UNAVAILABLE,
    MACRO_AI_VETO,
    MACRO_AI_VETO_UNVERIFIED,
    MACRO_ALIGNED,
    MACRO_CONFIDENCE_THRESHOLD_UNSET,
    MACRO_CONFLICT,
    MACRO_CONFLICT_CAP_UNSET,
    MACRO_DATA_UNAVAILABLE,
    MACRO_DEADBAND_UNSET,
    MACRO_LOW_CONFIDENCE,
    MACRO_NEUTRAL,
    MACRO_SIDE_MISSING,
    MACRO_UNKNOWN_CAP_UNSET,
)
from core.scanner_v4_models import (
    ALIGNED,
    BLOCK,
    BLOCKED,
    BUY,
    CAUTION,
    CONFLICT,
    DATA_UNAVAILABLE,
    MACRO_UNKNOWN,
    NEUTRAL,
    PASS,
    SCANNER_V4_MACRO_POLICY_VERSION,
    UNKNOWN,
    MacroAssessment,
    MacroGateResult,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
    VALID_SIDES,
)

__all__ = [
    "AI_ERROR_SOURCES",
    "AI_VERDICT_SOURCES",
    "CONFLICT_CAP_BLOCK_SENTINEL",
    "DEFAULT_MACRO_POLICY",
    "MACRO_AI_POLICY_VERSION",
    "MACRO_CAP_POLICY_VERSION",
    "MACRO_CONFIDENCE_POLICY_VERSION",
    "MACRO_DEADBAND_POLICY_VERSION",
    "MacroGate",
    "MacroGateError",
    "MacroPolicy",
    "VALID_MACRO_DECISION_CAPS",
    "build_macro_assessment",
    "classify_macro_status",
]

# ---------------------------------------------------------------------------
# Locked policy versions (Step 05; see docs/scanner/scanner-v4-architecture.md
# Mục 7.1). The *semantics* are locked here; numeric values stay OPEN until the
# Bước 09 calibration (V3 effective thresholds / V2 shadow candidates are
# evidence references, never copied defaults).
# ---------------------------------------------------------------------------
MACRO_DEADBAND_POLICY_VERSION = "scanner-macro-deadband-raw-v1"
MACRO_CONFIDENCE_POLICY_VERSION = "scanner-macro-confidence-v1"
MACRO_CAP_POLICY_VERSION = "scanner-macro-cap-v1"
MACRO_AI_POLICY_VERSION = "scanner-macro-ai-veto-v1"

# decision_cap is restricted to candidate-statuses that can only lower eligibility.
VALID_MACRO_DECISION_CAPS = frozenset({
    WAITING_CONFIRMATION,
    WATCH_ZONE,
    BLOCKED,
    DATA_UNAVAILABLE,
})
# Sentinel conflict policy value: conflict -> BLOCK (instead of CAUTION + cap).
CONFLICT_CAP_BLOCK_SENTINEL = "BLOCK"

# AI verdict provenance sources (mirrors services/macro_ai_verdict.py lifecycle).
AI_VERDICT_SOURCES = frozenset({
    "ai",
    "fallback",
    "skip_disabled",
    "skip_below_threshold",
    "skip_backtest_no_cache",
    "skip_fatal_error",
})
# Genuine provider/AI failure: no veto can be certified -> gate must not PASS.
AI_ERROR_SOURCES = frozenset({"fallback", "skip_fatal_error"})

_PRECEDENCE = {
    BLOCK: 3,
    UNKNOWN: 2,
    CAUTION: 1,
    PASS: 0,
}


class MacroGateError(ValueError):
    """Fail-closed error on malformed macro policy/assessment input."""


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_int(value: int | None, path: str, *, min_value: int, max_value: int) -> None:
    if value is not None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise MacroGateError(f"{path}: expected an integer")
        if not min_value <= value <= max_value:
            raise MacroGateError(f"{path}: must be within {min_value}..{max_value}")


def _require_confidence(value: float | None, path: str) -> None:
    if value is not None:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise MacroGateError(f"{path}: expected a number")
        if not math.isfinite(float(value)):
            raise MacroGateError(f"{path}: expected a finite number")
        if not 0 <= float(value) <= 1:
            raise MacroGateError(f"{path}: must be within 0..1")


def _require_decision_cap(value: str, path: str) -> None:
    if value not in VALID_MACRO_DECISION_CAPS:
        raise MacroGateError(
            f"{path}: unexpected decision cap {value!r}; "
            f"expected one of {sorted(VALID_MACRO_DECISION_CAPS)}"
        )


def _require_side(value: str | None, path: str) -> None:
    if value is not None and value not in VALID_SIDES:
        raise MacroGateError(f"{path}: expected 'buy', 'sell' or None")


# ---------------------------------------------------------------------------
# Deterministic classification
# ---------------------------------------------------------------------------


def classify_macro_status(
    raw_buy: int | None,
    raw_sell: int | None,
    assessed_side: str | None,
    deadband_points: int | None,
) -> str:
    """Deterministic macro status relative to the assessed side (0-30 raw scale).

    Fail-closed: missing raw or side, or an uncalibrated deadband, cannot certify
    a directional statement and returns ``unknown``.

    With a locked deadband ``D``:
      |raw[assessed] - raw[other]| <= D  -> neutral
      raw[assessed] - raw[other]  >  D   -> aligned
      raw[assessed] - raw[other]  < -D   -> conflict
    """
    if assessed_side not in VALID_SIDES:
        return MACRO_UNKNOWN
    if raw_buy is None or raw_sell is None:
        return MACRO_UNKNOWN
    if deadband_points is None:
        return MACRO_UNKNOWN
    diff = int(raw_buy) - int(raw_sell) if assessed_side == BUY else int(raw_sell) - int(raw_buy)
    if -deadband_points <= diff <= deadband_points:
        return NEUTRAL
    if diff > deadband_points:
        return ALIGNED
    return CONFLICT


def build_macro_assessment(
    *,
    symbol: str,
    captured_at: datetime,
    raw_buy: int | None,
    raw_sell: int | None,
    confidence: float | None,
    assessed_side: str | None,
    deadband_points: int | None,
    correlation_context: Mapping[str, Any] | None = None,
    events: Sequence[Mapping[str, Any]] | None = None,
    macro_sources: Mapping[str, Any] | None = None,
    ai_verdict: Mapping[str, Any] | None = None,
) -> MacroAssessment:
    """Build a canonical ``MacroAssessment`` (data only; the decision stays in the gate).

    Status is derived deterministically from raw + assessed side + deadband, and
    the model itself downgrades to ``unknown`` whenever raw/confidence data is
    incomplete. No consumer may inject an arbitrary status.

    ``provenance`` is the single trace carrier: macro sources, correlation
    context, event context and the raw AI verdict. It never contains a scored
    field or a contract identity field (the model enforces both).
    """
    if not isinstance(symbol, str) or not symbol.strip():
        raise MacroGateError("symbol: expected a non-empty string")
    if not isinstance(captured_at, datetime):
        raise MacroGateError("captured_at: expected a datetime")
    _require_int(raw_buy, "raw_buy", min_value=0, max_value=30)
    _require_int(raw_sell, "raw_sell", min_value=0, max_value=30)
    _require_confidence(confidence, "confidence")
    _require_side(assessed_side, "assessed_side")
    if deadband_points is not None:
        if not isinstance(deadband_points, int) or isinstance(deadband_points, bool):
            raise MacroGateError("deadband_points: expected an integer")
        if deadband_points <= 0:
            raise MacroGateError("deadband_points: expected a positive integer")
    for name, value in (
        ("correlation_context", correlation_context),
        ("macro_sources", macro_sources),
    ):
        if value is not None and not isinstance(value, Mapping):
            raise MacroGateError(f"{name}: expected a mapping")
    if events is not None:
        if not isinstance(events, (list, tuple)):
            raise MacroGateError("events: expected a list of mappings")
        for event in events:
            if not isinstance(event, Mapping):
                raise MacroGateError("events: each entry must be a mapping")

    status = classify_macro_status(raw_buy, raw_sell, assessed_side, deadband_points)
    if confidence is None:
        status = MACRO_UNKNOWN

    provenance: dict[str, Any] = {
        "symbol": symbol,
        "captured_at": captured_at.isoformat(),
        "macro_sources": dict(macro_sources or {}),
        "correlation": dict(correlation_context or {}),
        "events": [dict(event) for event in (events or [])],
    }
    if ai_verdict is not None:
        # The key is absent when no AI signal was provided, so the gate can
        # distinguish "AI not invoked" (dimension contributes nothing) from a
        # skipped or failed verdict.
        provenance["ai_verdict"] = dict(ai_verdict)

    return MacroAssessment(
        raw_buy=raw_buy,
        raw_sell=raw_sell,
        confidence=confidence,
        status=status,
        correlation_context=dict(correlation_context or {}),
        provenance=provenance,
    )


# ---------------------------------------------------------------------------
# MacroPolicy
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MacroPolicy:
    """Versioned macro thresholds. OPEN sub-policies default to None -> fail closed.

    - deadband_points: raw BUY/SELL deadband (OPEN). None means directional
      classification cannot be certified and every assessment gates UNKNOWN.
    - confidence_threshold: minimum macro data-quality confidence (OPEN). None
      means trust cannot be certified -> UNKNOWN (MACRO_CONFIDENCE_THRESHOLD_UNSET).
    - conflict_cap: decision cap for a conflict, or sentinel ``"BLOCK"`` to BLOCK
      outright (mapping OPEN). None -> conflict gates UNKNOWN (MACRO_CONFLICT_CAP_UNSET).
    - unknown_cap: decision cap carried on any deterministic UNKNOWN result
      (macro unknown / data missing). None -> stays uncapped UNKNOWN.
    - ai_conviction_threshold: minimum AI conviction to assert a veto (OPEN).
      None -> a present veto cannot be certified -> UNKNOWN (MACRO_AI_VETO_UNVERIFIED).

    Caps are restricted to ``VALID_MACRO_DECISION_CAPS``. The gate is
    override-free: no runtime flags or bypasses exist.
    """

    policy_version: str = SCANNER_V4_MACRO_POLICY_VERSION
    deadband_points: int | None = None
    confidence_threshold: float | None = None
    conflict_cap: str | None = None
    unknown_cap: str | None = None
    ai_conviction_threshold: float | None = None
    # Locked semantics versions (values themselves stay OPEN to Bước 09).
    deadband_semantics_version: str = MACRO_DEADBAND_POLICY_VERSION
    confidence_semantics_version: str = MACRO_CONFIDENCE_POLICY_VERSION
    cap_semantics_version: str = MACRO_CAP_POLICY_VERSION
    ai_policy_version: str = MACRO_AI_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.policy_version != SCANNER_V4_MACRO_POLICY_VERSION:
            raise MacroGateError(
                f"MacroPolicy.policy_version expected {SCANNER_V4_MACRO_POLICY_VERSION!r}, "
                f"got {self.policy_version!r}"
            )
        if self.deadband_points is not None and (
            not isinstance(self.deadband_points, int)
            or isinstance(self.deadband_points, bool)
            or self.deadband_points <= 0
        ):
            raise MacroGateError("deadband_points: expected None or a positive integer")
        _require_confidence(self.confidence_threshold, "confidence_threshold")
        _require_confidence(self.ai_conviction_threshold, "ai_conviction_threshold")
        if self.deadband_semantics_version != MACRO_DEADBAND_POLICY_VERSION:
            raise MacroGateError(
                f"deadband_semantics_version must be {MACRO_DEADBAND_POLICY_VERSION!r}"
            )
        if self.confidence_semantics_version != MACRO_CONFIDENCE_POLICY_VERSION:
            raise MacroGateError(
                f"confidence_semantics_version must be {MACRO_CONFIDENCE_POLICY_VERSION!r}"
            )
        if self.cap_semantics_version != MACRO_CAP_POLICY_VERSION:
            raise MacroGateError(
                f"cap_semantics_version must be {MACRO_CAP_POLICY_VERSION!r}"
            )
        if self.ai_policy_version != MACRO_AI_POLICY_VERSION:
            raise MacroGateError(f"ai_policy_version must be {MACRO_AI_POLICY_VERSION!r}")
        if self.conflict_cap is not None and self.conflict_cap != CONFLICT_CAP_BLOCK_SENTINEL:
            _require_decision_cap(self.conflict_cap, "conflict_cap")
        if self.unknown_cap is not None:
            _require_decision_cap(self.unknown_cap, "unknown_cap")


DEFAULT_MACRO_POLICY = MacroPolicy(policy_version=SCANNER_V4_MACRO_POLICY_VERSION)


# ---------------------------------------------------------------------------
# MacroGate
# ---------------------------------------------------------------------------


class MacroGate:
    """Canonical owner of the macro decision (target-only, not wired to runtime).

    Only this module constructs ``MacroAssessment``/``MacroGateResult`` in the
    V4 target, and only here is the AI verdict interpreted into a veto/cap —
    the single owner of the AI veto/cap.
    """

    def evaluate(
        self,
        assessment: MacroAssessment,
        *,
        assessed_side: str | None,
        policy: MacroPolicy | None = None,
        now: datetime | None = None,
    ) -> MacroGateResult:
        policy = policy if policy is not None else DEFAULT_MACRO_POLICY
        now = now if now is not None else _utc_now()
        if not isinstance(assessment, MacroAssessment):
            raise MacroGateError("evaluate requires a MacroAssessment")
        if assessed_side is not None and assessed_side not in VALID_SIDES:
            raise MacroGateError("assessed_side: expected 'buy', 'sell' or None")

        # Single owner of the decision: the assessment status must equal what
        # this policy's classifier derives, else the input is rejected.
        expected_status = self._expected_status(assessment, policy, assessed_side)
        if expected_status != assessment.status:
            raise MacroGateError(
                f"assessment.status {assessment.status!r} inconsistent with policy-derived "
                f"status {expected_status!r}; the gate must be the sole owner of the "
                f"macro decision"
            )

        deterministic = self._deterministic_dimension(assessment, policy, assessed_side)
        ai = self._ai_dimension(assessment, policy)
        status, cap = self._merge_dimensions(deterministic, ai)
        reasons: list[str] = []
        for code in (*deterministic[2], *ai[2]):
            if code not in reasons:
                reasons.append(code)

        provenance: dict[str, Any] = {
            "symbol": assessment.provenance.get("symbol"),
            "assessment_status": assessment.status,
            "policy": {
                "deadband_points": policy.deadband_points,
                "confidence_threshold": policy.confidence_threshold,
                "conflict_cap": policy.conflict_cap,
                "unknown_cap": policy.unknown_cap,
                "ai_policy_version": policy.ai_policy_version,
            },
            "ai_decision": self._ai_decision_record(assessment),
        }

        return MacroGateResult(
            assessed_side=assessed_side,
            status=status,  # type: ignore[arg-type]
            decision_cap=cap,
            reason_codes=tuple(reasons),
            policy_version=policy.policy_version,
            checked_at=now,
            provenance=provenance,
        )

    # --- dimension resolution -------------------------------------------------

    def _expected_status(
        self,
        assessment: MacroAssessment,
        policy: MacroPolicy,
        assessed_side: str | None,
    ) -> str:
        """The classification the gate derives for this assessment + policy.

        Deliberately ignores the confidence threshold: the assessment status is
        a *data* classification; whether that data can be trusted is the gate's
        confidence dimension (which may still downgrade the final status).
        """
        if assessed_side not in VALID_SIDES:
            return MACRO_UNKNOWN
        if (
            assessment.raw_buy is None
            or assessment.raw_sell is None
            or assessment.confidence is None
        ):
            return MACRO_UNKNOWN
        return classify_macro_status(
            assessment.raw_buy,
            assessment.raw_sell,
            assessed_side,
            policy.deadband_points,
        )

    def _deterministic_dimension(
        self,
        assessment: MacroAssessment,
        policy: MacroPolicy,
        assessed_side: str | None,
    ) -> tuple[str, str | None, list[str]]:
        """Deterministic macro direction -> (status, cap, reasons). Fail-closed.

        Every UNKNOWN here may carry ``policy.unknown_cap`` as the decision cap
        for the open macro decision. When the policy has no unknown cap, the
        uncapped unknown is itself explicit (``MACRO_UNKNOWN_CAP_UNSET``) so the
        decision layer can tell "unknown but mitigated by a cap" from "unknown
        with no mitigation" (singular unknown-cap knob).
        """

        def _unknown(reason: str) -> tuple[str, str | None, list[str]]:
            reasons = [reason]
            if policy.unknown_cap is None:
                reasons.append(MACRO_UNKNOWN_CAP_UNSET)
            return UNKNOWN, policy.unknown_cap, reasons

        if assessed_side not in VALID_SIDES:
            return _unknown(MACRO_SIDE_MISSING)
        if (
            assessment.raw_buy is None
            or assessment.raw_sell is None
            or assessment.confidence is None
        ):
            return _unknown(MACRO_DATA_UNAVAILABLE)
        if policy.deadband_points is None:
            return _unknown(MACRO_DEADBAND_UNSET)
        if policy.confidence_threshold is None:
            return _unknown(MACRO_CONFIDENCE_THRESHOLD_UNSET)
        if float(assessment.confidence) < float(policy.confidence_threshold):
            return _unknown(MACRO_LOW_CONFIDENCE)

        status = classify_macro_status(
            assessment.raw_buy,
            assessment.raw_sell,
            assessed_side,
            policy.deadband_points,
        )
        if status == NEUTRAL:
            return PASS, None, [MACRO_NEUTRAL]
        if status == ALIGNED:
            # Aligned never adds score, promotes, tie-breaks; it is simply the
            # absence of a macro obstacle -> PASS with no cap.
            return PASS, None, [MACRO_ALIGNED]
        # status == CONFLICT
        if policy.conflict_cap is None:
            return _unknown(MACRO_CONFLICT_CAP_UNSET)
        if policy.conflict_cap == CONFLICT_CAP_BLOCK_SENTINEL:
            return BLOCK, BLOCKED, [MACRO_CONFLICT]
        return CAUTION, policy.conflict_cap, [MACRO_CONFLICT]

    def _ai_dimension(
        self,
        assessment: MacroAssessment,
        policy: MacroPolicy,
    ) -> tuple[str, str | None, list[str]]:
        """AI verdict -> (status, cap, reasons). Asymmetric: veto/cap only.

        A present veto with an uncalibrated conviction threshold gates UNKNOWN
        (MACRO_AI_VETO_UNVERIFIED); a certified veto gates BLOCK + BLOCKED cap.
        Provider/AI error sources gate UNKNOWN (MACRO_AI_VERDICT_UNAVAILABLE) and
        never allow the gate to PASS; intentional skips are recorded with
        MACRO_AI_VERDICT_SKIPPED without blocking the deterministic side.
        """
        verdict = assessment.provenance.get("ai_verdict")
        if verdict is None:
            # No AI signal provided for this assessment: nothing to interpret.
            return PASS, None, []
        if not isinstance(verdict, Mapping):
            raise MacroGateError("provenance.ai_verdict: expected an object")
        source = str(verdict.get("source") or "")
        if source not in AI_VERDICT_SOURCES:
            raise MacroGateError(
                f"provenance.ai_verdict.source: unexpected {source!r}; "
                f"expected one of {sorted(AI_VERDICT_SOURCES)}"
            )
        if source in AI_ERROR_SOURCES:
            return UNKNOWN, None, [MACRO_AI_VERDICT_UNAVAILABLE]
        if source != "ai":
            return PASS, None, [MACRO_AI_VERDICT_SKIPPED]

        conviction = verdict.get("conviction")
        if isinstance(conviction, bool) or not isinstance(conviction, (int, float)):
            raise MacroGateError("provenance.ai_verdict.conviction: expected a number")
        if not 0 <= float(conviction) <= 1:
            raise MacroGateError("provenance.ai_verdict.conviction: must be within 0..1")
        if not isinstance(verdict.get("veto"), bool):
            raise MacroGateError("provenance.ai_verdict.veto: expected a boolean")
        if not verdict["veto"]:
            return PASS, None, []
        if policy.ai_conviction_threshold is None:
            return UNKNOWN, None, [MACRO_AI_VETO_UNVERIFIED]
        if float(conviction) >= float(policy.ai_conviction_threshold):
            return BLOCK, BLOCKED, [MACRO_AI_VETO]
        return PASS, None, [MACRO_AI_VERDICT_SKIPPED]

    @staticmethod
    def _merge_dimensions(
        deterministic: tuple[str, str | None, list[str]],
        ai: tuple[str, str | None, list[str]],
    ) -> tuple[str, str | None]:
        d_status, d_cap, _ = deterministic
        a_status, a_cap, _ = ai
        if _PRECEDENCE[a_status] > _PRECEDENCE[d_status]:
            return a_status, a_cap
        return d_status, d_cap

    @staticmethod
    def _ai_decision_record(assessment: MacroAssessment) -> dict[str, Any]:
        verdict = assessment.provenance.get("ai_verdict")
        if not isinstance(verdict, Mapping):
            return {"present": bool(verdict)}
        conflicts = verdict.get("conflicts")
        return {
            "present": True,
            "source": str(verdict.get("source")),
            "veto": bool(verdict.get("veto", False)),
            "conviction": verdict.get("conviction"),
            "conflicts": list(conflicts) if isinstance(conflicts, (list, tuple)) else [],
        }