"""Shared RR formatting helpers for order dialog UI (Phase 9).

Extracted from ``ui/screens/scanner_screen.py`` so both production UI and
tests can use the exact same logic.  Output format is locked — do NOT change
without updating the corresponding contract tests.
"""

from __future__ import annotations

from typing import Any


def format_order_rr_text(order: dict[str, Any]) -> str:
    """Return the main R:R column text for an order row.

    Uses best-case anchor (``risk_reward_range`` or ``risk_reward`` string).
    Never uses base or current RR as the primary display.
    """
    rr = order.get("risk_reward")
    rr_range = order.get("risk_reward_range")
    if rr_range and isinstance(rr_range, dict):
        best = rr_range.get("best")
        worst = rr_range.get("worst")
        if best is not None and worst is not None and best != worst:
            return f"{best:.1f} ({worst:.1f}–{best:.1f})"
        elif best is not None:
            return f"{best:.1f}"
    return str(rr) if rr else "--"


def format_order_rr_tooltip(order: dict[str, Any]) -> str:
    """Return the R:R column tooltip with best/base/current breakdown."""
    rr_text = format_order_rr_text(order)
    parts = [f"Best: {rr_text}"]

    base_rr = order.get("expected_effective_rr_base")
    if base_rr is None:
        rr_range = order.get("risk_reward_range")
        if isinstance(rr_range, dict):
            base_rr = rr_range.get("base")
    if base_rr is not None:
        parts.append(f"Base: {base_rr:.1f}")

    cur_rr = order.get("current_effective_rr")
    cur_px = order.get("current_entry_price")
    cur_zone = order.get("current_price_in_entry_zone")
    if cur_rr is not None and cur_px is not None:
        zone_tag = "in zone" if cur_zone is True else ("out of zone" if cur_zone is False else "")
        parts.append(f"Current @ {float(cur_px):.5f}: {cur_rr:.2f} {zone_tag}".strip())
    elif cur_rr is not None:
        parts.append(f"Current RR: {cur_rr:.2f}")

    return "\n".join(parts)


def format_order_entry_tooltip(order: dict[str, Any]) -> str:
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
