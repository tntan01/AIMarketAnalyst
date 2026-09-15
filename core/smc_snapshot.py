"""Shared SMC snapshot input seam (task 101).

One frozen input per cutoff, shared by every live and replay caller of the
canonical chain:

```text
cutoff + symbol metadata + SMC context + technical + M15 window + core verdict
  -> evaluator -> candidate order -> coordinator/planner -> final result
  -> projection/consumer -> composition/readiness/revalidation
```

The seam owns the *input boundary* only:

* the cutoff is frozen once and must be timezone-aware; it is never created from
  ``datetime.now()`` inside the chain, and a missing/naive cutoff fails closed
  with the canonical reason instead of being guessed;
* every timeframe is filtered with :func:`core.market_models.closed_candles_at_cutoff`
  before the context is built, so a forming or future candle can neither create
  structure, a zone nor a confirmation;
* the core-data verdict comes from :func:`core.smc_history.assess_smc_history`
  over the D1/H4/H1 groups (data spec §5/§6) — a group that is missing, too
  short or broken makes the side ``DATA_UNAVAILABLE`` instead of "no zone";
* M15 stays *optional* input: a missing or unusable M15 window is a readiness
  fact reported by the evaluator, never a core-data reason and never a zero;
* symbol metadata (tick size and its provenance) travels with the snapshot.

The evaluator/coordinator are invoked exactly once per snapshot through
:func:`evaluate_smc_snapshot`; no caller may rebuild the chain for the same
cutoff.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from math import isfinite
from typing import Any, Callable, Mapping, Sequence

from core.market_models import closed_candles_at_cutoff
from core.smc_history import assess_smc_history
from core.smc_quality import evaluate_candidate_sets
from core.smc_selection import (
    SideSelection,
    finalize_canonical_result,
    select_canonical_sides,
)
from core.smc_models import SmcCandidateSet
from core.smc_scoring_result import SmcScoringResult

SMC_SNAPSHOT_INPUT_VERSION = "smc-snapshot-input-v1"
SMC_SNAPSHOT_EVALUATION_VERSION = "smc-snapshot-evaluation-v1"

# Timeframes whose absence makes the canonical verdict impossible (data spec
# §5: D1/H4/H1 are required for the structure/zone thesis).
CORE_TIMEFRAMES = ("D1", "H4", "H1")
M15_TIMEFRAME = "M15"
VALID_SNAPSHOT_TIMEFRAMES = frozenset((*CORE_TIMEFRAMES, M15_TIMEFRAME))

# Reason codes owned by this seam (data spec §6).  They are canonical
# data-quality reasons: a side carrying one is ``DATA_UNAVAILABLE`` with
# ``quality_raw=null``, never an evaluated zero.
SNAPSHOT_CUTOFF_MISSING = "SMC_CUTOFF_MISSING"
SNAPSHOT_CUTOFF_NAIVE = "SMC_CUTOFF_NAIVE"
SNAPSHOT_SYMBOL_MISSING = "SMC_SYMBOL_MISSING"
SNAPSHOT_CONTEXT_MISSING = "SMC_CONTEXT_MISSING"
SNAPSHOT_TECHNICAL_MISSING = "SMC_TECHNICAL_MISSING"
# D101-02: a missing tick size is NOT a core/snapshot verdict.  It is a
# dependency of the individual rules that quantize price, so the canonical
# evaluator fails those candidates closed with ``SMC_TICK_SIZE_UNAVAILABLE``
# (``core.smc_geometry.GEOMETRY_TICK_SIZE_UNAVAILABLE``).  The snapshot records
# the fact and its provenance so the reason stays traceable.
SNAPSHOT_TICK_SIZE_UNAVAILABLE = "SMC_TICK_SIZE_UNAVAILABLE"
SNAPSHOT_EMPTY_CANDLES = "SMC_CANDLES_MISSING"

# Tick-size provenance (data spec §3): the only sanctioned fallback is the
# broker ``point``, and it must be labelled.
TICK_SIZE_SOURCE_BROKER = "trade_tick_size"
TICK_SIZE_SOURCE_POINT_FALLBACK = "point_fallback"

ContextBuilder = Callable[..., dict[str, Any]]
PlanFor = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class SmcSnapshotInput:
    """The frozen input of one canonical evaluation at one cutoff."""

    as_of: datetime | None
    symbol: str
    smc: Mapping[str, Any] | None
    technical: Mapping[str, Any] | None
    candles: Mapping[str, tuple[Any, ...]] = field(default_factory=dict)
    m15_candles: tuple[Any, ...] | None = None
    m15_as_of: datetime | None = None
    tick_size: float | None = None
    tick_size_source: str | None = None
    core_reason_codes: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)
    contract_version: str = SMC_SNAPSHOT_INPUT_VERSION

    @property
    def usable(self) -> bool:
        """Whether the canonical chain may conclude anything for this snapshot."""

        return (
            self.as_of is not None
            and self.smc is not None
            and self.technical is not None
            and not self.core_reason_codes
        )

    @property
    def m15_available(self) -> bool:
        return bool(self.m15_candles) and self.m15_as_of is not None

    def evaluator_kwargs(self) -> dict[str, Any]:
        """The exact keyword set the canonical evaluator consumes."""

        return {
            "as_of": self.as_of,
            "core_reason_codes": self.core_reason_codes,
            "m15_candles": self.m15_candles,
            "m15_as_of": self.m15_as_of,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "as_of": _text(self.as_of),
            "symbol": self.symbol,
            "tick_size": self.tick_size,
            "tick_size_source": self.tick_size_source,
            "m15_as_of": _text(self.m15_as_of),
            "m15_candle_count": len(self.m15_candles or ()),
            "core_reason_codes": list(self.core_reason_codes),
            "provenance": dict(self.provenance),
        }


@dataclass(frozen=True, slots=True)
class SmcSnapshotEvaluation:
    """The single canonical outcome of one snapshot (tasks 101–103)."""

    snapshot: SmcSnapshotInput
    candidate_sets: Mapping[str, SmcCandidateSet]
    selections: Mapping[str, SideSelection]
    result: SmcScoringResult
    evaluation_version: str = SMC_SNAPSHOT_EVALUATION_VERSION

    def selection(self, side: str) -> SideSelection | None:
        value = self.selections.get(str(side or "").strip().lower())
        return value if isinstance(value, SideSelection) else None

    def side_result(self, side: str):
        return self.result.side(side)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluation_version": self.evaluation_version,
            "snapshot": self.snapshot.to_dict(),
            "sides": {
                side: _selection_payload(self.selection(side))
                for side in ("buy", "sell")
            },
        }


def build_smc_snapshot(
    candles: Mapping[str, Sequence[Any]] | None,
    *,
    symbol: Any,
    as_of: Any,
    m15_as_of: Any = None,
    tick_size: Any = None,
    tick_size_source: Any = None,
    scan_interval_min: int = 15,
    context_builder: ContextBuilder | None = None,
    technical_builder: Callable[..., dict[str, Any]] | None = None,
    core_reason_codes: Sequence[str] = (),
) -> SmcSnapshotInput:
    """Freeze one snapshot from the existing candle source.

    The builder filters every supplied timeframe at the cutoff *before* the SMC
    context and the technical snapshot are derived, so the whole chain sees the
    same closed-candle set.  Missing or unusable inputs are reported as explicit
    core reason codes; nothing is filled in, defaulted or shifted forward.
    """

    reasons: list[str] = [str(code) for code in core_reason_codes if str(code)]
    cutoff = _utc_cutoff(as_of, reasons)
    normalized_symbol = str(symbol or "").strip()
    if not normalized_symbol:
        reasons.append(SNAPSHOT_SYMBOL_MISSING)

    source = candles if isinstance(candles, Mapping) else {}
    filtered: dict[str, tuple[Any, ...]] = {}
    for timeframe in (*CORE_TIMEFRAMES, M15_TIMEFRAME):
        values = source.get(timeframe)
        if values is None:
            continue
        if cutoff is None:
            # Without a boundary the closed set cannot be established, so an
            # unfiltered list is never passed on as if it were closed.
            continue
        filtered[timeframe] = closed_candles_at_cutoff(
            list(values), timeframe, cutoff
        )

    if cutoff is not None:
        for timeframe in CORE_TIMEFRAMES:
            if not filtered.get(timeframe):
                reasons.append(SNAPSHOT_EMPTY_CANDLES)
                break
        reasons.extend(_core_history_reasons(filtered, normalized_symbol))

    m15_cutoff = _utc_cutoff(m15_as_of, reasons) if m15_as_of is not None else cutoff
    m15_candles = filtered.get(M15_TIMEFRAME)
    metadata = _tick_metadata(tick_size, tick_size_source)

    smc: Mapping[str, Any] | None = None
    technical: Mapping[str, Any] | None = None
    if cutoff is not None:
        # D101-01: the default producer is the canonical façade, so the
        # evaluator receives canonical evidence.  ``context_builder`` stays an
        # injection point for replay/tests; the legacy public builder is never
        # the default here.
        builder = (
            context_builder if context_builder is not None else _context_builder()
        )
        smc = builder(
            list(filtered.get("D1") or ()),
            list(filtered.get("H4") or ()),
            list(filtered.get("H1") or ()),
            scan_interval_min=scan_interval_min,
            symbol=normalized_symbol,
            as_of=cutoff,
            tick_size=metadata["tick_size"],
        )
        technical = _technical(technical_builder, filtered)
        if not isinstance(smc, Mapping):
            reasons.append(SNAPSHOT_CONTEXT_MISSING)
        if not isinstance(technical, Mapping):
            reasons.append(SNAPSHOT_TECHNICAL_MISSING)

    deduped = tuple(dict.fromkeys(reason for reason in reasons if reason))
    return SmcSnapshotInput(
        as_of=cutoff,
        symbol=normalized_symbol,
        smc=smc,
        technical=technical,
        candles=filtered,
        m15_candles=m15_candles,
        m15_as_of=m15_cutoff,
        tick_size=metadata["tick_size"],
        tick_size_source=metadata["tick_size_source"],
        core_reason_codes=deduped,
        provenance=_provenance(
            source, filtered, cutoff, m15_cutoff, metadata
        ),
    )


def freeze_smc_snapshot(
    snapshot: SmcSnapshotInput,
    *,
    smc: Any = None,
    technical: Any = None,
    core_reason_codes: Sequence[str] = (),
) -> SmcSnapshotInput:
    """Attach an externally built context/technical pair to a built snapshot.

    Only used where the existing producer already derived those two values from
    the same closed-candle set; the cutoff, M15 window and metadata are kept.
    """

    if not isinstance(snapshot, SmcSnapshotInput):
        raise ValueError("freeze_smc_snapshot requires an SmcSnapshotInput")
    reasons = list(snapshot.core_reason_codes)
    reasons.extend(str(code) for code in core_reason_codes if str(code))
    resolved_smc = snapshot.smc if smc is None else smc
    resolved_technical = snapshot.technical if technical is None else technical
    if not isinstance(resolved_smc, Mapping):
        reasons.append(SNAPSHOT_CONTEXT_MISSING)
    if not isinstance(resolved_technical, Mapping):
        reasons.append(SNAPSHOT_TECHNICAL_MISSING)
    return replace(
        snapshot,
        smc=resolved_smc,
        technical=resolved_technical,
        core_reason_codes=tuple(dict.fromkeys(reason for reason in reasons if reason)),
    )


def evaluate_smc_snapshot(
    snapshot: SmcSnapshotInput,
    *,
    min_rr: Any | None = None,
    plan_for: PlanFor | None = None,
    snapshot_metadata: Mapping[str, Any] | None = None,
    external_status: Mapping[str, str] | None = None,
    external_reason_codes: Mapping[str, Sequence[str]] | None = None,
) -> SmcSnapshotEvaluation:
    """Run evaluator -> coordinator -> finalizer exactly once for *snapshot*.

    Every caller (Scanner, Analyze, replay) receives the same object, so the
    chain cannot be rebuilt twice for one cutoff and the three routes can only
    disagree if their snapshot input differs.
    """

    if not isinstance(snapshot, SmcSnapshotInput):
        raise ValueError("evaluate_smc_snapshot requires an SmcSnapshotInput")
    technical = snapshot.technical if isinstance(snapshot.technical, Mapping) else {}
    candidate_sets = evaluate_candidate_sets(
        dict(snapshot.smc or {}),
        dict(technical),
        **snapshot.evaluator_kwargs(),
    )
    metadata = snapshot_metadata if snapshot_metadata is not None else {}
    selections = select_canonical_sides(
        candidate_sets,
        technical,
        min_rr=min_rr,
        plan_for=plan_for,
        snapshot_metadata=metadata,
        external_status=external_status,
        external_reason_codes=external_reason_codes,
    )
    return SmcSnapshotEvaluation(
        snapshot=snapshot,
        candidate_sets=candidate_sets,
        selections=selections,
        result=finalize_canonical_result(selections),
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _utc_cutoff(value: Any, reasons: list[str]) -> datetime | None:
    """Normalize one cutoff, recording the canonical reason when unusable."""

    if value is None or (isinstance(value, str) and not value.strip()):
        if SNAPSHOT_CUTOFF_MISSING not in reasons:
            reasons.append(SNAPSHOT_CUTOFF_MISSING)
        return None
    parsed = value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            if SNAPSHOT_CUTOFF_MISSING not in reasons:
                reasons.append(SNAPSHOT_CUTOFF_MISSING)
            return None
    if not isinstance(parsed, datetime):
        if SNAPSHOT_CUTOFF_MISSING not in reasons:
            reasons.append(SNAPSHOT_CUTOFF_MISSING)
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        if SNAPSHOT_CUTOFF_NAIVE not in reasons:
            reasons.append(SNAPSHOT_CUTOFF_NAIVE)
        return None
    return parsed.astimezone(timezone.utc)


def _core_history_reasons(
    filtered: Mapping[str, tuple[Any, ...]],
    symbol: str,
) -> list[str]:
    """Core-data verdict of the D1/H4/H1 groups (data spec §5/§6).

    Only the reasons that make the thesis impossible are promoted: a missing or
    too-short group, invalid candles, an in-session coverage hole and a missing
    ATR warm-up.  M15 is deliberately absent here — it is readiness, not core
    data, and its absence must never be reported as a core failure.
    """

    reasons: list[str] = []
    for timeframe in CORE_TIMEFRAMES:
        values = filtered.get(timeframe) or ()
        coverage = assess_smc_history(values, timeframe, symbol=symbol or None)
        if coverage.status == "complete":
            continue
        reasons.extend(coverage.reason_codes)
    return reasons


def _tick_metadata(tick_size: Any, source: Any) -> dict[str, Any]:
    if isinstance(tick_size, bool):
        return {"tick_size": None, "tick_size_source": None}
    try:
        number = float(tick_size)
    except (TypeError, ValueError, OverflowError):
        return {"tick_size": None, "tick_size_source": None}
    if not isfinite(number) or number <= 0:
        return {"tick_size": None, "tick_size_source": None}
    text = str(source or "").strip()
    return {
        "tick_size": number,
        "tick_size_source": text or TICK_SIZE_SOURCE_BROKER,
    }


def _context_builder() -> ContextBuilder:
    """The canonical context producer (D101-01).

    ``core.smc_context.build_smc_context`` is the LEGACY route and is kept for
    its approved callers; the snapshot seam uses the canonical façade so the
    evaluator sees canonical evidence on the same closed-candle set.
    """

    from core.smc_canonical_context import build_canonical_smc_context

    return build_canonical_smc_context


def _technical(
    builder: Callable[..., dict[str, Any]] | None,
    filtered: Mapping[str, tuple[Any, ...]],
) -> Mapping[str, Any] | None:
    if builder is None:
        from core.technical_context import build_technical_snapshot

        builder = build_technical_snapshot
    return builder(
        list(filtered.get("D1") or ()),
        list(filtered.get("H4") or ()),
        list(filtered.get("H1") or ()),
    )


def _provenance(
    source: Mapping[str, Any],
    filtered: Mapping[str, tuple[Any, ...]],
    cutoff: datetime | None,
    m15_cutoff: datetime | None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    tick = metadata if isinstance(metadata, Mapping) else {}
    return {
        # D101-02: the tick dependency travels as provenance.  It is reported
        # (and carried on the snapshot) without turning the snapshot into a
        # core-data failure.
        "tick_size_status": (
            "available"
            if tick.get("tick_size") is not None
            else SNAPSHOT_TICK_SIZE_UNAVAILABLE
        ),
        "timeframes": {
            timeframe: {
                "raw_count": len(source.get(timeframe) or ()),
                "eligible_count": len(filtered.get(timeframe) or ()),
                "first_open_at": _open_at(filtered.get(timeframe), first=True),
                "last_open_at": _open_at(filtered.get(timeframe), first=False),
            }
            for timeframe in (*CORE_TIMEFRAMES, M15_TIMEFRAME)
            if timeframe in source
        },
        "cutoff": _text(cutoff),
        "m15_cutoff": _text(m15_cutoff),
    }


def _open_at(values: Sequence[Any] | None, *, first: bool) -> str | None:
    items = list(values or ())
    if not items:
        return None
    candle = items[0] if first else items[-1]
    return _text(getattr(candle, "time", None))


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _selection_payload(selection: SideSelection | None) -> dict[str, Any]:
    if selection is None:
        return {}
    return {
        "state": selection.state,
        "selected_zone_id": selection.selected_zone_id,
        "selected_setup_id": selection.selected_setup_id,
        "quality_raw": selection.selected_quality_raw,
        "plan_available": selection.plan_available,
        "plan_rejection_codes": list(selection.plan_rejection_codes),
        "selection_reason_codes": list(selection.selection_reason_codes),
        "readiness_status": (
            selection.readiness.status if selection.readiness is not None else None
        ),
    }


__all__ = [
    "CORE_TIMEFRAMES",
    "M15_TIMEFRAME",
    "SMC_SNAPSHOT_EVALUATION_VERSION",
    "SMC_SNAPSHOT_INPUT_VERSION",
    "SNAPSHOT_CONTEXT_MISSING",
    "SNAPSHOT_CUTOFF_MISSING",
    "SNAPSHOT_CUTOFF_NAIVE",
    "SNAPSHOT_EMPTY_CANDLES",
    "SNAPSHOT_SYMBOL_MISSING",
    "SNAPSHOT_TECHNICAL_MISSING",
    "SNAPSHOT_TICK_SIZE_UNAVAILABLE",
    "TICK_SIZE_SOURCE_BROKER",
    "TICK_SIZE_SOURCE_POINT_FALLBACK",
    "SmcSnapshotEvaluation",
    "SmcSnapshotInput",
    "build_smc_snapshot",
    "evaluate_smc_snapshot",
    "freeze_smc_snapshot",
]
