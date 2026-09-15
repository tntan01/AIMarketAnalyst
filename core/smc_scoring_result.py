"""Neutral canonical SMC scoring result contract.

The single-runtime contract holds both BUY and SELL side payloads produced by
the one canonical scorer.  Public names here are deliberately free of
v1/v2/legacy/shadow concepts: ``scoring_version`` is immutable formula
provenance, never a mode selector.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from math import isfinite
from typing import Any, Mapping, Sequence

from core.smc_models import (
    QUALITY_B_WEIGHT,
    QUALITY_C_WEIGHT,
    QUALITY_L_WEIGHT,
    QUALITY_Q_WEIGHT,
    QUALITY_SCORE_SCALE,
    QUALITY_S_MAX,
    round_half_up,
)
from core.smc_versions import SMC_SCORER_VERSION as _CANONICAL_SCORER_VERSION
from core.smc_versions import SMC_SELECTION_VERSION


SMC_SCORING_CONTRACT_VERSION = "smc-scoring-canonical-2026-08"
SMC_SELECTION_CONTRACT_VERSION = "smc-side-selection-2026-09"
VALID_SIDES = frozenset({"buy", "sell"})

# Canonical raw range, derived from the one owner of the formula scale so the
# final invariant never restates the number (compatibility spec §2).
SMC_QUALITY_RAW_MAX = int(QUALITY_S_MAX)

# Selection states of one side's final result (selection spec §6/§8, readiness
# spec §5.4/§5.5/§10).  ``no_zone`` and ``data_unavailable`` are deliberately
# different results: the first was evaluated and found nothing, the second
# could not be concluded at all.
SELECTION_STATE_EVALUATED = "evaluated"
SELECTION_STATE_WATCH_ZONE = "watch_zone"
SELECTION_STATE_NO_ZONE = "no_zone"
SELECTION_STATE_OUT_OF_STRATEGY = "out_of_strategy"
SELECTION_STATE_DATA_UNAVAILABLE = "data_unavailable"
SELECTION_STATE_BLOCKED = "blocked"
VALID_SELECTION_STATES = frozenset({
    SELECTION_STATE_EVALUATED,
    SELECTION_STATE_WATCH_ZONE,
    SELECTION_STATE_NO_ZONE,
    SELECTION_STATE_OUT_OF_STRATEGY,
    SELECTION_STATE_DATA_UNAVAILABLE,
    SELECTION_STATE_BLOCKED,
})

# Selection reason codes owned by the finalizer (selection spec §8).
SELECTION_REASON_QUALITY_RANK = "QUALITY_RANK"
SELECTION_REASON_NEXT_CANDIDATE = "NEXT_CANDIDATE_AFTER_REJECT"
SELECTION_REASON_WATCH_NO_PLAN = "WATCH_NO_PLAN"
SELECTION_REASON_NO_VALID_SETUP = "SMC_NO_VALID_SETUP"
SELECTION_REASON_CORE_UNAVAILABLE = "SMC_CORE_DATA_UNAVAILABLE"
SELECTION_REASON_EXTERNAL_BLOCKED = "SMC_EXTERNAL_GATE_BLOCKED"
SELECTION_REASON_ZONE_INVALID = "SMC_ZONE_INVALID_OR_EXPIRED"


@dataclass(frozen=True, slots=True)
class SmcCandidateTraceEntry:
    """One candidate the coordinator actually attempted, in order.

    It is plain data written by the finalizer; a consumer may explain the
    decision with it but can never turn an entry into a second selected result
    (selection spec §7).
    """

    candidate_id: str
    side: str
    timeframe: str = ""
    family: str = ""
    zone_id: str | None = None
    setup_id: str | None = None
    confirmation_state: str = ""
    confirmation_rank: int | None = None
    quality_raw: int | None = None
    quality_score: float | None = None
    distance_atr: float | None = None
    plan_available: bool = False
    rejection_codes: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "rejection_codes", _tuple_of_text(self.rejection_codes)
        )
        object.__setattr__(self, "reason_codes", _tuple_of_text(self.reason_codes))

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "side": self.side,
            "timeframe": self.timeframe,
            "family": self.family,
            "zone_id": self.zone_id,
            "setup_id": self.setup_id,
            "confirmation_state": self.confirmation_state,
            "confirmation_rank": self.confirmation_rank,
            "quality_raw": self.quality_raw,
            "quality_score": self.quality_score,
            "distance_atr": self.distance_atr,
            "plan_available": self.plan_available,
            "rejection_codes": list(self.rejection_codes),
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_dict(cls, value: object) -> "SmcCandidateTraceEntry":
        payload = value if isinstance(value, dict) else {}
        return cls(
            candidate_id=str(payload.get("candidate_id") or "unknown-candidate"),
            side=str(payload.get("side") or "").strip().lower() or "buy",
            timeframe=_optional_text(payload.get("timeframe")) or "",
            family=_optional_text(payload.get("family")) or "",
            zone_id=_optional_text(payload.get("zone_id")),
            setup_id=_optional_text(payload.get("setup_id")),
            confirmation_state=_optional_text(payload.get("confirmation_state"))
            or "",
            confirmation_rank=_optional_int(payload.get("confirmation_rank")),
            quality_raw=_optional_int(payload.get("quality_raw")),
            quality_score=_optional_float(payload.get("quality_score")),
            distance_atr=_optional_float(payload.get("distance_atr")),
            plan_available=bool(payload.get("plan_available")),
            rejection_codes=payload.get("rejection_codes") or (),
            reason_codes=payload.get("reason_codes") or (),
        )


@dataclass(frozen=True, slots=True)
class SmcSideSelection:
    """Final canonical selection of one side (tasks 94/95, selection spec §8).

    Every field describes ONE selected setup: the quality, the lifecycle/
    confirmation evidence of its zone and the plan reference of the same
    candidate.  When a side keeps a watch zone without a plan, the selected
    ids/quality stay and only ``plan``/``plan_available`` say so; when the core
    data was unavailable the quality is ``null`` (never ``0``).
    """

    side: str
    state: str
    selection_version: str = SMC_SELECTION_VERSION
    contract_version: str = SMC_SELECTION_CONTRACT_VERSION
    selected_candidate_id: str | None = None
    selected_zone_id: str | None = None
    selected_setup_id: str | None = None
    timeframe: str | None = None
    family: str | None = None
    lifecycle_status: str | None = None
    confirmation_state: str | None = None
    confirmation_rank: int | None = None
    entry_visit_id: str | None = None
    confirmation_event_id: str | None = None
    quality_raw: int | None = None
    quality_score: float | None = None
    b: float | None = None
    q: float | None = None
    l: float | None = None
    c: float | None = None
    total: float | None = None
    # Entry band of the selected candidate and the identity of the plan built
    # for it (R100-01).  They prove the plan reference and the selected zone are
    # the same setup instead of two different ones glued together.
    zone_low: float | None = None
    zone_high: float | None = None
    plan: dict[str, Any] | None = None
    plan_available: bool = False
    plan_zone_id: str | None = None
    plan_setup_id: str | None = None
    plan_rejection_codes: tuple[str, ...] = ()
    readiness: dict[str, Any] | None = None
    selection_reason_codes: tuple[str, ...] = ()
    candidate_trace: tuple[SmcCandidateTraceEntry, ...] = ()
    alternatives: tuple[SmcCandidateTraceEntry, ...] = ()

    def __post_init__(self) -> None:
        side = str(self.side or "").strip().lower()
        if side not in VALID_SIDES:
            raise ValueError(f"Invalid SMC selection side: {self.side}")
        object.__setattr__(self, "side", side)
        state = str(self.state or "").strip().lower()
        if state not in VALID_SELECTION_STATES:
            raise ValueError(f"Invalid SMC selection state: {self.state}")
        object.__setattr__(self, "state", state)
        object.__setattr__(
            self, "selection_reason_codes", _tuple_of_text(self.selection_reason_codes)
        )
        object.__setattr__(
            self, "plan_rejection_codes", _tuple_of_text(self.plan_rejection_codes)
        )
        object.__setattr__(
            self, "candidate_trace", tuple(self.candidate_trace)
        )
        object.__setattr__(self, "alternatives", tuple(self.alternatives))
        if self.plan_available != (self.plan is not None):
            raise ValueError("SMC selection plan_available must match the plan")
        # Only a state that really selected a usable candidate may carry plan;
        # no-zone/core-unavailable never certify a selected setup.
        if self.plan_available and self.selected_zone_id is None:
            raise ValueError("an available plan requires a selected zone")
        if self.state in {
            SELECTION_STATE_NO_ZONE,
            SELECTION_STATE_DATA_UNAVAILABLE,
        } and any(
            value is not None
            for value in (
                self.selected_zone_id,
                self.selected_setup_id,
                self.selected_candidate_id,
            )
        ):
            raise ValueError("no-zone/core-unavailable cannot certify a selection")
        if (
            self.state == SELECTION_STATE_DATA_UNAVAILABLE
            and self.quality_raw is not None
        ):
            raise ValueError("data unavailable keeps quality_raw null")
        if self.state == SELECTION_STATE_NO_ZONE and self.quality_raw != 0:
            raise ValueError("no-zone is an evaluated zero, not null")
        _validate_plan_identity(self)
        _validate_quality_arithmetic(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "state": self.state,
            "selection_version": self.selection_version,
            "contract_version": self.contract_version,
            "selected_candidate_id": self.selected_candidate_id,
            "selected_zone_id": self.selected_zone_id,
            "selected_setup_id": self.selected_setup_id,
            "timeframe": self.timeframe,
            "family": self.family,
            "lifecycle_status": self.lifecycle_status,
            "confirmation_state": self.confirmation_state,
            "confirmation_rank": self.confirmation_rank,
            "entry_visit_id": self.entry_visit_id,
            "confirmation_event_id": self.confirmation_event_id,
            "quality_raw": self.quality_raw,
            "quality_score": self.quality_score,
            "b": self.b,
            "q": self.q,
            "l": self.l,
            "c": self.c,
            "total": self.total,
            "zone_low": self.zone_low,
            "zone_high": self.zone_high,
            "plan": dict(self.plan) if self.plan is not None else None,
            "plan_available": self.plan_available,
            "plan_zone_id": self.plan_zone_id,
            "plan_setup_id": self.plan_setup_id,
            "plan_rejection_codes": list(self.plan_rejection_codes),
            "readiness": dict(self.readiness) if self.readiness is not None else None,
            "selection_reason_codes": list(self.selection_reason_codes),
            "candidate_trace": [entry.to_dict() for entry in self.candidate_trace],
            "alternatives": [entry.to_dict() for entry in self.alternatives],
        }

    @classmethod
    def from_dict(cls, value: object) -> "SmcSideSelection":
        payload = value if isinstance(value, dict) else {}
        plan = payload.get("plan")
        readiness = payload.get("readiness")
        return cls(
            side=payload.get("side"),
            state=payload.get("state"),
            selection_version=(
                _optional_text(payload.get("selection_version"))
                or SMC_SELECTION_VERSION
            ),
            contract_version=(
                _optional_text(payload.get("contract_version"))
                or SMC_SELECTION_CONTRACT_VERSION
            ),
            selected_candidate_id=_optional_text(payload.get("selected_candidate_id")),
            selected_zone_id=_optional_text(payload.get("selected_zone_id")),
            selected_setup_id=_optional_text(payload.get("selected_setup_id")),
            timeframe=_optional_text(payload.get("timeframe")),
            family=_optional_text(payload.get("family")),
            lifecycle_status=_optional_text(payload.get("lifecycle_status")),
            confirmation_state=_optional_text(payload.get("confirmation_state")),
            confirmation_rank=_optional_int(payload.get("confirmation_rank")),
            entry_visit_id=_optional_text(payload.get("entry_visit_id")),
            confirmation_event_id=_optional_text(
                payload.get("confirmation_event_id")
            ),
            quality_raw=_optional_int(payload.get("quality_raw")),
            quality_score=_optional_float(payload.get("quality_score")),
            b=_optional_float(payload.get("b")),
            q=_optional_float(payload.get("q")),
            l=_optional_float(payload.get("l")),
            c=_optional_float(payload.get("c")),
            total=_optional_float(payload.get("total")),
            zone_low=_optional_float(payload.get("zone_low")),
            zone_high=_optional_float(payload.get("zone_high")),
            plan=dict(plan) if isinstance(plan, dict) else None,
            plan_available=bool(payload.get("plan_available")),
            plan_zone_id=_optional_text(payload.get("plan_zone_id")),
            plan_setup_id=_optional_text(payload.get("plan_setup_id")),
            plan_rejection_codes=payload.get("plan_rejection_codes") or (),
            readiness=dict(readiness) if isinstance(readiness, dict) else None,
            selection_reason_codes=payload.get("selection_reason_codes") or (),
            candidate_trace=tuple(
                SmcCandidateTraceEntry.from_dict(entry)
                for entry in _sequence(payload.get("candidate_trace"))
            ),
            alternatives=tuple(
                SmcCandidateTraceEntry.from_dict(entry)
                for entry in _sequence(payload.get("alternatives"))
            ),
        )



@dataclass(frozen=True, slots=True)
class SmcSideScoringResult:
    """One side of the canonical SMC scoring output."""

    score: int | None
    breakdown: dict[str, Any]
    selected_zone: dict[str, Any] | None = None
    selected_zone_id: str | None = None
    selected_zone_type: str | None = None
    selected_zone_timeframe: str | None = None
    reason_codes: tuple[str, ...] = ()
    smc_reason: str = ""
    selected_zone_score: int | None = None
    selected_zone_quality_score: int | None = None
    selected_zone_relevance_score: int | None = None
    selected_zone_setup_score: int | None = None
    # Task 94: the final canonical selection of this side (candidate, quality,
    # lifecycle/confirmation and plan reference of the SAME setup).  It is plain
    # data written by the finalizer; this module never imports the planner, the
    # scorer or the coordinator.
    selection: "SmcSideSelection | None" = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "breakdown", dict(self.breakdown))
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        if self.selection is not None and not isinstance(
            self.selection, SmcSideSelection
        ):
            raise ValueError("selection must be an SmcSideSelection")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "score": self.score,
            "breakdown": dict(self.breakdown),
            "selected_zone": self.selected_zone,
            "selected_zone_id": self.selected_zone_id,
            "selected_zone_type": self.selected_zone_type,
            "selected_zone_timeframe": self.selected_zone_timeframe,
            "reason_codes": list(self.reason_codes),
            "smc_reason": self.smc_reason,
            "selected_zone_score": self.selected_zone_score,
            "selected_zone_quality_score": self.selected_zone_quality_score,
            "selected_zone_relevance_score": self.selected_zone_relevance_score,
            "selected_zone_setup_score": self.selected_zone_setup_score,
            "selection": (
                self.selection.to_dict() if self.selection is not None else None
            ),
        }
        return {key: value for key, value in payload.items() if value is not None}

    @classmethod
    def from_dict(cls, value: object) -> "SmcSideScoringResult":
        payload = value if isinstance(value, dict) else {}
        selected_zone = payload.get("selected_zone")
        selection = payload.get("selection")
        return cls(
            score=_optional_int(payload.get("score")),
            breakdown=_optional_dict(payload.get("breakdown")),
            selected_zone=(
                dict(selected_zone)
                if isinstance(selected_zone, dict)
                else None
            ),
            selected_zone_id=_optional_text(payload.get("selected_zone_id")),
            selected_zone_type=_optional_text(payload.get("selected_zone_type")),
            selected_zone_timeframe=_optional_text(
                payload.get("selected_zone_timeframe")
            ),
            reason_codes=_tuple_of_text(payload.get("reason_codes")),
            smc_reason=(_optional_text(payload.get("smc_reason")) or ""),
            selected_zone_score=_optional_int(payload.get("selected_zone_score")),
            selected_zone_quality_score=_optional_int(
                payload.get("selected_zone_quality_score")
            ),
            selected_zone_relevance_score=_optional_int(
                payload.get("selected_zone_relevance_score")
            ),
            selected_zone_setup_score=_optional_int(
                payload.get("selected_zone_setup_score")
            ),
            selection=(
                SmcSideSelection.from_dict(selection)
                if isinstance(selection, dict)
                else None
            ),
        )



@dataclass(frozen=True, slots=True)
class SmcScoringResult:
    """Canonical result containing both BUY and SELL side payloads.

    ``scoring_version`` is immutable provenance of the formula that produced
    this result.  The structure intentionally carries no scorer selection.
    """

    scoring_version: str
    contract_version: str = SMC_SCORING_CONTRACT_VERSION
    sides: Mapping[str, SmcSideScoringResult] = field(default_factory=dict)
    # R80-91-03 (option A): internal diagnostics of the canonical
    # evidence → candidate → B/Q/L/C → readiness/order chain for this snapshot.
    # It is deliberately NOT part of ``to_dict()``: the public/serialized
    # contract stays exactly as before and moving it there belongs to task 94.
    canonical_diagnostics: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        normalized = {
            side: payload
            for side, payload in self.sides.items()
            if side in VALID_SIDES
        }
        object.__setattr__(self, "sides", dict(normalized))

    def side(self, side: str) -> SmcSideScoringResult | None:
        return self.sides.get(side)

    @property
    def diagnostics(self) -> dict[str, Any] | None:
        """Internal canonical diagnostics of this snapshot (not serialized)."""

        return self.canonical_diagnostics

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "scoring_version": self.scoring_version,
            "sides": {
                side: self.sides[side].to_dict()
                for side in ("buy", "sell")
                if side in self.sides
            },
        }

    @classmethod
    def from_dict(cls, value: object) -> "SmcScoringResult":
        payload = value if isinstance(value, dict) else {}
        raw_sides = payload.get("sides")
        sides: dict[str, SmcSideScoringResult] = {}
        if isinstance(raw_sides, dict):
            for side in VALID_SIDES:
                side_payload = raw_sides.get(side)
                if isinstance(side_payload, dict):
                    sides[side] = SmcSideScoringResult.from_dict(side_payload)
        return cls(
            scoring_version=(
                _optional_text(payload.get("scoring_version"))
                or _CANONICAL_SCORER_VERSION
            ),
            contract_version=(
                _optional_text(payload.get("contract_version"))
                or SMC_SCORING_CONTRACT_VERSION
            ),
            sides=sides,
        )


def validate_smc_result(value: object) -> bool:
    """Return whether *value* is a structurally valid canonical SMC result.

    A valid result carries both BUY and SELL sides, each with a valid score and
    breakdown.  A missing or malformed side makes the result invalid so the
    caller can fail closed instead of synthesizing empty sides.
    """
    if not isinstance(value, SmcScoringResult):
        return False
    for side in ("buy", "sell"):
        side_result = value.side(side)
        if side_result is None:
            return False
        if not isinstance(side_result.score, int):
            return False
        if not isinstance(side_result.breakdown, dict):
            return False
    return True


def validate_smc_side_selection(value: object) -> bool:
    """Whether ONE final side selection satisfies the whole final invariant.

    A forged or foreign payload (one that never went through this constructor,
    e.g. a legacy/deserialized object) is re-checked against the same rules, so
    a projection or reader can refuse it instead of publishing a fabricated SMC
    raw.  The rules stay owned by ``SmcSideSelection.__post_init__``.
    """

    if not isinstance(value, SmcSideSelection):
        return False
    values = {
        item.name: getattr(value, item.name)
        for item in fields(SmcSideSelection)
    }
    try:
        SmcSideSelection(**values)
    except (ValueError, TypeError):
        return False
    return True


def _real_number(value: object, label: str) -> float:
    """A finite real scalar; ``bool`` is NOT a number on this contract (R100-01).

    Python makes ``True == 1`` and ``float(True) == 1.0``, so any comparison
    would happily accept a boolean that happens to land on the canonical value.
    Every scalar the final invariant reads goes through this gate first.
    """

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"SMC selection {label} must be a real number")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"SMC selection {label} must be finite")
    return number


def _canonical_raw(value: object, label: str = "quality_raw") -> int:
    """A real integer raw inside the canonical ``0..15`` range (no ``bool``)."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"SMC selection {label} must be an integer")
    if not 0 <= value <= SMC_QUALITY_RAW_MAX:
        raise ValueError(
            f"SMC selection {label} must be inside 0..{SMC_QUALITY_RAW_MAX}"
        )
    return value


def _validate_quality_arithmetic(selection: SmcSideSelection) -> None:
    """B/Q/L/C, total, quality_score and quality_raw must be one consistent S.

    This re-derives nothing new: it applies the single canonical formula
    (design §9, compatibility spec §2) to the numbers the result already
    carries, with the one round-half-up owner and no cap/penalty step.  A
    payload whose components disagree with its raw is refused instead of being
    published as a valid SMC score.

    Scalar typing is part of the same rule (R100-01): every number is checked to
    be a real, finite scalar and ``quality_raw`` a real integer before any
    arithmetic, so a boolean can never be read as the canonical value it equals.
    """

    features = (selection.b, selection.q, selection.l, selection.c)
    present = [value is not None for value in features]
    if any(present) and not all(present):
        raise ValueError("SMC selection must carry all of B/Q/L/C or none")

    if not all(present):
        # Evaluated-empty (`no_zone`) or unavailable: there is no S to report.
        if selection.total is not None:
            raise ValueError("SMC selection without B/Q/L/C cannot carry a total")
        if selection.quality_score is not None:
            score = _real_number(selection.quality_score, "quality_score")
            if score != 0.0:
                raise ValueError(
                    "SMC selection without B/Q/L/C keeps quality_score null or 0"
                )
        if selection.state == SELECTION_STATE_DATA_UNAVAILABLE:
            if selection.quality_raw is not None:
                raise ValueError("data unavailable keeps quality_raw null")
        elif _canonical_raw(selection.quality_raw) != 0:
            raise ValueError("an evaluated side without B/Q/L/C is the no-zone zero")
        return

    numbers = {
        name: _real_number(value, name)
        for name, value in zip(("b", "q", "l", "c"), features)
    }
    for name, number in numbers.items():
        if not 0.0 <= number <= 1.0:
            raise ValueError(f"SMC selection {name} must be inside [0, 1]")

    expected_total = (
        QUALITY_B_WEIGHT * numbers["b"]
        + QUALITY_Q_WEIGHT * numbers["q"]
        + QUALITY_L_WEIGHT * numbers["l"]
        + QUALITY_C_WEIGHT * numbers["c"]
    )
    if selection.total is None:
        raise ValueError("SMC selection total must equal 4B + 7Q + 2L + 2C")
    total = _real_number(selection.total, "total")
    if abs(total - expected_total) > 1e-9:
        raise ValueError("SMC selection total must equal 4B + 7Q + 2L + 2C")
    raw = _canonical_raw(selection.quality_raw)
    if raw != round_half_up(expected_total):
        raise ValueError("SMC selection quality_raw must be round_half_up(S)")
    if selection.quality_score is None:
        raise ValueError("SMC selection quality_score must equal 100*S/15")
    score = _real_number(selection.quality_score, "quality_score")
    expected_score = QUALITY_SCORE_SCALE * expected_total / QUALITY_S_MAX
    if abs(score - expected_score) > 1e-9:
        raise ValueError("SMC selection quality_score must equal 100*S/15")


def _validate_plan_identity(selection: SmcSideSelection) -> None:
    """An accepted plan must belong to the selected candidate/zone/setup.

    R100-01: without this, a final result could report one selected zone while
    carrying another zone's scenario.  Only ``evaluated`` promises a plan; the
    watch/no-zone/core-unavailable semantics are unchanged.
    """

    if selection.state != SELECTION_STATE_EVALUATED:
        return
    if selection.selected_candidate_id is None or selection.selected_zone_id is None:
        raise ValueError("an evaluated side requires the selected candidate identity")
    if selection.plan is None or selection.plan_available is not True:
        raise ValueError("an evaluated side requires an available plan")
    plan = selection.plan
    if plan.get("direction") != selection.side:
        raise ValueError("the plan must belong to the selected side")
    if plan.get("zone_id") != selection.selected_zone_id:
        raise ValueError("the plan must belong to the selected zone")
    if plan.get("setup_id") != selection.selected_setup_id:
        raise ValueError("the plan must belong to the selected setup")
    if selection.plan_zone_id != selection.selected_zone_id:
        raise ValueError("the plan reference must name the selected zone")
    if selection.plan_setup_id != selection.selected_setup_id:
        raise ValueError("the plan reference must name the selected setup")
    if selection.zone_low is None or selection.zone_high is None:
        raise ValueError("an evaluated side requires the selected zone band")
    # Same strict scalar rule as the quality numbers: the band is compared
    # against the plan, so a boolean must not stand in for a price level.
    band = (
        _real_number(selection.zone_low, "zone_low"),
        _real_number(selection.zone_high, "zone_high"),
    )
    plan_band = (
        _real_number(plan.get("entry_zone_low"), "plan.entry_zone_low"),
        _real_number(plan.get("entry_zone_high"), "plan.entry_zone_high"),
    )
    if plan_band != band:
        raise ValueError("the plan must be anchored on the selected zone band")


def validate_smc_selection_result(value: object) -> bool:
    """Return whether *value* is a final selection result (task 94/96, R100-01).

    The final result must carry exactly the two sides, each with a
    ``SmcSideSelection`` that satisfies the whole final invariant: the selected
    candidate identity, an available plan belonging to that same zone/setup and
    a B/Q/L/C breakdown consistent with ``total``/``quality_raw``/
    ``quality_score``.  A no-zone side is an evaluated ``0``, a core-unavailable
    side is ``null``; neither may certify a selection, so a malformed payload
    fails here instead of reaching a consumer as a usable setup.
    """

    if not isinstance(value, SmcScoringResult):
        return False
    if set(value.sides) != VALID_SIDES:
        return False
    for side in VALID_SIDES:
        side_result = value.side(side)
        selection = side_result.selection if side_result is not None else None
        if not validate_smc_side_selection(selection):
            return False
        if selection.side != side:
            return False
    return True


def smc_selection_of(side_result: object) -> SmcSideSelection | None:
    """Typed final selection of one side result, or ``None`` when absent."""

    selection = getattr(side_result, "selection", None)
    return selection if isinstance(selection, SmcSideSelection) else None


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def _sequence(value: object) -> Sequence[Any]:
    if isinstance(value, (list, tuple)):
        return value
    return ()


def _optional_dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _tuple_of_text(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(
        str(item).strip()
        for item in value
        if str(item).strip()
    )
