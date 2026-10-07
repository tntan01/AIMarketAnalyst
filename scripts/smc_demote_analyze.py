"""Statistical analysis of the SD-C2 replay corpus (task SD-C3).

Run:
    python -X utf8 scripts/smc_demote_analyze.py check-scorer
    python -X utf8 scripts/smc_demote_analyze.py analyze

This is a *numbers only* tool: it reads the stored replay rows, recomputes the two
TechnicalScore variants from the stored raws, and measures discrimination / side
selection / SMC TP-SL separation.  It writes no conclusion (that is SD-C4) and
never calls MT5.  Everything is deterministic: the same inputs produce a
byte-identical ``analysis.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from collections import defaultdict
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from statistics import median
from typing import Any, Callable

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
_SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from smc_demote_replay import (  # noqa: E402
    ERRORS_PATH,
    MANIFEST_PATH,
    ROWS_PATH,
    SUMMARY_PATH,
    live_analysis_at,
    read_jsonl,
)
from smc_demote_corpus import DATA_DIR, load_symbol_data  # noqa: E402
from core.technical_signal_scorer import (  # noqa: E402
    TECHNICAL_COMPONENT_RAW_MAX,
    TECHNICAL_REGIME_WEIGHTS,
    score_technical_signal,
)

OUTPUT_DIR = PROJECT_ROOT / "reports" / "scanner" / "smc_demote"
ANALYSIS_JSON = OUTPUT_DIR / "analysis.json"          # commit
ANALYSIS_MD = OUTPUT_DIR / "analysis.md"              # commit
SCORER_CHECK_JSON = OUTPUT_DIR / "scorer_check.json"  # commit
SEED = 20261007
BOOTSTRAP_N = 2000
MIN_SCORE_GAP = 5          # config/scanner_order_policy.json threshold.min_score_gap
Q4_DIFF_FLOOR = -0.05      # Q4 điều kiện (1)
Q4_AUC_FLOOR = 0.55        # Q4 điều kiện (2)
Q4_MIN_RESOLVED = 200
NO_SMC_WEIGHTS = {         # Q5 — Trend/Momentum/Location, tổng 100
    "trending_up":   {"trend": 50, "momentum": 25, "location": 25},
    "trending_down": {"trend": 50, "momentum": 25, "location": 25},
    "ranging":       {"trend": 17, "momentum": 17, "location": 66},
    "volatile":      {"trend": 29, "momentum": 14, "location": 57},
    "unknown":       {"trend": 34, "momentum": 33, "location": 33},
}
REGIMES = ("trending_up", "trending_down", "ranging", "volatile", "unknown")
RAW_COMPONENTS = ("trend", "momentum", "location", "smc_raw")
SIDES = ("buy", "sell")
BUCKETS = {
    "trend": ((0, 8), (9, 16), (17, 25)),
    "momentum": ((0, 6), (7, 13), (14, 20)),
    "location": ((0, 0), (1, 8), (9, 16), (17, 25)),
    "smc_raw": ((0, 0), (1, 5), (6, 7), (8, 8), (9, 15)),
}


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Deterministic statistics (no scipy)
# ---------------------------------------------------------------------------

def rankdata_average(values: list[float]) -> list[float]:
    """Average ranks, ties sharing the mean of their rank span."""

    count = len(values)
    order = sorted(range(count), key=lambda index: values[index])
    ranks = [0.0] * count
    position = 0
    while position < count:
        end = position
        while end + 1 < count and values[order[end + 1]] == values[order[position]]:
            end += 1
        average = (position + end) / 2.0 + 1.0
        for index in range(position, end + 1):
            ranks[order[index]] = average
        position = end + 1
    return ranks


def auc(scores: list[float], labels: list[int]) -> float | None:
    """Mann-Whitney AUC with average ranks; ``None`` when a class is missing."""

    n_pos = sum(1 for label in labels if label == 1)
    n_neg = sum(1 for label in labels if label == 0)
    if n_pos == 0 or n_neg == 0:
        return None
    ranks = rankdata_average(list(scores))
    sum_rank_pos = sum(rank for rank, label in zip(ranks, labels) if label == 1)
    return (sum_rank_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    count = len(xs)
    if count == 0:
        return None
    mean_x = sum(xs) / count
    mean_y = sum(ys) / count
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x <= 0 or var_y <= 0:
        return None
    return covariance / math.sqrt(var_x * var_y)


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation of average ranks; ``None`` below 3 points or no variance."""

    if len(xs) != len(ys) or len(xs) < 3:
        return None
    return _pearson(rankdata_average(xs), rankdata_average(ys))


def bootstrap_clusters(
    day_items: dict[str, list[Any]],
    stat_fn: Callable[[list[Any]], float | None],
    seed: int = SEED,
    n: int = BOOTSTRAP_N,
) -> tuple[float | None, float | None, int]:
    """Cluster bootstrap over UTC days; returns ``(lo, hi, valid_rounds)``."""

    days = sorted(day_items)
    if not days:
        return None, None, 0
    rng = np.random.default_rng(seed)
    indices = np.arange(len(days))
    values: list[float] = []
    for _ in range(n):
        picked = rng.choice(indices, size=len(indices), replace=True)
        sample: list[Any] = []
        for index in picked:
            sample.extend(day_items[days[int(index)]])
        result = stat_fn(sample)
        if result is not None:
            values.append(float(result))
    if not values:
        return None, None, 0
    low, high = np.percentile(values, [2.5, 97.5])
    return float(low), float(high), len(values)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


# ---------------------------------------------------------------------------
# TechnicalScore variants
# ---------------------------------------------------------------------------

def round_half_up_once(value: Fraction) -> int:
    quotient, remainder = divmod(value.numerator, value.denominator)
    return quotient + int(remainder * 2 >= value.denominator)


def _exact_total(regime: str, weights: dict[str, dict[str, int]], raws: dict[str, int]) -> Fraction:
    total = Fraction(0, 1)
    for component, raw in raws.items():
        maximum = TECHNICAL_COMPONENT_RAW_MAX[component]
        clamped = max(0, min(maximum, int(raw)))
        total += Fraction(clamped * weights[regime][component], maximum)
    return max(Fraction(0, 1), min(Fraction(100, 1), total))


def current_score(
    regime: str,
    trend: int | None,
    momentum: int | None,
    location: int | None,
    smc_raw: int | None,
) -> int | None:
    """Variant (a): the real four-component scorer formula (fail-closed on SMC)."""

    if smc_raw is None:
        return None
    raws = {"trend": trend, "momentum": momentum, "location": location, "smc": smc_raw}
    return round_half_up_once(_exact_total(regime, TECHNICAL_REGIME_WEIGHTS, raws))


def no_smc_score(
    regime: str,
    trend: int | None,
    momentum: int | None,
    location: int | None,
) -> int | None:
    """Variant (b): Trend/Momentum/Location only, Q5 weights."""

    raws = {"trend": trend, "momentum": momentum, "location": location}
    return round_half_up_once(_exact_total(regime, NO_SMC_WEIGHTS, raws))


def select_side(
    buy_score: int | None,
    sell_score: int | None,
) -> tuple[str | None, int | None, bool]:
    """Pick a side (ties → BUY) and report the gap and whether it clears the floor."""

    if buy_score is None or sell_score is None:
        return None, None, False
    side = "buy" if buy_score >= sell_score else "sell"
    gap = abs(buy_score - sell_score)
    return side, gap, gap >= MIN_SCORE_GAP


def _round_half_up_number(value: float) -> int:
    return round_half_up_once(Fraction(str(value)))


def _variant_scores(row: dict[str, Any]) -> dict[str, Any]:
    regime = row["regime"]
    scores: dict[str, Any] = {}
    for variant, fn in (
        ("current", lambda side: current_score(regime, side["trend"], side["momentum"], side["location"], side["smc_raw"])),
        ("no_smc", lambda side: no_smc_score(regime, side["trend"], side["momentum"], side["location"])),
    ):
        buy_score = fn(row["sides"]["buy"])
        sell_score = fn(row["sides"]["sell"])
        side, gap, gap_ok = select_side(buy_score, sell_score)
        scores[variant] = {
            "buy": buy_score,
            "sell": sell_score,
            "side": side,
            "gap": gap,
            "gap_ok": gap_ok,
        }
    return scores


# ---------------------------------------------------------------------------
# check-scorer
# ---------------------------------------------------------------------------

def _run_check_scorer(_args) -> int:
    rows, _ = read_jsonl(ROWS_PATH)
    if not rows:
        print(f"BLOCKED: no replay rows at {ROWS_PATH}")
        return 2
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    min_rr = manifest.get("min_rr")

    pool = [
        row
        for row in rows
        if all(row["sides"][side]["smc_raw"] is not None for side in SIDES)
    ]
    sample_size = min(50, len(pool))
    sample = random.Random(SEED).sample(pool, sample_size)

    mismatches: list[dict[str, Any]] = []
    checked = 0
    for row in sample:
        cutoff = datetime.fromisoformat(row["cutoff"])
        symbol = row["symbol"]
        data = load_symbol_data(DATA_DIR / f"{symbol.replace('/', '')}.json.gz")
        analysis, _, _ = live_analysis_at(data, cutoff, min_rr)
        for side_name in SIDES:
            raws = analysis["raws"].per_side[side_name]
            scorer = score_technical_signal(
                side_name,
                trend_raw=raws.trend,
                momentum_raw=raws.momentum,
                location_raw=raws.location,
                canonical_smc=analysis["canonical_smc"],
                regime=analysis["regime"],
            ).technical_signal_score
            side_row = row["sides"][side_name]
            from_row = current_score(
                row["regime"],
                side_row["trend"],
                side_row["momentum"],
                side_row["location"],
                side_row["smc_raw"],
            )
            checked += 1
            if scorer != from_row:
                mismatches.append(
                    {
                        "symbol": symbol,
                        "cutoff": row["cutoff"],
                        "side": side_name,
                        "scorer": scorer,
                        "from_row": from_row,
                    }
                )

    payload = {"checked": checked, "mismatches": mismatches}
    _atomic_write_text(
        SCORER_CHECK_JSON,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    print(f"check-scorer: {sample_size} rows, {len(mismatches)} mismatches")
    print(f"report -> {SCORER_CHECK_JSON}")
    return 0 if not mismatches else 1


# ---------------------------------------------------------------------------
# analyze blocks
# ---------------------------------------------------------------------------

def _inputs(rows: list[dict[str, Any]], errors: list[dict[str, Any]], rows_hash: str) -> dict[str, Any]:
    days = {row["cutoff"][:10] for row in rows}
    error_types: dict[str, int] = {}
    for error in errors:
        key = str(error.get("error_type") or "unknown")
        error_types[key] = error_types.get(key, 0) + 1
    return {
        "rows": len(rows),
        "errors": len(errors),
        "error_types": dict(sorted(error_types.items())),
        "day_clusters": len(days),
        "rows_sha256": rows_hash,
        "seed": SEED,
        "bootstrap_n": BOOTSTRAP_N,
    }


def _regime_distribution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {regime: 0 for regime in REGIMES}
    by_symbol: dict[str, dict[str, int]] = {}
    by_month: dict[str, dict[str, int]] = {}
    for row in rows:
        regime = row["regime"] if row["regime"] in counts else "unknown"
        counts[regime] += 1
        symbol = row["symbol"]
        by_symbol.setdefault(symbol, {name: 0 for name in REGIMES})[regime] += 1
        month = row["cutoff"][:7]
        by_month.setdefault(month, {name: 0 for name in REGIMES})[regime] += 1
    total = len(rows)
    distribution = {
        regime: {
            "count": counts[regime],
            "fraction": counts[regime] / total if total else 0.0,
        }
        for regime in REGIMES
    }
    return {
        "total": total,
        "distribution": distribution,
        "by_symbol": {symbol: dict(sorted(value.items())) for symbol, value in sorted(by_symbol.items())},
        "by_month": {month: dict(sorted(value.items())) for month, value in sorted(by_month.items())},
    }


def _numeric_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"mean": None, "median": None, "min": None, "max": None}
    return {
        "mean": float(sum(values) / len(values)),
        "median": float(median(values)),
        "min": float(min(values)),
        "max": float(max(values)),
    }


def _value_counts(values: list[int]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: int(item[0])))


def _raw_distribution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for component in RAW_COMPONENTS:
        groups = ["all", *REGIMES]
        component_result: dict[str, Any] = {}
        for group in groups:
            observations: list[Any] = []
            for row in rows:
                if group != "all" and row["regime"] != group:
                    continue
                for side in SIDES:
                    observations.append(row["sides"][side][component])
            non_null = [value for value in observations if value is not None]
            summary = _numeric_summary([float(value) for value in non_null])
            component_result[group] = {
                "n": len(observations),
                "n_null": len(observations) - len(non_null),
                **summary,
                "value_counts": _value_counts(non_null),
            }
        result[component] = component_result
    return result


def _observations(rows: list[dict[str, Any]], value_fn: Callable[[dict[str, Any]], Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for row in rows:
        day = row["cutoff"][:10]
        for side in SIDES:
            side_row = row["sides"][side]
            labels = side_row["labels"]
            observations.append(
                {
                    "day": day,
                    "regime": row["regime"],
                    "value": value_fn(side_row),
                    "fwd8": labels["fwd_8h_atr"],
                    "fwd24": labels["fwd_24h_atr"],
                }
            )
    return observations


def _bucket_label(low: int, high: int) -> str:
    return str(low) if low == high else f"{low}-{high}"


def _discrimination(observations: list[dict[str, Any]], component: str) -> dict[str, Any]:
    valid = [obs for obs in observations if obs["value"] is not None]
    result: dict[str, Any] = {"n": len(valid)}

    pairs8 = [(obs["value"], obs["fwd8"]) for obs in valid if obs["fwd8"] is not None]
    pairs24 = [(obs["value"], obs["fwd24"]) for obs in valid if obs["fwd24"] is not None]
    result["spearman_fwd_8h"] = spearman([a for a, _ in pairs8], [b for _, b in pairs8])
    result["spearman_fwd_24h"] = spearman([a for a, _ in pairs24], [b for _, b in pairs24])

    auc_pairs = [
        (obs["value"], 1 if obs["fwd24"] > 0 else 0)
        for obs in valid
        if obs["fwd24"] is not None
    ]
    result["auc_fwd_24h_pos"] = auc([a for a, _ in auc_pairs], [b for _, b in auc_pairs])

    if component in BUCKETS:
        buckets: dict[str, Any] = {}
        for low, high in BUCKETS[component]:
            items = [
                obs
                for obs in valid
                if low <= obs["value"] <= high and obs["fwd24"] is not None
            ]
            if items:
                buckets[_bucket_label(low, high)] = {
                    "n": len(items),
                    "hit_rate": sum(1 for obs in items if obs["fwd24"] > 0) / len(items),
                    "mean_fwd_24h": _mean([obs["fwd24"] for obs in items]),
                }
            else:
                buckets[_bucket_label(low, high)] = {
                    "n": 0,
                    "hit_rate": None,
                    "mean_fwd_24h": None,
                }
        result["hit_rate_by_bucket"] = buckets
    return result


def _component_discrimination(rows: list[dict[str, Any]]) -> dict[str, Any]:
    components = {
        "trend": lambda side: side["trend"],
        "momentum": lambda side: side["momentum"],
        "location": lambda side: side["location"],
        "smc_raw": lambda side: side["smc_raw"],
        "quality_score": lambda side: side["quality_score"],
    }
    result: dict[str, Any] = {"all": {}, "by_regime": {}}
    for component, value_fn in components.items():
        observations = _observations(rows, value_fn)
        result["all"][component] = _discrimination(observations, component)
        result["by_regime"][component] = {}
        for regime in REGIMES:
            regime_observations = [obs for obs in observations if obs["regime"] == regime]
            block = _discrimination(regime_observations, component)
            if len(regime_observations) < 30:
                block["few_samples"] = True
            result["by_regime"][component][regime] = block
    return result


def _row_fwd24(row: dict[str, Any], side: str | None) -> float | None:
    if side is None:
        return None
    return row["sides"][side]["labels"]["fwd_24h_atr"]


def _row_fwd8(row: dict[str, Any], side: str | None) -> float | None:
    if side is None:
        return None
    return row["sides"][side]["labels"]["fwd_8h_atr"]


def _side_selection(rows: list[dict[str, Any]]) -> dict[str, Any]:
    both_rows: list[dict[str, Any]] = []
    only_no_smc_rows: list[dict[str, Any]] = []
    neither = 0
    for row in rows:
        scores = _variant_scores(row)
        has_current = scores["current"]["side"] is not None
        has_no_smc = scores["no_smc"]["side"] is not None
        if has_current and has_no_smc:
            both_rows.append(row)
        elif has_no_smc and not has_current:
            only_no_smc_rows.append(row)
        elif not has_current and not has_no_smc:
            neither += 1

    changed_rows: list[dict[str, Any]] = []
    diff24_by_day: dict[str, list[float]] = defaultdict(list)
    diff8_by_day: dict[str, list[float]] = defaultdict(list)
    changed_details: list[dict[str, Any]] = []
    variant_stats = {
        "current": {"fwd24": [], "fwd8": [], "hits": [], "gaps": [], "gap_ok_fwd24": [], "gap_ok_hits": []},
        "no_smc": {"fwd24": [], "fwd8": [], "hits": [], "gaps": [], "gap_ok_fwd24": [], "gap_ok_hits": []},
    }
    gap_ok_keys = {"current": set(), "no_smc": set()}

    for row in both_rows:
        scores = _variant_scores(row)
        side_a = scores["current"]["side"]
        side_b = scores["no_smc"]["side"]
        fwd24_a = _row_fwd24(row, side_a)
        fwd24_b = _row_fwd24(row, side_b)
        fwd8_a = _row_fwd8(row, side_a)
        fwd8_b = _row_fwd8(row, side_b)

        for variant, side, fwd24, fwd8 in (
            ("current", side_a, fwd24_a, fwd8_a),
            ("no_smc", side_b, fwd24_b, fwd8_b),
        ):
            if fwd24 is not None:
                variant_stats[variant]["fwd24"].append(fwd24)
                variant_stats[variant]["hits"].append(1 if fwd24 > 0 else 0)
            if fwd8 is not None:
                variant_stats[variant]["fwd8"].append(fwd8)
            if scores[variant]["gap"] is not None:
                variant_stats[variant]["gaps"].append(scores[variant]["gap"])
            if scores[variant]["gap_ok"]:
                gap_ok_keys[variant].add(f"{row['symbol']}@{row['cutoff']}")
                if fwd24 is not None:
                    variant_stats[variant]["gap_ok_fwd24"].append(fwd24)
                    variant_stats[variant]["gap_ok_hits"].append(1 if fwd24 > 0 else 0)

        day = row["cutoff"][:10]
        if side_a == side_b:
            diff24_by_day[day].append(0.0)
            diff8_by_day[day].append(0.0)
        else:
            changed_rows.append(row)
            if fwd24_a is not None and fwd24_b is not None:
                diff24_by_day[day].append(fwd24_b - fwd24_a)
            if fwd8_a is not None and fwd8_b is not None:
                diff8_by_day[day].append(fwd8_b - fwd8_a)
            changed_details.append(
                {
                    "symbol": row["symbol"],
                    "cutoff": row["cutoff"],
                    "regime": row["regime"],
                    "side_current": side_a,
                    "side_no_smc": side_b,
                    "buy_current": scores["current"]["buy"],
                    "sell_current": scores["current"]["sell"],
                    "buy_no_smc": scores["no_smc"]["buy"],
                    "sell_no_smc": scores["no_smc"]["sell"],
                    "smc_raw_buy": row["sides"]["buy"]["smc_raw"],
                    "smc_raw_sell": row["sides"]["sell"]["smc_raw"],
                    "fwd_24h_current": fwd24_a,
                    "fwd_24h_no_smc": fwd24_b,
                }
            )

    def _mean_stat(items: list[Any]) -> float | None:
        values = [value for value in items if value is not None]
        return _mean(values)

    diff24 = _mean([value for values in diff24_by_day.values() for value in values])
    ci24 = bootstrap_clusters(diff24_by_day, _mean_stat)
    diff8 = _mean([value for values in diff8_by_day.values() for value in values])
    ci8 = bootstrap_clusters(diff8_by_day, _mean_stat)

    def _variant_result(variant: str) -> dict[str, Any]:
        stats = variant_stats[variant]
        return {
            "mean_fwd_24h": _mean(stats["fwd24"]),
            "mean_fwd_8h": _mean(stats["fwd8"]),
            "hit_rate": _mean([float(hit) for hit in stats["hits"]]),
            "median_gap": float(median(stats["gaps"])) if stats["gaps"] else None,
            "gap_ok_count": len(gap_ok_keys[variant]),
            "gap_ok_mean_fwd_24h": _mean(stats["gap_ok_fwd24"]),
            "gap_ok_hit_rate": _mean([float(hit) for hit in stats["gap_ok_hits"]]),
        }

    only_current_ok = gap_ok_keys["current"] - gap_ok_keys["no_smc"]
    only_no_smc_ok = gap_ok_keys["no_smc"] - gap_ok_keys["current"]

    by_regime: dict[str, Any] = {}
    for regime in REGIMES:
        regime_both = [row for row in both_rows if row["regime"] == regime]
        regime_changed = [row for row in regime_both if _variant_scores(row)["current"]["side"] != _variant_scores(row)["no_smc"]["side"]]
        regime_diffs: list[float] = []
        for row in regime_both:
            scores = _variant_scores(row)
            side_a = scores["current"]["side"]
            side_b = scores["no_smc"]["side"]
            if side_a == side_b:
                regime_diffs.append(0.0)
            else:
                fwd_a = _row_fwd24(row, side_a)
                fwd_b = _row_fwd24(row, side_b)
                if fwd_a is not None and fwd_b is not None:
                    regime_diffs.append(fwd_b - fwd_a)
        by_regime[regime] = {
            "both": len(regime_both),
            "changed": len(regime_changed),
            "mean_diff_fwd_24h": _mean(regime_diffs),
        }

    only_no_smc_fwd = [
        fwd
        for row in only_no_smc_rows
        for fwd in [_row_fwd24(row, _variant_scores(row)["no_smc"]["side"])]
        if fwd is not None
    ]

    return {
        "counts": {
            "both": len(both_rows),
            "only_no_smc": len(only_no_smc_rows),
            "neither": neither,
            "changed_side": len(changed_rows),
        },
        "current": _variant_result("current"),
        "no_smc": _variant_result("no_smc"),
        "q4_condition_1": {
            "diff": diff24,
            "ci95": [ci24[0], ci24[1]],
            "pass": ci24[0] is not None and ci24[0] >= Q4_DIFF_FLOOR,
        },
        "descriptive_fwd_8h": {
            "diff": diff8,
            "ci95": [ci8[0], ci8[1]],
        },
        "gap_ok_only_one_variant": {
            "current_not_no_smc": len(only_current_ok),
            "no_smc_not_current": len(only_no_smc_ok),
        },
        "only_no_smc_mean_fwd_24h": _mean(only_no_smc_fwd),
        "changed_rows": changed_details,
        "by_regime": by_regime,
    }


def _smc_tp_sl(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tp_sl_values = ("tp_first", "sl_first", "unresolved", "not_filled", "plan_invalid")
    counts = {side: {value: 0 for value in (*tp_sl_values, "None")} for side in SIDES}
    total_counts = {value: 0 for value in (*tp_sl_values, "None")}
    resolved: list[dict[str, Any]] = []
    for row in rows:
        for side in SIDES:
            side_row = row["sides"][side]
            value = side_row["labels"]["tp_sl"]
            key = value if value in tp_sl_values else "None"
            counts[side][key] += 1
            total_counts[key] += 1
            if value in ("tp_first", "sl_first"):
                resolved.append(
                    {
                        "day": row["cutoff"][:10],
                        "label": 1 if value == "tp_first" else 0,
                        "quality_score": side_row["quality_score"],
                        "quality_raw": side_row["quality_raw"],
                        "b": side_row["b"],
                        "q": side_row["q"],
                        "l": side_row["l"],
                        "c": side_row["c"],
                        "readiness_status": side_row["readiness_status"],
                        "mfe_r": side_row["labels"]["mfe_r"],
                        "mae_r": side_row["labels"]["mae_r"],
                    }
                )

    n_resolved = len(resolved)
    n_tp = sum(1 for item in resolved if item["label"] == 1)
    n_sl = n_resolved - n_tp

    def _auc_stat(field: str) -> Callable[[list[Any]], float | None]:
        def stat(items: list[Any]) -> float | None:
            pairs = [(item[field], item["label"]) for item in items if item[field] is not None]
            return auc([a for a, _ in pairs], [b for _, b in pairs])
        return stat

    def _auc_with_ci(field: str, seed: int) -> dict[str, Any]:
        by_day: dict[str, list[Any]] = defaultdict(list)
        for item in resolved:
            by_day[item["day"]].append(item)
        point = _auc_stat(field)(resolved)
        low, high, valid = bootstrap_clusters(by_day, _auc_stat(field), seed)
        return {"auc": point, "ci95": [low, high], "valid_rounds": valid}

    quality_auc = _auc_with_ci("quality_score", SEED)
    q4_condition_2 = {
        "n_resolved": n_resolved,
        "n_tp": n_tp,
        "n_sl": n_sl,
        "auc": quality_auc["auc"],
        "ci95": quality_auc["ci95"],
        "pass": (
            n_resolved >= Q4_MIN_RESOLVED
            and quality_auc["auc"] is not None
            and quality_auc["auc"] >= Q4_AUC_FLOOR
            and quality_auc["ci95"][0] is not None
            and quality_auc["ci95"][0] > 0.5
        ),
        "insufficient_samples": n_resolved < Q4_MIN_RESOLVED,
    }

    extra_auc = {
        field: _auc_with_ci(field, SEED + index)
        for index, field in enumerate(("quality_raw", "b", "q", "l", "c"), start=1)
    }

    tp_by_raw_bucket: dict[str, Any] = {}
    for low, high in BUCKETS["smc_raw"]:
        items = [
            item
            for item in resolved
            if item["quality_raw"] is not None and low <= item["quality_raw"] <= high
        ]
        tp_by_raw_bucket[_bucket_label(low, high)] = {
            "n": len(items),
            "tp_first_rate": (sum(1 for item in items if item["label"] == 1) / len(items)) if items else None,
        }

    tp_by_readiness: dict[str, Any] = {}
    for item in resolved:
        key = str(item["readiness_status"])
        entry = tp_by_readiness.setdefault(key, {"n": 0, "tp_first": 0})
        entry["n"] += 1
        entry["tp_first"] += item["label"]
    tp_by_readiness = {
        key: {
            "n": entry["n"],
            "tp_first_rate": entry["tp_first"] / entry["n"] if entry["n"] else None,
        }
        for key, entry in sorted(tp_by_readiness.items())
    }

    mfe_tp = [item["mfe_r"] for item in resolved if item["label"] == 1 and item["mfe_r"] is not None]
    mfe_sl = [item["mfe_r"] for item in resolved if item["label"] == 0 and item["mfe_r"] is not None]
    mae_tp = [item["mae_r"] for item in resolved if item["label"] == 1 and item["mae_r"] is not None]
    mae_sl = [item["mae_r"] for item in resolved if item["label"] == 0 and item["mae_r"] is not None]

    return {
        "counts_by_side": {side: counts[side] for side in SIDES},
        "counts_total": total_counts,
        "n_resolved": n_resolved,
        "n_tp": n_tp,
        "n_sl": n_sl,
        "q4_condition_2": q4_condition_2,
        "auc_extra": extra_auc,
        "tp_first_rate_by_quality_raw_bucket": tp_by_raw_bucket,
        "tp_first_rate_by_readiness_status": tp_by_readiness,
        "mfe_r_mean_by_label": {"tp_first": _mean(mfe_tp), "sl_first": _mean(mfe_sl)},
        "mae_r_mean_by_label": {"tp_first": _mean(mae_tp), "sl_first": _mean(mae_sl)},
    }


def _q6_evidence(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values: list[int | None] = []
    state_counts: dict[str, int] = {}
    for row in rows:
        for side in SIDES:
            side_row = row["sides"][side]
            state = side_row["smc_state"]
            state_counts[state] = state_counts.get(state, 0) + 1
            if state == "data_unavailable" or side_row["quality_raw"] is None:
                values.append(None)
            elif state == "no_zone":
                values.append(0)
            else:
                values.append(_round_half_up_number(side_row["quality_score"]))
    non_null = [value for value in values if value is not None]
    positive = [value for value in non_null if value > 0]
    distribution = _numeric_summary([float(value) for value in positive])
    p25 = float(np.percentile(positive, 25)) if positive else None
    p75 = float(np.percentile(positive, 75)) if positive else None
    return {
        "n_none": sum(1 for value in values if value is None),
        "n_zero": sum(1 for value in values if value == 0),
        "n_positive": len(positive),
        "positive_distribution": {
            "min": distribution["min"],
            "p25": p25,
            "median": distribution["median"],
            "p75": p75,
            "max": distribution["max"],
        },
        "counts_by_state": dict(sorted(state_counts.items())),
    }


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = ["# SD-C3 — Phân tích corpus SMC demote", ""]
    lines.append("Sinh tự động từ `analysis.json` (số chỉ để đọc; kết luận ở SD-C4).")
    lines.append("")

    regime = payload["regime_distribution"]
    lines.append("## Regime")
    lines.append("")
    lines.append("| regime | count | fraction |")
    lines.append("|---|---:|---:|")
    for name in REGIMES:
        entry = regime["distribution"][name]
        lines.append(f"| {name} | {entry['count']} | {_fmt(entry['fraction'])} |")
    lines.append("")

    lines.append("## Component discrimination (all)")
    lines.append("")
    lines.append("| component | n | spearman_fwd_8h | spearman_fwd_24h | auc_fwd_24h_pos |")
    lines.append("|---|---:|---:|---:|---:|")
    for component in ("trend", "momentum", "location", "smc_raw", "quality_score"):
        block = payload["component_discrimination"]["all"][component]
        lines.append(
            f"| {component} | {block['n']} | {_fmt(block['spearman_fwd_8h'])} | "
            f"{_fmt(block['spearman_fwd_24h'])} | {_fmt(block['auc_fwd_24h_pos'])} |"
        )
    lines.append("")

    side_selection = payload["side_selection"]
    lines.append("## Side selection")
    lines.append("")
    lines.append("| metric | current | no_smc |")
    lines.append("|---|---:|---:|")
    for key in ("mean_fwd_24h", "mean_fwd_8h", "hit_rate", "median_gap", "gap_ok_count", "gap_ok_mean_fwd_24h", "gap_ok_hit_rate"):
        lines.append(
            f"| {key} | {_fmt(side_selection['current'][key])} | {_fmt(side_selection['no_smc'][key])} |"
        )
    lines.append("")
    q4_1 = side_selection["q4_condition_1"]
    lines.append(
        f"- Q4(1) diff = {_fmt(q4_1['diff'])}, CI95 = "
        f"[{_fmt(q4_1['ci95'][0])}, {_fmt(q4_1['ci95'][1])}], pass = {q4_1['pass']}"
    )
    lines.append(f"- changed_side = {side_selection['counts']['changed_side']}")
    lines.append("")

    smc = payload["smc_tp_sl"]
    lines.append("## SMC TP/SL")
    lines.append("")
    lines.append("| tp_sl | buy | sell | total |")
    lines.append("|---|---:|---:|---:|")
    for value in ("tp_first", "sl_first", "unresolved", "not_filled", "plan_invalid", "None"):
        lines.append(
            f"| {value} | {smc['counts_by_side']['buy'][value]} | "
            f"{smc['counts_by_side']['sell'][value]} | {smc['counts_total'][value]} |"
        )
    lines.append("")
    q4_2 = smc["q4_condition_2"]
    lines.append(
        f"- Q4(2) auc = {_fmt(q4_2['auc'])}, CI95 = "
        f"[{_fmt(q4_2['ci95'][0])}, {_fmt(q4_2['ci95'][1])}], "
        f"n_resolved = {q4_2['n_resolved']}, pass = {q4_2['pass']}"
    )
    lines.append("")

    q6 = payload["q6_evidence"]
    lines.append("## Q6 evidence mapping")
    lines.append("")
    lines.append("| bucket | count |")
    lines.append("|---|---:|")
    lines.append(f"| None | {q6['n_none']} |")
    lines.append(f"| 0 | {q6['n_zero']} |")
    lines.append(f"| >0 | {q6['n_positive']} |")
    lines.append("")

    lines.append("## Changed-side rows")
    lines.append("")
    lines.append("| symbol | cutoff | regime | side_current | side_no_smc | buy_cur | sell_cur | buy_ns | sell_ns |")
    lines.append("|---|---|---|---|---|---:|---:|---:|---:|")
    for item in side_selection["changed_rows"]:
        lines.append(
            f"| {item['symbol']} | {item['cutoff']} | {item['regime']} | "
            f"{item['side_current']} | {item['side_no_smc']} | {item['buy_current']} | "
            f"{item['sell_current']} | {item['buy_no_smc']} | {item['sell_no_smc']} |"
        )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------

def _run_analyze(_args) -> int:
    rows, _ = read_jsonl(ROWS_PATH)
    errors, _ = read_jsonl(ERRORS_PATH)
    if not rows:
        print(f"BLOCKED: no replay rows at {ROWS_PATH}")
        return 2
    if not SUMMARY_PATH.exists():
        print(f"BLOCKED: no summary at {SUMMARY_PATH}; run SD-C2 `summary` first.")
        return 2

    rows_hash = "sha256:" + hashlib.sha256(ROWS_PATH.read_bytes()).hexdigest()
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    expected_hash = summary.get("rows_sha256")
    if expected_hash is not None and expected_hash != rows_hash:
        print("BLOCKED: replay_rows.jsonl khác replay_summary.json")
        return 2

    payload = {
        "inputs": {**_inputs(rows, errors, rows_hash)},
        "regime_distribution": _regime_distribution(rows),
        "raw_distribution": _raw_distribution(rows),
        "component_discrimination": _component_discrimination(rows),
        "side_selection": _side_selection(rows),
        "smc_tp_sl": _smc_tp_sl(rows),
        "q6_evidence": _q6_evidence(rows),
    }
    _atomic_write_text(
        ANALYSIS_JSON,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    _atomic_write_text(ANALYSIS_MD, _render_markdown(payload))
    print(f"analyze: rows={payload['inputs']['rows']} clusters={payload['inputs']['day_clusters']}")
    print(f"q4_condition_1={payload['side_selection']['q4_condition_1']}")
    print(f"q4_condition_2={payload['smc_tp_sl']['q4_condition_2']}")
    print(f"analysis -> {ANALYSIS_JSON}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SMC demote corpus analysis (task SD-C3)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check-scorer")
    sub.add_parser("analyze")
    args = parser.parse_args()
    if args.command == "check-scorer":
        return _run_check_scorer(args)
    return _run_analyze(args)


if __name__ == "__main__":
    raise SystemExit(main())
