from __future__ import annotations

from collections.abc import Mapping


def normalize_choice(
    value: object,
    valid_values: set[str] | frozenset[str],
    *,
    aliases: Mapping[str, str] | None = None,
    default: str | None = "unknown",
    case: str = "lower",
    null_values: set[str] | frozenset[str] = frozenset(),
) -> str | None:
    """Normalize a string value against a canonical set and alias map."""
    if not isinstance(value, str):
        return default

    cleaned = value.strip()
    if not cleaned:
        return default

    alias_key = cleaned.lower()
    if alias_key in null_values:
        return default

    canonical = cleaned.upper() if case == "upper" else alias_key
    if canonical in valid_values:
        return canonical

    if aliases is None:
        return default
    return aliases.get(alias_key, default)


# Canonical entry-status sets — decision engine excludes scanner-only values
_DECISION_ENTRY_STATUS_SET: frozenset[str] = frozenset({
    "confirmed_entry", "waiting_confirmation", "watch_zone",
    "invalidated", "no_setup",
})

_SCANNER_ENTRY_STATUS_SET: frozenset[str] = frozenset({
    "confirmed_entry", "waiting_confirmation", "watch_zone",
    "invalidated", "no_setup", "data_unavailable",
})


def normalize_entry_status(value: object) -> str:
    """Normalise an entry-status string (decision-engine set, 5 values).

    ``None`` or unrecognised -> ``"unknown"``.  Never raises.
    """
    return normalize_choice(value, _DECISION_ENTRY_STATUS_SET, default="unknown") or "unknown"


def normalize_scanner_entry_status(value: object) -> str:
    """Normalise an entry-status string (scanner set, includes data_unavailable).

    ``None`` or unrecognised -> ``"unknown"``.  Never raises.
    """
    return normalize_choice(value, _SCANNER_ENTRY_STATUS_SET, default="unknown") or "unknown"
