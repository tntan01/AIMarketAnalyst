"""Scan health observability — rollout-independent scan quality metrics.

The Phase-8 rollout stage ladder (SHADOW/DEMO/CANARY/PRODUCTION) was removed
when the app went fully live (2026-08-15). What survives here is the part of
the old scan-health report that never depended on any rollout logic:
independent scan health metrics (SMC no-zone rate, data availability,
analysis latency) and closed-trade expectancy summarized per SMC scorer
version.
"""

from __future__ import annotations

from typing import Any


SCAN_HEALTH_VERSION = "scan-health-v1"


def build_scan_health_report(
    rows: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Collect independent scan health metrics.

    Keeps only the health metrics that do not depend on any legacy logic:
    SMC no-zone rate, data availability and analysis latency.
    """
    smc_no_zone_sides = 0
    smc_side_samples = 0
    data_unavailable = 0
    analysis_errors = 0
    latency_values: list[float] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue

        analysis = (
            row.get("analysis_result")
            if isinstance(row.get("analysis_result"), dict)
            else {}
        )
        smc_diagnostics = (
            analysis.get("smc_scoring")
            if isinstance(analysis.get("smc_scoring"), dict)
            else {}
        )
        # Independent no-zone health metric from the canonical sides, not a
        # v1/v2 comparison payload.
        smc_sides = (
            smc_diagnostics.get("sides")
            if isinstance(smc_diagnostics.get("sides"), dict)
            else {}
        )
        for side in ("buy", "sell"):
            side_payload = (
                smc_sides.get(side)
                if isinstance(smc_sides.get(side), dict)
                else None
            )
            if side_payload is None:
                continue
            smc_side_samples += 1
            if not side_payload.get("selected_zone_id"):
                smc_no_zone_sides += 1

        if str(
            row.get("candidate_status", "DATA_UNAVAILABLE")
            or "DATA_UNAVAILABLE"
        ).upper() == "DATA_UNAVAILABLE":
            data_unavailable += 1
        if row.get("analysis_error") is True:
            analysis_errors += 1
        latency = _finite_float(
            row.get("analysis_latency_ms"),
            -1.0,
        )
        if latency >= 0:
            latency_values.append(latency)

    return {
        "scan_health_version": SCAN_HEALTH_VERSION,
        "smc_no_zone_sides": smc_no_zone_sides,
        "smc_side_samples": smc_side_samples,
        "data_unavailable": data_unavailable,
        "analysis_errors": analysis_errors,
        "analysis_latency_ms_total": round(sum(latency_values), 3),
        "analysis_latency_samples": len(latency_values),
        "analysis_latency_ms_max": round(
            max(latency_values) if latency_values else 0.0,
            3,
        ),
    }


def build_scorer_performance(
    trades: list[dict[str, Any]] | None,
) -> dict[str, dict[str, float | int]]:
    """Summarize closed-trade expectancy/drawdown by SMC scorer version."""

    grouped: dict[str, list[tuple[str, float]]] = {}
    for trade in trades if isinstance(trades, list) else []:
        if not isinstance(trade, dict):
            continue
        try:
            result_r = float(trade.get("result_r"))
        except (TypeError, ValueError, OverflowError):
            continue
        if result_r != result_r or abs(result_r) == float("inf"):
            continue
        version = str(
            trade.get("smc_scorer_version")
            or trade.get("entry_zone_scoring_version")
            or "unknown"
        )
        timestamp = str(
            trade.get("closed_at")
            or trade.get("timestamp_utc")
            or trade.get("entry_time")
            or ""
        )
        grouped.setdefault(version, []).append((timestamp, result_r))

    result: dict[str, dict[str, float | int]] = {}
    for version, values in grouped.items():
        ordered = [value for _, value in sorted(values)]
        equity = 0.0
        peak = 0.0
        max_drawdown = 0.0
        for value in ordered:
            equity += value
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, peak - equity)
        result[version] = {
            "trades": len(ordered),
            "expectancy_r": round(sum(ordered) / len(ordered), 6),
            "max_drawdown_r": round(max_drawdown, 6),
        }
    return result


def _finite_float(value: object, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if number == number and abs(number) != float("inf") else default


__all__ = [
    "SCAN_HEALTH_VERSION",
    "build_scan_health_report",
    "build_scorer_performance",
]
