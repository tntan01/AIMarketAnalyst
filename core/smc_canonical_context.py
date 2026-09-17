"""Canonical SMC context façade for the shared snapshot (D101-01).

The public builder ``core.smc_context.build_smc_context`` runs the LEGACY
per-timeframe detector and is kept exactly as gate 72 approved it.  This module
is the narrow, canonical-only producer the snapshot seam uses instead: it
composes the canonical detectors that already exist (tasks 41–71) — structure
replay, OB/FVG/S-D candidates and their confirmation, availability/lifetime,
canonical pool/sweep linking, lifecycle enrichment and directional confluence —
on the SAME closed-candle set and the SAME cutoff.

Discipline kept here:

* the legacy route is NOT called, replaced or modified; nothing in this module
  imports or touches ``_smc_for_timeframe``;
* no legacy zone is "upgraded": every zone comes from a canonical detector and
  must pass its own confirmation before it carries ``confirmed`` status.  A raw
  candidate stays ``candidate``/``entry_eligible=False``;
* nothing is invented — a field the canonical detector did not measure stays
  absent, so the evaluator fails that candidate closed instead of scoring it;
* the cutoff is the snapshot's, and only candles closed at it take part.

Scope: this façade exists to feed :func:`core.smc_snapshot.build_smc_snapshot`.
It is not a second public context API and grants no entry permission by itself.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from core.market_models import Candle, candle_close_at
from core.smc_confluence import build_directional_confluence
from core.smc_structure_window import StructureWindowReuse
from core.smc_context import (
    _attach_zone_sweep_links,
    _filter_swings_by_atr,
    apply_zone_availability,
    atr_value_before_event,
    confirm_fvg_candidates,
    confirm_order_block_candidates,
    confirm_supply_demand_candidate,
    detect_fvg_candidates,
    detect_liquidity_pools,
    detect_liquidity_sweeps,
    detect_order_block_candidates,
    detect_supply_demand_candidates,
    enrich_zones,
    external_swing_points,
    premium_discount_bounds,
)
from core.smc_models import SMC_DOMAIN_VERSION
from core.smc_structure_replay import replay_smc_structure

SMC_CANONICAL_CONTEXT_VERSION = "smc-canonical-context-v1"

# Canonical structure event types (core.smc_models.VALID_STRUCTURE_EVENT_TYPES).
_EVENT_BOS = "BOS"
_EVENT_CHOCH_CANDIDATE = "CHOCH_CANDIDATE"
_EVENT_CHOCH_CONFIRMED = "CHOCH_CONFIRMED"

# Timeframe intervals in minutes (data spec §2).
_TIMEFRAME_MINUTES = {"D1": 1440, "H4": 240, "H1": 60}
# Pivot width of the canonical external detector (parameter table P2).
_EXTERNAL_PIVOT_WIDTH = 5
# Canonical sweep lookback window (task 67/68 contract).
_SWEEP_LOOKBACK_BARS = 60
# Display caps applied AFTER lifecycle (task 53); they never decide existence.
_DISPLAY_LIMITS = {"order_block": 6, "fvg": 6, "supply_demand": 5}

_STRUCTURE_BULLISH = "HH/HL"
_STRUCTURE_BEARISH = "LH/LL"
_STRUCTURE_UNKNOWN = "unknown"


def build_canonical_smc_context(
    d1: Sequence[Candle],
    h4: Sequence[Candle],
    h1: Sequence[Candle],
    *,
    symbol: str,
    as_of: datetime | str | None,
    scan_interval_min: int = 15,
    tick_size: float | None = None,
) -> dict[str, Any]:
    """Build the D1/H4/H1 canonical context of one frozen snapshot."""

    cutoff = _parse_cutoff(as_of)
    per_timeframe = {
        "D1": build_canonical_timeframe_context(
            d1,
            symbol=symbol,
            timeframe="D1",
            as_of=cutoff,
            scan_interval_min=scan_interval_min,
            tick_size=tick_size,
        ),
        "H4": build_canonical_timeframe_context(
            h4,
            symbol=symbol,
            timeframe="H4",
            as_of=cutoff,
            scan_interval_min=scan_interval_min,
            tick_size=tick_size,
        ),
        "H1": build_canonical_timeframe_context(
            h1,
            symbol=symbol,
            timeframe="H1",
            as_of=cutoff,
            scan_interval_min=scan_interval_min,
            tick_size=tick_size,
        ),
    }
    confluence = build_directional_confluence(
        per_timeframe["D1"],
        per_timeframe["H4"],
        per_timeframe["H1"],
    )
    return {
        "domain_version": SMC_DOMAIN_VERSION,
        "contract_version": SMC_CANONICAL_CONTEXT_VERSION,
        "symbol": symbol,
        "as_of": cutoff.isoformat(),
        "D1": per_timeframe["D1"],
        "H4": per_timeframe["H4"],
        "H1": per_timeframe["H1"],
        "confluence": confluence.to_dict(),
    }


def build_canonical_timeframe_context(
    candles: Sequence[Candle],
    *,
    symbol: str,
    timeframe: str,
    as_of: datetime,
    scan_interval_min: int = 15,
    tick_size: float | None = None,
) -> dict[str, Any]:
    """One timeframe of the canonical context, on the snapshot's closed set."""

    normalized = str(timeframe or "").strip().upper()
    tf_minutes = _TIMEFRAME_MINUTES[normalized]
    closed = _closed_candles(candles, normalized, as_of)
    # Task 137: one reuse for this window, shared by every step below that would
    # otherwise revalidate the same candles or rescan them for pivots/ATR. It is
    # created here, lives only for this call, and stores nothing across
    # evaluations.
    window = StructureWindowReuse(closed, normalized, symbol=symbol)

    structure = replay_smc_structure(
        closed,
        symbol=symbol,
        timeframe=normalized,
        as_of=as_of,
        tick_size=tick_size,
        window=window,
    )
    events = list(structure.get("events") or ())
    state = dict(structure.get("structure_state") or {})
    vocabulary = _structure_vocabulary(state, events, structure.get("snapshots") or ())

    swings = _canonical_swings(closed, symbol=symbol, timeframe=normalized)

    order_blocks = confirm_order_block_candidates(
        detect_order_block_candidates(closed, symbol=symbol, timeframe=normalized),
        events,
        candles=closed,
        as_of=as_of,
    )
    fvg = confirm_fvg_candidates(
        detect_fvg_candidates(
            closed,
            symbol=symbol,
            timeframe=normalized,
            tick_size=tick_size,
        ),
        closed,
        timeframe=normalized,
        as_of=as_of,
    )
    supply_demand = _confirm_supply_demand(
        closed, symbol=symbol, timeframe=normalized, as_of=as_of, window=window
    )

    zones = [*order_blocks, *fvg, *supply_demand]
    # Data spec §4: a zone must carry the causal formation ATR of its own
    # timeframe.  The OB/S-D detectors record it inside their measurement; the
    # FVG detector computes it but does not store it, so the façade records the
    # SAME canonical value (`atr_value_before_event` on the prefix before the
    # event candle).  Nothing is inferred: an index the detector did not publish
    # leaves the field absent and the candidate fails closed instead.
    for zone in zones:
        if _positive(zone.get("formation_atr")) is not None:
            continue
        event_index = zone.get("departure_end_index")
        if not isinstance(event_index, int) or isinstance(event_index, bool):
            continue
        causal_atr = atr_value_before_event(
            closed,
            timeframe=normalized,
            event_index=event_index,
            window=window,
        )
        if _positive(causal_atr) is not None:
            zone["formation_atr"] = float(causal_atr)
    zones = apply_zone_availability(
        zones,
        closed,
        timeframe=normalized,
        symbol=symbol,
        as_of=as_of,
        require_lifetime=True,
        window=window,
    )
    # D101-02: the canonical tick size of the snapshot is real metadata the
    # geometry/quantization rules need.  It is stamped onto every canonical
    # zone; when the snapshot has no usable tick the field stays absent and the
    # rule that needs it fails that candidate closed with
    # ``SMC_TICK_SIZE_UNAVAILABLE`` — nothing is substituted.
    if _positive(tick_size) is not None:
        for zone in zones:
            zone["tick_size"] = _positive(tick_size)
    by_id = {str(zone.get("zone_id") or ""): zone for zone in zones}
    order_blocks = _pick(order_blocks, by_id)
    fvg = _pick(fvg, by_id)
    supply_demand = _pick(supply_demand, by_id)

    demand_zones = [zone for zone in supply_demand if _zone_direction(zone) == "buy"]
    supply_zones = [zone for zone in supply_demand if _zone_direction(zone) == "sell"]

    pools = detect_liquidity_pools(
        closed,
        swings,
        tick_size=tick_size,
        atr_value=_latest_atr(closed),
    )
    sweeps = detect_liquidity_sweeps(
        closed,
        swings,
        symbol=symbol,
        timeframe=normalized,
        lookback_bars=_SWEEP_LOOKBACK_BARS,
        max_results=None,
        causal_only=True,
        liquidity_pools=pools,
    )
    _attach_zone_sweep_links(
        (
            ("demand", demand_zones),
            ("supply", supply_zones),
            ("order_block", order_blocks),
            ("fvg", fvg),
        ),
        sweeps,
        candles=closed,
        symbol=symbol,
        timeframe=normalized,
        tf_minutes=tf_minutes,
    )
    premium_discount_range = premium_discount_bounds(swings)
    for family, zones_for_family in (
        ("demand", demand_zones),
        ("supply", supply_zones),
        ("order_block", order_blocks),
        ("fvg", fvg),
    ):
        _enrich(
            zones_for_family,
            closed,
            family,
            sweeps,
            premium_discount_range,
            symbol=symbol,
            timeframe=normalized,
            tf_minutes=tf_minutes,
            scan_interval_min=scan_interval_min,
            tick_size=tick_size,
        )

    return {
        "domain_version": SMC_DOMAIN_VERSION,
        "contract_version": SMC_CANONICAL_CONTEXT_VERSION,
        "symbol": symbol,
        "timeframe": normalized,
        "cutoff": as_of.isoformat(),
        "structure": vocabulary["structure"],
        "bos": vocabulary["bos"],
        "choch": vocabulary["choch"],
        "choch_confirmed": vocabulary["choch_confirmed"],
        "displacement": vocabulary["displacement"],
        "bos_strength": vocabulary["bos_strength"],
        "swings": swings,
        "external_swings": swings,
        "structure_events": events,
        "structure_state": state,
        "liquidity_pools": pools,
        "liquidity_sweeps": sweeps,
        "zone_link_sweeps": sweeps,
        "premium_discount_range": premium_discount_range,
        "demand_zones": _limit(demand_zones, "supply_demand"),
        "supply_zones": _limit(supply_zones, "supply_demand"),
        "order_blocks": _limit(order_blocks, "order_block"),
        "fvg": _limit(fvg, "fvg"),
    }


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _closed_candles(
    candles: Sequence[Candle],
    timeframe: str,
    cutoff: datetime,
) -> list[Candle]:
    """Candles whose real close boundary is at or before the cutoff."""

    result: list[Candle] = []
    for candle in candles or ():
        if not isinstance(candle, Candle):
            continue
        if candle_close_at(candle.time, timeframe) <= cutoff:
            result.append(candle)
    return result


def _canonical_swings(
    candles: Sequence[Candle],
    *,
    symbol: str,
    timeframe: str,
) -> dict[str, list[dict[str, Any]]]:
    """Confirmed external swings of the closed set, ATR-filtered."""

    swings = external_swing_points(
        candles,
        symbol=symbol,
        timeframe=timeframe,
        lookback=_EXTERNAL_PIVOT_WIDTH,
    )
    return _filter_swings_by_atr(list(candles), swings)


def _confirm_supply_demand(
    candles: Sequence[Candle],
    *,
    symbol: str,
    timeframe: str,
    as_of: datetime,
    window: Any = None,
) -> list[dict[str, Any]]:
    """Confirm each S/D candidate with its OWN causal departure ATR."""

    candidates = detect_supply_demand_candidates(
        candles,
        symbol=symbol,
        timeframe=timeframe,
    )
    confirmed: list[dict[str, Any]] = []
    for candidate in candidates:
        departure_index = int(candidate.get("departure_end_index", -1))
        causal_atr = (
            atr_value_before_event(
                list(candles),
                timeframe=timeframe,
                event_index=departure_index,
                window=window,
            )
            if departure_index >= 0
            else None
        )
        confirmed.append(
            confirm_supply_demand_candidate(
                candidate,
                candles,
                timeframe=timeframe,
                atr_before_event=causal_atr,
                as_of=as_of,
            )
        )
    return confirmed


def _structure_vocabulary(
    state: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
    snapshots: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Translate the canonical structure state into the evaluator's vocabulary.

    The mapping only renames what the canonical replay already concluded: the
    direction of the tracked structure and which confirmed event type is
    current.  Nothing new is inferred, and an unknown state stays ``unknown``.
    """

    direction = str(state.get("direction") or "").strip().lower()
    if direction == "bullish":
        structure = _STRUCTURE_BULLISH
        displacement = "bullish"
    elif direction == "bearish":
        structure = _STRUCTURE_BEARISH
        displacement = "bearish"
    else:
        structure = _STRUCTURE_UNKNOWN
        displacement = "neutral"

    types = {
        str(event.get("event_type") or event.get("type") or "").strip().upper()
        for event in events
        if event.get("invalidated_at") is None
    }
    bos = _EVENT_BOS in types
    choch = bool(types & {_EVENT_CHOCH_CANDIDATE, _EVENT_CHOCH_CONFIRMED})
    choch_confirmed = bool(
        _EVENT_CHOCH_CONFIRMED in types
        or any(bool(item.get("choch_confirmed")) for item in snapshots)
    )
    return {
        "structure": structure,
        "bos": bos,
        "choch": choch,
        "choch_confirmed": choch_confirmed,
        "displacement": displacement if (bos or choch) else "neutral",
        "bos_strength": "strong" if bos else "weak",
    }


def _enrich(
    zones: list[dict[str, Any]],
    candles: Sequence[Candle],
    family: str,
    sweeps: Mapping[str, Any],
    premium_discount_range: Mapping[str, Any],
    *,
    symbol: str,
    timeframe: str,
    tf_minutes: int,
    scan_interval_min: int,
    tick_size: float | None,
) -> None:
    """Enrich in place with lifecycle/visit evidence (task 57–65 contract)."""

    if not zones:
        return
    enriched = enrich_zones(
        zones,
        list(candles),
        family,
        dict(sweeps),
        dict(premium_discount_range),
        tf_minutes=tf_minutes,
        scan_interval_min=scan_interval_min,
        symbol=symbol,
        timeframe=timeframe,
        tick_size=tick_size,
    )
    zones[:] = enriched


def _pick(
    zones: Sequence[dict[str, Any]],
    by_id: Mapping[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep detector order but use the availability-processed payload."""

    result: list[dict[str, Any]] = []
    for zone in zones:
        processed = by_id.get(str(zone.get("zone_id") or ""))
        if processed is not None:
            result.append(processed)
    return result


def _limit(zones: Sequence[dict[str, Any]], family: str) -> list[dict[str, Any]]:
    """Apply the display cap only for output; existence is decided earlier."""

    limit = _DISPLAY_LIMITS.get(family)
    if limit is None or len(zones) <= limit:
        return list(zones)
    ordered = sorted(
        zones,
        key=lambda zone: (
            0 if str(zone.get("lifecycle_status") or "") in {"confirmed", "usable"} else 1,
            str(zone.get("zone_id") or ""),
        ),
    )
    return ordered[:limit]


def _positive(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number > 0 else None


def _zone_direction(zone: Mapping[str, Any]) -> str:
    return str(zone.get("direction") or "").strip().lower()


def _latest_atr(candles: Sequence[Candle]) -> float | None:
    from core.smc_context import _latest_atr as latest

    return latest(list(candles)) if candles else None


def _parse_cutoff(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    else:
        raise ValueError("canonical SMC context requires a snapshot cutoff")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("snapshot cutoff must be timezone-aware")
    return parsed.astimezone(timezone.utc)


__all__ = [
    "SMC_CANONICAL_CONTEXT_VERSION",
    "build_canonical_smc_context",
    "build_canonical_timeframe_context",
]
