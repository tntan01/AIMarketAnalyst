"""Presentation-order sort for the scanner UI table.

Pure Python — no PyQt, no canonical ranking imports.  This module produces
a display-only reorder so that SMC zones appear above Technical, which appear
above Fallback, while preserving the relative backend execution order within
each group.

**Precondition**: *execution_rows* must already be canonical-sorted by the
backend (``rank_scanner_rows`` / ``sort_scanner_rows``).  This helper only
applies the presentation priority on top; it does **not** compute or alter
execution order.
"""

from __future__ import annotations

from typing import Any

from core.scanner_zone_origin import (
    ZONE_ORIGIN_FALLBACK,
    ZONE_ORIGIN_NONE,
    ZONE_ORIGIN_SMC,
    ZONE_ORIGIN_TECHNICAL,
    zone_origin_from_row,
)

# ---------------------------------------------------------------------------
# Presentation priority (UI-only — NOT for canonical / auto-trade ordering)
# ---------------------------------------------------------------------------

PRESENTATION_ZONE_ORIGIN_PRIORITY: dict[str, int] = {
    ZONE_ORIGIN_SMC: 0,
    ZONE_ORIGIN_TECHNICAL: 1,
    ZONE_ORIGIN_FALLBACK: 2,
    ZONE_ORIGIN_NONE: 3,
}


# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------

def sort_scanner_rows_for_display(
    execution_rows: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Return a new list of display-row copies, stable-sorted by zone origin.

    * Input ``None`` or non-list → ``[]``.
    * Non-dict items are silently dropped (same spirit as the ranking engine).
    * Each row is shallow-copied via ``dict(row)`` so the original
      ``scan_result["rows"]`` is never mutated.
    * Sort is **stable** — relative execution order is preserved within each
      ``zone_origin_class`` group.
    * Does **not** call ``rank_scanner_rows``, ``sort_scanner_rows``, or read
      any private ranking internals.
    """
    if not isinstance(execution_rows, list):
        return []

    display_rows: list[dict[str, Any]] = []
    for row in execution_rows:
        if not isinstance(row, dict):
            continue
        display_rows.append(dict(row))

    display_rows.sort(
        key=lambda row: PRESENTATION_ZONE_ORIGIN_PRIORITY.get(
            zone_origin_from_row(row),
            PRESENTATION_ZONE_ORIGIN_PRIORITY[ZONE_ORIGIN_NONE],
        ),
    )
    return display_rows
