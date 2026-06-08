"""Execution quality engine — score how well a trade was executed.

Phase 11: provides an ``execution_quality_score`` (0–100) that measures
how closely the trader followed the planned trade.  A score of 100 means
the trade was executed exactly as planned.  Penalties are applied for
deviations such as chasing price, oversizing, moving SL further, or
revenge trading.

Design principles
-----------------
* **Not a signal score.**  Execution quality is independent of the
  technical / SMC / macro analysis.  A great setup executed badly still
  gets a low score here.
* **Not a gate.**  This module does not block or permit trades.  It only
  scores execution *after* the trade is closed.
* **Not an auto-detector (Phase 12).**  Phase 11 only reads existing
  flags and tags (boolean fields, ``auto_mistake_tags``,
  ``manual_mistake_tags``).  Phase 12 will add automatic detection of
  mistakes from price / lot / time patterns.
* **Missing data is never penalised.**  When a trade lacks execution
  annotations the score stays at 100 with an
  ``EXECUTION_DATA_INCOMPLETE`` warning — silent journals are not
  punished.
* **Stable across recalculations.**  When ``use_existing_score=True``
  (default), a pre-existing numeric ``execution_quality_score`` is
  returned as-is, so historical scores don't drift when the penalty
  rules evolve.

Phase 11 does **not** affect the live entry decision — the score is only
meaningful after a trade has been closed and its execution data is
available.
"""

from __future__ import annotations

from math import isnan
from typing import Any

from core.reason_codes import (
    EXECUTION_CHASED_PRICE,
    EXECUTION_DATA_INCOMPLETE,
    EXECUTION_MANUAL_PENALTY,
    EXECUTION_MOVED_SL_FURTHER,
    EXECUTION_OVERSIZED,
    EXECUTION_QUALITY_OK,
    EXECUTION_REVENGE_CONFIRMED,
)

DEFAULT_EXECUTION_QUALITY_SCORE = 100
MIN_EXECUTION_QUALITY_SCORE = 0
MAX_EXECUTION_QUALITY_SCORE = 100


def clamp_score(value: object, minimum: int = 0, maximum: int = 100) -> int:
    """Safely clamp any numeric input into [*minimum*, *maximum*].

    Returns *minimum* for unparseable / NaN / infinite / None input.
    """
    if value is None:
        return minimum
    try:
        if isinstance(value, float) and (isnan(value) or value != value):
            return minimum
        num = float(value) if not isinstance(value, (int, float)) else float(value)
        if isnan(num) or num != num:
            return minimum
        if num > maximum:
            return maximum
        if num < minimum:
            return minimum
        return int(round(num))
    except (ValueError, TypeError, OverflowError):
        return minimum


def default_execution_quality_result(
    reason: str = "no_execution_issue_detected",
) -> dict[str, Any]:
    """Return a perfect-score result when no execution issues are detected."""
    return {
        "execution_quality_score": DEFAULT_EXECUTION_QUALITY_SCORE,
        "reason_codes": [EXECUTION_QUALITY_OK],
        "penalty_codes": [],
        "warning_codes": [],
        "score_breakdown": {},
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Data-reading helpers
# ---------------------------------------------------------------------------

_TRUTHY = frozenset({"true", "yes", "y", "1", "có", "co", "đúng", "dung"})
_FALSEY = frozenset({"false", "no", "n", "0", "không", "khong", "sai"})


def truthy(value: object) -> bool:
    """Interpret a loosely-typed value as a boolean.

    Accepts Vietnamese aliases (``có``, ``đúng``, ``không``, ``sai``)
    alongside standard English forms.  Never raises.
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
        if stripped in _FALSEY:
            return False
        try:
            return bool(int(stripped))
        except (ValueError, OverflowError):
            pass
    return False


def normalize_tags(value: object) -> list[str]:
    """Normalise a flexible tag input into a clean list of lowercase strings.

    Handles:
    - Already a list/tuple/set
    - JSON-encoded list string
    - Comma-separated string
    - None / garbage → empty list
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
        # JSON list?
        if stripped.startswith("[") and stripped.endswith("]"):
            import json
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return normalize_tags(parsed)
            except (json.JSONDecodeError, ValueError):
                pass
        # Comma-separated
        parts = [p.strip().lower() for p in stripped.split(",")]
        return [p for p in parts if p]
    return []


_TAG_FIELDS = ("auto_mistake_tags", "manual_mistake_tags", "mistake_tags", "execution_tags")


def has_tag(trade: dict[str, object], tag: str) -> bool:
    """Check whether *trade* has *tag* in any known mistake/execution tag field.

    Comparison is case-insensitive.  Returns ``False`` for non-dict input.
    """
    if not isinstance(trade, dict):
        return False
    needle = tag.strip().lower()
    if not needle:
        return False
    for field in _TAG_FIELDS:
        tags = normalize_tags(trade.get(field))
        if needle in tags:
            return True
    return False


# ---------------------------------------------------------------------------
# Penalty helpers
# ---------------------------------------------------------------------------

_UNKNOWN_PENALTY = "UNKNOWN_EXECUTION_PENALTY"


def make_penalty_item(code: str, points: int, description: str = "") -> dict[str, object]:
    """Create a standardised penalty item dict.

    *points* is always converted to a non-negative integer (absolute
    value).  Empty *code* falls back to ``UNKNOWN_EXECUTION_PENALTY``.
    """
    code_str = str(code).strip() if code else ""
    if not code_str:
        code_str = _UNKNOWN_PENALTY
    safe_points = abs(int(points)) if isinstance(points, (int, float)) else 0
    return {
        "code": code_str,
        "points": safe_points,
        "description": str(description or ""),
    }


def sum_penalty_points(items: list[dict[str, object]] | None) -> int:
    """Sum the *points* field across a list of penalty item dicts.

    Skips entries that are not dicts or have missing / unparseable points.
    Never raises.
    """
    if items is None:
        return 0
    total = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        pts = item.get("points", 0)
        try:
            total += abs(int(pts))
        except (ValueError, TypeError):
            pass
    return total


# ---------------------------------------------------------------------------
# Main execution quality calculation
# ---------------------------------------------------------------------------

# (tag, boolean_field, penalty_points, reason_code)
_PENALTY_RULES: list[tuple[str, str, int, str]] = [
    ("chased_price", "chased_price", 25, EXECUTION_CHASED_PRICE),
    ("oversized_position", "oversized_position", 30, EXECUTION_OVERSIZED),
    ("moved_sl_further", "moved_sl_further", 30, EXECUTION_MOVED_SL_FURTHER),
    ("moved_stop_loss", "moved_stop_loss", 30, EXECUTION_MOVED_SL_FURTHER),
    ("revenge_trade", "revenge_trade", 35, EXECUTION_REVENGE_CONFIRMED),
    ("revenge_trade_confirmed", "revenge_trade_confirmed", 35, EXECUTION_REVENGE_CONFIRMED),
]


def calculate_execution_quality(
    trade: dict[str, object] | None,
    *,
    use_existing_score: bool = True,
) -> dict[str, Any]:
    """Score a closed trade's execution quality from its flag/tag data.

    Accepts a trade dict from the journal, an export payload, or a
    future UI form.  Reads the following fields when present:

    * Boolean flags: ``chased_price``, ``oversized_position``,
      ``moved_sl_further``, ``revenge_trade``,
      ``revenge_trade_confirmed``.
    * Tag fields: ``auto_mistake_tags``, ``manual_mistake_tags``,
      ``mistake_tags``, ``execution_tags`` (string, JSON-list, or
      comma-separated).
    * Manual input: ``manual_penalty_points`` / ``manual_execution_penalty``
      (capped at 50).
    * Pre-existing score: ``execution_quality_score`` (honoured when
      *use_existing_score* is ``True``).

    Returns a stable dict suitable for UI display, journal storage, or
    downstream aggregation.  Never raises on malformed input.
    """
    if not isinstance(trade, dict):
        return {
            "execution_quality_score": DEFAULT_EXECUTION_QUALITY_SCORE,
            "reason_codes": [],
            "penalty_codes": [],
            "warning_codes": [EXECUTION_DATA_INCOMPLETE],
            "score_breakdown": {
                "base_score": DEFAULT_EXECUTION_QUALITY_SCORE,
                "total_penalty": 0,
                "penalties": [],
                "data_complete": False,
            },
        }

    # Honour an existing score when requested
    if use_existing_score and "execution_quality_score" in trade:
        existing = trade["execution_quality_score"]
        # Must be a genuine numeric value, not a bogus string
        if isinstance(existing, (int, float)):
            score = clamp_score(existing, MIN_EXECUTION_QUALITY_SCORE, MAX_EXECUTION_QUALITY_SCORE)
            return {
                "execution_quality_score": score,
                "reason_codes": [EXECUTION_QUALITY_OK] if score == 100 else [],
                "penalty_codes": [],
                "warning_codes": [],
                "score_breakdown": {
                    "base_score": DEFAULT_EXECUTION_QUALITY_SCORE,
                    "total_penalty": 0,
                    "penalties": [],
                    "data_complete": True,
                    "used_existing_score": True,
                },
            }
        # Non-numeric existing score → fall through to normal calculation

    penalties: list[dict[str, object]] = []
    seen_codes: set[str] = set()

    for tag, bool_field, points, code in _PENALTY_RULES:
        if code in seen_codes:
            continue
        triggered = has_tag(trade, tag) or truthy(trade.get(bool_field))
        if triggered:
            penalties.append(make_penalty_item(code, points))
            seen_codes.add(code)

    # Manual penalty points — trader / UI input, NOT auto-detected by the engine.
    # Capped to 50 to guard against accidental over-penalisation from input errors.
    _MANUAL_PENALTY_CAP = 50
    manual_pts_raw = trade.get("manual_penalty_points") or trade.get("manual_execution_penalty")
    if manual_pts_raw is not None:
        try:
            manual_pts = abs(int(float(manual_pts_raw)))  # type: ignore[arg-type]
        except (ValueError, TypeError):
            manual_pts = 0
        if manual_pts > 0:
            capped = min(manual_pts, _MANUAL_PENALTY_CAP)
            penalties.append(make_penalty_item(
                EXECUTION_MANUAL_PENALTY, capped,
                "Điểm phạt thủ công từ journal/trader.",
            ))

    total_penalty = sum_penalty_points(penalties)
    score = max(DEFAULT_EXECUTION_QUALITY_SCORE - total_penalty, MIN_EXECUTION_QUALITY_SCORE)

    penalty_codes = [str(p["code"]) for p in penalties]
    reason_codes = [EXECUTION_QUALITY_OK] if not penalties else []

    # Determine whether execution data is present
    data_complete = _has_execution_data(trade)

    warnings: list[str] = []
    if not data_complete:
        warnings.append(EXECUTION_DATA_INCOMPLETE)

    return {
        "execution_quality_score": score,
        "reason_codes": reason_codes,
        "penalty_codes": penalty_codes,
        "warning_codes": warnings,
        "score_breakdown": {
            "base_score": DEFAULT_EXECUTION_QUALITY_SCORE,
            "total_penalty": total_penalty,
            "penalties": penalties,
            "data_complete": data_complete,
        },
    }


_EXECUTION_FIELDS = frozenset({
    "chased_price", "oversized_position", "moved_sl_further",
    "revenge_trade", "revenge_trade_confirmed", "moved_stop_loss",
    "manual_penalty_points", "manual_execution_penalty",
})


def _has_execution_data(trade: dict[str, object]) -> bool:
    """Check whether *trade* contains any execution-quality data."""
    # Boolean flags
    for field in _EXECUTION_FIELDS:
        if field in trade:
            return True
    # Tag fields — present even if empty list means data exists
    for field in _TAG_FIELDS:
        val = trade.get(field)
        if val is not None and val != "":
            return True
    return False


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------


def calculate_execution_quality_batch(
    trades: list[dict[str, object]] | None,
) -> list[dict[str, Any]]:
    """Score execution quality for every trade in a list.

    Each result includes identifying fields (*symbol*, *direction*,
    *closed_at*, *result_r*) alongside the execution quality output.
    Original trades are never mutated.
    """
    if not isinstance(trades, list):
        return []
    results: list[dict[str, Any]] = []
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        quality = calculate_execution_quality(trade)
        quality["symbol"] = trade.get("symbol")
        quality["direction"] = trade.get("direction")
        quality["closed_at"] = trade.get("closed_at")
        quality["result_r"] = trade.get("result_r")
        results.append(quality)
    return results


def summarize_execution_quality(
    results: list[dict[str, object]] | None,
) -> dict[str, Any]:
    """Aggregate execution quality results into a summary.

    Returns counts, averages, and code frequency breakdowns.  Handles
    dirty / missing data gracefully.
    """
    if not isinstance(results, list):
        return _empty_summary()

    scores: list[int] = []
    penalty_counts: dict[str, int] = {}
    warning_counts: dict[str, int] = {}

    for item in results:
        if not isinstance(item, dict):
            continue
        score = item.get("execution_quality_score")
        try:
            scores.append(int(score))  # type: ignore[arg-type]
        except (ValueError, TypeError):
            continue
        for code in item.get("penalty_codes", []) or []:
            c = str(code)
            penalty_counts[c] = penalty_counts.get(c, 0) + 1
        for code in item.get("warning_codes", []) or []:
            c = str(code)
            warning_counts[c] = warning_counts.get(c, 0) + 1

    sample_size = len(scores)
    if sample_size == 0:
        return _empty_summary()

    return {
        "sample_size": sample_size,
        "average_execution_quality_score": round(sum(scores) / sample_size, 2),
        "min_execution_quality_score": min(scores),
        "max_execution_quality_score": max(scores),
        "penalty_code_counts": penalty_counts,
        "warning_code_counts": warning_counts,
    }


def _empty_summary() -> dict[str, Any]:
    return {
        "sample_size": 0,
        "average_execution_quality_score": None,
        "min_execution_quality_score": None,
        "max_execution_quality_score": None,
        "penalty_code_counts": {},
        "warning_code_counts": {},
    }


# ---------------------------------------------------------------------------
# Journal payload builder (for future migration / export)
# ---------------------------------------------------------------------------


def build_execution_quality_journal_payload(
    trade: dict[str, object] | None,
) -> dict[str, Any]:
    """Create a flat, journal-ready payload from execution quality analysis.

    Calls :func:`calculate_execution_quality` and flattens the result
    into keys suitable for storing in a journal row or exporting.
    Normalises *auto_mistake_tags* and *manual_mistake_tags* from the
    source trade when present.

    This helper does **not** touch the database or file system.
    """
    quality = calculate_execution_quality(trade)
    payload: dict[str, Any] = {
        "execution_quality_score": quality["execution_quality_score"],
        "execution_quality_penalty_codes": quality["penalty_codes"],
        "execution_quality_warning_codes": quality["warning_codes"],
        "execution_quality_breakdown": quality["score_breakdown"],
    }

    if isinstance(trade, dict):
        auto_tags = normalize_tags(trade.get("auto_mistake_tags"))
        manual_tags = normalize_tags(trade.get("manual_mistake_tags"))
        if auto_tags:
            payload["auto_mistake_tags"] = auto_tags
        if manual_tags:
            payload["manual_mistake_tags"] = manual_tags

    return payload
