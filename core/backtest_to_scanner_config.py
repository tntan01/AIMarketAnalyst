"""Analyze backtest results to generate per-symbol scanner configuration.

Reads a backtest snapshot and finds the best (regime, side, min_score,
min_rr) combination for each symbol based on actual trade performance.
"""

from __future__ import annotations

from typing import Any


# ---- Thresholds ----

MIN_TRADES_FOR_RECOMMENDATION = 10    # symbol phai co it nhat X lenh
MIN_TRADES_AFTER_FILTER = 8           # sau khi loc phai con it nhat X lenh
MIN_EXPECTANCY = 0.10                 # expectancy toi thieu (R/lenh)
MIN_PROFIT_FACTOR = 1.2               # profit factor toi thieu

SCORE_THRESHOLDS = [50, 55, 60, 65, 70, 75, 80]
RR_THRESHOLDS = [1.0, 1.3, 1.5, 2.0]


# ---- Public API ----

def recommend_scanner_configs(result: dict[str, Any]) -> dict[str, dict[str, Any] | None]:
    """Analyze a backtest result and return per-symbol recommendations.

    Args:
        result: A backtest result dict containing ``trades`` and ``summary``.

    Returns:
        Dict mapping symbol → config dict or None.
        Config dict keys: regime, side, min_score, min_rr, _evidence.
        None means not enough data to recommend anything for that symbol.
    """
    trades = _normalize_trades(result.get("trades", []))
    if not trades:
        return {}

    # Group trades by symbol
    by_symbol: dict[str, list[dict]] = {}
    for t in trades:
        by_symbol.setdefault(t["symbol"], []).append(t)

    recommendations: dict[str, dict[str, Any] | None] = {}
    for symbol, symbol_trades in sorted(by_symbol.items()):
        cfg = _recommend_for_symbol(symbol, symbol_trades)
        recommendations[symbol] = cfg

    return recommendations


def summarize_recommendations(
    recommendations: dict[str, dict[str, Any] | None],
) -> str:
    """Return a human-readable summary of recommendations in Vietnamese."""
    lines: list[str] = []
    for symbol, cfg in sorted(recommendations.items()):
        if cfg is None:
            lines.append(f"{symbol}: không đủ dữ liệu để đề xuất.")
        else:
            evidence = cfg.get("_evidence", "")
            lines.append(
                f"{symbol}: regime={cfg['regime']}, side={cfg['side']}, "
                f"min_score={cfg['min_score']}, min_rr={cfg['min_rr']}"
            )
            if evidence:
                lines.append(f"  → {evidence}")
    return "\n".join(lines) if lines else "Không có đề xuất nào."


# ---- Internal helpers ----

def _normalize_trades(raw: list[Any]) -> list[dict[str, Any]]:
    """Convert raw trade dicts to a uniform format."""
    trades: list[dict[str, Any]] = []
    for t in raw:
        if not isinstance(t, dict):
            continue
        trades.append({
            "symbol": str(t.get("symbol", "")),
            "side": str(t.get("side", "")).lower(),
            "market_regime": str(t.get("market_regime", "")).lower(),
            "signal_score": int(t.get("signal_score", 0) or 0),
            "final_score": int(t.get("final_score", 0) or 0),
            "expected_effective_rr": _safe_float(t.get("expected_effective_rr")),
            "result": str(t.get("result", "")).lower(),
            "result_r": float(t.get("result_r", 0) or 0),
        })
    return trades


def _recommend_for_symbol(symbol: str, trades: list[dict]) -> dict[str, Any] | None:
    """Find the best config for one symbol."""
    if len(trades) < MIN_TRADES_FOR_RECOMMENDATION:
        return None

    # Find all (regime, side) combinations with enough trades
    combos = _find_regime_side_combos(trades)
    if not combos:
        return None

    # Score each combination and pick the best one
    best_combo = None
    best_score = -999.0

    for regime, side in combos:
        filtered = [t for t in trades if t["market_regime"] == regime and t["side"] == side]
        if len(filtered) < MIN_TRADES_FOR_RECOMMENDATION:
            continue

        # Find optimal min_score for this combination
        min_score, score_evidence = _find_optimal_min_score(filtered)
        if min_score is None:
            continue

        # Apply min_score filter
        score_filtered = [t for t in filtered if t["final_score"] >= min_score]
        if len(score_filtered) < MIN_TRADES_AFTER_FILTER:
            continue

        # Find optimal min_rr
        min_rr, rr_evidence = _find_optimal_min_rr(score_filtered)
        if min_rr is None:
            min_rr = 1.0
            rr_evidence = ""

        # Apply min_rr filter
        final_trades = [t for t in score_filtered
                        if t["expected_effective_rr"] is None
                        or t["expected_effective_rr"] >= min_rr]
        if len(final_trades) < MIN_TRADES_AFTER_FILTER:
            continue

        summary = _summarize(final_trades)
        exp_r = summary["expectancy_r"]
        pf = summary["profit_factor"]

        if exp_r < MIN_EXPECTANCY or pf < MIN_PROFIT_FACTOR:
            continue

        # Composite score: reward higher expectancy + more trades
        composite = exp_r * 10 + pf + len(final_trades) * 0.01
        if composite > best_score:
            best_score = composite
            best_combo = {
                "regime": regime,
                "side": side,
                "min_score": min_score,
                "min_rr": min_rr,
                "_evidence": (
                    f"{len(final_trades)} lệnh, kỳ vọng {exp_r:+.2f}R, "
                    f"PF {pf:.2f}, win rate {summary['win_rate']:.1f}%"
                ),
            }

    return best_combo


def _find_regime_side_combos(trades: list[dict]) -> list[tuple[str, str]]:
    """Find all (regime, side) pairs that appear in the trades."""
    combos: set[tuple[str, str]] = set()
    for t in trades:
        regime = t["market_regime"] or "unknown"
        side = t["side"]
        if side in ("buy", "sell"):
            combos.add((regime, side))
    return sorted(combos)


def _find_optimal_min_score(trades: list[dict]) -> tuple[int | None, str]:
    """Try each score threshold, pick the one with best expectancy.

    Returns (min_score, evidence_string) or (None, "") if none works.
    """
    best_threshold = None
    best_exp = -999.0
    best_evidence = ""

    for threshold in SCORE_THRESHOLDS:
        filtered = [t for t in trades if t["final_score"] >= threshold]
        if len(filtered) < MIN_TRADES_AFTER_FILTER:
            continue
        s = _summarize(filtered)
        if s["expectancy_r"] < MIN_EXPECTANCY:
            continue
        if s["profit_factor"] < MIN_PROFIT_FACTOR:
            continue

        composite = s["expectancy_r"] * 10 + s["profit_factor"]
        if composite > best_exp:
            best_exp = composite
            best_threshold = threshold
            best_evidence = (
                f"score≥{threshold}: {len(filtered)} lệnh, "
                f"kỳ vọng {s['expectancy_r']:+.2f}R, PF {s['profit_factor']:.2f}"
            )

    return best_threshold, best_evidence


def _find_optimal_min_rr(trades: list[dict]) -> tuple[float | None, str]:
    """Try each RR threshold, pick the one with best expectancy."""
    best_threshold = None
    best_exp = -999.0
    best_evidence = ""

    for threshold in RR_THRESHOLDS:
        filtered = [
            t for t in trades
            if t["expected_effective_rr"] is None
            or t["expected_effective_rr"] >= threshold
        ]
        if len(filtered) < MIN_TRADES_AFTER_FILTER:
            continue
        s = _summarize(filtered)
        if s["expectancy_r"] < MIN_EXPECTANCY:
            continue

        composite = s["expectancy_r"] * 10 + s["profit_factor"]
        if composite > best_exp:
            best_exp = composite
            best_threshold = threshold
            best_evidence = (
                f"RR≥{threshold}: {len(filtered)} lệnh, "
                f"kỳ vọng {s['expectancy_r']:+.2f}R, PF {s['profit_factor']:.2f}"
            )

    return best_threshold, best_evidence


def _summarize(trades: list[dict]) -> dict[str, Any]:
    """Compute summary stats for a list of trades."""
    n = len(trades)
    if n == 0:
        return {"total_trades": 0, "win_rate": 0.0, "expectancy_r": 0.0,
                "profit_factor": 0.0, "total_r": 0.0}

    wins = [t for t in trades if t["result"] == "win"]
    losses = [t for t in trades if t["result"] == "loss"]
    results = [t["result_r"] for t in trades]

    total_r = sum(results)
    gross_profit = sum(t["result_r"] for t in wins)
    gross_loss = abs(sum(t["result_r"] for t in losses))

    return {
        "total_trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / n * 100, 1) if n else 0.0,
        "total_r": round(total_r, 2),
        "expectancy_r": round(total_r / n, 4) if n else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0
        else (round(gross_profit, 2) if gross_profit > 0 else 0.0),
    }


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
