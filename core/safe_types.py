"""Shared helpers for reading numeric values from loose input.

These utilities centralise the project's common "dirty data" handling:
numeric strings are accepted, blank/non-numeric/non-finite values fall back,
and score values are clamped into a stable integer range.
"""

from __future__ import annotations

from math import isfinite


def _parse_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except (ValueError, OverflowError):
            return None
    return None


def finite_float(value: object) -> float | None:
    """Return a finite float for numeric-like input, otherwise ``None``."""
    num = _parse_float(value)
    return num if num is not None and isfinite(num) else None


def safe_float(
    value: object,
    default: float | None = 0.0,
    *,
    allow_negative: bool = True,
) -> float | None:
    """Safely convert *value* to float, returning *default* on failure."""
    num = finite_float(value)
    if num is None:
        return default
    if not allow_negative and num < 0:
        return default
    return num


def safe_optional_float(value: object, *, allow_negative: bool = True) -> float | None:
    """Safely convert *value* to float, returning ``None`` on failure."""
    return safe_float(value, default=None, allow_negative=allow_negative)


def optional_float(value: object) -> float | None:
    """Convert *value* to float or ``None``, preserving NaN/Inf values."""
    return _parse_float(value)


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(min(value, maximum), minimum)


def clamp_score(
    value: object,
    minimum: int = 0,
    maximum: int = 100,
    *,
    default: object | None = None,
) -> int:
    """Read a numeric score and clamp it into [*minimum*, *maximum*].

    Invalid input returns *default* when provided, otherwise *minimum*.
    The score itself is rounded before clamping; fallback defaults are cast
    with ``int()`` to match the older per-module helper behavior.
    """
    fallback_source = minimum if default is None else default
    fallback_num = finite_float(fallback_source)
    fallback = (
        minimum
        if fallback_num is None
        else _clamp_int(int(fallback_num), minimum, maximum)
    )

    num = finite_float(value)
    if num is None:
        return fallback
    return _clamp_int(int(round(num)), minimum, maximum)
