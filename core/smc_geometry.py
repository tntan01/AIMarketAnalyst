"""Shared SMC zone geometry: width, distance and ordering (task 89).

One owner for the geometry rules the scorer and the Scanner planner both need,
so a candidate can never be scored as eligible while the planner rejects the
same bounds (or the other way round).  Everything here is pure data: no risk,
SL/TP, spread or policy decision is made in this module, and the approved
thresholds keep their existing values.

Contract sources: parameter table P11 (min/max width, hard distance, formation
and execution ATR), BQLC spec §4.2 (geometry features) and selection spec §4.1
(hard geometry filter).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

SMC_GEOMETRY_VERSION = "smc-geometry-v1"

# Parameter table P11 — approved thresholds, unchanged.
MAX_ZONE_WIDTH_ATR = 1.00          # zone wider than this cannot make a plan
HARD_DISTANCE_ATR = 3.00           # nearest-edge distance from price
MIN_ZONE_WIDTH_TICK_MULTIPLE = 2.0  # zone must be representable on the tick grid
NARROW_WIDTH_ATR = 0.35            # width_score plateau (BQLC spec §4.2)

# Geometry feature weights (BQLC spec §4.2).
WIDTH_WEIGHT = 0.65
FAMILY_GEOMETRY_WEIGHT = 0.35

VALID_GEOMETRY_FAMILIES = frozenset({"ob", "fvg", "supply_demand", "demand", "supply"})

# Reason/rejection codes owned by this seam.
GEOMETRY_BOUNDS_INVALID = "INVALID_ZONE_BOUNDS"
GEOMETRY_WIDTH_TOO_WIDE = "ZONE_WIDTH_TOO_WIDE"
GEOMETRY_WIDTH_TOO_NARROW = "ZONE_WIDTH_TOO_NARROW"
GEOMETRY_BEYOND_HARD_DISTANCE = "ZONE_BEYOND_HARD_DISTANCE"
GEOMETRY_UNAVAILABLE = "ZONE_GEOMETRY_UNAVAILABLE"
GEOMETRY_WRONG_PRICE_SIDE = "ZONE_ON_WRONG_PRICE_SIDE"
GEOMETRY_DISTANCE_UNAVAILABLE = "ZONE_DISTANCE_UNAVAILABLE"
# A zone that claims canonical formation evidence but has no usable formation
# ATR cannot be measured: both the geometry gate (scorer) and the plan seam
# (planner) fail closed with this one code instead of substituting the
# execution ATR (parameter table P11).
GEOMETRY_FORMATION_ATR_UNAVAILABLE = "FORMATION_ATR_UNAVAILABLE"
# D101-02: the canonical tick size is a dependency of the rules that quantize
# price (min width on the tick grid, gap/break buffers, rounding).  A rule that
# needs it and does not have it cannot be considered evaluated, so it fails
# closed HERE — at the candidate — and never as a snapshot-wide verdict.
GEOMETRY_TICK_SIZE_UNAVAILABLE = "SMC_TICK_SIZE_UNAVAILABLE"

# Fields whose presence means "this payload carries canonical evidence".
# A payload without any of them is a legacy/selected-zone projection, which
# keeps its documented pre-canonical reference (R80-91-02 note) instead of
# being failed closed for evidence it never claimed to have.
CANONICAL_PROVENANCE_FIELDS = ("departure_measurement", "formation_atr", "original_bounds")


def has_canonical_provenance(zone: object) -> bool:
    """Whether *zone* claims canonical evidence (one owner for the rule)."""

    return isinstance(zone, dict) and any(
        field in zone for field in CANONICAL_PROVENANCE_FIELDS
    )


def clamp01(value: object) -> float | None:
    """Clamp a finite number into ``[0, 1]``; ``None`` when unusable."""

    number = _finite(value)
    if number is None:
        return None
    return min(1.0, max(0.0, number))


def linear(value: float, start: float, end: float) -> float:
    """``clamp01((value - start) / (end - start))`` (BQLC spec §2)."""

    if end <= start:
        raise ValueError("linear() requires end > start")
    return min(1.0, max(0.0, (value - start) / (end - start)))


def inverse(value: float, start: float, end: float) -> float:
    """``clamp01((end - value) / (end - start))`` (BQLC spec §2)."""

    if end <= start:
        raise ValueError("inverse() requires end > start")
    return min(1.0, max(0.0, (end - value) / (end - start)))


def zone_width(low: object, high: object) -> float | None:
    """Protective/original width, or ``None`` when the bounds are unusable."""

    low_value = _finite(low)
    high_value = _finite(high)
    if low_value is None or high_value is None:
        return None
    width = high_value - low_value
    return width if width > 0 else None


def min_zone_width(tick_size: object) -> float | None:
    """Minimum representable width ``2 * tick``; unknown tick -> ``None``."""

    tick = _finite(tick_size)
    if tick is None or tick <= 0:
        return None
    return MIN_ZONE_WIDTH_TICK_MULTIPLE * tick


def bounds_are_ordered(
    low: object,
    high: object,
    *,
    tick_size: object = None,
) -> bool:
    """Hard validation gate: finite, ordered and representable on the tick grid.

    Passing this gate only allows the other features to be measured; it never
    contributes a geometry score by itself (BQLC spec §4.2).
    """

    width = zone_width(low, high)
    if width is None:
        return False
    minimum = min_zone_width(tick_size)
    if minimum is None:
        return True
    return width >= minimum


def width_atr(width: object, atr_value: object) -> float | None:
    """``width / ATR``; ``None`` when either input is unusable."""

    width_value = _finite(width)
    atr = _finite(atr_value)
    if width_value is None or width_value <= 0 or atr is None or atr <= 0:
        return None
    return width_value / atr


def width_score(width_ratio: object) -> float | None:
    """Width feature: 1 below ``0.35 ATR``, falling linearly to 0 at ``1.00``."""

    ratio = _finite(width_ratio)
    if ratio is None or ratio <= 0:
        return None
    if ratio <= NARROW_WIDTH_ATR:
        return 1.0
    return inverse(ratio, NARROW_WIDTH_ATR, MAX_ZONE_WIDTH_ATR)


def distance_to_zone(price: object, low: object, high: object) -> float | None:
    """Nearest-edge distance from price to the zone; ``0`` inside the zone."""

    price_value = _finite(price)
    low_value = _finite(low)
    high_value = _finite(high)
    if price_value is None or low_value is None or high_value is None:
        return None
    if high_value < low_value:
        return None
    if low_value <= price_value <= high_value:
        return 0.0
    return min(abs(price_value - low_value), abs(price_value - high_value))


def distance_atr(
    price: object,
    low: object,
    high: object,
    atr_value: object = None,
) -> float | None:
    """Nearest-edge distance in ``execution_atr`` units."""

    distance = distance_to_zone(price, low, high)
    atr = _finite(atr_value)
    if distance is None or atr is None or atr <= 0:
        return None
    return distance / atr


def price_on_zone_side(price: object, low: object, high: object, side: str) -> bool:
    """Whether price is on the correct side to trade the zone (buy below, sell above)."""

    price_value = _finite(price)
    low_value = _finite(low)
    high_value = _finite(high)
    if price_value is None or low_value is None or high_value is None:
        return False
    return low_value <= price_value if side == "buy" else high_value >= price_value


def family_geometry_score(
    family: str,
    *,
    base_width: object = None,
    formation_atr: object = None,
    remaining_width: object = None,
    original_width: object = None,
    average_range: object = None,
    compression_limit: object = None,
) -> float | None:
    """Family geometry feature (BQLC spec §4.2); ``None`` when it cannot be measured.

    ``None`` means the feature is unavailable and the candidate must be rejected
    with :data:`GEOMETRY_UNAVAILABLE` — it is never filled with 0 to rescue a plan.
    """

    normalized = str(family or "").strip().lower()
    if normalized in {"ob", "order_block"}:
        width = _finite(base_width)
        atr = _finite(formation_atr)
        if width is None or width <= 0 or atr is None or atr <= 0:
            return None
        return clamp01(1.0 - width / atr)
    if normalized == "fvg":
        remaining = _finite(remaining_width)
        original = _finite(original_width)
        if remaining is None or remaining < 0 or original is None or original <= 0:
            return None
        return clamp01(remaining / original)
    if normalized in {"supply_demand", "demand", "supply", "sd"}:
        width = _finite(base_width)
        avg_range = _finite(average_range)
        limit = _finite(compression_limit)
        if (
            width is None
            or width <= 0
            or avg_range is None
            or avg_range <= 0
            or limit is None
            or limit <= 0
        ):
            return None
        return clamp01(1.0 - width / (avg_range * limit))
    return None


@dataclass(frozen=True, slots=True)
class ZoneGeometryState:
    """Geometry verdict for one candidate at one cutoff."""

    bounds_valid: bool
    width: float | None = None
    width_ratio: float | None = None
    width_score: float | None = None
    family_geometry_score: float | None = None
    geometry: float | None = None
    distance: float | None = None
    distance_atr: float | None = None
    within_width_gate: bool = False
    within_distance_gate: bool = False
    rejection_codes: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()

    @property
    def plan_eligible(self) -> bool:
        """Whether the shared pre-plan gate passes (width and distance)."""

        return (
            self.bounds_valid
            and self.within_width_gate
            and self.within_distance_gate
            and not self.rejection_codes
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "geometry_version": SMC_GEOMETRY_VERSION,
            "bounds_valid": self.bounds_valid,
            "width": self.width,
            "width_atr": self.width_ratio,
            "width_score": self.width_score,
            "family_geometry_score": self.family_geometry_score,
            "geometry": self.geometry,
            "distance": self.distance,
            "distance_atr": self.distance_atr,
            "within_width_gate": self.within_width_gate,
            "within_distance_gate": self.within_distance_gate,
            "plan_eligible": self.plan_eligible,
            "rejection_codes": list(self.rejection_codes),
            "reason_codes": list(self.reason_codes),
        }


def evaluate_zone_geometry(
    *,
    family: str,
    side: str,
    original_low: object,
    original_high: object,
    formation_atr: object = None,
    execution_atr: object = None,
    price: object = None,
    tick_size: object = None,
    family_inputs: dict[str, Any] | None = None,
    require_family_geometry: bool = True,
    require_tick: bool = False,
) -> ZoneGeometryState:
    """Evaluate the shared geometry of one candidate.

    ``formation_atr`` is the causal same-timeframe ATR of the source zone and
    owns width/quality geometry; ``execution_atr`` is the shared execution
    reference and owns the hard distance gate.  They are never interchanged
    (parameter table P11).
    """

    inputs = family_inputs if isinstance(family_inputs, dict) else {}
    rejections: list[str] = []
    reasons: list[str] = []

    low = _finite(original_low)
    high = _finite(original_high)
    bounds_valid = bounds_are_ordered(low, high, tick_size=tick_size)
    if not bounds_valid:
        rejections.append(GEOMETRY_BOUNDS_INVALID)
        return ZoneGeometryState(
            bounds_valid=False,
            rejection_codes=tuple(rejections),
            reason_codes=tuple(reasons),
        )
    width = zone_width(low, high)
    assert width is not None

    ratio = width_atr(width, formation_atr)
    feature_width = width_score(ratio)
    family_feature = family_geometry_score(
        family,
        base_width=inputs.get("base_width", width),
        formation_atr=formation_atr,
        remaining_width=inputs.get("remaining_width"),
        original_width=inputs.get("original_width"),
        average_range=inputs.get("average_range"),
        compression_limit=inputs.get("compression_limit"),
    )
    if feature_width is None or (require_family_geometry and family_feature is None):
        rejections.append(GEOMETRY_UNAVAILABLE)
        reasons.append(GEOMETRY_UNAVAILABLE)
        return ZoneGeometryState(
            bounds_valid=True,
            width=width,
            width_ratio=ratio,
            width_score=feature_width,
            family_geometry_score=family_feature,
            rejection_codes=tuple(rejections),
            reason_codes=tuple(reasons),
        )

    minimum = min_zone_width(tick_size)
    if minimum is None:
        if require_tick:
            # D101-02: the canonical payload needs the tick size for this rule
            # and does not have it, so the rule was not evaluated and the
            # candidate fails closed HERE.  A legacy payload that never claimed
            # canonical evidence keeps its documented pre-canonical reference.
            rejections.append(GEOMETRY_TICK_SIZE_UNAVAILABLE)
    elif width < minimum:
        rejections.append(GEOMETRY_WIDTH_TOO_NARROW)
    within_width_gate = ratio <= MAX_ZONE_WIDTH_ATR
    if not within_width_gate:
        rejections.append(GEOMETRY_WIDTH_TOO_WIDE)

    distance = distance_to_zone(price, low, high)
    distance_ratio = distance_atr(price, low, high, execution_atr)
    within_distance_gate = False
    if distance is None:
        reasons.append(GEOMETRY_DISTANCE_UNAVAILABLE)
    elif distance_ratio is None:
        rejections.append(GEOMETRY_DISTANCE_UNAVAILABLE)
    elif not price_on_zone_side(price, low, high, side):
        rejections.append(GEOMETRY_WRONG_PRICE_SIDE)
    elif distance_ratio > HARD_DISTANCE_ATR:
        rejections.append(GEOMETRY_BEYOND_HARD_DISTANCE)
    else:
        within_distance_gate = True

    geometry = (
        WIDTH_WEIGHT * feature_width + FAMILY_GEOMETRY_WEIGHT * (family_feature or 0.0)
    )
    return ZoneGeometryState(
        bounds_valid=True,
        width=width,
        width_ratio=ratio,
        width_score=feature_width,
        family_geometry_score=family_feature,
        geometry=geometry,
        distance=distance,
        distance_atr=distance_ratio,
        within_width_gate=within_width_gate,
        within_distance_gate=within_distance_gate,
        rejection_codes=tuple(rejections),
        reason_codes=tuple(reasons),
    )


def pre_plan_geometry_gate(
    *,
    side: str,
    original_low: object,
    original_high: object,
    formation_atr: object,
    execution_atr: object,
    price: object,
    tick_size: object = None,
    require_tick: bool = False,
) -> ZoneGeometryState:
    """The planner-side subset of the same gate (width and distance only)."""

    return evaluate_zone_geometry(
        family="",
        side=side,
        original_low=original_low,
        original_high=original_high,
        formation_atr=formation_atr,
        execution_atr=execution_atr,
        price=price,
        tick_size=tick_size,
        require_family_geometry=False,
        require_tick=require_tick,
    )


def _finite(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None
