"""Canonical SMC persistence contract: stamp a stored result, read it back.

Tasks 117–120.  The canonical SMC result travels into a Scanner analysis
document under ``analysis_result.smc_scoring``.  This module owns exactly two
things: what a stored payload must carry so it can be read back later, and how a
reader decides whether it may be used.

Nothing here scores, selects, plans, confirms or revalidates.  It only reads
identity and structure, so a stored payload can never be turned into a valid
live result by the reader, and a stored payload is never rewritten into the
current contract.

Four states are kept apart (compatibility spec §3 and §5):

``canonical_compatible``
    The payload carries the canonical contract *and* the persistence identity of
    the logic that produced it matches the running one.  Only this state may be
    read as a current result.
``historical``
    The payload is readable but was produced by another identity (or carries no
    identity at all).  It is opened "as it was created", is never promoted to a
    live/current verdict and never gets canonical provenance attached.
``incompatible``
    The payload parses but cannot be interpreted under the current contract: an
    unknown contract version, or a selection that does not satisfy the final
    invariant.  It must be rebuilt from source.
``corrupted``
    The payload cannot be read at all — no SMC block, or the wrong shape.

The identity is an internal marker.  It is written into diagnostic/persistence
metadata only and must never be shown as a generation label in the UI
(compatibility spec §5, writer policy).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from math import isfinite
from typing import Any, Mapping

from core.smc_scoring_result import (
    SMC_SCORING_CONTRACT_VERSION,
    SMC_SELECTION_CONTRACT_VERSION,
    SmcConfirmationIdentityError,
    SmcScoringResult,
    SmcSideSelection,
)
from core.smc_snapshot_cache import (
    SMC_CACHE_IDENTITY_VERSION,
    SMC_RULE_IDENTITY,
    smc_rule_identity,
    smc_rule_identity_digest,
    smc_rule_versions,
)
from core.smc_versions import SMC_SELECTION_VERSION


SMC_PERSISTENCE_CONTRACT_VERSION = "smc-persistence-v1"

# Key the writer stamps next to ``sides`` inside the SMC diagnostics block.
SMC_PERSISTENCE_IDENTITY_KEY = "persistence_identity"
# Key holding the frozen input the result was produced from.  Without it a
# reader cannot tell WHEN the decision was taken: the analysis document's own
# timestamp is the wall clock of the run, not the cutoff of the data.
SMC_PERSISTENCE_SNAPSHOT_KEY = "snapshot"

SMC_PAYLOAD_CANONICAL = "canonical_compatible"
SMC_PAYLOAD_HISTORICAL = "historical"
SMC_PAYLOAD_INCOMPATIBLE = "incompatible"
SMC_PAYLOAD_CORRUPTED = "corrupted"

VALID_SMC_PAYLOAD_STATUSES = frozenset({
    SMC_PAYLOAD_CANONICAL,
    SMC_PAYLOAD_HISTORICAL,
    SMC_PAYLOAD_INCOMPATIBLE,
    SMC_PAYLOAD_CORRUPTED,
})

# Which field a reader must read the selection evidence from.  It is reported on
# its own so a caller can tell "this payload recorded a canonical selection"
# apart from "this payload only has the legacy zone field" without inferring it
# from a missing value.
SMC_SOURCE_CANONICAL_SELECTION = "canonical_selection"
SMC_SOURCE_LEGACY_SELECTED_ZONE = "legacy_selected_zone"

# Payload cannot be read at all.
SMC_PERSISTENCE_BLOCK_MISSING = "SMC_PERSISTENCE_BLOCK_MISSING"
SMC_PERSISTENCE_BLOCK_MALFORMED = "SMC_PERSISTENCE_BLOCK_MALFORMED"
SMC_PERSISTENCE_CONTRACT_MISSING = "SMC_PERSISTENCE_CONTRACT_MISSING"
# Readable, but not under the current contract.
SMC_PERSISTENCE_CONTRACT_UNSUPPORTED = "SMC_PERSISTENCE_CONTRACT_UNSUPPORTED"
SMC_PERSISTENCE_SELECTION_MALFORMED = "SMC_PERSISTENCE_SELECTION_MALFORMED"
SMC_PERSISTENCE_SELECTION_MISSING = "SMC_PERSISTENCE_SELECTION_MISSING"
# Readable and meaningful, but produced by another identity.  Every marker the
# writer stamps is verified, so a single tampered/rolled marker is reported with
# its own reason instead of being accepted on the strength of the others.
SMC_PERSISTENCE_IDENTITY_MISSING = "SMC_PERSISTENCE_IDENTITY_MISSING"
SMC_PERSISTENCE_IDENTITY_MISMATCH = "SMC_PERSISTENCE_IDENTITY_MISMATCH"
SMC_PERSISTENCE_IDENTITY_DIGEST_MISMATCH = (
    "SMC_PERSISTENCE_IDENTITY_DIGEST_MISMATCH"
)
# A payload claiming the CURRENT identity must carry the whole canonical shape.
SMC_PERSISTENCE_SNAPSHOT_MISSING = "SMC_PERSISTENCE_SNAPSHOT_MISSING"
SMC_PERSISTENCE_SELECTION_CONTRACT_MISSING = (
    "SMC_PERSISTENCE_SELECTION_CONTRACT_MISSING"
)
SMC_PERSISTENCE_SELECTION_CONTRACT_MISMATCH = (
    "SMC_PERSISTENCE_SELECTION_CONTRACT_MISMATCH"
)
# A stored confirmation that describes another side/zone than the selection
# carrying it: internally valid, but a forged pairing rather than a malformed
# record, so it is reported on its own.
SMC_PERSISTENCE_CONFIRMATION_IDENTITY_MISMATCH = (
    "SMC_PERSISTENCE_CONFIRMATION_IDENTITY_MISMATCH"
)


def smc_persistence_identity() -> dict[str, Any]:
    """The identity record the writer stamps into one stored SMC payload.

    It is the rule identity of compatibility spec §4.1 plus the two contracts
    that define the stored shape, so a reader can decide compatibility by
    comparison instead of re-deriving anything.
    """

    return {
        "persistence_contract_version": SMC_PERSISTENCE_CONTRACT_VERSION,
        "rule_identity": smc_rule_identity(),
        "rule_identity_digest": smc_rule_identity_digest(),
        "scoring_contract_version": SMC_SCORING_CONTRACT_VERSION,
        "selection_contract_version": SMC_SELECTION_CONTRACT_VERSION,
        "selection_version": SMC_SELECTION_VERSION,
        "cache_identity_version": SMC_CACHE_IDENTITY_VERSION,
    }


@dataclass(frozen=True, slots=True)
class SmcPersistenceCompat:
    """The compatibility verdict of one stored SMC payload.

    ``status`` is the trust level; ``source`` says which field the reader must
    read.  They are deliberately independent: a historical payload may still
    carry a canonical selection written under older rules, and reading that
    payload "as it was created" is not the same as calling it current.
    """

    status: str
    reason_codes: tuple[str, ...] = ()
    source: str = SMC_SOURCE_LEGACY_SELECTED_ZONE
    identity: Mapping[str, Any] | None = None
    sides: Mapping[str, Any] = field(default_factory=dict)
    block: Mapping[str, Any] = field(default_factory=dict)

    @property
    def canonical(self) -> bool:
        """Whether this payload may be read as a CURRENT canonical result."""

        return self.status == SMC_PAYLOAD_CANONICAL

    @property
    def readable(self) -> bool:
        """Whether the payload can be opened at all (current or historical)."""

        return self.status in {SMC_PAYLOAD_CANONICAL, SMC_PAYLOAD_HISTORICAL}

    @property
    def usable_as_current(self) -> bool:
        """Never true for anything but a canonical-compatible payload."""

        return self.canonical

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "source": self.source,
            "identity": dict(self.identity) if isinstance(self.identity, Mapping) else None,
        }


def snapshot_record(snapshot: object) -> dict[str, Any]:
    """The frozen input identity of the evaluation that produced a result.

    Task 117: the result alone is not enough to read a decision back.  The
    cutoff (``as_of``), the M15 window cutoff, the tick size that priced the
    rule and the caller's core-data verdict are what say *when* and *from what*
    the result was produced — and the analysis document's own timestamp is only
    the wall clock of the run.  Every field is copied, never recomputed, and a
    missing snapshot yields ``None`` instead of an invented cutoff.
    """

    if snapshot is None:
        # A fresh structure every call: these containers end up inside a stored
        # document, and a shared default could be mutated by one caller and leak
        # into the next.
        return {
            "as_of": None,
            "m15_as_of": None,
            "symbol": None,
            "tick_size": None,
            "tick_size_source": None,
            "m15_available": False,
            "contract_version": None,
            "core_reason_codes": [],
            "provenance": {},
        }
    return {
        "as_of": _iso(getattr(snapshot, "as_of", None)),
        "m15_as_of": _iso(getattr(snapshot, "m15_as_of", None)),
        "symbol": _text(getattr(snapshot, "symbol", None)),
        "tick_size": _number(getattr(snapshot, "tick_size", None)),
        "tick_size_source": _text(getattr(snapshot, "tick_size_source", None)),
        "m15_available": getattr(snapshot, "m15_as_of", None) is not None
        and bool(getattr(snapshot, "m15_candles", None)),
        "contract_version": _text(getattr(snapshot, "contract_version", None)),
        "core_reason_codes": [
            str(code)
            for code in (getattr(snapshot, "core_reason_codes", None) or ())
            if str(code)
        ],
        "provenance": (
            dict(getattr(snapshot, "provenance", None))
            if isinstance(getattr(snapshot, "provenance", None), Mapping)
            else {}
        ),
    }


def stored_snapshot_of(block: object) -> Mapping[str, Any]:
    """The stored snapshot record of a block, never a re-derived cutoff."""

    source = block if isinstance(block, Mapping) else {}
    record = source.get(SMC_PERSISTENCE_SNAPSHOT_KEY)
    return record if isinstance(record, Mapping) else {}


def _iso(value: object) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo is not None else None
        return parsed.astimezone(timezone.utc).isoformat() if parsed else None
    return _text(value)


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def build_smc_persistence_block(
    smc_result: object,
    consumer_contract: Mapping[str, Any] | None,
    *,
    snapshot: object = None,
) -> dict[str, Any]:
    """The canonical SMC block one evaluation is persisted as (single owner).

    Both routes (Analyze and Scanner) write the SAME block shape, built here from
    the objects they already produced:

    * ``sides`` — the per-side projection of the canonical scorer result;
    * ``consumer_contract`` — the selection/readiness/plan payload the consumers
      read;
    * ``persistence_identity`` — the identity of the logic that produced it;
    * ``snapshot`` — the frozen input (cutoff, tick size, provenance).

    Nothing is recomputed here: every value is copied from the result/contract/
    snapshot the caller already has, so the block that reaches the bytes on disk
    is the evaluation that actually ran.  There is deliberately no default for
    the identity or the snapshot: a caller that has no evaluation passes nothing
    and gets no block, instead of a fabricated one.
    """

    from core.smc_versions import SMC_SCORER_VERSION

    sides: dict[str, Any] = {}
    for side in ("buy", "sell"):
        side_result = (
            smc_result.side(side)
            if isinstance(smc_result, SmcScoringResult)
            else None
        )
        sides[side] = {
            "score": side_result.score if side_result else None,
            "smc_reason": side_result.smc_reason if side_result else None,
            "selected_zone_id": (
                side_result.selected_zone_id if side_result else None
            ),
            "selected_zone_type": (
                side_result.selected_zone_type if side_result else None
            ),
            "selected_zone_timeframe": (
                side_result.selected_zone_timeframe if side_result else None
            ),
            "selected_zone_score": (
                side_result.selected_zone_score if side_result else None
            ),
            "selected_zone_quality_score": (
                side_result.selected_zone_quality_score if side_result else None
            ),
            "selected_zone_relevance_score": (
                side_result.selected_zone_relevance_score if side_result else None
            ),
            "selected_zone_setup_score": (
                side_result.selected_zone_setup_score if side_result else None
            ),
            "scoring_version": (
                smc_result.scoring_version
                if isinstance(smc_result, SmcScoringResult)
                else None
            ),
            "breakdown": side_result.breakdown if side_result else {},
        }
    scoring_version = (
        smc_result.scoring_version
        if isinstance(smc_result, SmcScoringResult)
        else ""
    )
    return {
        "contract_version": SMC_SCORING_CONTRACT_VERSION,
        "scoring_version": scoring_version or SMC_SCORER_VERSION,
        "sides": sides,
        "consumer_contract": (
            dict(consumer_contract) if isinstance(consumer_contract, Mapping) else None
        ),
        # Task 117: the identity of the logic that produced this result travels
        # with it, so a reader can tell a current payload from a historical one
        # instead of guessing.  It is internal metadata: no generation label is
        # derived from it for display.
        SMC_PERSISTENCE_IDENTITY_KEY: smc_persistence_identity(),
        # The frozen input of that evaluation — the cutoff the decision was
        # taken at, which the document's own wall-clock timestamp cannot say.
        SMC_PERSISTENCE_SNAPSHOT_KEY: snapshot_record(snapshot),
    }


def smc_block_of(document: object) -> Mapping[str, Any]:
    """The SMC diagnostics block of a stored analysis document (or row).

    Both shapes are accepted because the same block is written inside a Scanner
    analysis document (``analysis_result.smc_scoring``) and returned directly by
    the Analyze route (``smc_scoring``).  A missing/mistyped block yields an
    empty mapping so every caller fails closed instead of reading a wrong key.
    """

    payload = document if isinstance(document, Mapping) else {}
    analysis = payload.get("analysis_result")
    if isinstance(analysis, Mapping):
        block = analysis.get("smc_scoring")
        if isinstance(block, Mapping):
            return block
    block = payload.get("smc_scoring")
    return block if isinstance(block, Mapping) else {}


def consumer_sides_of(block: object) -> Mapping[str, Any]:
    """The per-side consumer payloads (selection + legacy zone) of a block."""

    source = block if isinstance(block, Mapping) else {}
    consumer = source.get("consumer_contract")
    if not isinstance(consumer, Mapping):
        consumer = source.get("smc_consumer")
    if not isinstance(consumer, Mapping):
        return {}
    sides = consumer.get("sides")
    return sides if isinstance(sides, Mapping) else {}


def classify_persisted_smc(document: object) -> SmcPersistenceCompat:
    """Classify one stored SMC payload without reading a single decision.

    The order matters: structure, then contract, then the selection payload,
    then the identity stamp.  A payload that cannot be parsed is never reported
    as merely "historical", and a payload whose recorded selection breaks its own
    invariant is never reported as compatible.
    """

    block = smc_block_of(document)
    if not block:
        return SmcPersistenceCompat(
            status=SMC_PAYLOAD_CORRUPTED,
            reason_codes=(SMC_PERSISTENCE_BLOCK_MISSING,),
        )
    raw_sides = block.get("sides")
    if not isinstance(raw_sides, Mapping):
        return SmcPersistenceCompat(
            status=SMC_PAYLOAD_CORRUPTED,
            reason_codes=(SMC_PERSISTENCE_BLOCK_MALFORMED,),
            block=block,
        )
    contract_version = block.get("contract_version")
    if not isinstance(contract_version, str) or not contract_version.strip():
        return SmcPersistenceCompat(
            status=SMC_PAYLOAD_CORRUPTED,
            reason_codes=(SMC_PERSISTENCE_CONTRACT_MISSING,),
            sides=raw_sides,
            block=block,
        )
    if contract_version != SMC_SCORING_CONTRACT_VERSION:
        return SmcPersistenceCompat(
            status=SMC_PAYLOAD_INCOMPATIBLE,
            reason_codes=(SMC_PERSISTENCE_CONTRACT_UNSUPPORTED,),
            sides=raw_sides,
            block=block,
        )

    consumer_sides = consumer_sides_of(block)
    present, invalid_sides, contract_faults = _inspect_recorded_selections(
        consumer_sides
    )
    if invalid_sides:
        return SmcPersistenceCompat(
            status=SMC_PAYLOAD_INCOMPATIBLE,
            reason_codes=(SMC_PERSISTENCE_SELECTION_MALFORMED, *invalid_sides),
            source=SMC_SOURCE_CANONICAL_SELECTION,
            sides=raw_sides,
            block=block,
        )
    if contract_faults:
        # The recorded selection does not name the contract it was written
        # under.  Reading it would silently adopt today's contract for a payload
        # that never claimed it, so the payload is refused instead.
        return SmcPersistenceCompat(
            status=SMC_PAYLOAD_INCOMPATIBLE,
            reason_codes=contract_faults,
            source=SMC_SOURCE_CANONICAL_SELECTION,
            sides=raw_sides,
            block=block,
        )

    identity = block.get(SMC_PERSISTENCE_IDENTITY_KEY)
    if not isinstance(identity, Mapping):
        return SmcPersistenceCompat(
            status=SMC_PAYLOAD_HISTORICAL,
            reason_codes=(SMC_PERSISTENCE_IDENTITY_MISSING,),
            source=_source_for(present),
            sides=raw_sides,
            block=block,
        )
    identity_codes = _identity_mismatch_codes(identity)
    if identity_codes:
        # Some marker disagrees with the running logic (or with the record's own
        # digest).  That is exactly what "produced by another identity" means, so
        # the payload stays readable as history and can never be current.
        return SmcPersistenceCompat(
            status=SMC_PAYLOAD_HISTORICAL,
            reason_codes=identity_codes,
            source=_source_for(present),
            identity=identity,
            sides=raw_sides,
            block=block,
        )
    if not isinstance(block.get(SMC_PERSISTENCE_SNAPSHOT_KEY), Mapping):
        # A payload claiming the CURRENT identity but missing the frozen input
        # it was produced from is a torn write: without the cutoff it cannot be
        # read back as the decision it claims to be.
        return SmcPersistenceCompat(
            status=SMC_PAYLOAD_INCOMPATIBLE,
            reason_codes=(SMC_PERSISTENCE_SNAPSHOT_MISSING,),
            source=SMC_SOURCE_CANONICAL_SELECTION,
            identity=identity,
            sides=raw_sides,
            block=block,
        )
    missing_sides = tuple(
        f"SMC_PERSISTENCE_SELECTION_MISSING_{side.upper()}"
        for side in ("buy", "sell")
        if side not in present
    )
    if missing_sides:
        # A payload stamped with the CURRENT identity must actually carry what
        # that identity promises — one selection per side.  A stamp with a side
        # missing is a torn write, not a payload to trust, and reading the
        # absent side through the historical field would report evidence the
        # canonical route never recorded.
        return SmcPersistenceCompat(
            status=SMC_PAYLOAD_INCOMPATIBLE,
            reason_codes=(SMC_PERSISTENCE_SELECTION_MISSING, *missing_sides),
            source=SMC_SOURCE_CANONICAL_SELECTION,
            identity=identity,
            sides=raw_sides,
            block=block,
        )
    return SmcPersistenceCompat(
        status=SMC_PAYLOAD_CANONICAL,
        source=SMC_SOURCE_CANONICAL_SELECTION,
        identity=identity,
        sides=raw_sides,
        block=block,
    )


def selection_payload_for_side(
    block: object,
    *,
    side: str,
    compat: SmcPersistenceCompat | None = None,
) -> Mapping[str, Any]:
    """The recorded selection of *side*, or an empty mapping.

    The legacy ``selected_zone`` field is deliberately NOT returned here: a
    caller that wants the historical zone must ask for it explicitly through
    :func:`legacy_zone_for_side`, so the two sources can never be confused.
    """

    if compat is not None and compat.source != SMC_SOURCE_CANONICAL_SELECTION:
        return {}
    item = consumer_sides_of(block).get(side)
    if not isinstance(item, Mapping):
        return {}
    selection = item.get("selection")
    return selection if isinstance(selection, Mapping) else {}


def legacy_zone_for_side(block: object, *, side: str) -> Mapping[str, Any]:
    """The historical ``selected_zone`` payload of *side*, or an empty mapping."""

    item = consumer_sides_of(block).get(side)
    if not isinstance(item, Mapping):
        return {}
    zone = item.get("selected_zone")
    return zone if isinstance(zone, Mapping) else {}


def _inspect_recorded_selections(
    consumer_sides: Mapping[str, Any],
) -> tuple[frozenset[str], tuple[str, ...], tuple[str, ...]]:
    """Which sides recorded a selection, which are broken, which lost their contract.

    The recorded selection is re-checked against the SAME invariant the
    finalizer enforces (``SmcSideSelection.__post_init__``), so a stored payload
    that claims a canonical selection but cannot satisfy it is refused instead of
    being republished as a usable setup.

    The third result is the one this module exists to get right: a selection must
    NAME the contracts it was written under.  ``SmcSideSelection.from_dict``
    fills a missing ``selection_version``/``contract_version`` with today's
    constants, which would let a payload written under other rules borrow the
    current identity — so the raw payload is checked here, before any default
    can apply.
    """

    present: set[str] = set()
    invalid: list[str] = []
    contract_faults: list[str] = []
    for side in ("buy", "sell"):
        item = consumer_sides.get(side)
        selection = item.get("selection") if isinstance(item, Mapping) else None
        if not isinstance(selection, Mapping):
            continue
        present.add(side)
        faults = _selection_contract_faults(selection, side=side)
        if faults:
            contract_faults.extend(faults)
            continue
        try:
            SmcSideSelection.from_dict(selection)
        except SmcConfirmationIdentityError as exc:
            # The confirmation is valid on its own but belongs to another
            # setup.  Reported as its own reason so a reviewer sees a forged
            # pairing rather than a merely broken record.
            invalid.append(
                f"{SMC_PERSISTENCE_CONFIRMATION_IDENTITY_MISMATCH}:"
                f"{side.upper()}:{exc.field_name}"
            )
        except (ValueError, TypeError):
            invalid.append(f"SMC_PERSISTENCE_SELECTION_INVALID_{side.upper()}")
    return frozenset(present), tuple(invalid), tuple(contract_faults)


def _selection_contract_faults(
    selection: Mapping[str, Any],
    *,
    side: str,
) -> list[str]:
    """Whether a recorded selection names the contracts it was written under."""

    faults: list[str] = []
    expected = (
        ("contract_version", SMC_SELECTION_CONTRACT_VERSION),
        ("selection_version", SMC_SELECTION_VERSION),
    )
    for field_name, current in expected:
        recorded = selection.get(field_name)
        if not isinstance(recorded, str) or not recorded.strip():
            faults.append(
                f"{SMC_PERSISTENCE_SELECTION_CONTRACT_MISSING}:"
                f"{side.upper()}:{field_name}"
            )
        elif recorded != current:
            faults.append(
                f"{SMC_PERSISTENCE_SELECTION_CONTRACT_MISMATCH}:"
                f"{side.upper()}:{field_name}"
            )
    return faults


def smc_identity_mismatch_codes(identity: object) -> tuple[str, ...]:
    """Every reason a stamped identity disagrees with the running logic.

    Public face of the verification the whole lot rests on: any caller that
    decides "may this stored artifact be reused?" must ask this instead of
    comparing a representative subset of markers.  An empty result means the
    record is exactly the one this process would write.
    """

    if not isinstance(identity, Mapping):
        return (SMC_PERSISTENCE_IDENTITY_MISSING,)
    return _identity_mismatch_codes(identity)


def _identity_mismatch_codes(identity: Mapping[str, Any]) -> tuple[str, ...]:
    """Every reason a stamped identity disagrees with the running logic.

    All markers are verified, not a representative subset: the digest is
    recomputed from the record it describes (so a tampered digest is caught even
    when every other field looks right) and each contract/selection version is
    compared with the running constant.  An empty result means the record is
    exactly the one this process would write.
    """

    codes: list[str] = []
    if identity.get("persistence_contract_version") != SMC_PERSISTENCE_CONTRACT_VERSION:
        codes.append(SMC_PERSISTENCE_IDENTITY_MISMATCH)
    if identity.get("cache_identity_version") != SMC_CACHE_IDENTITY_VERSION:
        codes.append(SMC_PERSISTENCE_IDENTITY_MISMATCH)
    if identity.get("scoring_contract_version") != SMC_SCORING_CONTRACT_VERSION:
        codes.append(SMC_PERSISTENCE_IDENTITY_MISMATCH)
    if identity.get("selection_contract_version") != SMC_SELECTION_CONTRACT_VERSION:
        codes.append(SMC_PERSISTENCE_IDENTITY_MISMATCH)
    if identity.get("selection_version") != SMC_SELECTION_VERSION:
        codes.append(SMC_PERSISTENCE_IDENTITY_MISMATCH)

    stamped_rule = identity.get("rule_identity")
    if not isinstance(stamped_rule, Mapping):
        codes.append(SMC_PERSISTENCE_IDENTITY_MISMATCH)
        return _unique(codes)
    if stamped_rule.get("rule_identity") != SMC_RULE_IDENTITY:
        codes.append(SMC_PERSISTENCE_IDENTITY_MISMATCH)
    versions = stamped_rule.get("rule_versions")
    if not isinstance(versions, Mapping):
        codes.append(SMC_PERSISTENCE_IDENTITY_MISMATCH)
    elif {str(k): str(v) for k, v in versions.items()} != smc_rule_versions():
        codes.append(SMC_PERSISTENCE_IDENTITY_MISMATCH)
    if stamped_rule.get("cache_identity_version") != SMC_CACHE_IDENTITY_VERSION:
        codes.append(SMC_PERSISTENCE_IDENTITY_MISMATCH)

    # The digest must describe the record it travels with AND be the digest of
    # the running identity.  Recomputing catches an edit that left every other
    # marker untouched.
    recorded_digest = identity.get("rule_identity_digest")
    recomputed = _digest_of(stamped_rule)
    if not isinstance(recorded_digest, str) or recorded_digest != recomputed:
        codes.append(SMC_PERSISTENCE_IDENTITY_DIGEST_MISMATCH)
    elif recomputed != smc_rule_identity_digest():
        codes.append(SMC_PERSISTENCE_IDENTITY_MISMATCH)
    return _unique(codes)


def _digest_of(rule_identity_record: Mapping[str, Any]) -> str:
    """The digest a given rule-identity record must carry."""

    canonical = json.dumps(
        _plain(rule_identity_record),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _plain(value: object) -> Any:
    """A JSON-comparable copy of a decoded payload (dicts/lists/scalars only)."""

    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _source_for(present: frozenset[str]) -> str:
    return (
        SMC_SOURCE_CANONICAL_SELECTION
        if present
        else SMC_SOURCE_LEGACY_SELECTED_ZONE
    )


def _identity_is_current(identity: Mapping[str, Any]) -> bool:
    """Whether a stamped identity equals the running rule identity.

    Kept as the boolean face of :func:`_identity_mismatch_codes` so callers that
    only need the verdict do not have to inspect reason codes.
    """

    return not _identity_mismatch_codes(identity)


__all__ = [
    "SMC_PAYLOAD_CANONICAL",
    "SMC_PAYLOAD_CORRUPTED",
    "SMC_PAYLOAD_HISTORICAL",
    "SMC_PAYLOAD_INCOMPATIBLE",
    "SMC_PERSISTENCE_BLOCK_MALFORMED",
    "SMC_PERSISTENCE_BLOCK_MISSING",
    "SMC_PERSISTENCE_CONFIRMATION_IDENTITY_MISMATCH",
    "SMC_PERSISTENCE_CONTRACT_MISSING",
    "SMC_PERSISTENCE_CONTRACT_UNSUPPORTED",
    "SMC_PERSISTENCE_CONTRACT_VERSION",
    "SMC_PERSISTENCE_IDENTITY_KEY",
    "SMC_PERSISTENCE_IDENTITY_MISMATCH",
    "SMC_PERSISTENCE_IDENTITY_MISSING",
    "SMC_PERSISTENCE_IDENTITY_DIGEST_MISMATCH",
    "SMC_PERSISTENCE_SELECTION_CONTRACT_MISMATCH",
    "SMC_PERSISTENCE_SELECTION_CONTRACT_MISSING",
    "SMC_PERSISTENCE_SELECTION_MALFORMED",
    "SMC_PERSISTENCE_SELECTION_MISSING",
    "SMC_PERSISTENCE_SNAPSHOT_KEY",
    "SMC_PERSISTENCE_SNAPSHOT_MISSING",
    "SMC_SOURCE_CANONICAL_SELECTION",
    "SMC_SOURCE_LEGACY_SELECTED_ZONE",
    "VALID_SMC_PAYLOAD_STATUSES",
    "SmcPersistenceCompat",
    "build_smc_persistence_block",
    "classify_persisted_smc",
    "consumer_sides_of",
    "legacy_zone_for_side",
    "selection_payload_for_side",
    "smc_block_of",
    "smc_identity_mismatch_codes",
    "smc_persistence_identity",
    "snapshot_record",
    "stored_snapshot_of",
]
