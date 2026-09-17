"""Shared versioned SMC selection contract for downstream consumers."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Mapping

from core.smc_scoring_result import (
    SELECTION_STATE_EVALUATED,
    SmcScoringResult,
    SmcSideSelection,
    smc_selection_of,
    validate_smc_result,
    validate_smc_selection_result,
    validate_smc_side_selection,
)


SMC_CONSUMER_CONTRACT_VERSION = "smc-consumer-v2"

# How a reader may present one side's SMC selection (task 128, P0):
# ``current`` is the only status that may be rendered as the result of the
# logic running now.  ``historical`` may be shown as a stored record with its
# own meaning; ``unavailable`` may not be shown at all.
SMC_READ_CURRENT = "current"
SMC_READ_HISTORICAL = "historical"
SMC_READ_UNAVAILABLE = "unavailable"
VALID_SMC_READ_STATUSES = frozenset(
    {SMC_READ_CURRENT, SMC_READ_HISTORICAL, SMC_READ_UNAVAILABLE}
)

# Safe reason codes of the read boundary itself (technical traceability, never
# a user-facing sentence).
SMC_READ_NO_SIDE = "SMC_READ_NO_SIDE"
SMC_READ_NO_SELECTION = "SMC_READ_NO_SELECTION"
SMC_READ_SELECTION_INVALID = "SMC_READ_SELECTION_INVALID"
# The payload carries the Scanner selection carrier but not the canonical block
# that travels with it: it is a stored/older payload, not a live result.
SMC_READ_CARRIER_WITHOUT_BLOCK = "SMC_READ_CARRIER_WITHOUT_BLOCK"
# F-LA-01: the carrier's ``protected_swing`` disagrees with the record the
# persistence block certified for the SAME side.  The selection stays readable
# (only this one additive field is affected), but the field is NOT current: it
# is withheld and this code says why, so no consumer can draw a level the
# certification does not support.
SMC_READ_PROTECTED_SWING_MISMATCH = "SMC_READ_PROTECTED_SWING_MISMATCH"


@dataclass(frozen=True, slots=True)
class SmcSelectionRead:
    """The outcome of reading one side's SMC selection (task 128, P0).

    ``selection`` is present ONLY for :data:`SMC_READ_CURRENT`.  A historical or
    unavailable read carries the reason codes of the verdict instead, so a
    caller can explain the absence without ever rendering the payload.
    """

    status: str
    side: str = ""
    selection: dict[str, Any] | None = field(default=None, repr=False)
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in VALID_SMC_READ_STATUSES:
            raise ValueError(f"Invalid SMC read status: {self.status}")
        if self.status != SMC_READ_CURRENT and self.selection is not None:
            raise ValueError("only a current read may carry a selection")
        object.__setattr__(
            self, "reason_codes", tuple(str(code) for code in self.reason_codes)
        )

    @property
    def is_current(self) -> bool:
        return self.status == SMC_READ_CURRENT

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "side": self.side,
            "reason_codes": list(self.reason_codes),
        }

# R114-01: the Analyze scenario builder consumes the risk-plan "preferred zone"
# shape (see ``core.risk_engine.build_trade_plan``).  The canonical FINAL
# selection is converted into that shape here, at the consumer boundary, so the
# scenario reads the SAME candidate the coordinator accepted.
#
# This is a READER: it copies the selected zone/setup identity, the selected band
# and the plan reference of that same candidate.  It never looks for another
# zone and never recomputes quality/B-Q-L-C, geometry, confirmation, lifecycle,
# score or the plan itself.
SELECTED_ZONE_SOURCE = "smc_selected"
PREFERRED_ZONE_PROVENANCE = "smc_canonical_selection"
# The directional zone type of the selection's own side.  ``risk_engine``
# matches a preferred zone against the side through this field, and the
# canonical selection's ``family`` (fvg / order_block / supply / demand) is not
# itself a zone type a direction can be matched against.
_BUY_ZONE_TYPE = "demand_zone"
_SELL_ZONE_TYPE = "supply_zone"


def build_smc_consumer_from_canonical_result(
    *,
    result: SmcScoringResult | None,
) -> dict[str, Any]:
    """Build the decision-path consumer from one canonical scorer result.

    The canonical result already carries the selected zone for each side, so no
    shadow/legacy selection or context lookup is needed.  A malformed or
    incomplete result is rejected rather than silently producing empty sides.

    Task 107: the side payload also carries the FINAL ``selection`` — the
    selected candidate, its B/Q/L/C quality, lifecycle/confirmation evidence,
    readiness verdict and the plan reference of the SAME setup.  Consumers and
    the scenario producer read from there; the legacy ``selected_zone`` keys are
    kept only so stored/legacy payload readers keep working (removal condition:
    architecture review §9.4 lot 2E, after task 116 is APPROVED).
    """

    # A result that carries final selections is held to the FINAL invariant
    # (task 94/96), which is the owner of the canonical contract.  A stored
    # payload written before the canonical path has no selections and keeps the
    # legacy structural check, so history stays readable without weakening the
    # live path.
    if _carries_selection(result):
        if not validate_smc_selection_result(result):
            raise ValueError(
                "SMC final selection result is malformed or disagrees with its "
                "own quality/plan identity"
            )
    elif not validate_smc_result(result):
        raise ValueError("SMC scoring result is malformed or missing a side")

    contract: dict[str, Any] = {
        "contract_version": SMC_CONSUMER_CONTRACT_VERSION,
        "sides": {},
    }
    for side in ("buy", "sell"):
        side_result = (
            result.side(side)
            if isinstance(result, SmcScoringResult)
            else None
        )
        selection = smc_selection_of(side_result)
        contract["sides"][side] = {
            "side": side,
            "scoring_version": (
                result.scoring_version
                if isinstance(result, SmcScoringResult)
                else None
            ),
            "selection": (
                selection.to_dict() if selection is not None else None
            ),
            "readiness": (
                dict(selection.readiness)
                if selection is not None and isinstance(selection.readiness, dict)
                else None
            ),
            "plan": (
                dict(selection.plan)
                if selection is not None and isinstance(selection.plan, dict)
                else None
            ),
            "plan_available": bool(
                selection is not None and selection.plan_available
            ),
            "selected_zone": (
                side_result.selected_zone if side_result is not None else None
            ),
            "selected_zone_id": (
                side_result.selected_zone_id
                if side_result is not None
                else None
            ),
            "selected_zone_type": (
                side_result.selected_zone_type
                if side_result is not None
                else None
            ),
            "selected_zone_timeframe": (
                side_result.selected_zone_timeframe
                if side_result is not None
                else None
            ),
            "selected_zone_quality_score": (
                side_result.selected_zone_quality_score
                if side_result is not None
                else None
            ),
            "selected_zone_relevance_score": (
                side_result.selected_zone_relevance_score
                if side_result is not None
                else None
            ),
            "selected_zone_setup_score": (
                side_result.selected_zone_setup_score
                if side_result is not None
                else None
            ),
            "score_breakdown": (
                side_result.breakdown if side_result is not None else {}
            ),
        }
    return contract


def read_canonical_selection(
    source: dict[str, Any] | None,
    side: str,
) -> "SmcSelectionRead":
    """Read one side's canonical SMC selection, gated by the document verdict.

    *source* is either an analysis result (``analysis_result``) or the row/
    document that carries one.  Three outcomes, and only the first may be
    rendered as the result of the CURRENT logic:

    * :data:`SMC_READ_CURRENT` — a live in-memory result, or a stored payload the
      persistence owner certified as canonical-compatible, whose selection also
      satisfies the final invariant;
    * :data:`SMC_READ_HISTORICAL` — a stored payload produced by another
      identity: readable "as it was created", never as a current verdict;
    * :data:`SMC_READ_UNAVAILABLE` — incompatible/corrupted bytes, no selection,
      or a selection that breaks its own invariant: nothing may be shown.

    The verdict is the persistence owner's (``classify_persisted_smc``); this
    boundary only applies it, so tooltip, detail panel and chart cannot disagree
    about whether a payload is current.  A payload that carries no persistence
    block and no stored-document marker is a live in-memory result from this
    process and is read as before — the one shape the writer never produces on
    disk.

    This is a READER: it never scores, re-selects a zone, rebuilds a
    confirmation, revalidates, or falls back to ``selected_zone*``/legacy SMC.
    """

    normalized = side if side in ("buy", "sell") else ""
    document, result = _split_source(source)
    if not normalized or result is None:
        return SmcSelectionRead(
            status=SMC_READ_UNAVAILABLE,
            side=normalized,
            reason_codes=(SMC_READ_NO_SIDE,) if not normalized else (),
        )

    status, reason_codes = _document_read_status(document, result)
    if status != SMC_READ_CURRENT:
        return SmcSelectionRead(status=status, side=normalized, reason_codes=reason_codes)

    selection, swing_mismatch = _selection_payload_of(result, normalized)
    if selection is None:
        return SmcSelectionRead(
            status=SMC_READ_UNAVAILABLE,
            side=normalized,
            reason_codes=(SMC_READ_NO_SELECTION,),
        )
    if not _selection_is_self_consistent(selection, normalized):
        return SmcSelectionRead(
            status=SMC_READ_UNAVAILABLE,
            side=normalized,
            reason_codes=(SMC_READ_SELECTION_INVALID,),
        )
    if swing_mismatch:
        # The selection itself is current; only the protected-swing FIELD is
        # withheld (it is already absent from ``selection``), and the reason
        # travels with the read so the tooltip, the detail panel and the chart
        # all state the same thing instead of each guessing.
        return SmcSelectionRead(
            status=SMC_READ_CURRENT,
            side=normalized,
            selection=selection,
            reason_codes=(SMC_READ_PROTECTED_SWING_MISMATCH,),
        )
    return SmcSelectionRead(
        status=SMC_READ_CURRENT, side=normalized, selection=selection
    )


def _split_source(
    source: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Split a row/document from its analysis result.

    A row or document is a mapping with an ``analysis_result`` mapping inside;
    anything else is treated as an analysis result itself.
    """

    if not isinstance(source, dict):
        return None, None
    inner = source.get("analysis_result")
    if isinstance(inner, dict):
        return source, inner
    return None, source


def _document_read_status(
    document: dict[str, Any] | None,
    result: dict[str, Any],
) -> tuple[str, tuple[str, ...]]:
    """The read status of a payload, from its own bytes.

    A stored document is recognised by the SMC block the writer stamps or by the
    observability envelope it is written in; both are absent from the in-memory
    results the routes produce.  Anything recognised as stored goes through the
    persistence classifier — including a document whose block is missing, which
    is *not* the same as a live result and must not be trusted as one.
    """

    from core.smc_persistence import (
        SMC_PAYLOAD_CANONICAL,
        SMC_PAYLOAD_HISTORICAL,
        classify_persisted_smc,
    )

    if _looks_like_smc_block(result):
        # A bare SMC block (the shape a cache record embeds) is classified as
        # itself, so a cached payload cannot slip in as a live result either.
        verdict = classify_persisted_smc({"smc_scoring": result})
    elif "smc_scoring" in result or _looks_like_document(document, result):
        verdict = classify_persisted_smc(
            document if document is not None else {"analysis_result": result}
        )
    elif _carries_carrier_without_block(result):
        # The Scanner carrier travels WITH the canonical block (task 128
        # follow-up): the route that publishes ``smc_selection`` also forwards
        # the block into the same analysis result.  A payload carrying the
        # carrier but no block was therefore written by something else — an
        # older document, or a document whose block was stripped — and unwrapping
        # it must not turn it into a live result.  No caller-supplied flag is
        # involved: the payload's own shape decides.
        return SMC_READ_UNAVAILABLE, (SMC_READ_CARRIER_WITHOUT_BLOCK,)
    else:
        return SMC_READ_CURRENT, ()

    codes = tuple(str(code) for code in verdict.reason_codes)
    if verdict.status == SMC_PAYLOAD_CANONICAL:
        return SMC_READ_CURRENT, ()
    if verdict.status == SMC_PAYLOAD_HISTORICAL:
        return SMC_READ_HISTORICAL, codes
    return SMC_READ_UNAVAILABLE, codes


def _looks_like_smc_block(result: dict[str, Any]) -> bool:
    """Whether the payload IS the SMC diagnostics block (cache-record shape)."""

    return isinstance(result.get("sides"), Mapping) and "contract_version" in result


def _carries_carrier_without_block(result: dict[str, Any]) -> bool:
    """Whether the payload carries a per-side selection with no canonical block.

    Only the Scanner route publishes ``smc_selection``, and it publishes the
    canonical block beside it; a payload with one and not the other cannot come
    from the running logic.
    """

    direct = result.get("smc_selection")
    if not isinstance(direct, Mapping):
        return False
    return any(isinstance(value, Mapping) for value in direct.values())


def _looks_like_document(
    document: dict[str, Any] | None,
    result: dict[str, Any],
) -> bool:
    """Whether the payload came off disk rather than from a live evaluation.

    The analysis-document writer (``scanner_observability.build_analysis_document``)
    always stamps ``observability_version`` next to the analysis result; no live
    route produces that key, and a live row is a different shape entirely.
    """

    for payload in (document, result):
        if isinstance(payload, dict) and "observability_version" in payload:
            return True
    return False


def _certified_selection_payload(
    result: dict[str, Any],
    side: str,
) -> dict[str, Any] | None:
    """The selection the persistence BLOCK certifies for *side*, if present.

    The block is the only part of a Scanner payload the persistence owner
    classifies (``classify_persisted_smc``).  It is therefore the certification
    for every field the two carriers disagree about; the carrier summary beside
    it is a projection of the same finalizer and carries no authority of its own.
    """

    from core.smc_persistence import consumer_sides_of, smc_block_of

    block = smc_block_of(result)
    if not block:
        return None
    item = consumer_sides_of(block).get(side)
    raw = item.get("selection") if isinstance(item, dict) else None
    return dict(raw) if isinstance(raw, dict) else None


def _bind_protected_swing(
    selection: dict[str, Any],
    certified: dict[str, Any],
) -> tuple[dict[str, Any] | None, bool]:
    """Bind ONE side's protected swing to the record the block certified.

    Returns ``(published, mismatch)``.  The block is authoritative for this
    field (F-LA-01), so:

    * both sides carry the same record — publish it (the corpus case: the
      carrier summary and the block are projections of one selection);
    * the carrier omits the field — the certified record supplies it, because
      binding means the certified value is the published one;
    * the block certified NO record while the carrier carries one — that record
      was injected and is withheld;
    * both carry a record and they differ — neither is published, because the
      bytes disagree about the very thing the field asserts.

    Nothing is recomputed, re-measured or substituted: the only two values this
    can publish are the certified record or ``None``.  A withheld record is not
    an absent one — the caller raises the mismatch reason so the absence is
    explained rather than silent.
    """

    carrier_value = selection.get("protected_swing")
    certified_value = certified.get("protected_swing")
    if carrier_value is None and certified_value is None:
        return None, False
    if carrier_value is None:
        return certified_value, False
    if certified_value is None:
        return None, True
    if carrier_value != certified_value:
        return None, True
    return carrier_value, False


def _selection_payload_of(
    result: dict[str, Any], side: str
) -> tuple[dict[str, Any] | None, bool]:
    """The raw selection mapping of *side*, and whether its swing was withheld.

    Three carrier keys are accepted because the same payload travels under
    different names: ``smc_selection`` (the per-side summary a Scanner row
    publishes), ``smc_consumer`` (the Analyze route's result key) and
    ``consumer_contract`` (the key inside the persisted SMC block).  They are the
    same canonical selection written by the same finalizer.

    F-LA-01: when a persistence block is present too, its selection is the
    certification for the ``protected_swing`` field, so the value published here
    is the one the block carries — never the carrier's copy of it.  Every other
    field is untouched, and a payload with no block (a live in-memory result) is
    read exactly as before.
    """

    selection: dict[str, Any] | None = None
    direct = result.get("smc_selection")
    if isinstance(direct, dict):
        candidate = direct.get(side)
        if isinstance(candidate, dict):
            selection = dict(candidate)

    if selection is None:
        for key in ("smc_consumer", "consumer_contract"):
            consumer = result.get(key)
            sides = consumer.get("sides") if isinstance(consumer, dict) else None
            item = sides.get(side) if isinstance(sides, dict) else None
            raw = item.get("selection") if isinstance(item, dict) else None
            if not isinstance(raw, dict):
                continue
            selection = dict(raw)
            readiness = item.get("readiness")
            if isinstance(readiness, dict):
                for name, target in (
                    ("status", "readiness_status"),
                    ("smc_state", "smc_state"),
                    ("m15_status", "m15_status"),
                    ("reason_codes", "readiness_reason_codes"),
                ):
                    if selection.get(target) is None and readiness.get(name) is not None:
                        selection[target] = readiness[name]
            break
    if selection is None:
        return None, False

    certified = _certified_selection_payload(result, side)
    if certified is None:
        return selection, False
    published, mismatch = _bind_protected_swing(selection, certified)
    selection["protected_swing"] = published
    return selection, mismatch


def canonical_selection_of(
    result: dict[str, Any] | None,
    side: str,
) -> dict[str, Any] | None:
    """The CURRENT canonical SMC selection of *side*, or ``None``.

    Thin gate over :func:`read_canonical_selection`: a stored payload that is not
    certified current (historical, incompatible, corrupted) yields ``None``, so
    every caller that renders the result — the UI panels and the chart — stops
    drawing it without having to know about persistence.  Callers that must tell
    "historical" from "unavailable" use the read itself.
    """

    read = read_canonical_selection(result, side)
    return read.selection if read.status == SMC_READ_CURRENT else None


def _selection_is_self_consistent(selection: dict[str, Any], side: str) -> bool:
    """Whether a selection payload satisfies the canonical final invariant.

    Reuses the contract's own validator (the task 94/96 owner) instead of
    restating its rules, and additionally requires the payload to name the side
    it was read for, so a selection belonging to another side can never be
    presented as this one's.
    """

    try:
        parsed = SmcSideSelection.from_dict(selection)
    except (TypeError, ValueError):
        return False
    if parsed.side != side:
        return False
    return validate_smc_side_selection(parsed)


def _carries_selection(result: SmcScoringResult | None) -> bool:
    if not isinstance(result, SmcScoringResult):
        return False
    return any(
        smc_selection_of(result.side(side)) is not None for side in ("buy", "sell")
    )


def selection_for_side(
    contract: dict[str, Any] | None,
    side: str,
) -> dict[str, Any] | None:
    """The final canonical selection payload of *side*, or ``None``.

    ``None`` means the side carries no selection at all (a legacy payload) —
    it is NOT the same as an evaluated side whose selection says ``no_zone``.
    A consumer must therefore read the state from here, never infer it from a
    missing zone.
    """

    payload = contract if isinstance(contract, dict) else {}
    sides = payload.get("sides") if isinstance(payload.get("sides"), dict) else {}
    item = sides.get(side) if isinstance(sides.get(side), dict) else {}
    return _copy_dict(item.get("selection")) or None


def selected_zone_for_side(
    contract: dict[str, Any] | None,
    side: str,
) -> dict[str, Any] | None:
    """Return a copy of the decision-path selected zone for *side*.

    This is the HISTORICAL zone payload (``SmcSideScoringResult.selected_zone``),
    which the canonical finalizer never fills: on a canonical contract it is
    ``None`` for every side.  A caller that needs the zone the canonical
    coordinator actually accepted reads :func:`scenario_preferred_zone_for_side`
    instead (R114-01).
    """

    payload = contract if isinstance(contract, dict) else {}
    sides = payload.get("sides") if isinstance(payload.get("sides"), dict) else {}
    item = sides.get(side) if isinstance(sides.get(side), dict) else {}
    return _copy_dict(item.get("selected_zone")) or None


def scenario_preferred_zone_for_side(
    contract: dict[str, Any] | None,
    side: str,
) -> dict[str, Any] | None:
    """The risk-plan "preferred zone" of *side*, read from the final selection.

    R114-01: the scenario builder must be driven by the canonical FINAL
    selection — the candidate the coordinator accepted — not by the legacy
    ``selected_zone`` field, which the canonical finalizer never fills.  This
    converts that selection into the zone shape ``build_trade_plan`` already
    consumes (``low``/``high``/``level``/``zone_type``/``source``/``zone_id``).

    Fail-closed: a side whose selection is absent but whose payload carries a
    canonical contract (``no_zone``, ``data_unavailable``, ``watch_zone``,
    ``out_of_strategy``), or whose selection has no accepted plan, no
    consistent zone/setup identity, or an unusable band, yields ``None``.  It
    never falls back to another zone — technical or legacy.

    A stored/legacy payload that carries NO canonical selection at all keeps its
    historical reader compatibility from ``selected_zone``.
    """

    payload = contract if isinstance(contract, dict) else {}
    sides = payload.get("sides") if isinstance(payload.get("sides"), dict) else {}
    item = sides.get(side) if isinstance(sides.get(side), dict) else {}
    selection = _copy_dict(item.get("selection")) or None
    if selection is None:
        # No canonical selection was ever written for this side: the payload is
        # a stored/legacy document, so the old reader stays in force.
        return _copy_dict(item.get("selected_zone")) or None
    return _preferred_zone_from_selection(selection)


def _preferred_zone_from_selection(
    selection: dict[str, Any],
) -> dict[str, Any] | None:
    """Convert one FINAL selection into the risk-plan zone shape, or ``None``.

    Only an ``evaluated`` selection with an accepted plan belonging to the SAME
    candidate can become a preferred zone.  Every value is copied from the
    selection/plan; ``level`` is the midpoint of the selection's own band, which
    is the same convention the retired ``SelectedSmcZone.from_zone`` used.
    """

    if selection.get("state") != SELECTION_STATE_EVALUATED:
        return None
    if selection.get("plan_available") is not True:
        return None
    plan = selection.get("plan")
    if not isinstance(plan, dict):
        return None

    side = str(selection.get("side") or "").strip().lower()
    zone_id = selection.get("selected_zone_id")
    setup_id = selection.get("selected_setup_id")
    if side not in ("buy", "sell") or not zone_id or not setup_id:
        return None
    # The plan must belong to the selected zone/setup: a mismatched pair is a
    # malformed selection, never a usable preferred zone.  Both the plan payload
    # and the selection's own plan reference are checked, so a selection that
    # names one zone in its plan and another in its reference is refused.
    if plan.get("zone_id") != zone_id or plan.get("setup_id") != setup_id:
        return None
    plan_zone_id = selection.get("plan_zone_id")
    if plan_zone_id is not None and plan_zone_id != zone_id:
        return None
    plan_setup_id = selection.get("plan_setup_id")
    if plan_setup_id is not None and plan_setup_id != setup_id:
        return None
    plan_direction = plan.get("direction")
    if plan_direction is not None and plan_direction != side:
        return None

    low = _finite_price(selection.get("zone_low"))
    high = _finite_price(selection.get("zone_high"))
    if low is None or high is None or high <= low:
        return None

    return {
        "zone_id": zone_id,
        "setup_id": setup_id,
        "direction": side,
        "side": side,
        "zone_type": _BUY_ZONE_TYPE if side == "buy" else _SELL_ZONE_TYPE,
        "type": _BUY_ZONE_TYPE if side == "buy" else _SELL_ZONE_TYPE,
        "family": selection.get("family"),
        "timeframe": selection.get("timeframe"),
        "low": low,
        "high": high,
        # Band midpoint, matching the retired ``SelectedSmcZone.from_zone``.
        "level": (low + high) / 2.0,
        "source": SELECTED_ZONE_SOURCE,
        "selection_status": selection.get("state"),
        "selection_reason_codes": list(selection.get("selection_reason_codes") or ()),
        "provenance": PREFERRED_ZONE_PROVENANCE,
        "plan_zone_id": selection.get("plan_zone_id"),
        "plan_setup_id": selection.get("plan_setup_id"),
    }


def _finite_price(value: object) -> float | None:
    """A real price level, or ``None`` — a boolean must not stand in for one."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) else None


def side_consumer_metadata(
    contract: dict[str, Any] | None,
    side: str,
) -> dict[str, Any]:
    payload = contract if isinstance(contract, dict) else {}
    sides = payload.get("sides") if isinstance(payload.get("sides"), dict) else {}
    item = sides.get(side) if isinstance(sides.get(side), dict) else {}
    return dict(item)


def _copy_dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}
