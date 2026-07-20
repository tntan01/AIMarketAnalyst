"""Shared calendar utilities — stateless helpers used across the economic calendar subsystem.

These helpers are provider-agnostic.  They handle formatting, validation,
and normalization of economic calendar event data regardless of source
(ForexFactory JSON, ForexFactory HTML, or future providers).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from html import unescape
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HIGH_IMPACT_VALUES: frozenset[str] = frozenset({"high", "red", "cao"})

_VALID_ECON_VALUE_RE = re.compile(r'^-?\d+(?:\.\d+)?[%KMB]?$')

_NON_NUMERIC_EVENT_PATTERNS = [
    "testifies", "speaks", "speech", "press conference", "statement",
    "minutes", "report", "hearing", "panel", "discussion",
]

# ---------------------------------------------------------------------------
# Merge confidence levels
# ---------------------------------------------------------------------------
# HIGH   — match on (currency, normalized_event, date)
#          Allowed: fill empty actual + overwrite stale/corrupted cache
# MEDIUM — match on (currency, raw_event_name)
#          Allowed: fill empty actual only (in lookup_actuals_batch)
# LOW    — match on (currency, ±30 min time proximity)
#          REMOVED — never merge (provably copies wrong data)


# ---------------------------------------------------------------------------
# Time parsing
# ---------------------------------------------------------------------------

def parse_event_time(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _event_time(event: object) -> datetime | None:
    if not isinstance(event, dict):
        return None
    return parse_event_time(str(event.get("time_utc") or ""))


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

def clean_text(value: str) -> str:
    return " ".join(unescape(value or "").split())


# ---------------------------------------------------------------------------
# Impact classification
# ---------------------------------------------------------------------------

def _is_high_impact(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in HIGH_IMPACT_VALUES or "high" in normalized or "red" in normalized


# ---------------------------------------------------------------------------
# Economic value validation
# ---------------------------------------------------------------------------

def _is_valid_actual_value(value: str) -> bool:
    """Return True if *value* looks like a real economic number.

    Placeholder / sentinel values that signal missing or unparseable
    data are rejected.  This prevents invalid actuals from entering
    the html_lookup and overwriting valid cache entries.
    """
    if not value or not value.strip():
        return False
    v = value.strip()
    return v not in ("—", "-", "N/A", "n/a", "null", "None")


def _clean_economic_value(raw: object) -> str:
    """Return *raw* if it looks like a valid economic number, else '—'.

    Filters out corrupted values like dates masquerading as data (e.g. ``"2026M"``).
    """
    v = str(raw).strip() if raw is not None else ""
    if not v:
        return ""
    if not _VALID_ECON_VALUE_RE.match(v):
        return "—"
    num_part = v.rstrip("%KMB")
    if len(num_part) >= 4 and (num_part.startswith("19") or num_part.startswith("20")):
        return "—"
    return v


# ---------------------------------------------------------------------------
# Event field sanitization (cache cleanup)
# ---------------------------------------------------------------------------

def _sanitize_event_fields(row: dict[str, object]) -> dict[str, object]:
    """Clean stale cache entries that may contain corrupted economic values."""
    evt = str(row.get("event", "")).lower()
    is_speech = any(p in evt for p in _NON_NUMERIC_EVENT_PATTERNS)
    for field in ("forecast", "previous", "actual"):
        raw = row.get(field)
        if raw is not None and raw != "":
            cleaned = _clean_economic_value(raw)
            if is_speech and field == "actual" and cleaned not in ("", "—"):
                cleaned = ""
            row[field] = cleaned
    return row
