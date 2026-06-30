"""Statistical edge engine — simple evidence score from trade history.

Phase 10: provides an ``evidence_score`` (0–100) based on historical trade
outcomes stored in the journal.  When insufficient data is available the
module returns a neutral score (50) so it **never** blocks a setup purely
for lack of history.

Design principles
-----------------
* **evidence_score = 50** means *neutral* or *not enough data*.  It does
  *not* mean "bad" — it means "no opinion yet".
* **Low sample size always caps the score at 50**, regardless of how
  good the historical expectancy looks.  This prevents over-fitting on
  noise.
* Phase 10 does **not** feed evidence_score into the final decision.
  The score is computed and returned but has zero effect on
  ``READY_TO_TRADE`` / gate / decision logic.

Future integration (Phase 13)
-----------------------------
Phase 13 will combine three scores into a single ``final_score``::

    final_score = signal_score * 0.65
                + evidence_score * 0.20
                + execution_quality_score * 0.15

The blending weights start conservative (signal dominant) and will shift
toward evidence + execution as the journal accumulates more data.

Public API
----------
* ``calculate_edge(trades)`` — raw evidence score from any trade list.
* ``calculate_evidence_score(trades, symbol, direction, regime=None)`` —
  primary entry point: selects the best group, runs stats, returns a
  full evidence result with normalised keys.
"""

from __future__ import annotations

from math import isfinite, isnan
from typing import Any

from core.reason_codes import (
    STAT_EDGE_NEGATIVE,
    STAT_EDGE_NOT_ENOUGH_DATA,
    STAT_EDGE_POSITIVE,
)
from core.safe_types import clamp_score

DEFAULT_EVIDENCE_SCORE = 50
MIN_SAMPLE_SIZE = 30
STRONG_SAMPLE_SIZE = 50

# Values that should be treated as missing / unparseable
_INVALID_STRINGS = frozenset({"", "nan", "none", "n/a", "null", "na"})


def coerce_result_r(value: object) -> float | None:
    """Safely convert a raw *result_r* value to a float.

    Returns ``None`` for anything that cannot be interpreted as a
    finite number.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (isnan(value) or not isfinite(value)):
            return None
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lower() in _INVALID_STRINGS:
            return None
        try:
            val = float(stripped)
        except (ValueError, OverflowError):
            return None
        if isnan(val) or not isfinite(val):
            return None
        return val
    return None


def extract_closed_trade_results(trades: list[dict[str, object]] | None) -> list[float]:
    """Extract valid *result_r* values from a list of closed trades.

    Skips trades that are still open, pending, missing a close timestamp,
    or have an unparseable *result_r*.  Never raises on malformed data.
    """
    if trades is None:
        return []
    results: list[float] = []
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        status = str(trade.get("status", "")).lower()
        if status in ("open", "pending"):
            continue
        # A trade is considered closed if it has a closed_at timestamp
        # or an explicit closed/win/loss status.
        has_closed_at = trade.get("closed_at") is not None
        is_explicit_closed = status in ("closed", "win", "loss")
        if not has_closed_at and not is_explicit_closed:
            continue
        rr = coerce_result_r(trade.get("result_r"))
        if rr is None:
            continue
        results.append(rr)
    return results


# ---------------------------------------------------------------------------
# Symbol / direction normalisation
# ---------------------------------------------------------------------------


def normalize_symbol(symbol: object) -> str | None:
    """Normalise a trading symbol to a consistent canonical form.

    Strips whitespace, uppercases, and removes common separators
    (``/``, ``-``, ``_``, spaces).

    Returns ``None`` for empty or non-string input.
    """
    if symbol is None:
        return None
    if not isinstance(symbol, str):
        return None
    cleaned = symbol.strip()
    if not cleaned:
        return None
    upper = cleaned.upper()
    for ch in ("/", "-", "_", " "):
        upper = upper.replace(ch, "")
    return upper if upper else None


def normalize_direction(direction: object) -> str | None:
    """Normalise a trade direction to ``"buy"`` or ``"sell"``.

    Accepts common aliases: ``long``/``buy`` → ``"buy"``,
    ``short``/``sell`` → ``"sell"``.  Unknown values return ``None``.
    """
    if direction is None:
        return None
    if not isinstance(direction, str):
        return None
    stripped = direction.strip().lower()
    if not stripped:
        return None
    if stripped in ("buy", "long"):
        return "buy"
    if stripped in ("sell", "short"):
        return "sell"
    return None


def filter_trades_by_symbol_direction(
    trades: list[dict[str, object]] | None,
    symbol: str,
    direction: str,
) -> list[dict[str, object]]:
    """Return trades matching a normalised *symbol* + *direction* pair.

    Accepts flexible input (e.g. ``"EUR/USD"``, ``"eurusd"``,
    ``"BUY"``, ``"long"``) and normalises both before comparing.
    Falls back to ``trade["pair"]`` / ``trade["side"]`` when the
    primary keys are absent.  Never mutates the original trade dicts.
    """
    if not isinstance(trades, list):
        return []

    norm_symbol = normalize_symbol(symbol)
    norm_direction = normalize_direction(direction)
    if norm_symbol is None or norm_direction is None:
        return []

    matched: list[dict[str, object]] = []
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        trade_symbol = normalize_symbol(
            trade.get("symbol") if "symbol" in trade else trade.get("pair")
        )
        trade_direction = normalize_direction(
            trade.get("direction") if "direction" in trade else trade.get("side")
        )
        if trade_symbol == norm_symbol and trade_direction == norm_direction:
            matched.append(trade)

    return matched


# ---------------------------------------------------------------------------
# Regime-aware grouping
# ---------------------------------------------------------------------------

_VALID_REGIMES: dict[str, str] = {
    "trending_up": "trending_up",
    "trending_down": "trending_down",
    "trend_up": "trending_up",
    "trend_down": "trending_down",
    "uptrend": "trending_up",
    "downtrend": "trending_down",
    "ranging": "ranging",
    "volatile": "volatile",
    "range": "ranging",
    "trend": "trending_up",  # ambiguous — conservatively map to up
}


def normalize_regime(regime: object) -> str | None:
    """Normalise a market regime label to a canonical form.

    Maps common aliases (``"range"`` → ``"ranging"``) and returns
    ``None`` for empty / unrecognised input.
    """
    if regime is None:
        return None
    if not isinstance(regime, str):
        return None
    cleaned = regime.strip().lower()
    if not cleaned:
        return None
    if cleaned in _VALID_REGIMES:
        return _VALID_REGIMES[cleaned]
    # Unknown — pass through rather than drop, but only if reasonable
    return cleaned if len(cleaned) <= 30 else None


def filter_trades_by_symbol_direction_regime(
    trades: list[dict[str, object]] | None,
    symbol: str,
    direction: str,
    regime: str,
) -> list[dict[str, object]]:
    """Narrow *trades* to a matching symbol + direction + regime group."""
    by_symbol_dir = filter_trades_by_symbol_direction(trades, symbol, direction)
    norm_regime = normalize_regime(regime)
    if norm_regime is None:
        return []

    matched: list[dict[str, object]] = []
    for trade in by_symbol_dir:
        trade_regime = normalize_regime(
            trade.get("regime") if "regime" in trade else trade.get("market_regime")
        )
        if trade_regime == norm_regime:
            matched.append(trade)
    return matched


def select_evidence_group(
    trades: list[dict[str, object]] | None,
    symbol: str,
    direction: str,
    regime: str | None = None,
    min_group_size: int = STRONG_SAMPLE_SIZE,
) -> dict[str, Any]:
    """Choose the best available trade group for evidence scoring.

    Precedence:
    1. symbol + direction + regime (if *regime* is provided and the
       group has ≥ *min_group_size* valid closed results).
    2. symbol + direction (same threshold).
    3. Best-effort fallback — ``group_used`` is ``None`` and
       *sample_size* reflects whatever is available.

    *sample_size* always counts valid (filtered, closed) *result_r*
    values, not raw trade rows.
    """
    # Tier 1: symbol + direction + regime
    if regime is not None:
        regime_trades = filter_trades_by_symbol_direction_regime(
            trades, symbol, direction, regime
        )
        regime_rr = extract_closed_trade_results(regime_trades)
        if len(regime_rr) >= min_group_size:
            return {
                "group_used": "symbol_direction_regime",
                "trades": regime_trades,
                "sample_size": len(regime_rr),
            }

    # Tier 2: symbol + direction
    sd_trades = filter_trades_by_symbol_direction(trades, symbol, direction)
    sd_rr = extract_closed_trade_results(sd_trades)
    if len(sd_rr) >= min_group_size:
        return {
            "group_used": "symbol_direction",
            "trades": sd_trades,
            "sample_size": len(sd_rr),
        }

    # Tier 3: best effort
    best_trades = filter_trades_by_symbol_direction_regime(
        trades, symbol, direction, regime
    ) if regime is not None else sd_trades
    best_rr = extract_closed_trade_results(best_trades)
    if len(best_rr) == 0 and regime is not None:
        # Fall back to symbol_direction even if below threshold
        best_trades = sd_trades
        best_rr = extract_closed_trade_results(sd_trades)

    return {
        "group_used": None,
        "trades": best_trades,
        "sample_size": len(best_rr),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def calculate_evidence_score(
    trades: list[dict[str, object]] | None,
    symbol: str,
    direction: str,
    regime: str | None = None,
) -> dict[str, Any]:
    """Compute an evidence score for a symbol + direction (+ regime) group.

    This is the primary Phase 10 entry point.  It selects the best
    available trade group, runs statistics, and returns a conservative
    evidence score that defaults to 50 (neutral) when data is
    insufficient.

    Never raises — dirty journal data is silently filtered.
    """
    norm_symbol = normalize_symbol(symbol)
    norm_direction = normalize_direction(direction)
    norm_regime = normalize_regime(regime) if regime is not None else None

    if norm_symbol is None or norm_direction is None:
        result = neutral_evidence_result("invalid_symbol_or_direction")
        result["normalized_symbol"] = norm_symbol
        result["normalized_direction"] = norm_direction
        result["normalized_regime"] = norm_regime
        return result

    group = select_evidence_group(trades, norm_symbol, norm_direction, norm_regime)

    if group["group_used"] is None:
        # Insufficient data — run stats on best group for info, but cap score at 50
        edge = calculate_edge(group["trades"], group_used=group["group_used"])
        edge["evidence_score"] = DEFAULT_EVIDENCE_SCORE
        edge["confidence"] = "low"
        if STAT_EDGE_NOT_ENOUGH_DATA not in edge["reason_codes"]:
            edge["reason_codes"] = [STAT_EDGE_NOT_ENOUGH_DATA]
        if STAT_EDGE_NOT_ENOUGH_DATA not in edge["warning_codes"]:
            edge["warning_codes"] = [STAT_EDGE_NOT_ENOUGH_DATA]
        edge["normalized_symbol"] = norm_symbol
        edge["normalized_direction"] = norm_direction
        edge["normalized_regime"] = norm_regime
        edge["group_used"] = group["group_used"]
        edge["sample_size"] = group["sample_size"]
        return edge

    edge = calculate_edge(group["trades"], group_used=group["group_used"])
    edge["normalized_symbol"] = norm_symbol
    edge["normalized_direction"] = norm_direction
    edge["normalized_regime"] = norm_regime
    return edge


def neutral_evidence_result(reason: str = "not_enough_data") -> dict[str, Any]:
    """Return a neutral evidence result when data is insufficient.

    This ensures a missing history never penalises a setup.  The score
    sits at the midpoint (50) so downstream blending treats it as
    "no opinion".
    """
    return {
        "evidence_score": DEFAULT_EVIDENCE_SCORE,
        "sample_size": 0,
        "confidence": "low",
        "reason_codes": [STAT_EDGE_NOT_ENOUGH_DATA],
        "warning_codes": [STAT_EDGE_NOT_ENOUGH_DATA],
        "stats": {
            "win_rate": None,
            "avg_win_r": None,
            "avg_loss_r": None,
            "expectancy_r": None,
        },
        "group_used": None,
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Trade statistics
# ---------------------------------------------------------------------------


def calculate_trade_stats(results_r: list[float]) -> dict[str, Any]:
    """Compute core trade statistics from a list of realised R-multiples.

    Breakeven trades (``result_r == 0``) are conservatively counted as
    losses to avoid overstating the edge.

    Returns
    -------
    dict
        Keys: sample_size, win_count, loss_count, win_rate,
        avg_win_r, avg_loss_r, expectancy_r.
        All float fields are raw (unrounded); rounding is a UI concern.
    """
    sample_size = len(results_r)
    if sample_size == 0:
        return {
            "sample_size": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate": None,
            "avg_win_r": 0.0,
            "avg_loss_r": 0.0,
            "expectancy_r": None,
        }

    wins = [r for r in results_r if r > 0]
    losses = [r for r in results_r if r <= 0]

    win_count = len(wins)
    loss_count = len(losses)
    win_rate = win_count / sample_size

    avg_win_r = sum(wins) / win_count if wins else 0.0
    avg_loss_r = abs(sum(losses) / loss_count) if losses else 0.0

    expectancy_r = win_rate * avg_win_r - (1.0 - win_rate) * avg_loss_r

    return {
        "sample_size": sample_size,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": win_rate,
        "avg_win_r": avg_win_r,
        "avg_loss_r": avg_loss_r,
        "expectancy_r": expectancy_r,
    }


# ---------------------------------------------------------------------------
# Expectancy → evidence score mapping
# ---------------------------------------------------------------------------


def map_expectancy_to_score(expectancy_r: float | None, sample_size: int) -> int:
    """Convert an expectancy R-multiple into a 0–100 evidence score.

    The mapping is deliberately conservative:
    - Insufficient samples always return the neutral midpoint (50).
    - Very negative expectancy is capped at a low floor.
    - Zero-ish expectancy stays near 50 (±15).
    - Strong positive expectancy is rewarded but not excessively.
    """
    if expectancy_r is None or sample_size < MIN_SAMPLE_SIZE:
        return DEFAULT_EVIDENCE_SCORE

    if expectancy_r < 0.00:
        return 35

    if expectancy_r >= 0.75:
        return 95

    anchors = [
        (0.00, 50),
        (0.15, 65),
        (0.30, 75),
        (0.50, 85),
        (0.75, 95),
    ]
    for i in range(len(anchors) - 1):
        exp_low, score_low = anchors[i]
        exp_high, score_high = anchors[i + 1]
        if exp_low <= expectancy_r < exp_high:
            score = score_low + (score_high - score_low) * (expectancy_r - exp_low) / (exp_high - exp_low)
            return clamp_score(int(round(score)), minimum=20, maximum=95)

    return DEFAULT_EVIDENCE_SCORE


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def calculate_edge(
    trades: list[dict[str, object]] | None,
    *,
    group_used: str | None = None,
) -> dict[str, Any]:
    """Compute an evidence score from a list of historical trades.

    Parameters
    ----------
    trades : list[dict] | None
        Raw trade journal entries.  Dirty / open / invalid entries are
        safely filtered via :func:`extract_closed_trade_results`.
    group_used : str | None
        Optional label describing the grouping key (e.g.
        ``"EUR/USD:buy"``).  Passed through to the output for
        downstream reporting.

    Returns
    -------
    dict
        Full evidence result including score, confidence, stats, and
        reason/warning codes.  When sample size is too low the score
        defaults to 50 (neutral).
    """
    if not isinstance(trades, list) or len(trades) == 0:
        return neutral_evidence_result()

    results_r = extract_closed_trade_results(trades)
    sample_size = len(results_r)

    if sample_size < MIN_SAMPLE_SIZE:
        stats = calculate_trade_stats(results_r)
        return {
            "evidence_score": DEFAULT_EVIDENCE_SCORE,
            "sample_size": sample_size,
            "confidence": "low",
            "reason_codes": [STAT_EDGE_NOT_ENOUGH_DATA],
            "warning_codes": [STAT_EDGE_NOT_ENOUGH_DATA],
            "stats": stats,
            "group_used": group_used,
        }

    stats = calculate_trade_stats(results_r)
    expectancy_r = stats["expectancy_r"]
    evidence_score = map_expectancy_to_score(expectancy_r, sample_size)

    # Confidence tier
    if sample_size >= STRONG_SAMPLE_SIZE * 2:  # 100
        confidence = "high"
    elif sample_size >= STRONG_SAMPLE_SIZE:     # 50
        confidence = "medium"
    else:
        confidence = "low"

    # Reason code based on expectancy sign
    if expectancy_r is not None and expectancy_r > 0:
        reason_codes = [STAT_EDGE_POSITIVE]
    elif expectancy_r is not None and expectancy_r < 0:
        reason_codes = [STAT_EDGE_NEGATIVE]
    else:
        reason_codes = [STAT_EDGE_NOT_ENOUGH_DATA]

    return {
        "evidence_score": evidence_score,
        "sample_size": sample_size,
        "confidence": confidence,
        "reason_codes": reason_codes,
        "warning_codes": [],
        "stats": stats,
        "group_used": group_used,
    }
