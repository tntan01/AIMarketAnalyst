"""Directional multi-timeframe confluence for the canonical SMC contract."""

from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any

from core.smc_models import (
    DirectionalConfluence,
    TimeframeConfluenceEvidence,
)


_BULLISH_STRUCTURE = "HH/HL"
_BEARISH_STRUCTURE = "LH/LL"
PARENT_CHILD_OVERLAP_MIN = 0.50
D1_REACTION_LIFETIME_BARS = 20


def build_parent_child_relation(
    parent: dict[str, Any],
    child: dict[str, Any],
    *,
    tick_size: float | None = None,
    atr_parent: float | None = None,
    expansion_tolerance: float | None = None,
    overlap_min: float = PARENT_CHILD_OVERLAP_MIN,
) -> dict[str, Any]:
    """Evaluate one directional parent/child zone relation.

    Containment is checked after the approved parent expansion
    ``max(1*tick, 0.05*ATR_parent)``.  If containment fails, an overlap of at
    least 50% of the narrower zone is accepted as the documented alternative.
    Missing geometry or expansion metadata is returned as ``unknown`` rather
    than being inferred from proximity.
    """

    parent_value = parent if isinstance(parent, dict) else {}
    child_value = child if isinstance(child, dict) else {}
    parent_side = _zone_direction(parent_value)
    child_side = _zone_direction(child_value)
    parent_bounds = _bounds(parent_value)
    child_bounds = _bounds(child_value)
    base = {
        "parent_id": _identifier(parent_value, "parent_id"),
        "child_id": _identifier(child_value, "child_id"),
        "direction": child_side or parent_side or "unknown",
        "valid": False,
        "relation": "unknown",
        "score": 0.0,
        "overlap_ratio": None,
        "expansion_tolerance": None,
        "reason_codes": [],
    }
    if parent_side not in {"buy", "sell"} or child_side != parent_side:
        base["reason_codes"] = ["PARENT_CHILD_DIRECTION_MISMATCH"]
        return base
    if parent_bounds is None or child_bounds is None:
        base["reason_codes"] = ["PARENT_CHILD_GEOMETRY_UNAVAILABLE"]
        return base

    if expansion_tolerance is not None:
        tolerance = _non_negative(expansion_tolerance)
    elif tick_size is not None and atr_parent is not None:
        tick = _positive(tick_size)
        atr = _positive(atr_parent)
        if tick is None or atr is None:
            base["reason_codes"] = ["PARENT_CHILD_EXPANSION_UNAVAILABLE"]
            return base
        tolerance = max(tick, 0.05 * atr)
    else:
        base["reason_codes"] = ["PARENT_CHILD_EXPANSION_UNAVAILABLE"]
        return base
    if tolerance is None:
        base["reason_codes"] = ["PARENT_CHILD_EXPANSION_INVALID"]
        return base

    parent_low, parent_high = parent_bounds
    child_low, child_high = child_bounds
    expanded_low = parent_low - tolerance
    expanded_high = parent_high + tolerance
    contained = expanded_low <= child_low and child_high <= expanded_high
    overlap_low = max(parent_low, child_low)
    overlap_high = min(parent_high, child_high)
    overlap_width = max(0.0, overlap_high - overlap_low)
    narrower_width = min(parent_high - parent_low, child_high - child_low)
    overlap_ratio = (
        overlap_width / narrower_width if narrower_width > 0 else None
    )
    base["expansion_tolerance"] = tolerance
    base["overlap_ratio"] = overlap_ratio
    if contained:
        base.update({
            "valid": True,
            "relation": "contained",
            "score": 1.0,
            "reason_codes": ["PARENT_CHILD_CONTAINED"],
        })
    elif overlap_ratio is not None and overlap_ratio >= overlap_min:
        base.update({
            "valid": True,
            "relation": "overlap",
            "score": 0.75,
            "reason_codes": ["PARENT_CHILD_OVERLAP"],
        })
    else:
        base["reason_codes"] = ["PARENT_CHILD_RELATION_INVALID"]
    return base


def build_d1_reaction_evidence(
    d1_zone: dict[str, Any],
    lifecycle: Any,
    *,
    as_of: datetime | str | None = None,
    lifetime_bars: int = D1_REACTION_LIFETIME_BARS,
) -> dict[str, Any]:
    """Read one valid D1 reaction from canonical lifecycle visits only.

    Legacy proximity or boolean reaction flags are intentionally ignored.  A
    reaction requires a visit in ``completed_reacted`` state with a canonical
    ``reacted_at`` and must not be stale/expired at the supplied cutoff.
    """

    zone = d1_zone if isinstance(d1_zone, dict) else {}
    zone_id = _identifier(zone, "zone_id")
    result: dict[str, Any] = {
        "valid": False,
        "score": 0.0,
        "zone_id": zone_id,
        "source_visit_id": None,
        "source_event_id": None,
        "reacted_at": None,
        "age_bars": None,
        "reason_codes": [],
    }
    visits = _lifecycle_value(lifecycle, "visits", [])
    if not isinstance(visits, (list, tuple)):
        result["reason_codes"] = ["D1_REACTION_LIFECYCLE_UNAVAILABLE"]
        return result
    valid_visits: list[dict[str, Any]] = []
    for raw_visit in visits:
        visit = _as_mapping(raw_visit)
        if not visit:
            continue
        state = str(
            visit.get("visit_state", visit.get("state", visit.get("status", "")))
            or ""
        ).strip().lower()
        reacted_at = _parse_time(visit.get("reacted_at"))
        visit_zone_id = str(visit.get("zone_id", "") or "").strip()
        if (
            state != "completed_reacted"
            or reacted_at is None
            or (visit_zone_id and zone_id and visit_zone_id != zone_id)
        ):
            continue
        valid_visits.append({"visit": visit, "reacted_at": reacted_at})
    if not valid_visits:
        result["reason_codes"] = ["D1_REACTION_NOT_COMPLETED_REACTED"]
        return result

    cutoff = _parse_time(as_of) if as_of is not None else None

    def _sources() -> tuple[Any, Any]:
        return (zone, lifecycle)

    def _terminal_flag(key: str) -> bool:
        """True when EITHER source reports this terminal flag.

        B-R1: terminal evidence from the actual lifecycle must not be masked by a default or
        explicitly non-terminal flag on the zone mapping (nor the other way round), so the
        flags are combined with OR instead of letting one source win per field.
        """

        for source in _sources():
            value = (
                source.get(key)
                if isinstance(source, dict)
                else _lifecycle_value(source, key, None)
            )
            if bool(value):
                return True
        return False

    def _terminal_status() -> bool:
        for source in _sources():
            value = (
                source.get("lifecycle_status")
                if isinstance(source, dict)
                else _lifecycle_value(source, "lifecycle_status", None)
            )
            if str(value or "").strip().lower() in {"invalid", "expired", "stale"}:
                return True
        return False

    def _earliest_terminal_at() -> Any:
        """Earliest declared terminal timestamp across both sources."""

        found = []
        for source in _sources():
            for key in ("invalidated_at", "expired_at"):
                value = (
                    source.get(key)
                    if isinstance(source, dict)
                    else _lifecycle_value(source, key, None)
                )
                parsed = _parse_time(value)
                if parsed is not None:
                    found.append(parsed)
        return min(found) if found else None

    def _largest_age() -> int | None:
        """Largest declared age: a default `0` on one source must not mask a real age."""

        ages = []
        for source in _sources():
            value = (
                source.get("age_bars")
                if isinstance(source, dict)
                else _lifecycle_value(source, "age_bars", None)
            )
            parsed = _optional_int(value)
            if parsed is not None:
                ages.append(parsed)
        return max(ages) if ages else None

    lifecycle_expired = _terminal_flag("lifecycle_expired")
    lifecycle_stale = _terminal_flag("lifecycle_stale")
    lifecycle_broken = _terminal_flag("lifecycle_broken") or _terminal_flag("broken")
    age_bars = _largest_age()
    # Canonical terminal evidence forbids an active reaction (A-D04) and outranks any legacy
    # `d1_reaction`/`proximity` flag. The terminal timestamp is inclusive at the cutoff, so a
    # zone terminating exactly at the cutoff is terminal while an earlier cutoff stays a valid
    # positive prefix — no past snapshot is rebuilt from a later terminal payload.
    terminal_at = _earliest_terminal_at()
    terminal_at_cutoff = (
        terminal_at is not None and cutoff is not None and terminal_at <= cutoff
    )
    if (
        lifecycle_broken
        or _terminal_status()
        or lifecycle_expired
        or lifecycle_stale
        or terminal_at_cutoff
        or (age_bars is not None and age_bars > lifetime_bars)
    ):
        result["age_bars"] = age_bars
        result["reason_codes"] = ["D1_REACTION_STALE"]
        return result
    latest = max(valid_visits, key=lambda item: item["reacted_at"])
    if cutoff is not None and latest["reacted_at"] > cutoff:
        result["reason_codes"] = ["D1_REACTION_AFTER_CUTOFF"]
        return result
    visit = latest["visit"]
    result.update({
        "valid": True,
        "score": 1.0,
        "source_visit_id": str(visit.get("visit_id", "") or "") or None,
        "source_event_id": str(
            visit.get("reaction_event_id", visit.get("event_id", "")) or ""
        ) or None,
        "reacted_at": latest["reacted_at"].isoformat(),
        "age_bars": age_bars,
        "reason_codes": ["D1_REACTION_COMPLETED_REACTED"],
    })
    return result


def _zone_direction(value: dict[str, Any]) -> str:
    return str(value.get("direction", value.get("side", "")) or "").strip().lower()


def _bounds(value: dict[str, Any]) -> tuple[float, float] | None:
    try:
        low = float(value.get("low"))
        high = float(value.get("high"))
    except (TypeError, ValueError, OverflowError):
        return None
    if not isfinite(low) or not isfinite(high) or high <= low:
        return None
    return low, high


def _identifier(value: dict[str, Any], key: str) -> str | None:
    fallback = "zone_id" if key == "parent_id" else "zone_id"
    result = str(value.get(key, value.get(fallback, "")) or "").strip()
    return result or None


def _positive(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if isfinite(parsed) and parsed > 0 else None


def _non_negative(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if isfinite(parsed) and parsed >= 0 else None


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    to_dict = getattr(value, "to_dict", None)
    converted = to_dict() if callable(to_dict) else None
    return converted if isinstance(converted, dict) else {}


def _lifecycle_value(value: Any, key: str, default: Any) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _parse_time(value: object) -> datetime | None:
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


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def build_directional_confluence(
    d1_smc: dict[str, Any],
    h4_smc: dict[str, Any],
    h1_smc: dict[str, Any],
) -> DirectionalConfluence:
    """Build side-aware D1/H4/H1 confluence from canonical evidence."""

    d1 = _timeframe_evidence("D1", d1_smc)
    h4 = _timeframe_evidence("H4", h4_smc)
    h1 = _timeframe_evidence("H1", h1_smc)
    evidence = (d1, h4, h1)

    buy_score = 0
    sell_score = 0
    buy_reasons: list[str] = []
    sell_reasons: list[str] = []
    common_reasons: list[str] = []

    def award(side: str, points: int, code: str) -> None:
        nonlocal buy_score, sell_score
        if side == "buy":
            buy_score += points
            buy_reasons.append(code)
        elif side == "sell":
            sell_score += points
            sell_reasons.append(code)

    d1_h4_aligned = (
        d1.direction in {"buy", "sell"}
        and d1.direction == h4.direction
    )
    h4_h1_aligned = (
        h4.direction in {"buy", "sell"}
        and h4.direction == h1.direction
    )
    h1_against_h4 = (
        h4.direction in {"buy", "sell"}
        and h1.direction in {"buy", "sell"}
        and h4.direction != h1.direction
    )
    all_aligned = d1_h4_aligned and h4_h1_aligned

    if d1_h4_aligned:
        side_code = d1.direction.upper()
        award(d1.direction, 2, f"{side_code}_D1_H4_ALIGNED")
        common_reasons.append("D1_H4_ALIGNED")

    h1_relationship = "unknown"
    if h4_h1_aligned:
        side_code = h4.direction.upper()
        award(h4.direction, 2, f"{side_code}_H4_H1_ALIGNED")
        common_reasons.append("H4_H1_ALIGNED")
        h1_relationship = "aligned"
    elif h1_against_h4:
        if _is_h1_reversal_signal(h1):
            h1_relationship = "reversal"
            award(
                h1.direction,
                1,
                f"{h1.direction.upper()}_H1_REVERSAL_SIGNAL",
            )
            _append_side_reason(
                buy_reasons,
                sell_reasons,
                h4.direction,
                f"{h4.direction.upper()}_H1_REVERSAL_RISK",
            )
            common_reasons.append("H1_REVERSAL_AGAINST_H4")
        else:
            h1_relationship = "pullback"
            _append_side_reason(
                buy_reasons,
                sell_reasons,
                h4.direction,
                f"{h4.direction.upper()}_H1_PULLBACK_AGAINST_H4",
            )
            common_reasons.append("H1_PULLBACK_AGAINST_H4")
    elif h4.direction in {"buy", "sell"} and h1.direction == "unknown":
        h1_relationship = "unknown"

    if all_aligned:
        side_code = h4.direction.upper()
        award(
            h4.direction,
            1,
            f"{side_code}_ALL_TIMEFRAMES_ALIGNED",
        )
        common_reasons.append("ALL_TIMEFRAMES_ALIGNED")

    buy_score = max(0, min(5, buy_score))
    sell_score = max(0, min(5, sell_score))
    if buy_score > sell_score:
        direction = "bullish"
    elif sell_score > buy_score:
        direction = "bearish"
    elif buy_score or sell_score:
        direction = "mixed"
    else:
        direction = "unknown"

    known_count = sum(
        item.direction in {"buy", "sell"}
        for item in evidence
    )
    if known_count == 3:
        data_status = "complete"
    elif known_count:
        data_status = "partial"
        common_reasons.append("PARTIAL_TIMEFRAME_DATA")
    else:
        data_status = "insufficient"
        common_reasons.append("INSUFFICIENT_TIMEFRAME_DATA")

    return DirectionalConfluence(
        direction=direction,
        buy_score=buy_score,
        sell_score=sell_score,
        d1_h4_aligned=d1_h4_aligned,
        h4_h1_aligned=h4_h1_aligned,
        h1_against_h4=h1_against_h4,
        all_aligned=all_aligned,
        h1_relationship=h1_relationship,
        data_status=data_status,
        buy_reason_codes=tuple(buy_reasons),
        sell_reason_codes=tuple(sell_reasons),
        reason_codes=tuple(common_reasons),
        timeframe_evidence=evidence,
    )


def _timeframe_evidence(
    timeframe: str,
    payload: dict[str, Any],
) -> TimeframeConfluenceEvidence:
    value = payload if isinstance(payload, dict) else {}
    structure = str(value.get("structure", "unknown") or "unknown")
    direction = _structure_side(structure)
    displacement = str(
        value.get("displacement", "neutral") or "neutral"
    ).lower()
    bos = bool(value.get("bos", False))
    choch = bool(value.get("choch", False))
    choch_confirmed = bool(value.get("choch_confirmed", False))
    reasons = [f"{timeframe}_STRUCTURE_{direction.upper()}"]
    if bos:
        reasons.append(f"{timeframe}_BOS_{displacement.upper()}")
    if choch:
        suffix = "_CONFIRMED" if choch_confirmed else ""
        reasons.append(
            f"{timeframe}_CHOCH_{displacement.upper()}{suffix}"
        )
    if direction == "unknown":
        reasons.append(f"{timeframe}_STRUCTURE_UNAVAILABLE")
    return TimeframeConfluenceEvidence(
        timeframe=timeframe,
        structure=structure,
        direction=direction,
        bos=bos,
        choch=choch,
        choch_confirmed=choch_confirmed,
        displacement=displacement,
        reason_codes=tuple(reasons),
    )


def _structure_side(structure: str) -> str:
    if structure == _BULLISH_STRUCTURE:
        return "buy"
    if structure == _BEARISH_STRUCTURE:
        return "sell"
    return "unknown"


def _is_h1_reversal_signal(
    evidence: TimeframeConfluenceEvidence,
) -> bool:
    expected_displacement = (
        "bullish" if evidence.direction == "buy" else "bearish"
    )
    displacement_confirms = (
        evidence.displacement == expected_displacement
    )
    return (
        evidence.choch_confirmed
        or (evidence.choch and displacement_confirms)
        or (evidence.bos and displacement_confirms)
    )


def _append_side_reason(
    buy_reasons: list[str],
    sell_reasons: list[str],
    side: str,
    code: str,
) -> None:
    if side == "buy":
        buy_reasons.append(code)
    elif side == "sell":
        sell_reasons.append(code)
