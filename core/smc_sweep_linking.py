"""Canonical liquidity-sweep to SMC-zone association.

This module assigns at most one concrete sweep to one concrete zone. It is
side-aware, price-aware, time-aware, and deterministic so live and replay paths
produce the same relationship from the same inputs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from math import isfinite
from typing import Any


SMC_SWEEP_LINK_VERSION = "smc-sweep-link-v1"
SWEEP_ZONE_TOLERANCE_ATR = 0.25


def _claim_instant(value: object) -> datetime | None:
    """Parse a claim timestamp to an aware UTC instant, or ``None`` when it is unusable."""

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            parsed = datetime.fromisoformat(
                text[:-1] + "+00:00" if text.endswith("Z") else text
            )
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def setup_owner_key(zone: dict[str, Any]) -> str:
    """Owner key of a zone: its setup when it has one, otherwise the zone itself."""

    setup_id = str(zone.get("setup_id", "") or "").strip()
    if setup_id:
        return setup_id
    return f"zone:{str(zone.get('zone_id', '') or '').strip()}"


def setup_availability_by_owner(zones: list[dict[str, Any]]) -> dict[str, str | None]:
    """The availability instant each setup declares, independent of zone list order.

    A setup's availability is the *setup's* meaning, not whichever child happens to be ranked
    first, so children that declare different instants resolve to the earliest one the setup
    declares.  Children without a parseable instant contribute nothing to the map.
    """

    declared: dict[str, list[tuple[datetime, str]]] = {}
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        instant = _claim_instant(zone.get("available_at"))
        if instant is None:
            continue
        declared.setdefault(setup_owner_key(zone), []).append(
            (instant, str(zone.get("available_at")).strip())
        )
    return {
        owner_key: min(values, key=lambda item: item[0])[1]
        for owner_key, values in declared.items()
    }


@dataclass(frozen=True, slots=True)
class SweepZoneLink:
    zone_id: str
    sweep_id: str
    sweep_kind: str
    sweep_level: float
    sweep_time: str
    sweep_index: int
    distance_atr: float
    time_delta: int
    link_version: str = SMC_SWEEP_LINK_VERSION
    setup_id: str | None = None
    visit_id: str | None = None

    def to_zone_payload(self) -> dict[str, Any]:
        return {
            "liquidity_sweep_linked": True,
            "linked_sweep_id": self.sweep_id,
            "linked_sweep_kind": self.sweep_kind,
            "linked_sweep_level": self.sweep_level,
            "linked_sweep_time": self.sweep_time,
            "linked_sweep_index": self.sweep_index,
            "linked_sweep_distance_atr": self.distance_atr,
            "linked_sweep_time_delta": self.time_delta,
            "sweep_link_version": self.link_version,
            "linked_sweep_setup_id": self.setup_id,
            "linked_sweep_visit_id": self.visit_id,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SweepAssignment:
    """The immutable owner record for one sweep contribution.

    ``pool_id``/``source_ids`` keep the causal pool lineage the owner was granted for, so a
    later observation of the same pool can be tied back to this consumption (A-D06, F10).
    """

    sweep_id: str
    owner_setup_id: str
    assignment_id: str
    claim_eligible_at: str
    assigned_at: str
    contribution_applied: bool = True
    pool_id: str | None = None
    source_ids: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_sweep_id(
    *,
    symbol: object,
    timeframe: object,
    side: object,
    kind: object,
    level: object,
    occurred_at: object,
) -> str:
    """Build a stable content identity for one detected liquidity sweep."""

    parts = (
        _normalize_symbol(symbol),
        str(timeframe or "UNKNOWN").strip().upper() or "UNKNOWN",
        str(side or "").strip().lower(),
        str(kind or "").strip().lower(),
        _canonical_number(level),
        str(occurred_at or "").strip(),
    )
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"smcs-{digest[:20]}"


def _build_assignment_id(
    sweep_id: str,
    owner_setup_id: str,
    claim_eligible_at: str,
) -> str:
    digest = hashlib.sha256(
        f"{sweep_id}|{owner_setup_id}|{claim_eligible_at}".encode("utf-8")
    ).hexdigest()
    return f"smca-{digest[:20]}"


def associate_sweeps_to_zones(
    zones: list[dict[str, Any]],
    liquidity_sweeps: dict[str, list[dict[str, Any]]],
    *,
    atr_value: float | None,
    tolerance_atr: float = SWEEP_ZONE_TOLERANCE_ATR,
    visits: list[dict[str, Any]] | None = None,
    max_time_bars: int = 20,
) -> dict[str, SweepZoneLink]:
    """Return deterministic sweep links at setup/visit scope.

    A sweep may be assigned once to a setup, then referenced by every child
    zone in that setup.  Zones without setup metadata retain the legacy
    one-to-one behavior.  Eligible pairs are side-aware, time-bounded to the
    formation/departure (or visit) window, and price-bounded by
    ``tolerance_atr``.
    """

    normalized_atr = _positive_float(atr_value)
    tolerance = max(0.0, _finite_float(tolerance_atr, 0.0))
    try:
        time_window = int(max_time_bars)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("max_time_bars must be a non-negative integer") from None
    if isinstance(max_time_bars, bool) or time_window < 0:
        raise ValueError("max_time_bars must be a non-negative integer")

    if not isinstance(zones, list) or not isinstance(liquidity_sweeps, dict):
        return {}
    explicit_visits = visits if isinstance(visits, list) else []
    # The setup's availability, resolved once per owner so a child's list position can never
    # redefine the meaning the setup already agreed on (F08).
    setup_availability = setup_availability_by_owner(zones)

    def optional_index(value: object) -> int | None:
        return _optional_int(value)

    def visit_candidates(zone: dict[str, Any]) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        raw_values = zone.get("visits", [])
        if isinstance(raw_values, list):
            values.extend(item for item in raw_values if isinstance(item, dict))
        zone_id = str(zone.get("zone_id", "") or "").strip()
        for item in explicit_visits:
            item_zone_id = str(item.get("zone_id", "") or "").strip()
            if item_zone_id and item_zone_id == zone_id:
                values.append(item)
        return values

    def candidate_link(
        zone: dict[str, Any],
        sweep: dict[str, Any],
    ) -> tuple[tuple[Any, ...], SweepZoneLink] | None:
        zone_id = str(zone.get("zone_id", "") or "").strip()
        sweep_id = str(sweep.get("sweep_id", "") or "").strip()
        sweep_side = str(sweep.get("side", "") or "").strip().lower()
        sweep_index = optional_index(sweep.get("index"))
        sweep_level = _optional_float(sweep.get("level"))
        zone_side = str(zone.get("direction", "") or "").strip().lower()
        if (
            not zone_id
            or not sweep_id
            or sweep_side not in {"buy", "sell"}
            or zone_side != sweep_side
            or sweep_index is None
            or sweep_level is None
        ):
            return None

        low = _optional_float(zone.get("low"))
        high = _optional_float(zone.get("high"))
        if low is None or high is None:
            return None
        zone_low, zone_high = sorted((low, high))
        # A sweep whose consumption is already recorded may only be referenced again by the
        # setup that consumed it: a consumed sweep never becomes a fresh claim for another
        # setup (A-D06, F10).
        recorded_owner = str(sweep.get("owner_setup_id", "") or "").strip()
        if recorded_owner and bool(sweep.get("consumed")):
            if setup_owner_key(zone) != recorded_owner:
                return None
        price_distance = _distance_to_zone(sweep_level, zone_low, zone_high)
        if price_distance == 0:
            distance_atr = 0.0
        elif normalized_atr is None:
            return None
        else:
            distance_atr = price_distance / normalized_atr
        if distance_atr > tolerance:
            return None

        origin_index = optional_index(zone.get("origin_index", zone.get("index")))
        departure_index = optional_index(zone.get("departure_end_index"))
        formation_start = optional_index(zone.get("formation_start_index"))
        if formation_start is None:
            formation_start = origin_index

        matches: list[tuple[int, str | None, int]] = []
        for visit in visit_candidates(zone):
            start = optional_index(visit.get("start_index", visit.get("index")))
            end = optional_index(visit.get("end_index"))
            if start is None or sweep_index < start:
                continue
            if end is not None and sweep_index > end:
                continue
            if sweep_index - start > time_window:
                continue
            visit_id = str(visit.get("visit_id", "") or "").strip() or None
            matches.append((sweep_index - start, visit_id, start))

        window_match = (
            formation_start is not None
            and departure_index is not None
            and formation_start <= sweep_index <= departure_index
            and sweep_index - formation_start <= time_window
        )
        if not window_match and not matches:
            return None

        visit_delta, visit_id, visit_start = min(
            matches,
            key=lambda item: (item[0], item[1] or ""),
            default=(sweep_index - (formation_start or sweep_index), None, formation_start or sweep_index),
        )
        if matches:
            time_delta = visit_delta
        else:
            time_delta = sweep_index - (origin_index if origin_index is not None else visit_start)
            visit_id = None
        departure_gap = (
            departure_index - sweep_index
            if departure_index is not None
            else time_delta
        )
        setup_id = str(zone.get("setup_id", "") or "").strip() or None
        link = SweepZoneLink(
            zone_id=zone_id,
            sweep_id=sweep_id,
            sweep_kind=str(sweep.get("kind", "") or ""),
            sweep_level=sweep_level,
            sweep_time=str(
                sweep.get("reclaimed_at", sweep.get("time", "")) or ""
            ),
            sweep_index=sweep_index,
            distance_atr=round(distance_atr, 6),
            time_delta=time_delta,
            setup_id=setup_id,
            visit_id=visit_id,
        )
        # F08 / A-D02: a setup-scoped claim is owned by causal claim time —
        # `max(reclaimed_at, setup_available_at)` earliest, then the stable setup ID — and never
        # by distance or the caller's input order. This is the explicit boundary against the
        # legacy one-to-one zone path (a zone without setup metadata), which keeps its documented
        # distance/departure ranking. A candidate whose canonical claim time is incomplete ranks
        # after every complete one instead of being handed the remaining timestamp as a substitute.
        reclaim_instant = _claim_instant(sweep.get("reclaimed_at"))
        available_instant = _claim_instant(setup_availability.get(setup_owner_key(zone)))
        complete_claim = reclaim_instant is not None and available_instant is not None
        claim_instant = (
            max(reclaim_instant, available_instant) if complete_claim
            else (reclaim_instant or available_instant)
        )
        owner_key = setup_owner_key(zone)
        has_setup = bool(str(zone.get("setup_id", "") or "").strip())
        legacy_keys = (
            round(distance_atr, 12),
            departure_gap,
            abs(time_delta),
            zone_id,
            sweep_id,
        )
        claim_keys = (
            0 if complete_claim else 1,
            claim_instant.isoformat() if claim_instant is not None else "",
        )
        # Position 2 separates the two owner classes, so the class-specific tails below are only
        # ever compared against candidates of their own class.
        if has_setup:
            rank = (*claim_keys, 0, owner_key, legacy_keys)
        else:
            rank = (*claim_keys, 1, legacy_keys, owner_key)
        return rank, link

    candidates: list[tuple[tuple[Any, ...], SweepZoneLink]] = []

    for sweep in _flatten_sweeps(liquidity_sweeps):
        for zone in zones:
            linked = candidate_link(zone, sweep)
            if linked is not None:
                candidates.append(linked)

    links: dict[str, SweepZoneLink] = {}
    used_owners: set[tuple[str, str]] = set()
    for _, link in sorted(candidates, key=lambda item: item[0]):
        owner_key = (link.setup_id or f"zone:{link.zone_id}", link.sweep_id)
        if link.zone_id in links or any(
            existing.sweep_id == link.sweep_id
            and (existing.setup_id or f"zone:{existing.zone_id}") != owner_key[0]
            for existing in links.values()
        ):
            continue
        links[link.zone_id] = link
        used_owners.add(owner_key)
    return links


def assign_sweep_ownership(
    claims: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    assignment_history: dict[str, dict[str, Any]] | None = None,
    history_complete: bool = True,
) -> dict[str, Any]:
    """Assign each sweep to one setup using causal claim time.

    ``claims`` may contain one row per linked child.  Children sharing a
    ``setup_id`` therefore compete as one owner and receive the same
    assignment, while the contribution is counted once.  Existing history is
    authoritative, so a setup appearing later cannot take ownership away.
    """

    if not isinstance(claims, (list, tuple)):
        return {"assignments": {}, "claims": [], "reason_codes": []}
    history = assignment_history if isinstance(assignment_history, dict) else {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    normalized_claims: list[dict[str, Any]] = []

    def timestamp(value: object) -> datetime | None:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str) and value.strip():
            text = value.strip()
            try:
                parsed = datetime.fromisoformat(
                    text[:-1] + "+00:00" if text.endswith("Z") else text
                )
            except ValueError:
                return None
        else:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)

    def is_canonical_claim(claim: dict[str, Any]) -> bool:
        """A claim that declares pool lineage is canonical and must be causally complete."""

        if str(claim.get("pool_id", "") or "").strip():
            return True
        source_ids = claim.get("source_ids")
        return isinstance(source_ids, (list, tuple)) and len(source_ids) > 0

    def claim_time(claim: dict[str, Any]) -> datetime | None:
        if is_canonical_claim(claim):
            # A-D02: both canonical claim times are required. Neither the surviving timestamp nor
            # a legacy alias may stand in for the missing one.
            sweep_time = timestamp(claim.get("reclaimed_at"))
            available = timestamp(claim.get("setup_available_at"))
            if sweep_time is None or available is None:
                return None
            return max(sweep_time, available)
        # Legacy compatibility default: a claim without pool lineage keeps the documented alias
        # resolution, which this change deliberately leaves untouched.
        sweep_time = timestamp(
            claim.get(
                "reclaimed_at",
                claim.get("sweep_reclaim_at", claim.get("sweep_time", claim.get("time"))),
            )
        )
        available = timestamp(
            claim.get("setup_available_at", claim.get("available_at"))
        )
        if sweep_time is None:
            return available
        if available is None:
            return sweep_time
        return max(sweep_time, available)

    reason_codes: list[str] = []
    for claim_order, raw_claim in enumerate(claims):
        if not isinstance(raw_claim, dict):
            continue
        claim = dict(raw_claim)
        sweep_id = str(claim.get("sweep_id", "") or "").strip()
        setup_id = str(claim.get("setup_id", "") or "").strip()
        side = str(claim.get("side", "") or "").strip().lower()
        if not sweep_id or not setup_id or side not in {"buy", "sell"}:
            continue
        if claim.get("link_valid") is False or claim.get("consumed") is True:
            continue
        eligible_at = claim_time(claim)
        if eligible_at is None:
            if is_canonical_claim(claim):
                reason_codes.append("SWEEP_CLAIM_TIME_MISSING")
            continue
        claim["sweep_id"] = sweep_id
        claim["setup_id"] = setup_id
        claim["_eligible_at"] = eligible_at
        claim["_claim_order"] = claim_order
        normalized_claims.append(claim)
        grouped.setdefault(sweep_id, []).append(claim)

    def assignment_from_history(
        sweep_id: str,
        record: dict[str, Any],
    ) -> SweepAssignment | None:
        """Rebuild the recorded assignment verbatim, or ``None`` when it is not honourable."""

        owner = str(record.get("owner_setup_id", "") or "").strip()
        assignment_id = str(record.get("assignment_id", "") or "").strip()
        assigned_at = str(record.get("assigned_at", "") or "").strip()
        eligible_at = str(
            record.get("claim_eligible_at", assigned_at) or assigned_at
        ).strip()
        if not (owner and assignment_id and assigned_at and eligible_at):
            return None
        recorded_sources = record.get("source_ids")
        return SweepAssignment(
            sweep_id=sweep_id,
            owner_setup_id=owner,
            assignment_id=assignment_id,
            claim_eligible_at=eligible_at,
            assigned_at=assigned_at,
            contribution_applied=bool(record.get("contribution_applied", True)),
            pool_id=str(record.get("pool_id", "") or "").strip() or None,
            source_ids=(
                [str(item) for item in recorded_sources]
                if isinstance(recorded_sources, (list, tuple)) and recorded_sources
                else None
            ),
        )

    def history_record(sweep_id: str, claim: dict[str, Any]) -> dict[str, Any] | None:
        """The consumption record that governs this claim.

        A record is looked up by sweep identity first and then, for a canonical claim, by the
        causal pool lineage the record kept — so a new observation of an already-consumed pool
        (different sweep ID, time and rolling index) still cannot bypass that consumption
        (A-D06). Index, time and level never take part in the match.
        """

        record = history.get(sweep_id)
        if isinstance(record, dict):
            return record
        if not is_canonical_claim(claim):
            return None
        pool_id = str(claim.get("pool_id", "") or "").strip()
        if not pool_id:
            return None
        claim_sources = sorted(str(item) for item in claim.get("source_ids") or ())
        for candidate in history.values():
            if not isinstance(candidate, dict):
                continue
            if str(candidate.get("pool_id", "") or "").strip() != pool_id:
                continue
            recorded_sources = candidate.get("source_ids")
            if isinstance(recorded_sources, (list, tuple)) and sorted(
                str(item) for item in recorded_sources
            ) != claim_sources:
                continue
            return candidate
        return None

    def history_lineage(source: dict[str, Any]) -> tuple[str, tuple[str, ...]] | None:
        """The causal pool lineage an entry declares, or ``None`` when it declares none."""

        pool_id = str(source.get("pool_id", "") or "").strip()
        raw_sources = source.get("source_ids")
        if not pool_id or not isinstance(raw_sources, (list, tuple)) or not raw_sources:
            return None
        return pool_id, tuple(sorted(str(item) for item in raw_sources))

    def history_identity(record: dict[str, Any]) -> tuple[str, str]:
        return (
            str(record.get("owner_setup_id", "") or "").strip(),
            str(record.get("assignment_id", "") or "").strip(),
        )

    def conflicting_history(sweep_id: str, source: dict[str, Any]) -> bool:
        """Whether the history related to this sweep disagrees with itself.

        Every record tied to the same sweep — by identity or by the same causal pool lineage — has
        to agree on the owner/assignment identity before any of them is honoured, including when
        an exact sweep-ID match exists. Otherwise the outcome would depend on dict insertion order
        (C-R2), so the caller fails closed instead of picking one of the contradictory versions.
        """

        lineage = history_lineage(source)
        identities: set[tuple[str, str]] = set()
        for key, record in history.items():
            if not isinstance(record, dict):
                continue
            if str(key) == sweep_id:
                identities.add(history_identity(record))
                continue
            if lineage is None or history_lineage(record) != lineage:
                continue
            identities.add(history_identity(record))
        return len(identities) > 1

    assignments: dict[str, SweepAssignment] = {}
    claim_output: list[dict[str, Any]] = []
    for sweep_id, sweep_claims in grouped.items():
        if conflicting_history(sweep_id, sweep_claims[0]):
            reason_codes.append("SWEEP_OWNER_HISTORY_CONFLICT")
            continue
        historical = history_record(sweep_id, sweep_claims[0])
        if historical is not None:
            recorded = assignment_from_history(sweep_id, historical)
            if recorded is not None:
                assignments[sweep_id] = recorded
                continue
            # The record claims an owner for this sweep but cannot be honoured: fail closed
            # rather than silently resetting history and granting the sweep to the current
            # setup (A3-048). This is the conflict group, not the missing-coverage group.
            reason_codes.append("SWEEP_OWNER_HISTORY_CONFLICT")
            continue
        if not history_complete:
            reason_codes.append("SWEEP_OWNER_HISTORY_INCOMPLETE")
            continue

        ranked = sorted(
            sweep_claims,
            key=lambda claim: (
                claim["_eligible_at"],
                str(claim.get("setup_id", "") or ""),
                str(claim.get("zone_id", "") or ""),
            ),
        )
        winner = ranked[0]
        eligible_at = winner["_eligible_at"].isoformat()
        owner = str(winner["setup_id"])
        assignment_id = _build_assignment_id(sweep_id, owner, eligible_at)
        winner_sources = winner.get("source_ids")
        assignments[sweep_id] = SweepAssignment(
            sweep_id=sweep_id,
            owner_setup_id=owner,
            assignment_id=assignment_id,
            claim_eligible_at=eligible_at,
            assigned_at=eligible_at,
            # The causal pool lineage of the winning claim travels with the assignment, so a
            # later observation of that same pool resolves back to this consumption (A-D06).
            pool_id=str(winner.get("pool_id", "") or "").strip() or None,
            source_ids=(
                [str(item) for item in winner_sources]
                if isinstance(winner_sources, (list, tuple)) and winner_sources
                else None
            ),
        )

    # An owner that survives only in history keeps its recorded assignment even when the current
    # window has no child left to claim the sweep; its current contribution stays zero because
    # no current claim exists (A3-076, A-D03).
    for sweep_id, record in history.items():
        if sweep_id in assignments or grouped.get(sweep_id) or not isinstance(record, dict):
            continue
        if conflicting_history(str(sweep_id), record):
            reason_codes.append("SWEEP_OWNER_HISTORY_CONFLICT")
            continue
        restored = assignment_from_history(str(sweep_id), record)
        if restored is not None:
            assignments[str(sweep_id)] = restored

    # F09 / A-D03: the contribution slot is chosen *within the owner's own children* using the
    # approved tie-break (zone ID, visit ID, input order). Picking it across every claim and only
    # checking ownership afterwards let a non-owner with a smaller key consume the slot and left
    # the owner with nothing — an owner that is present must total exactly one contribution.
    contribution_winner: dict[str, tuple[str, str, int]] = {}
    for claim in normalized_claims:
        sweep_id = str(claim["sweep_id"])
        assignment = assignments.get(sweep_id)
        if assignment is None or str(claim["setup_id"]) != assignment.owner_setup_id:
            continue
        candidate_key = (
            str(claim.get("zone_id", "") or ""),
            str(claim.get("visit_id", "") or ""),
            int(claim["_claim_order"]),
        )
        current = contribution_winner.get(sweep_id)
        if current is None or candidate_key < current:
            contribution_winner[sweep_id] = candidate_key

    for claim in normalized_claims:
        assignment = assignments.get(claim["sweep_id"])
        if assignment is None:
            continue
        claim_copy = dict(claim)
        claim_copy.pop("_eligible_at", None)
        claim_copy.update({
            "owner_setup_id": assignment.owner_setup_id,
            "assignment_id": assignment.assignment_id,
            "assigned_at": assignment.assigned_at,
            "claim_eligible_at": assignment.claim_eligible_at,
            "contribution_applied": (
                claim["setup_id"] == assignment.owner_setup_id
                and contribution_winner.get(str(claim["sweep_id"])) == (
                    str(claim.get("zone_id", "") or ""),
                    str(claim.get("visit_id", "") or ""),
                    int(claim["_claim_order"]),
                )
            ),
        })
        claim_copy.pop("_claim_order", None)
        claim_output.append(claim_copy)

    return {
        "assignments": {
            sweep_id: assignment.to_dict()
            for sweep_id, assignment in assignments.items()
        },
        "claims": claim_output,
        "reason_codes": list(dict.fromkeys(reason_codes)),
    }


def mark_sweeps_consumed(
    liquidity_sweeps: dict[str, list[dict[str, Any]]],
    claims: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    assignment_history: dict[str, dict[str, Any]] | None = None,
    history_complete: bool = True,
) -> dict[str, Any]:
    """Return a copy of sweeps marked consumed by their setup owner.

    The returned ``assignments`` and ``claims`` are the canonical audit
    record.  Each sweep receives one owner/assignment, and only the first
    deterministic child claim of that owner receives the contribution flag.
    """

    source = liquidity_sweeps if isinstance(liquidity_sweeps, dict) else {}
    result = {
        key: [dict(item) for item in values if isinstance(item, dict)]
        for key, values in source.items()
        if isinstance(values, list)
    }
    ownership = assign_sweep_ownership(
        claims,
        assignment_history=assignment_history,
        history_complete=history_complete,
    )
    assignments = ownership["assignments"]
    by_sweep: dict[str, bool] = {}
    for claim in ownership["claims"]:
        sweep_id = str(claim.get("sweep_id", "") or "")
        by_sweep[sweep_id] = by_sweep.get(sweep_id, False) or bool(
            claim.get("contribution_applied")
        )
    for key, values in result.items():
        for sweep in values:
            sweep_id = str(sweep.get("sweep_id", "") or "")
            assignment = assignments.get(sweep_id)
            if assignment is None:
                sweep.setdefault("consumed", False)
                continue
            sweep.update({
                "consumed": True,
                "pool_consumed": True,
                "owner_setup_id": assignment["owner_setup_id"],
                "assignment_id": assignment["assignment_id"],
                "assigned_at": assignment["assigned_at"],
                "claim_eligible_at": assignment["claim_eligible_at"],
                "contribution_applied": bool(
                    # A sweep owned only by history has no current child to contribute from.
                    by_sweep.get(sweep_id, False)
                ),
            })
    ownership["sweeps"] = result
    return ownership


def dedupe_sweep_contributions(
    claims: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    **kwargs: Any,
) -> dict[str, Any]:
    """Compatibility alias for the canonical Task 69 ownership pass."""

    return assign_sweep_ownership(claims, **kwargs)


def empty_sweep_link_payload() -> dict[str, Any]:
    return {
        "liquidity_sweep_linked": False,
        "linked_sweep_id": None,
        "linked_sweep_kind": None,
        "linked_sweep_level": None,
        "linked_sweep_time": None,
        "linked_sweep_index": None,
        "linked_sweep_distance_atr": None,
        "linked_sweep_time_delta": None,
        "sweep_link_version": SMC_SWEEP_LINK_VERSION,
    }


def _flatten_sweeps(
    liquidity_sweeps: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for key, side, kind in (
        ("swept_lows", "buy", "swept_low"),
        ("swept_highs", "sell", "swept_high"),
    ):
        values = liquidity_sweeps.get(key, [])
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, dict):
                continue
            payload = dict(value)
            payload.setdefault("side", side)
            payload.setdefault("kind", kind)
            flattened.append(payload)
    return flattened


def _distance_to_zone(level: float, low: float, high: float) -> float:
    if level < low:
        return low - level
    if level > high:
        return level - high
    return 0.0


def _normalize_symbol(value: object) -> str:
    normalized = "".join(
        character
        for character in str(value or "").upper()
        if character.isalnum()
    )
    return normalized or "UNKNOWN"


def _canonical_number(value: object) -> str:
    try:
        decimal = Decimal(str(value))
        if not decimal.is_finite():
            return "0"
        normalized = format(decimal.normalize(), "f")
        return "0" if normalized in {"-0", ""} else normalized
    except (InvalidOperation, TypeError, ValueError):
        return "0"


def _positive_float(value: object) -> float | None:
    result = _optional_float(value)
    return result if result is not None and result > 0 else None


def _finite_float(value: object, default: float) -> float:
    result = _optional_float(value)
    return result if result is not None else default


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if isfinite(result) else None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None
