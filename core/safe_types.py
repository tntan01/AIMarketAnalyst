"""Shared helpers for reading numeric values from loose input.

These utilities centralise the project's common "dirty data" handling:
numeric strings are accepted, blank/non-numeric/non-finite values fall back,
and score values are clamped into a stable integer range.
"""

from __future__ import annotations

import json
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


# ---------------------------------------------------------------------------
# truthy — boolean coercion with Vietnamese alias support
# ---------------------------------------------------------------------------

_TRUTHY = frozenset({"true", "yes", "y", "1", "có", "co", "đúng", "dung"})
_FALSY = frozenset({"false", "no", "n", "0", "không", "khong", "sai"})


def truthy(value: object) -> bool:
    """Interpret a loosely-typed value as a boolean.

    Accepts English and Vietnamese aliases (``có``, ``đúng``, ``không``, ``sai``).
    Never raises.
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        stripped = value.strip().lower()
        if stripped in _TRUTHY:
            return True
        if stripped in _FALSY:
            return False
        try:
            return bool(int(stripped))
        except (ValueError, OverflowError):
            pass
    return False


def normalize_tags(value: object) -> list[str]:
    """Normalise flexible tag input into a clean list of lowercase strings.

    Handles:
    - Already a list / tuple / set
    - JSON-encoded list string (``'["a", "b"]'``)
    - Comma-separated string (``"a, b"``)
    - None / garbage -> empty list
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            if isinstance(item, str):
                s = item.strip().lower()
                if s:
                    result.append(s)
        return result
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return normalize_tags(parsed)
            except (json.JSONDecodeError, ValueError):
                pass
        parts = [p.strip().lower() for p in stripped.split(",")]
        return [p for p in parts if p]
    return []


def parse_risk_reward(value: object) -> float:
    """Parse a risk/reward ratio string into a float.

    - ``"1:1.8"`` -> 1.8
    - ``"1:2"`` -> 2.0
    - ``"2.5"`` -> 2.5
    - ``None``, dirty input, zero risk -> 0.0
    - Never raises.
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        f = float(value)
        return max(f, 0.0) if f == f else 0.0
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return 0.0
        if ":" in s:
            parts = s.split(":", 1)
            try:
                risk = float(parts[0].strip())
                reward = float(parts[1].strip())
                if risk == 0:
                    return 0.0
                return max(reward / risk, 0.0)
            except (ValueError, OverflowError):
                pass
        try:
            f = float(s)
            return max(f, 0.0) if f == f else 0.0
        except (ValueError, OverflowError):
            pass
    return 0.0
