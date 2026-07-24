"""Canonical liquidity-sweep to SMC-zone association.

This module assigns at most one concrete sweep to one concrete zone. It is
side-aware, price-aware, time-aware, and deterministic so live and replay paths
produce the same relationship from the same inputs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import hashlib
from math import isfinite
from typing import Any


SMC_SWEEP_LINK_VERSION = "smc-sweep-link-v1"
SWEEP_ZONE_TOLERANCE_ATR = 0.25


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
        }

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


def associate_sweeps_to_zones(
    zones: list[dict[str, Any]],
    liquidity_sweeps: dict[str, list[dict[str, Any]]],
    *,
    atr_value: float | None,
    tolerance_atr: float = SWEEP_ZONE_TOLERANCE_ATR,
) -> dict[str, SweepZoneLink]:
    """Return deterministic one-to-one sweep/zone links.

    Eligible pairs must have the same side, a sweep occurrence inside the
    zone's formation/departure window, and a level inside the zone or no more
    than ``tolerance_atr`` from its nearest boundary.
    """

    normalized_atr = _positive_float(atr_value)
    tolerance = max(0.0, _finite_float(tolerance_atr, 0.0))
    pairs: list[tuple[tuple[Any, ...], SweepZoneLink]] = []

    for sweep in _flatten_sweeps(liquidity_sweeps):
        sweep_id = str(sweep.get("sweep_id", "") or "").strip()
        sweep_side = str(sweep.get("side", "") or "").strip().lower()
        sweep_index = _optional_int(sweep.get("index"))
        sweep_level = _optional_float(sweep.get("level"))
        if (
            not sweep_id
            or sweep_side not in {"buy", "sell"}
            or sweep_index is None
            or sweep_level is None
        ):
            continue

        for zone in zones:
            zone_id = str(zone.get("zone_id", "") or "").strip()
            zone_side = str(zone.get("direction", "") or "").strip().lower()
            if not zone_id or zone_side != sweep_side:
                continue

            origin_index = _optional_int(
                zone.get("origin_index", zone.get("index"))
            )
            departure_index = _optional_int(zone.get("departure_end_index"))
            if origin_index is None or departure_index is None:
                continue
            formation_start = _optional_int(
                zone.get("formation_start_index")
            )
            if formation_start is None:
                formation_start = origin_index
            if not formation_start <= sweep_index <= departure_index:
                continue

            low = _optional_float(zone.get("low"))
            high = _optional_float(zone.get("high"))
            if low is None or high is None:
                continue
            zone_low, zone_high = sorted((low, high))
            price_distance = _distance_to_zone(
                sweep_level,
                zone_low,
                zone_high,
            )
            if price_distance == 0:
                distance_atr = 0.0
            elif normalized_atr is None:
                continue
            else:
                distance_atr = price_distance / normalized_atr
            if distance_atr > tolerance:
                continue

            departure_gap = departure_index - sweep_index
            time_delta = sweep_index - origin_index
            link = SweepZoneLink(
                zone_id=zone_id,
                sweep_id=sweep_id,
                sweep_kind=str(sweep.get("kind", "") or ""),
                sweep_level=sweep_level,
                sweep_time=str(sweep.get("time", "") or ""),
                sweep_index=sweep_index,
                distance_atr=round(distance_atr, 6),
                time_delta=time_delta,
            )
            rank = (
                round(distance_atr, 12),
                departure_gap,
                abs(time_delta),
                zone_id,
                sweep_id,
            )
            pairs.append((rank, link))

    links: dict[str, SweepZoneLink] = {}
    used_sweeps: set[str] = set()
    for _, link in sorted(pairs, key=lambda item: item[0]):
        if link.zone_id in links or link.sweep_id in used_sweeps:
            continue
        links[link.zone_id] = link
        used_sweeps.add(link.sweep_id)
    return links


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
