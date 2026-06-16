"""Final score engine — combine signal, evidence and execution quality scores.

Phase 13: computes a ``final_score`` (0–100) by blending three score layers:

    final_score = signal_score × 0.65
                + evidence_score × 0.20
                + execution_quality_score × 0.15

Design principles
-----------------
* **Not a decision engine.**  This module only computes a blended score.
  It does NOT decide READY_TO_TRADE, change trade gates, or alter
  existing decision logic.  That is Phase 14's job.
* **Not a gate.**  Gates run independently and can block a trade
  regardless of final_score.
* **Safe on dirty data.**  Missing or invalid inputs fall back to
  sensible defaults (signal=0, evidence=50, execution=100) so the
  score never crashes the pipeline.
* **Weights will evolve.**  The initial weights (0.65/0.20/0.15) favour
  signal_score.  As journal data accumulates the blend should shift
  toward evidence and execution quality.

Public API
----------
* ``calculate_final_score(signal_score, evidence_score, execution_quality_score)``
  — primary entry point.
* ``clamp_score(value)`` — safe numeric clamping.
* ``default_final_score_result()`` — safe fallback result.
"""

from __future__ import annotations

from math import isnan, isfinite
from typing import Any

from core.reason_codes import (
    FINAL_SCORE_OK,
    FINAL_SCORE_DATA_INCOMPLETE,
    FINAL_SCORE_SIGNAL_DOMINANT,
    FINAL_SCORE_EVIDENCE_NEUTRAL,
    FINAL_SCORE_EVIDENCE_POSITIVE,
    FINAL_SCORE_EVIDENCE_NEGATIVE,
    FINAL_SCORE_EXECUTION_STRONG,
    FINAL_SCORE_EXECUTION_WEAK,
)
from core.safe_types import clamp_score as _shared_clamp_score
from core.safe_types import safe_float as _safe_numeric_float

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SIGNAL_SCORE = 0
DEFAULT_EVIDENCE_SCORE = 50
DEFAULT_EXECUTION_QUALITY_SCORE = 100

MIN_FINAL_SCORE = 0
MAX_FINAL_SCORE = 100

DEFAULT_FINAL_SCORE_WEIGHTS: dict[str, float] = {
    "signal_score": 0.65,
    "evidence_score": 0.20,
    "execution_quality_score": 0.15,
}

# Evidence thresholds for reason-code classification
_EVIDENCE_POSITIVE = 65
_EVIDENCE_NEGATIVE = 40
_EXECUTION_STRONG = 85
_EXECUTION_WEAK = 70

_VALID_WEIGHT_KEYS = frozenset({"signal_score", "evidence_score", "execution_quality_score"})

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NumericLike = int | float | str | None


def _to_float_safe(value: object, default: float = 0.0) -> float:
    """Safely convert any value to a float, returning *default* on failure."""
    result = _safe_numeric_float(value, default=default, allow_negative=False)
    return default if result is None else result


def safe_score(value: object, default: int = 0) -> int:
    """Safely read a score value, clamping to 0–100.

    - Accepts int, float, or numeric strings.
    - ``None``, non-numeric, NaN, ±Inf → *default* (already clamped 0–100).
    - Never raises.
    """
    clamped_default = clamp_score(default, 0, 100)
    if value is None:
        return clamped_default
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return clamped_default
        try:
            value = float(stripped)
        except (ValueError, OverflowError):
            return clamped_default
    if isinstance(value, (int, float)):
        num = float(value)
        if isnan(num) or not isfinite(num):
            return clamped_default
        return clamp_score(num, 0, 100)
    return clamped_default


def normalize_weights(weights: dict[str, float] | None = None) -> dict[str, float]:
    """Normalise blending weights so they sum to 1.0.

    - *weights* is ``None`` → returns a copy of ``DEFAULT_FINAL_SCORE_WEIGHTS``.
    - Only keys ``signal_score``, ``evidence_score``, ``execution_quality_score``
      are kept; missing keys are filled from the default.
    - Invalid weight values (negative, None, NaN, non-numeric) fall back to
      the default for that key.
    - If the raw sum ≤ 0, returns the default.
    - Never mutates the input dict.
    - Never raises.
    """
    result: dict[str, float] = {}
    defaults = DEFAULT_FINAL_SCORE_WEIGHTS
    source = weights or {}

    for key in _VALID_WEIGHT_KEYS:
        raw = source.get(key)
        fallback = defaults[key]
        result[key] = _to_float_safe(raw, fallback) if raw is not None else fallback

    total = sum(result.values())
    if total <= 0.0:
        return dict(defaults)

    # Normalise
    for key in result:
        result[key] = result[key] / total

    return result


def weighted_component(score: int, weight: float) -> float:
    """Multiply a clamped score by a weight.

    - *score* is clamped 0–100.
    - *weight* is safely coerced to float (non-finite → 0.0, negative → 0.0).
    - Never raises.
    """
    safe_s = clamp_score(score, 0, 100)
    safe_w = _to_float_safe(weight, 0.0)
    return safe_s * safe_w


def build_score_inputs(
    signal_score: object = None,
    evidence_score: object = None,
    execution_quality_score: object = None,
) -> dict[str, int]:
    """Build a standardised score-inputs dict with safe defaults.

    signal_score fallback = 0.
    evidence_score fallback = 50.
    execution_quality_score fallback = 100.
    """
    return {
        "signal_score": safe_score(signal_score, DEFAULT_SIGNAL_SCORE),
        "evidence_score": safe_score(evidence_score, DEFAULT_EVIDENCE_SCORE),
        "execution_quality_score": safe_score(
            execution_quality_score, DEFAULT_EXECUTION_QUALITY_SCORE
        ),
    }


def clamp_score(value: object, minimum: int = 0, maximum: int = 100) -> int:
    """Safely clamp any numeric input into [*minimum*, *maximum*] as int.

    - Accepts int, float, or numeric strings like ``"72.5"``.
    - ``None``, ``""``, non-numeric strings, NaN, and ±Inf return *minimum*.
    - Result is rounded to the nearest integer.
    - Never raises an exception.
    """
    return _shared_clamp_score(value, minimum, maximum)


def default_final_score_result(reason: str = "final_score_not_calculated") -> dict[str, Any]:
    """Return a safe default result when final_score cannot be calculated."""
    return {
        "final_score": 0,
        "score_inputs": {
            "signal_score": DEFAULT_SIGNAL_SCORE,
            "evidence_score": DEFAULT_EVIDENCE_SCORE,
            "execution_quality_score": DEFAULT_EXECUTION_QUALITY_SCORE,
        },
        "score_weights": dict(DEFAULT_FINAL_SCORE_WEIGHTS),
        "weighted_components": {},
        "reason_codes": [],
        "penalty_codes": [],
        "warning_codes": [FINAL_SCORE_DATA_INCOMPLETE],
        "score_breakdown": {},
        "reason": reason,
    }


def _coerce_input(value: object, default: int) -> int:
    """Convert a loosely-typed score input to a clamped integer.

    Returns *default* for unparseable / missing input.
    """
    if value is None:
        return default
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            num = float(stripped)
            if isnan(num) or not isfinite(num):
                return default
            return clamp_score(num, 0, 100)
        except (ValueError, OverflowError):
            return default
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (isnan(value) or not isfinite(value)):
            return default
        return clamp_score(int(round(float(value))), 0, 100)
    return default


def _classify_reason_codes(
    signal_score: int,
    evidence_score: int,
    execution_quality_score: int,
    had_fallback: bool,
    weights: dict[str, float],
) -> tuple[list[str], list[str], list[str]]:
    """Classify reason/penalty/warning codes based on score inputs.

    Thresholds per Phase 13 spec:
    - FINAL_SCORE_OK = always when calculation succeeds.
    - Evidence ≥65 → POSITIVE; ≤40 → NEGATIVE (penalty); ==50 → NEUTRAL.
    - Execution ≥85 → STRONG; <70 → WEAK (penalty).
    - Signal weight is largest → SIGNAL_DOMINANT.
    - Any input had to fallback → DATA_INCOMPLETE (warning).
    """
    reason_codes: list[str] = []
    penalty_codes: list[str] = []
    warning_codes: list[str] = []

    reason_codes.append(FINAL_SCORE_OK)

    if had_fallback:
        warning_codes.append(FINAL_SCORE_DATA_INCOMPLETE)

    # Signal dominance — signal_score has the largest weight
    sig_weight = weights.get("signal_score", 0.0)
    ev_weight = weights.get("evidence_score", 0.0)
    eq_weight = weights.get("execution_quality_score", 0.0)
    if sig_weight > ev_weight and sig_weight > eq_weight:
        reason_codes.append(FINAL_SCORE_SIGNAL_DOMINANT)

    # Evidence classification
    if evidence_score >= _EVIDENCE_POSITIVE:
        reason_codes.append(FINAL_SCORE_EVIDENCE_POSITIVE)
    elif evidence_score <= _EVIDENCE_NEGATIVE:
        penalty_codes.append(FINAL_SCORE_EVIDENCE_NEGATIVE)
    elif evidence_score == DEFAULT_EVIDENCE_SCORE:
        warning_codes.append(FINAL_SCORE_EVIDENCE_NEUTRAL)

    # Execution classification
    if execution_quality_score >= _EXECUTION_STRONG:
        reason_codes.append(FINAL_SCORE_EXECUTION_STRONG)
    elif execution_quality_score < _EXECUTION_WEAK:
        penalty_codes.append(FINAL_SCORE_EXECUTION_WEAK)

    return reason_codes, penalty_codes, warning_codes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def calculate_final_score(
    signal_score: object = None,
    evidence_score: object = None,
    execution_quality_score: object = None,
    *,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Blend three score layers into a final_score (0–100).

    Parameters
    ----------
    signal_score : int | float | str | None
        Score from the rule-based technical/SMC/macro engine (0–100).
    evidence_score : int | float | str | None
        Score from :mod:`core.statistical_edge_engine` (0–100).
    execution_quality_score : int | float | str | None
        Score from :mod:`core.execution_quality_engine` (0–100).
    weights : dict | None
        Optional override of ``DEFAULT_FINAL_SCORE_WEIGHTS``.

    Returns
    -------
    dict
        Full result with final_score, weighted components, reason codes, etc.
        Never raises — returns ``default_final_score_result()`` on invalid input.
    """
    w = normalize_weights(weights)

    # Track whether any input needed fallback
    had_fallback = False
    if not _is_valid_score_value(signal_score):
        had_fallback = True
    if not _is_valid_score_value(evidence_score):
        had_fallback = True
    if not _is_valid_score_value(execution_quality_score):
        had_fallback = True

    sig = _coerce_input(signal_score, DEFAULT_SIGNAL_SCORE)
    ev = _coerce_input(evidence_score, DEFAULT_EVIDENCE_SCORE)
    eq = _coerce_input(execution_quality_score, DEFAULT_EXECUTION_QUALITY_SCORE)

    sig_weighted = weighted_component(sig, w["signal_score"])
    ev_weighted = weighted_component(ev, w["evidence_score"])
    eq_weighted = weighted_component(eq, w["execution_quality_score"])

    raw = sig_weighted + ev_weighted + eq_weighted
    final = clamp_score(raw, MIN_FINAL_SCORE, MAX_FINAL_SCORE)

    reason_codes, penalty_codes, warning_codes = _classify_reason_codes(
        sig, ev, eq, had_fallback, w,
    )

    return {
        "final_score": final,
        "score_inputs": {
            "signal_score": sig,
            "evidence_score": ev,
            "execution_quality_score": eq,
        },
        "score_weights": dict(w),
        "weighted_components": {
            "signal_score": round(sig_weighted, 2),
            "evidence_score": round(ev_weighted, 2),
            "execution_quality_score": round(eq_weighted, 2),
        },
        "reason_codes": reason_codes,
        "penalty_codes": penalty_codes,
        "warning_codes": warning_codes,
        "score_breakdown": {
            "raw_final_score": round(raw, 2),
            "formula": (
                "signal_score*{:.2f} + evidence_score*{:.2f} + execution_quality_score*{:.2f}"
            ).format(w["signal_score"], w["evidence_score"], w["execution_quality_score"]),
        },
        "reason": "final_score_calculated",
    }


def _is_valid_score_value(value: object) -> bool:
    """Return True if *value* is a usable score, False if it needs fallback."""
    if value is None:
        return False
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return False
        try:
            num = float(stripped)
            if isnan(num) or not isfinite(num):
                return False
            return True
        except (ValueError, OverflowError):
            return False
    if isinstance(value, (int, float)):
        num = float(value)
        if isnan(num) or not isfinite(num):
            return False
        return True
    return False


# ---------------------------------------------------------------------------
# Payload readers — extract scores from analysis_result / scanner rows
# ---------------------------------------------------------------------------


def pick_signal_score(payload: dict[str, Any] | None, side: str | None = None) -> int:
    """Extract a signal_score from a nested analysis-result payload.

    Precedence when *side* is ``"buy"`` or ``"sell"``:
    1. ``payload["scenario_scores"][side]["signal_score"]``
    2. ``payload["scenario_scores"][side]["total"]`` (backward-compat)

    When *side* is ``None``:
    1. ``payload["decision_summary"]["best_score"]``
    2. ``payload["best_score"]``
    3. ``payload["signal_score"]``
    4. Fallback: ``DEFAULT_SIGNAL_SCORE`` (0)

    Never raises.
    """
    if not isinstance(payload, dict):
        return DEFAULT_SIGNAL_SCORE

    if side in ("buy", "sell"):
        scenarios = payload.get("scenario_scores")
        if isinstance(scenarios, dict):
            side_data = scenarios.get(side)
            if isinstance(side_data, dict):
                sig = side_data.get("signal_score")
                if _is_valid_score_value(sig):
                    return clamp_score(sig, 0, 100)
                # backward-compat: total
                total = side_data.get("total")
                if _is_valid_score_value(total):
                    return clamp_score(total, 0, 100)

    # No side or side not found — use summary
    decision = payload.get("decision_summary")
    if isinstance(decision, dict):
        best = decision.get("best_score")
        if _is_valid_score_value(best):
            return clamp_score(best, 0, 100)

    best = payload.get("best_score")
    if _is_valid_score_value(best):
        return clamp_score(best, 0, 100)

    sig = payload.get("signal_score")
    if _is_valid_score_value(sig):
        return clamp_score(sig, 0, 100)

    return DEFAULT_SIGNAL_SCORE


def pick_evidence_score(payload: dict[str, Any] | None) -> int:
    """Extract an evidence_score from a nested analysis-result payload.

    Precedence:
    1. ``payload["evidence_score"]``
    2. ``payload["evidence"]["evidence_score"]``
    3. ``payload["statistical_edge"]["evidence_score"]``
    4. Fallback: ``DEFAULT_EVIDENCE_SCORE`` (50)

    Never raises.
    """
    if not isinstance(payload, dict):
        return DEFAULT_EVIDENCE_SCORE

    direct = payload.get("evidence_score")
    if _is_valid_score_value(direct):
        return clamp_score(direct, 0, 100)

    evidence_block = payload.get("evidence")
    if isinstance(evidence_block, dict):
        score = evidence_block.get("evidence_score")
        if _is_valid_score_value(score):
            return clamp_score(score, 0, 100)

    edge_block = payload.get("statistical_edge")
    if isinstance(edge_block, dict):
        score = edge_block.get("evidence_score")
        if _is_valid_score_value(score):
            return clamp_score(score, 0, 100)

    return DEFAULT_EVIDENCE_SCORE


def pick_execution_quality_score(payload: dict[str, Any] | None) -> int:
    """Extract an execution_quality_score from a nested analysis-result payload.

    Precedence:
    1. ``payload["execution_quality_score"]``
    2. ``payload["execution_quality"]["execution_quality_score"]``
    3. ``payload["execution"]["execution_quality_score"]``
    4. Fallback: ``DEFAULT_EXECUTION_QUALITY_SCORE`` (100)

    Never raises.
    """
    if not isinstance(payload, dict):
        return DEFAULT_EXECUTION_QUALITY_SCORE

    direct = payload.get("execution_quality_score")
    if _is_valid_score_value(direct):
        return clamp_score(direct, 0, 100)

    quality_block = payload.get("execution_quality")
    if isinstance(quality_block, dict):
        score = quality_block.get("execution_quality_score")
        if _is_valid_score_value(score):
            return clamp_score(score, 0, 100)

    exec_block = payload.get("execution")
    if isinstance(exec_block, dict):
        score = exec_block.get("execution_quality_score")
        if _is_valid_score_value(score):
            return clamp_score(score, 0, 100)

    return DEFAULT_EXECUTION_QUALITY_SCORE


# ---------------------------------------------------------------------------
# Payload-level entry point
# ---------------------------------------------------------------------------


def calculate_final_score_from_payload(
    payload: dict[str, Any] | None,
    *,
    side: str | None = None,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Blend a final_score from an analysis-result or scanner-row payload.

    Uses :func:`pick_signal_score`, :func:`pick_evidence_score`, and
    :func:`pick_execution_quality_score` to extract scores, then calls
    :func:`calculate_final_score` to blend them.

    Does **not** mutate *payload*.
    """
    signal = pick_signal_score(payload, side)
    evidence = pick_evidence_score(payload)
    exec_quality = pick_execution_quality_score(payload)

    result = calculate_final_score(signal, evidence, exec_quality, weights=weights)

    # Enrich breakdown with payload metadata
    breakdown = result.setdefault("score_breakdown", {})
    if isinstance(breakdown, dict):
        breakdown["source"] = "payload"
        breakdown["side"] = side

    return result


# ---------------------------------------------------------------------------
# Batch and summary
# ---------------------------------------------------------------------------


def calculate_final_score_batch(
    payloads: list[dict[str, Any] | None] | None,
    *,
    side: str | None = None,
    weights: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Compute final_score for every payload in a list.

    - Non-list input → ``[]``.
    - Non-dict items → default result with ``FINAL_SCORE_DATA_INCOMPLETE`` warning.
    - Never mutates input.
    - Never raises.
    """
    if not isinstance(payloads, list):
        return []
    results: list[dict[str, Any]] = []
    for item in payloads:
        if not isinstance(item, dict):
            results.append(default_final_score_result("batch_item_not_a_dict"))
        else:
            results.append(
                calculate_final_score_from_payload(item, side=side, weights=weights)
            )
    return results


def summarize_final_scores(
    results: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Aggregate a list of final_score results into a summary.

    Returns counts, averages, and code frequency breakdowns.  Handles dirty
    or missing data gracefully — never raises.
    """
    if not isinstance(results, list):
        return _empty_batch_summary()

    scores: list[int] = []
    warning_counts: dict[str, int] = {}
    penalty_counts: dict[str, int] = {}
    strong = 0
    weak = 0

    for item in results:
        if not isinstance(item, dict):
            continue
        score_val = item.get("final_score")
        try:
            s = int(score_val)  # type: ignore[arg-type]
            scores.append(s)
            if s >= 80:
                strong += 1
            if s < 50:
                weak += 1
        except (ValueError, TypeError):
            continue

        for code in (item.get("warning_codes") or []):
            c = str(code)
            warning_counts[c] = warning_counts.get(c, 0) + 1
        for code in (item.get("penalty_codes") or []):
            c = str(code)
            penalty_counts[c] = penalty_counts.get(c, 0) + 1

    count = len(scores)
    if count == 0:
        return _empty_batch_summary()

    return {
        "count": count,
        "average_final_score": round(sum(scores) / count, 2),
        "min_final_score": min(scores),
        "max_final_score": max(scores),
        "strong_count": strong,
        "weak_count": weak,
        "warning_code_counts": warning_counts,
        "penalty_code_counts": penalty_counts,
    }


def _empty_batch_summary() -> dict[str, Any]:
    return {
        "count": 0,
        "average_final_score": None,
        "min_final_score": None,
        "max_final_score": None,
        "strong_count": 0,
        "weak_count": 0,
        "warning_code_counts": {},
        "penalty_code_counts": {},
    }
