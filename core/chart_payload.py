from __future__ import annotations

from math import isfinite
from typing import Any

from core.market_models import Candle
from core.scanner_ranking_engine import _find_scenario_for_side


# ---------------------------------------------------------------------------
# Canonical SMC overlay (task 123)
# ---------------------------------------------------------------------------

# Where an overlay layer came from.  Only ``canonical`` may be drawn as the SMC
# result of this scan; a row stored before the canonical verdict existed keeps
# its absence instead of being shown as a current zone.
SMC_OVERLAY_SOURCE_CANONICAL = "canonical"
SMC_OVERLAY_SOURCE_MISSING = "missing"

# Zone status the chart renders differently (selected = solid, invalid = faded).
SMC_ZONE_STATUS_SELECTED = "selected"
SMC_ZONE_STATUS_WATCH = "watch"
SMC_ZONE_STATUS_INVALID = "invalid"

# Reason code emitted when a canonical payload exists but publishes no
# protected swing for the chart to draw.
SMC_PROTECTED_SWING_UNAVAILABLE = "SMC_PROTECTED_SWING_UNAVAILABLE"

# Lifecycle states that mean the zone can no longer be used for entry.
_INVALID_LIFECYCLE = frozenset({"invalid", "expired"})
# Confirmation states that invalidate an otherwise usable zone.
_INVALID_CONFIRMATION = frozenset({"invalidated", "expired"})


def _finite(value: Any) -> float | None:
    """A real finite number, or ``None`` (a boolean is never a price)."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) else None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _canonical_selection(result: Any, side: str) -> dict[str, Any] | None:
    """The CURRENT canonical SMC selection of *side*, or ``None``.

    The carrier resolution, the final-invariant check and the persisted-document
    verdict are all owned by ``core.smc_consumer_contract`` (task 128 P0), so the
    chart and the UI panels read the SAME boundary and cannot disagree about
    whether a payload is current.  The legacy ``smc`` zone dump is never read: it
    is historical evidence, not the current verdict.
    """

    from core.smc_consumer_contract import canonical_selection_of

    return canonical_selection_of(result, side)


def _read_selection(source: Any, side: str):
    """The full read outcome of one side (status + reasons), for the overlay."""

    from core.smc_consumer_contract import read_canonical_selection

    return read_canonical_selection(source, side if side in ("buy", "sell") else "")


def _effective_confirmation_status(selection: dict[str, Any]) -> str:
    """The confirmation status of this selection, from its strongest evidence.

    The typed M15 record is the evidence stored verbatim (task 117); when the
    payload carries one, its ``status`` decides.  The readiness projection
    (``m15_status``) is a separate vocabulary and is read only when no record is
    present, so an invalidated record can never be drawn as a live zone.
    """

    record = selection.get("confirmation")
    if isinstance(record, dict):
        status = _text(record.get("status")).lower()
        if status:
            return status
    return _text(selection.get("m15_status")).lower()


def _zone_status(selection: dict[str, Any]) -> str:
    """Whether the selected zone is still usable, only watched, or dead."""

    lifecycle = _text(selection.get("lifecycle_status")).lower()
    confirmation = _effective_confirmation_status(selection)
    if lifecycle in _INVALID_LIFECYCLE or confirmation in _INVALID_CONFIRMATION:
        return SMC_ZONE_STATUS_INVALID
    readiness = _text(selection.get("readiness_status")).upper()
    if readiness == "WATCH_ZONE":
        return SMC_ZONE_STATUS_WATCH
    return SMC_ZONE_STATUS_SELECTED


def _trigger_payload(selection: dict[str, Any], side: str) -> dict[str, Any] | None:
    """The canonical M15 trigger of the SAME selection, or ``None``.

    Every value is copied from the stored confirmation record: the trigger keeps
    its own identity and its own time.  A record whose trigger time is missing or
    placed before its confirmation is NOT drawn — the chart never moves an event
    to a moment it did not happen at, and never invents a trigger time from the
    visit anchor.
    """

    record = selection.get("confirmation")
    if not isinstance(record, dict):
        return None
    trigger_at = _text(record.get("trigger_at"))
    if not trigger_at:
        return None
    confirmed_at = _text(record.get("confirmed_at"))
    if confirmed_at and trigger_at < confirmed_at:
        return None
    low = _finite(record.get("zone_low"))
    high = _finite(record.get("zone_high"))
    if low is None or high is None or high <= low:
        return None
    return {
        "zone_id": _text(record.get("zone_id")) or _text(selection.get("selected_zone_id")),
        "setup_id": _text(selection.get("selected_setup_id")),
        "side": _text(record.get("side")) or side,
        "status": _text(record.get("status")).lower(),
        "trigger_event_id": _text(record.get("trigger_event_id")) or None,
        "trigger_kind": _text(record.get("trigger_kind")) or None,
        "trigger_at": trigger_at,
        "confirmed_at": confirmed_at or None,
        "expires_at": _text(record.get("expires_at")) or None,
        "invalidated_at": _text(record.get("invalidated_at")) or None,
        "from": low,
        "to": high,
    }


def _protected_swing_payload(selection: dict[str, Any] | None) -> dict[str, Any] | None:
    """The canonical protected swing of the selected setup, when one is published.

    Lô A: the record is read from ``selection["protected_swing"]``, the additive
    field the canonical selection carries from the structure state of the
    selected zone's own timeframe.  It is copied verbatim — nothing is derived,
    re-measured or looked up here.

    ``None`` means the canonical evidence did not publish one, and the overlay
    reports :data:`SMC_PROTECTED_SWING_UNAVAILABLE` instead of drawing a level
    taken from the legacy detector, from the plan's stop-loss or from a technical
    level.  ``level`` is what the chart draws, so a record whose level is not a
    finite positive number is treated as no record at all rather than drawn.
    """

    if not isinstance(selection, dict):
        return None
    record = selection.get("protected_swing")
    if not isinstance(record, dict):
        return None
    level = _finite(record.get("protected_swing_level"))
    if level is None or level <= 0:
        return None
    swing_id = _text(record.get("protected_swing_id"))
    if not swing_id:
        return None
    return {
        "id": swing_id,
        "kind": _text(record.get("protected_swing_kind")) or None,
        "level": level,
        "pivot_time": _text(record.get("protected_swing_pivot_time")) or None,
        "confirmed_at": _text(record.get("protected_swing_confirmed_at")) or None,
        "source_bos_id": _text(record.get("source_bos_id")) or None,
    }


def build_smc_overlay(result: Any) -> dict[str, Any]:
    """Build the canonical SMC overlay of a chart payload (task 123).

    *result* is an analysis result or the row/document that carries one.  The
    overlay is keyed by timeframe because a selected zone belongs to one
    timeframe; the chart draws the layer of the timeframe it is showing.

    Only a selection the shared read boundary certifies CURRENT may be drawn
    (task 128 P0): a stored payload that is historical, incompatible or
    corrupted contributes no band, and its verdict travels in ``read_status``/
    ``reason_codes`` so the chart states the absence instead of painting a legacy
    zone as if it were the live result.

    Geometry (bands, ids, times) is copied verbatim: the selected band, the
    trigger band and the trigger time keep the identity and the moment the
    canonical chain recorded.
    """

    timeframes: dict[str, Any] = {}
    sides: dict[str, Any] = {}
    for side in ("buy", "sell"):
        read = _read_selection(result, side)
        sides[side] = read.to_dict()
        selection = read.selection
        if selection is None:
            continue
        low = _finite(selection.get("zone_low"))
        high = _finite(selection.get("zone_high"))
        timeframe = _text(selection.get("timeframe")).upper()
        zone_id = _text(selection.get("selected_zone_id"))
        if low is None or high is None or high <= low or not timeframe or not zone_id:
            continue
        status = _zone_status(selection)
        zone = {
            "zone_id": zone_id,
            "setup_id": _text(selection.get("selected_setup_id")) or None,
            "side": side,
            "timeframe": timeframe,
            "family": _text(selection.get("family")) or None,
            "status": status,
            "lifecycle_status": _text(selection.get("lifecycle_status")) or None,
            "from": low,
            "to": high,
            "plan_available": bool(selection.get("plan_available")),
            # Only a zone that is still usable AND has an accepted plan is an
            # entry region.  A watched zone without a plan, or a zone whose
            # confirmation was invalidated, keeps its geometry but is never
            # drawn as something to enter on.
            "execution_eligible": bool(
                selection.get("plan_available")
            ) and status == SMC_ZONE_STATUS_SELECTED,
        }
        layer = timeframes.setdefault(
            timeframe,
            {"zones": [], "trigger": None, "protected_swing": None, "reason_codes": []},
        )
        layer["zones"].append(zone)
        if layer["trigger"] is None:
            layer["trigger"] = _trigger_payload(selection, side)
        if layer["protected_swing"] is None:
            layer["protected_swing"] = _protected_swing_payload(selection)
        if layer["protected_swing"] is None:
            layer["reason_codes"].append(SMC_PROTECTED_SWING_UNAVAILABLE)

    for layer in timeframes.values():
        layer["reason_codes"] = sorted(set(layer["reason_codes"]))

    reason_codes = sorted(
        {
            code
            for read in sides.values()
            for code in read["reason_codes"]
        }
    )
    return {
        # ``available`` is about the canonical verdict, not about how many
        # layers it happens to carry: an evaluated ``no_zone`` side has no band
        # to draw and is still a real canonical answer.
        "available": bool(timeframes),
        "source": (
            SMC_OVERLAY_SOURCE_CANONICAL
            if timeframes
            else SMC_OVERLAY_SOURCE_MISSING
        ),
        # What the shared read boundary said about this payload (task 128 P0).
        # ``read_status`` is ``current`` as soon as one side is current; when no
        # side is, it says whether the payload is a readable-but-older record or
        # unusable bytes.  The chart draws nothing in either case.
        "read_status": _overlay_read_status(sides),
        "reason_codes": reason_codes,
        "sides": sides,
        "timeframes": timeframes,
    }


def _overlay_read_status(sides: dict[str, Any]) -> str:
    """Aggregate read status of both sides for the overlay."""

    from core.smc_consumer_contract import (
        SMC_READ_CURRENT,
        SMC_READ_HISTORICAL,
        SMC_READ_UNAVAILABLE,
    )

    statuses = [read["status"] for read in sides.values()]
    if SMC_READ_CURRENT in statuses:
        return SMC_READ_CURRENT
    if SMC_READ_HISTORICAL in statuses:
        return SMC_READ_HISTORICAL
    return SMC_READ_UNAVAILABLE


def build_chart_payload(candles_by_timeframe: dict[str, list[Candle]]) -> dict[str, list[dict[str, Any]]]:
    return {
        timeframe: [
            {
                "time": candle.time.isoformat(),
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
            }
            for candle in candles
        ]
        for timeframe, candles in candles_by_timeframe.items()
    }


def build_full_chart_payload(
    symbol: str,
    result: dict,
    active_timeframe: str = "D1",
    *,
    smc_source: dict | None = None,
) -> dict:
    """Build complete chart payload for QWebEngineView rendering.

    Returns a dict with:
    - symbol
    - active_timeframe
    - timeframes: {D1/H4/H1/M15: {candles, indicators, smc_zones}}
    - trade_plan: entry_zone, stop_loss, take_profit, side
    - levels: SL/TP price lines
    - zones: entry zone rectangles
    - smc_overlay: the canonical SMC layer (task 123), read through the shared
      boundary so a stored payload that is not certified current is never drawn

    ``smc_source`` is the row/document the SMC layer must be read from when the
    caller has one (task 128 P0): a stored analysis document carries its
    persistence verdict at the document level, while ``result`` alone would be
    indistinguishable from a live in-memory evaluation.  It defaults to
    ``result``.
    """
    import logging
    _log = logging.getLogger(__name__)

    from core.indicators import ema

    chart_payload = result.get("chart_payload", {})
    if not isinstance(chart_payload, dict):
        chart_payload = {}

    # Build timeframe data
    timeframes_data = {}
    for tf, candles in chart_payload.items():
        if not candles:
            continue
        tf_data = {"candles": candles}
        # EMA indicators from close prices
        closes = [c["close"] for c in candles if isinstance(c, dict) and "close" in c]
        if len(closes) >= 20:
            ema20 = ema(closes, 20)
            ema50 = ema(closes, 50) if len(closes) >= 50 else None
            ema200 = ema(closes, 200) if len(closes) >= 200 else None
            indicators = []
            for i in range(len(candles)):
                point = {"time": candles[i]["time"]}
                if i < len(ema20):
                    point["ema20"] = round(ema20[i], 5)
                if ema50 and i < len(ema50):
                    point["ema50"] = round(ema50[i], 5)
                if ema200 and i < len(ema200):
                    point["ema200"] = round(ema200[i], 5)
                indicators.append(point)
            tf_data["indicators"] = indicators
        # SMC zones
        smc = result.get("smc", {})
        if isinstance(smc, dict):
            tf_smc = smc.get(tf, {})
            if isinstance(tf_smc, dict):
                zones = []
                for key in ["supply_zones", "demand_zones", "order_blocks", "fvg"]:
                    items = tf_smc.get(key, [])
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict) and "high" in item and "low" in item:
                                zones.append({
                                    "from": item["low"],
                                    "to": item["high"],
                                    "type": key,
                                    "label": item.get("type", key),
                                })
                tf_data["smc_zones"] = zones
        timeframes_data[tf] = tf_data

    # Daily is the default overview timeframe.  Older or partial snapshots may
    # not contain D1, so keep the chart usable by falling back in display order.
    if active_timeframe not in timeframes_data:
        active_timeframe = next(
            (
                timeframe
                for timeframe in ("D1", "H4", "H1", "M15")
                if timeframe in timeframes_data
            ),
            next(iter(timeframes_data), "D1"),
        )

    # Trade plan from scenarios
    trade_plan = {
        "side": "neutral",
        "entry_zone": None,
        "execution_zone": None,
        "source_zone": None,
        "structural_execution_zone": None,
        "rr_trim_diagnostics": None,
        "invalid_reason": None,
        "stop_loss": None,
        "take_profit": None,
        "entry_status": "no_setup",
    }
    scenarios = result.get("scenarios", [])
    if isinstance(scenarios, list) and scenarios:
        best_side = result.get("decision_summary", {}).get("best_side")
        primary = _find_scenario_for_side(
            scenarios,
            str(best_side or ""),
            fallback_to_first=best_side not in ("buy", "sell"),
        )
        if isinstance(primary, dict):
            # Skip fallback scenarios — no real entry/SL/TP
            if primary.get("entry_zone_source") != "fallback":
                trade_plan["side"] = primary.get("type") or primary.get("side") or "neutral"
                trade_plan["entry_zone"] = primary.get("entry_zone")
                trade_plan["execution_zone"] = primary.get("entry_zone")
                trade_plan["source_zone"] = primary.get("source_zone")
                trade_plan["structural_execution_zone"] = primary.get("structural_execution_zone")
                trade_plan["rr_trim_diagnostics"] = primary.get("rr_trim_diagnostics")
                trade_plan["invalid_reason"] = primary.get("invalid_reason")
                trade_plan["stop_loss"] = primary.get("stop_loss")
                trade_plan["take_profit"] = primary.get("take_profit")
                trade_plan["entry_status"] = primary.get("entry_status", "no_setup")

    def _to_float(value: Any) -> float | None:
        try:
            if value in (None, "", "--", "-"):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    # Build levels (horizontal price lines for SL/TP)
    levels = []
    sl = _to_float(trade_plan["stop_loss"])
    if sl is not None:
        levels.append({"price": sl, "label": "SL", "type": "stop_loss"})
    tp = trade_plan["take_profit"]
    if isinstance(tp, list):
        for idx, tp_price in enumerate(tp, 1):
            price = _to_float(tp_price)
            if price is not None:
                levels.append({"price": price, "label": f"TP{idx}", "type": "take_profit"})
    elif tp is not None:
        price = _to_float(tp)
        if price is not None:
            levels.append({"price": price, "label": "TP", "type": "take_profit"})

    # Source is reference-only; execution permission always uses entry_zone.
    zones = []
    source = trade_plan["source_zone"]
    if isinstance(source, dict):
        source_from = _to_float(source.get("original_low"))
        source_to = _to_float(source.get("original_high"))
        if source_from is not None and source_to is not None:
            zones.append({
                "from": source_from,
                "to": source_to,
                "label": "Source",
                "type": "source_zone",
                "execution_eligible": False,
            })
    entry = trade_plan["entry_zone"]
    if isinstance(entry, list) and len(entry) == 2:
        entry_from = _to_float(entry[0])
        entry_to = _to_float(entry[1])
        if entry_from is not None and entry_to is not None:
            zones.append({
                "from": entry_from,
                "to": entry_to,
                "label": "Entry",
                "type": "entry_zone",
                "execution_eligible": True,
            })

    # Current price
    technical = result.get("technical", {})
    current_price = None
    if isinstance(technical, dict):
        current_price = technical.get("price")

    # Diagnostic: warn if we have entry zone but no levels (SL/TP missing from chart)
    if zones and not levels:
        _log.warning(
            "Chart has entry zone but NO SL/TP levels — "
            "stop_loss=%s, take_profit=%s, trade_plan_side=%s, scenarios_count=%d",
            trade_plan.get("stop_loss"), trade_plan.get("take_profit"),
            trade_plan.get("side"), len(scenarios),
        )

    return {
        "symbol": symbol,
        "active_timeframe": active_timeframe,
        "current_price": current_price,
        "timeframes": timeframes_data,
        "trade_plan": trade_plan,
        "levels": levels,
        "zones": zones,
        # Task 123: the canonical SMC layer (selected/invalid bands, the M15
        # trigger, the protected swing when published).  It is built from the
        # canonical selection only; a result without one reports an absent
        # overlay instead of drawing a legacy zone as if it were current.
        "smc_overlay": build_smc_overlay(result if smc_source is None else smc_source),
    }
