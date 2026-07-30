"""Normalize raw entry_zone_source into a stable zone_origin_class.

This module is the single source of truth for classifying raw SMC/technical/
fallback provenance strings into four canonical origin classes: smc, technical,
fallback, none.

Whitelist-based classification: new SMC sources must be added to the allowlist
before they are recognized as SMC.

.. note::

    ``smc_distant`` is still real SMC structure — it represents a real SMC zone
    that is far from price and is displayed for watch-only purposes.
    ``technical`` is a separate class: real swing zones detected by technical
    analysis (not SMC, not ATR fallback).
    ``none`` covers missing sources, unknown sources, structural rejects, and
    data-unavailable rows — any row where we cannot determine a zone origin.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ZONE_ORIGIN_SMC = "smc"
ZONE_ORIGIN_TECHNICAL = "technical"
ZONE_ORIGIN_FALLBACK = "fallback"
ZONE_ORIGIN_NONE = "none"

VALID_ZONE_ORIGIN_CLASSES = frozenset({
    ZONE_ORIGIN_SMC,
    ZONE_ORIGIN_TECHNICAL,
    ZONE_ORIGIN_FALLBACK,
    ZONE_ORIGIN_NONE,
})

SMC_ENTRY_ZONE_SOURCES = frozenset({
    "smc",
    "smc_selected",
    "smc_active_selected",
    "smc_v2_selected",
    "smc_distant",
})

TECHNICAL_ENTRY_ZONE_SOURCES = frozenset({
    "technical",
})

FALLBACK_ENTRY_ZONE_SOURCES = frozenset({
    "fallback",
})


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

def classify_entry_zone_source(source: object) -> str:
    """Map a raw ``entry_zone_source`` value to a canonical origin class.

    Returns one of ``ZONE_ORIGIN_SMC``, ``ZONE_ORIGIN_TECHNICAL``,
    ``ZONE_ORIGIN_FALLBACK``, or ``ZONE_ORIGIN_NONE``.
    """
    normalized = str(source or "").strip().lower()
    if normalized in SMC_ENTRY_ZONE_SOURCES:
        return ZONE_ORIGIN_SMC
    if normalized in TECHNICAL_ENTRY_ZONE_SOURCES:
        return ZONE_ORIGIN_TECHNICAL
    if normalized in FALLBACK_ENTRY_ZONE_SOURCES:
        return ZONE_ORIGIN_FALLBACK
    return ZONE_ORIGIN_NONE


def zone_origin_from_row(row: object) -> str:
    """Extract ``zone_origin_class`` from a scanner row dict.

    Resolution order:

    1. If *row* is not a ``dict`` → ``none``.
    2. If ``row["zone_origin_class"]`` is a valid value → return it.
    3. If ``row`` has ``entry_zone_source`` → classify it directly.
    4. Fallback: inspect ``row["analysis_result"]["scenarios"]`` for the
       selected-side or best-side scenario.
    5. Source missing, empty, or not in any allowlist → ``none``.
    """
    if not isinstance(row, dict):
        return ZONE_ORIGIN_NONE

    # Priority 1 — already-stamped normalized field
    existing = row.get("zone_origin_class")
    if isinstance(existing, str) and existing.strip().lower() in VALID_ZONE_ORIGIN_CLASSES:
        return existing.strip().lower()

    # Priority 2 — row-level raw source (key existence, not truthiness)
    if "entry_zone_source" in row:
        return classify_entry_zone_source(row["entry_zone_source"])

    # Priority 3 — dig into scenarios for backward-compat with old payloads
    analysis = row.get("analysis_result")
    if not isinstance(analysis, dict):
        return ZONE_ORIGIN_NONE

    scenarios = analysis.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        return ZONE_ORIGIN_NONE

    selected_side = row.get("selected_side")

    # --- helper: pick the best directional scenario ---
    def _directional_scenarios() -> list[dict]:
        result: list[dict] = []
        for s in scenarios:
            if not isinstance(s, dict):
                continue
            type_val = str(s.get("type") or "").strip().lower()
            side_val = str(s.get("side") or "").strip().lower()
            if type_val in ("buy", "sell") or side_val in ("buy", "sell"):
                result.append(s)
        return result

    directional = _directional_scenarios()
    if not directional:
        return ZONE_ORIGIN_NONE

    # Try selected_side first
    if isinstance(selected_side, str) and selected_side.strip().lower() in ("buy", "sell"):
        side_key = selected_side.strip().lower()
        for s in directional:
            s_type = str(s.get("type") or "").strip().lower()
            s_side = str(s.get("side") or "").strip().lower()
            if s_type == side_key or s_side == side_key:
                return classify_entry_zone_source(s.get("entry_zone_source"))

    # Try best_side
    best_side = row.get("best_side")
    if isinstance(best_side, str) and best_side.strip().lower() in ("buy", "sell"):
        side_key = best_side.strip().lower()
        for s in directional:
            s_type = str(s.get("type") or "").strip().lower()
            s_side = str(s.get("side") or "").strip().lower()
            if s_type == side_key or s_side == side_key:
                return classify_entry_zone_source(s.get("entry_zone_source"))

    # Exactly one directional scenario → use it (not the first of many)
    if len(directional) == 1:
        return classify_entry_zone_source(directional[0].get("entry_zone_source"))

    return ZONE_ORIGIN_NONE


def _is_directional_scenario(scenario: object) -> bool:
    """Check whether a scenario dict has a buy/sell direction."""
    if not isinstance(scenario, dict):
        return False
    type_val = str(scenario.get("type") or "").strip().lower()
    side_val = str(scenario.get("side") or "").strip().lower()
    return type_val in ("buy", "sell") or side_val in ("buy", "sell")
