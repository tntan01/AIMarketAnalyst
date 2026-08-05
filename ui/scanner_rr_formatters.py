"""Shared RR formatting helpers for order dialog UI (Phase 9).

Extracted from ``ui/screens/scanner_screen.py`` so both production UI and
tests can use the exact same logic.  Output format is locked — do NOT change
without updating the corresponding contract tests.
"""

from __future__ import annotations

from typing import Any


def _zone_bounds(value: object) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        low, high = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    return (low, high) if low < high else None


def _price_digits(item: dict[str, Any]) -> int:
    digits = item.get("price_digits")
    if isinstance(digits, int) and 0 <= digits <= 10:
        return digits
    symbol = "".join(c for c in str(item.get("symbol", "")).upper() if c.isalpha())
    return 3 if symbol.endswith("JPY") else 5


def _format_zone(bounds: tuple[float, float] | None, digits: int) -> str:
    if bounds is None:
        return "--"
    return f"[{bounds[0]:.{digits}f} - {bounds[1]:.{digits}f}]"


def format_execution_zone_text(item: dict[str, Any]) -> str:
    """Format the final execution zone without falling back to source bounds."""
    return _format_zone(_zone_bounds(item.get("entry_zone")), _price_digits(item))


def format_source_zone_text(item: dict[str, Any]) -> str:
    """Format original source-zone boundaries for reference-only display."""
    source = item.get("source_zone")
    if not isinstance(source, dict):
        return "--"
    return _format_zone(
        _zone_bounds([source.get("original_low"), source.get("original_high")]),
        _price_digits(item),
    )


def format_execution_zone_width(item: dict[str, Any]) -> str:
    """Format final execution-zone width in pips and ATR."""
    bounds = _zone_bounds(item.get("entry_zone"))
    if bounds is None:
        return "--"
    symbol = "".join(c for c in str(item.get("symbol", "")).upper() if c.isalpha())
    pip_factor = 100.0 if symbol.endswith("JPY") else 10000.0
    width_pips = (bounds[1] - bounds[0]) * pip_factor
    width_atr = item.get("entry_zone_width_atr")
    try:
        atr_text = f" | {float(width_atr):.3f} ATR" if width_atr is not None else ""
    except (TypeError, ValueError):
        atr_text = ""
    return f"{width_pips:.1f} pips{atr_text}"


def format_rr_trim_reason(item: dict[str, Any]) -> str:
    """Describe Phase 16E trim/reject status without changing eligibility."""
    diagnostics = item.get("rr_trim_diagnostics")
    if not isinstance(diagnostics, dict):
        return ""
    status = str(diagnostics.get("status") or "")
    if status == "trimmed":
        before = diagnostics.get("pre_trim_effective_rr_worst")
        after = diagnostics.get("post_trim_effective_rr_worst")
        floor = diagnostics.get("min_effective_rr")
        try:
            return (
                f"RR trim: worst {float(before):.2f} -> {float(after):.2f} "
                f"(floor {float(floor):.2f})"
            )
        except (TypeError, ValueError):
            return "RR trim: execution zone narrowed"
    if status == "empty":
        reason = str(item.get("invalid_reason") or "").strip()
        return reason or "RR reject: no execution price meets the configured floor"
    if status == "not_applicable_no_tp1":
        return "RR trim: not applicable (no TP1)"
    if status == "unchanged":
        return "RR trim: not needed"
    return ""


def _safe_rr_number(value: object) -> float | None:
    """Coerce an RR range value to float; None when missing/invalid."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def format_order_rr_text(order: dict[str, Any]) -> str:
    """Return the main R:R column text for an order row.

    Primary anchor is **base** (zone midpoint — the same anchor used to
    validate TP1); the worst–best range stays alongside it and best is only
    secondary.  Falls back to best when base is unavailable.
    """
    rr_range = order.get("risk_reward_range")
    if isinstance(rr_range, dict):
        base = _safe_rr_number(rr_range.get("base"))
        best = _safe_rr_number(rr_range.get("best"))
        worst = _safe_rr_number(rr_range.get("worst"))
        primary = base if base is not None else best
        if primary is not None:
            if best is not None and worst is not None and best != worst:
                return f"{primary:.1f} ({worst:.1f}–{best:.1f})"
            return f"{primary:.1f}"
    base_field = _safe_rr_number(order.get("risk_reward_base"))
    if base_field is not None:
        return f"{base_field:.1f}"
    rr = order.get("risk_reward")
    return str(rr) if rr else "--"


def format_order_rr_tooltip(order: dict[str, Any]) -> str:
    """Return the R:R column tooltip: base primary, worst–best range, current.

    Best is demoted to its own secondary line.
    """
    parts: list[str] = []
    base: float | None = None
    best: float | None = None
    worst: float | None = None
    rr_range = order.get("risk_reward_range")
    if isinstance(rr_range, dict):
        base = _safe_rr_number(rr_range.get("base"))
        best = _safe_rr_number(rr_range.get("best"))
        worst = _safe_rr_number(rr_range.get("worst"))
    has_range = worst is not None and best is not None and best != worst
    range_suffix = f" ({worst:.1f}–{best:.1f})" if has_range else ""

    if base is None:
        base = _safe_rr_number(order.get("expected_effective_rr_base"))

    if base is not None:
        parts.append(f"Base: {base:.1f}{range_suffix}")
        if best is not None:
            parts.append(f"Best: {best:.1f}")
    elif best is not None:
        # No base available — keep the legacy best-primary display.
        parts.append(f"Best: {best:.1f}{range_suffix}")
    else:
        rr = order.get("risk_reward")
        parts.append(f"Best: {rr}" if rr else "--")

    cur_rr = order.get("current_effective_rr")
    cur_px = order.get("current_entry_price")
    cur_zone = order.get("current_price_in_entry_zone")
    if cur_rr is not None and cur_px is not None:
        zone_tag = "in zone" if cur_zone is True else ("out of zone" if cur_zone is False else "")
        parts.append(f"Current @ {float(cur_px):.5f}: {cur_rr:.2f} {zone_tag}".strip())
    elif cur_rr is not None:
        parts.append(f"Current RR: {cur_rr:.2f}")

    return "\n".join(parts)


def _format_order_entry_tooltip_legacy(order: dict[str, Any]) -> str:
    """Return the Entry column tooltip showing zone range and live price."""
    cur_px = order.get("current_entry_price")
    cur_zone = order.get("current_price_in_entry_zone")
    ez = order.get("entry_zone")
    parts: list[str] = []
    if isinstance(ez, list) and len(ez) >= 2:
        parts.append(f"Zone: [{float(ez[0]):.5f} – {float(ez[1]):.5f}]")
    if cur_px is not None:
        zone_tag = "in zone" if cur_zone is True else ("out of zone" if cur_zone is False else "unknown")
        parts.append(f"Live: {float(cur_px):.5f} ({zone_tag})")
    return "\n".join(parts)


def format_order_entry_tooltip(order: dict[str, Any]) -> str:
    """Show final execution zone plus reference-only source diagnostics."""
    cur_px = order.get("current_entry_price")
    cur_zone = order.get("current_price_in_entry_zone")
    parts = [f"Execution: {format_execution_zone_text(order)}"]
    source_text = format_source_zone_text(order)
    if source_text != "--":
        parts.append(f"Source (reference): {source_text}")
    width_text = format_execution_zone_width(order)
    if width_text != "--":
        parts.append(f"Width: {width_text}")
    trim_reason = format_rr_trim_reason(order)
    if trim_reason:
        parts.append(trim_reason)
    if cur_px is not None:
        zone_tag = (
            "in zone"
            if cur_zone is True
            else ("out of zone" if cur_zone is False else "unknown")
        )
        parts.append(
            f"Live: {float(cur_px):.{_price_digits(order)}f} ({zone_tag})"
        )
    return "\n".join(parts)


def enrich_order_note_with_current_rr(order: dict[str, Any]) -> str:
    """Return the note/message enriched with current RR diagnostic.

    When current RR is available, appends e.g.
    ``"Live 1.09850 RR=1.75 [in zone]"`` to the existing note.
    When current RR is missing, returns the original note unchanged.
    """
    note = str(order.get("note", "") or order.get("message", "") or "--")
    cur_rr = order.get("current_effective_rr")
    cur_px = order.get("current_entry_price")
    cur_zone = order.get("current_price_in_entry_zone")
    if cur_rr is not None and cur_px is not None:
        zone_tag = "[in zone]" if cur_zone is True else ("[out]" if cur_zone is False else "")
        cur_tag = f"Live {float(cur_px):.5f} RR={cur_rr:.2f} {zone_tag}".strip()
        return f"{note} | {cur_tag}" if note != "--" else cur_tag
    elif cur_rr is not None:
        tag = f"Live RR={cur_rr:.2f}"
        return f"{note} | {tag}" if note != "--" else tag
    return note
