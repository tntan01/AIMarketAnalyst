"""Pure, target-only Scanner FinalScore fallback and rounding contract.

Step 06 of the Scanner migration builds the *score* contract for FinalScore:
a single deterministic blend of three independent, per-side inputs with a fixed
formula, exact arithmetic, and one ``ROUND_HALF_UP`` only at the total:

    setup_score = technical_signal_score * 0.65
                + evidence_score          * 0.20
                + execution_quality_score * 0.15
    final_score = setup_score  # compatibility alias

Fail-closed rules (invalid/missing data never fabricates an optimistic score):

  * Technical missing/invalid  -> raise ``FinalScoreDataError``
    (``FINAL_SCORE_DATA_UNAVAILABLE``).  No numeric score is produced, so the
    pipeline maps the pair to ``DATA_UNAVAILABLE`` and no candidate/order is
    created.  There is deliberately NO fallback for technical.
  * Evidence / Execution missing or invalid -> exactly 50 neutral is substituted,
    a warning reason code is recorded (``FINAL_SCORE_EVIDENCE_NEUTRAL_FALLBACK`` /
    ``FINAL_SCORE_EXECUTION_NEUTRAL_FALLBACK``) and the source becomes the fixed
    ``fallback_neutral_50`` so every consumer can see the value is a fallback.
    The caller-supplied source is never kept when the value was substituted.
  * The neutral fallback is NEVER copied from the technical value: a technical of
    0 or 100 still falls back to exactly 50, never to 0/100.
  * No dynamic renormalization: the three weights are locked ``Fraction``
    constants that sum to exactly 1.  There is no ``weights=`` parameter, no
    adaptive/custom weight input and no default execution quality of 100.
  * Valid numeric inputs are clamped to 0..100 and blended as exact
    ``Fraction``\ s (full precision); the only rounding is one ``ROUND_HALF_UP``
    applied to the exact total.

The result is an immutable frozen object carrying ``setup_score``, the
``final_score`` alias, the three exact contributions, the actual (clamped)
input values and sources, the fallback warnings and the formula/version — so the
score is reproducible and auditable.

This module is intentionally NOT wired into the executable scanner.  The legacy
numeric mutation/optimistic paths are ledgered in the architecture doc (Mục 7.2)
for removal at Bước 07/12 and must not be duplicated here.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math
from typing import Any, Mapping

from core.reason_codes import (
    FINAL_SCORE_DATA_UNAVAILABLE,
    FINAL_SCORE_EVIDENCE_NEUTRAL_FALLBACK,
    FINAL_SCORE_EXECUTION_NEUTRAL_FALLBACK,
)
from core.scanner_v4_models import SCANNER_SCORING_VERSION, VALID_SIDES

FINAL_SCORE_POLICY_VERSION = "scanner-final-score"
FINAL_SCORE_POLICY_LEGACY_VERSION = "scanner-final-score-v4"
FINAL_SCORE_FORMULA = "0.65*technical_signal_score + 0.20*evidence_score + 0.15*execution_quality_score"

# Locked neutral fallback for missing/invalid evidence or execution quality.
# Exactly 50 — never copied from the technical value, never optimistic.
FINAL_SCORE_NEUTRAL_FALLBACK = 50
FINAL_SCORE_NEUTRAL_FALLBACK_SOURCE = "fallback_neutral_50"

# Locked blend weights.  Fractions sum to exactly 1 (no renormalization).
_TECHNICAL_WEIGHT = Fraction(65, 100)
_EVIDENCE_WEIGHT = Fraction(20, 100)
_EXECUTION_WEIGHT = Fraction(15, 100)

_SCORE_MIN = Fraction(0)
_SCORE_MAX = Fraction(100)

_INVALID = object()


class FinalScoreDataError(ValueError):
    """Typed fail-closed error: technical input missing/invalid -> no numeric score."""

    code = FINAL_SCORE_DATA_UNAVAILABLE

    def __init__(self, path: str, detail: str, *, side: str | None = None) -> None:
        self.path = path
        self.detail = detail
        self.side = side
        location = f" for {side}" if side is not None else ""
        super().__init__(
            f"{self.code}{location} at {path}: {detail}"
        )


@dataclass(frozen=True, slots=True)
class FinalScoreResult:
    """Immutable, auditable output of the locked FinalScore blend.

    ``setup_score`` is authoritative; ``final_score`` is the compatibility
    alias and must always equal it.  None of these fields can be mutated after
    construction, which makes the output safe to embed in a snapshot.
    """

    setup_score: int
    final_score: int
    technical_contribution: float
    evidence_contribution: float
    execution_contribution: float
    technical_signal_score: float
    evidence_score: float
    execution_quality_score: float
    evidence_source: str
    execution_quality_source: str
    fallback_warnings: tuple[str, ...]
    formula: str
    policy_version: str
    scoring_version: str
    side: str | None

    def __post_init__(self) -> None:
        if self.final_score != self.setup_score:
            raise ValueError("final_score must equal setup_score (compatibility alias)")
        if not 0 <= self.setup_score <= 100:
            raise ValueError("setup_score must be within 0..100")

    def to_dict(self) -> dict[str, Any]:
        return {
            "setup_score": self.setup_score,
            "final_score": self.final_score,
            "technical_contribution": self.technical_contribution,
            "evidence_contribution": self.evidence_contribution,
            "execution_contribution": self.execution_contribution,
            "technical_signal_score": self.technical_signal_score,
            "evidence_score": self.evidence_score,
            "execution_quality_score": self.execution_quality_score,
            "evidence_source": self.evidence_source,
            "execution_quality_source": self.execution_quality_source,
            "fallback_warnings": list(self.fallback_warnings),
            "formula": self.formula,
            "policy_version": self.policy_version,
            "scoring_version": self.scoring_version,
            "side": self.side,
        }

    @classmethod
    def from_dict(cls, value: object, *, path: str = "final_score") -> FinalScoreResult:
        """Strict deserializer (Bước 08 reader addition; does not change blending)."""
        expected = frozenset(
            {
                "setup_score",
                "final_score",
                "technical_contribution",
                "evidence_contribution",
                "execution_contribution",
                "technical_signal_score",
                "evidence_score",
                "execution_quality_score",
                "evidence_source",
                "execution_quality_source",
                "fallback_warnings",
                "formula",
                "policy_version",
                "scoring_version",
                "side",
            }
        )
        if type(value) is not dict or frozenset(value) != expected:
            raise ValueError(
                f"FINAL_SCORE_CONTRACT_INVALID at {path}: "
                f"expected exactly {sorted(expected)}, got "
                f"{sorted(value) if isinstance(value, Mapping) else type(value).__name__}"
            )

        def number(key: str) -> float:
            item = value[key]
            if type(item) is not int and type(item) is not float:
                raise ValueError(
                    f"FINAL_SCORE_CONTRACT_INVALID at {path}.{key}: expected a number"
                )
            return float(item)

        def text(key: str) -> str:
            item = value[key]
            if type(item) is not str:
                raise ValueError(
                    f"FINAL_SCORE_CONTRACT_INVALID at {path}.{key}: expected a string"
                )
            return item

        warnings = value["fallback_warnings"]
        if type(warnings) is not list or any(type(w) is not str for w in warnings):
            raise ValueError(
                f"FINAL_SCORE_CONTRACT_INVALID at {path}.fallback_warnings: "
                "expected a list of strings"
            )
        side = value["side"]
        if side is not None and type(side) is not str:
            raise ValueError(
                f"FINAL_SCORE_CONTRACT_INVALID at {path}.side: expected a string or null"
            )
        return cls(
            setup_score=value["setup_score"],
            final_score=value["final_score"],
            technical_contribution=number("technical_contribution"),
            evidence_contribution=number("evidence_contribution"),
            execution_contribution=number("execution_contribution"),
            technical_signal_score=number("technical_signal_score"),
            evidence_score=number("evidence_score"),
            execution_quality_score=number("execution_quality_score"),
            evidence_source=text("evidence_source"),
            execution_quality_source=text("execution_quality_source"),
            fallback_warnings=tuple(warnings),
            formula=text("formula"),
            policy_version=text("policy_version"),
            scoring_version=text("scoring_version"),
            side=side,
        )


def score_final_score(
    technical_signal_score: object,
    evidence_score: object,
    execution_quality_score: object,
    *,
    side: str | None = None,
    evidence_source: object = "",
    execution_quality_source: object = "",
) -> FinalScoreResult:
    """Blend the three per-side scores with the locked formula.

    Raises ``FinalScoreDataError`` when technical data is missing/invalid so the
    pipeline maps this pair to ``DATA_UNAVAILABLE`` and creates no order.
    Evidence/Execution missing/invalid never blocks the score: they become
    exactly 50 neutral with a warning and a fallback source.

    There is intentionally no ``weights=`` parameter — the blend is a fixed
    contract and custom/adaptive weights cannot influence the score.
    """
    if side is not None and (type(side) is not str or side not in VALID_SIDES):
        _data_error("side", f"must be one of {sorted(VALID_SIDES)}")

    technical_frac = _coerce_required_score(technical_signal_score, "technical_signal_score", side=side)

    evidence_frac, evidence_invalid = _coerce_fallback_score(evidence_score, "evidence_score", side=side)
    execution_frac, execution_invalid = _coerce_fallback_score(
        execution_quality_score, "execution_quality_score", side=side
    )

    evidence_source = _resolve_source(
        evidence_source, evidence_invalid, "evidence_source", side=side
    )
    execution_source = _resolve_source(
        execution_quality_source, execution_invalid, "execution_quality_source", side=side
    )

    warnings: list[str] = []
    if evidence_invalid:
        warnings.append(FINAL_SCORE_EVIDENCE_NEUTRAL_FALLBACK)
    if execution_invalid:
        warnings.append(FINAL_SCORE_EXECUTION_NEUTRAL_FALLBACK)

    technical_contribution = technical_frac * _TECHNICAL_WEIGHT
    evidence_contribution = evidence_frac * _EVIDENCE_WEIGHT
    execution_contribution = execution_frac * _EXECUTION_WEIGHT
    total = technical_contribution + evidence_contribution + execution_contribution

    rounded = _round_half_up_once(total)
    return FinalScoreResult(
        setup_score=rounded,
        final_score=rounded,
        technical_contribution=float(technical_contribution),
        evidence_contribution=float(evidence_contribution),
        execution_contribution=float(execution_contribution),
        technical_signal_score=float(technical_frac),
        evidence_score=float(evidence_frac),
        execution_quality_score=float(execution_frac),
        evidence_source=evidence_source,
        execution_quality_source=execution_source,
        fallback_warnings=tuple(warnings),
        formula=FINAL_SCORE_FORMULA,
        policy_version=FINAL_SCORE_POLICY_VERSION,
        scoring_version=SCANNER_SCORING_VERSION,
        side=side,
    )


def _coerce_required_score(value: object, path: str, *, side: str | None) -> Fraction:
    """Fail closed on technical input: missing/invalid raises the typed error."""
    frac = _coerce_score(value)
    if frac is None:
        _data_error(
            path,
            "technical_signal_score must be a finite real number in 0..100; "
            "there is no numeric fallback for technical data",
            side=side,
        )
    return frac


def _coerce_fallback_score(value: object, path: str, *, side: str | None) -> tuple[Fraction, bool]:
    """Evidence/Execution: invalid -> (exactly 50 neutral, True); else (clamped value, False)."""
    frac = _coerce_score(value)
    if frac is None:
        return Fraction(FINAL_SCORE_NEUTRAL_FALLBACK), True
    return frac, False


def _coerce_score(value: object) -> Fraction | None:
    """Exact Fraction of a finite real score clamped to 0..100; None if invalid.

    ``bool`` is rejected (a True/False flag is not a measurement), as are
    non-numeric values and non-finite floats (NaN/±inf).  Finite out-of-range
    numbers clamp into 0..100 — they are valid inputs, just bounded.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    frac = Fraction(value)
    if frac < _SCORE_MIN:
        return _SCORE_MIN
    if frac > _SCORE_MAX:
        return _SCORE_MAX
    return frac


def _resolve_source(source: object, invalid: bool, path: str, *, side: str | None) -> str:
    """The source must prove the fallback: substituted values never keep the real source."""
    if invalid:
        return FINAL_SCORE_NEUTRAL_FALLBACK_SOURCE
    if source is None:
        return ""
    if type(source) is not str:
        _data_error(path, "source must be a string or None", side=side)
    return source


def _round_half_up_once(value: Fraction) -> int:
    """Round one non-negative exact total once with ROUND_HALF_UP semantics."""
    quotient, remainder = divmod(value.numerator, value.denominator)
    return quotient + int(remainder * 2 >= value.denominator)


def _data_error(path: str, detail: str, *, side: str | None = None) -> None:
    raise FinalScoreDataError(path, detail, side=side)


__all__ = [
    "FINAL_SCORE_FORMULA",
    "FINAL_SCORE_NEUTRAL_FALLBACK",
    "FINAL_SCORE_NEUTRAL_FALLBACK_SOURCE",
    "FINAL_SCORE_POLICY_VERSION",
    "FinalScoreDataError",
    "FinalScoreResult",
    "score_final_score",
]