"""trend_verdict_parser - the content authority of an AI trend verdict (plan batch L3.1).

Sole owner of "tham quyen noi dung verdict (parse/chap nhan/tu choi)" (contract
section 11b, identity M5).  This module reads what the model answered on contract
section 9.1 step 5 and either accepts it as three typed horizon payloads or
refuses the whole answer - never a partial row (section 9.1: "khong luu verdict
rac").

What is accepted, per horizon of ``ai_horizons`` (contract section 4.5):

* ``direction`` - a member of the frozen value set (``bullish``/``bearish``/
  ``neutral``/``insufficient_data``);
* ``confidence`` - a member of ``high``/``medium``/``low``/``none``;
* ``rationale`` - a non-empty string (the prompt asks for Vietnamese; language
  itself is not machine-checked here - no clause defines such a check);
* ``evidence_item_ids`` - a list of integer row ids, each one a row **printed in
  the prompt**.  A citation outside that set is fabrication, which the inherited
  doctrine of section 9.1 step 3 forbids: the answer is refused rather than
  stored with a dangling reference.  Pass ``evidence_item_ids=None`` only when
  the caller cannot supply the set - the check is then skipped on purpose.

Purity and layering (the review point of this batch):

* **Pure (L2).**  No I/O, no network, no clock, no policy read: the expected
  horizon keys arrive as a parameter (the keys of the ``ai_horizons`` key of
  section 7 - R4).  The parser never retries and never builds a user-facing
  message: the single retry of section 9.1 step 5 and ``friendly_error()`` both
  belong to the caller (the AI flow of L3.5).
* **Layer-clean (L1).**  Imports only stdlib + ``core.news_models``; never
  services/ui/controllers/Qt.
* **No display string (L3).**  The source stays ASCII; every error is a typed
  machine-readable report, not prose for the user.

Retry signal (section 9.1 step 5, decided here on purpose): a response that is
not a usable JSON document is flagged ``retryable`` - a second attempt is the
sanctioned remedy for a fumbled answer.  A document that parses but violates the
verdict contract (missing/extra horizon, missing field, value outside a frozen
set, empty rationale, fabricated citation) is **not** retryable: the model
answered, the answer is unusable, and no junk verdict is stored.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TypeVar

from core.news_models import (
    VerdictConfidence,
    VerdictDirection,
    VerdictHorizon,
)

__all__ = ["HorizonVerdict", "TrendParseError", "TrendParseOutcome", "parse_trend_verdict"]

_EnumT = TypeVar("_EnumT", bound=Enum)


# Error vocabulary (machine-readable, frozen strings - never shown to the user).
_INVALID_RESPONSE = "InvalidResponse"
_INVALID_JSON = "InvalidJson"
_MISSING_HORIZON = "MissingHorizon"
_UNEXPECTED_HORIZON = "UnexpectedHorizon"
_INVALID_HORIZON_BLOCK = "InvalidHorizonBlock"
_MISSING_FIELD = "MissingField"
_INVALID_ENUM_VALUE = "InvalidEnumValue"
_INVALID_RATIONALE = "InvalidRationale"
_INVALID_EVIDENCE_IDS = "InvalidEvidenceIds"

# The document-level failures the sanctioned retry covers (section 9.1 step 5).
_RETRYABLE = frozenset({_INVALID_RESPONSE, _INVALID_JSON})


@dataclass(frozen=True, slots=True)
class HorizonVerdict:
    """One accepted horizon payload - **not** a verdict row.

    The row (``ai_trend_verdicts``) also carries ``created_at``, the scope, the
    provider/model, ``prompt_hash`` and the input snapshot; composing the three
    rows is the controller's job (L3.5).  ``evidence_item_ids`` are the rows the
    model cited, already checked against the ids printed in the prompt."""

    horizon: VerdictHorizon
    direction: VerdictDirection
    confidence: VerdictConfidence
    rationale: str
    evidence_item_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class TrendParseError:
    """Typed refusal of one answer (contract section 4.6 style).

    ``error_type`` is from the frozen vocabulary of this module, ``detail`` names
    the offending horizon/field for the operator, and ``retryable`` tells the
    caller whether the single retry of section 9.1 step 5 applies (the caller
    decides - this module never retries)."""

    error_type: str
    detail: str
    retryable: bool


@dataclass(frozen=True, slots=True)
class TrendParseOutcome:
    """Typed outcome of one parse (C3).

    ``verdicts`` holds all three horizons on success and is **empty** on any
    refusal - an answer is accepted whole or refused whole, so a partial set can
    never reach the store (section 9.1)."""

    verdicts: tuple[HorizonVerdict, ...]
    error: TrendParseError | None

    @property
    def ok(self) -> bool:
        """True when the whole answer was accepted."""
        return self.error is None


def _refuse(error_type: str, detail: str) -> TrendParseOutcome:
    """Build a refusal with nothing accepted (the only failure shape)."""
    return TrendParseOutcome(
        verdicts=(),
        error=TrendParseError(
            error_type=error_type,
            detail=detail,
            retryable=error_type in _RETRYABLE,
        ),
    )


def _enum_member(enum_type: type[_EnumT], value: object) -> _EnumT | None:
    """Read one frozen-set value: the persisted string (surrounding whitespace
    trimmed), no case folding and no coercion - anything else is refused."""
    if not isinstance(value, str):
        return None
    try:
        return enum_type(value.strip())
    except ValueError:
        return None


def _evidence(
    value: object, allowed: Collection[int] | None, horizon: str
) -> tuple[int, ...] | TrendParseOutcome:
    """Validate the citation list of one horizon: the ids, or the refusal.

    Only integers are ids (a bool is not an id); ``allowed=None`` skips the
    membership check (the caller did not supply the prompt's id set)."""
    if not isinstance(value, list):
        return _refuse(
            _INVALID_EVIDENCE_IDS, f"{horizon}: evidence_item_ids is not a list"
        )
    ids: list[int] = []
    for entry in value:
        if isinstance(entry, bool) or not isinstance(entry, int):
            return _refuse(
                _INVALID_EVIDENCE_IDS,
                f"{horizon}: evidence id {entry!r} is not an integer",
            )
        if allowed is not None and entry not in allowed:
            return _refuse(
                _INVALID_EVIDENCE_IDS,
                f"{horizon}: evidence id {entry} was not in the prompt",
            )
        ids.append(int(entry))
    return tuple(ids)


def _horizon_verdict(
    horizon: VerdictHorizon, block: object, allowed: Collection[int] | None
) -> HorizonVerdict | TrendParseOutcome:
    """Validate one horizon block, field by field: the verdict, or the refusal."""
    label = horizon.value
    if not isinstance(block, dict):
        return _refuse(
            _INVALID_HORIZON_BLOCK, f"{label}: horizon value is not an object"
        )
    for field in ("direction", "confidence", "rationale", "evidence_item_ids"):
        if field not in block:
            return _refuse(_MISSING_FIELD, f"{label}: missing {field}")

    direction = _enum_member(VerdictDirection, block["direction"])
    if direction is None:
        return _refuse(
            _INVALID_ENUM_VALUE, f"{label}: direction {block['direction']!r}"
        )
    confidence = _enum_member(VerdictConfidence, block["confidence"])
    if confidence is None:
        return _refuse(
            _INVALID_ENUM_VALUE, f"{label}: confidence {block['confidence']!r}"
        )

    rationale = block["rationale"]
    if not isinstance(rationale, str) or not rationale.strip():
        return _refuse(_INVALID_RATIONALE, f"{label}: rationale is empty")

    ids = _evidence(block["evidence_item_ids"], allowed, label)
    if isinstance(ids, TrendParseOutcome):
        return ids

    return HorizonVerdict(
        horizon=horizon,
        direction=direction,
        confidence=confidence,
        rationale=rationale.strip(),
        evidence_item_ids=ids,
    )


def parse_trend_verdict(
    raw: object,
    *,
    horizons: Sequence[str],
    evidence_item_ids: Collection[int] | None = None,
) -> TrendParseOutcome:
    """Parse one model answer into typed horizon verdicts (section 9.1 step 5).

    ``horizons`` are the horizon keys the prompt asked for (the keys of the
    ``ai_horizons`` policy key, R4); the answer must hold **exactly** those keys -
    a missing horizon refuses the whole answer, and an extra one does too (the
    answer is taken whole or not at all).  ``evidence_item_ids`` is the id set
    printed in the prompt (``TrendPrompt.evidence_item_ids``); pass ``None`` to
    skip that check.

    The response must be one JSON object: no surrounding prose and no markdown
    fence are accepted - the prompt asks for bare JSON, and a response that needs
    unwrapping is a fumbled answer, which the caller's single retry covers
    (section 9.1 step 5).  Nothing is ever written by this function."""
    if not isinstance(raw, str) or not raw.strip():
        return _refuse(_INVALID_RESPONSE, "the model returned no text")
    try:
        document = json.loads(raw)
    except (TypeError, ValueError) as exc:
        return _refuse(_INVALID_JSON, f"response is not JSON: {exc}")
    if not isinstance(document, dict):
        return _refuse(_INVALID_JSON, "response is not a JSON object")

    expected = tuple(VerdictHorizon(key) for key in horizons)
    missing = [horizon.value for horizon in expected if horizon.value not in document]
    if missing:
        return _refuse(_MISSING_HORIZON, "missing horizon(s): " + ", ".join(missing))
    unexpected = sorted(key for key in document if key not in {h.value for h in expected})
    if unexpected:
        return _refuse(
            _UNEXPECTED_HORIZON, "unexpected key(s): " + ", ".join(str(k) for k in unexpected)
        )

    verdicts: list[HorizonVerdict] = []
    for horizon in expected:
        parsed = _horizon_verdict(horizon, document[horizon.value], evidence_item_ids)
        if isinstance(parsed, TrendParseOutcome):
            return parsed
        verdicts.append(parsed)
    return TrendParseOutcome(verdicts=tuple(verdicts), error=None)
