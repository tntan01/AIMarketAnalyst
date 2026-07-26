"""Forward-demo reconciliation, engine shadow comparison and release gate."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any

from core.backtest_contract import VALIDATION_BACKTEST_ENGINE_VERSION
from core.backtest_golden_replay import (
    GOLDEN_REPLAY_VERSION,
    GOLDEN_RESULT_FINGERPRINT,
)
from core.backtest_provenance import canonical_fingerprint


BACKTEST_RELEASE_REPORT_VERSION = "backtest-phase7-release-report-v1"
BACKTEST_SHADOW_REPORT_VERSION = "backtest-phase7-engine-shadow-v1"
BACKTEST_FORWARD_RECONCILIATION_VERSION = "backtest-phase7-forward-demo-v1"

DEFAULT_RELEASE_THRESHOLDS: dict[str, float | int] = {
    "min_forward_samples": 20,
    "min_fill_rate": 0.80,
    "max_rejection_rate": 0.20,
    "max_average_adverse_slippage_bps": 5.0,
    "max_performance_degradation_pct": 25.0,
    "min_shadow_samples": 20,
    "max_shadow_disagreement_rate": 0.10,
}


def reconcile_forward_demo(
    backtest_trades: list[dict[str, Any]],
    demo_trades: list[dict[str, Any]],
    *,
    thresholds: dict[str, float | int] | None = None,
    time_tolerance_minutes: int = 240,
) -> dict[str, Any]:
    cfg = _thresholds(thresholds)
    available = [dict(row) for row in demo_trades if isinstance(row, dict)]
    matches: list[dict[str, Any]] = []
    used: set[int] = set()
    for expected in backtest_trades:
        if not isinstance(expected, dict):
            continue
        selected = _find_demo_match(
            expected, available, used,
            tolerance=timedelta(minutes=max(1, time_tolerance_minutes)),
        )
        if selected is None:
            continue
        index, actual = selected
        used.add(index)
        planned_entry = _number(expected.get("raw_entry_price"))
        if planned_entry is None:
            planned_entry = _number(expected.get("entry_price"))
        actual_entry = _number(actual.get("actual_entry"))
        side = str(expected.get("side") or "").lower()
        adverse = None
        adverse_bps = None
        if planned_entry and actual_entry is not None:
            adverse = (
                actual_entry - planned_entry
                if side == "buy" else planned_entry - actual_entry
            )
            adverse_bps = adverse / planned_entry * 10_000.0
        planned_risk = _number(expected.get("planned_risk_account"))
        demo_r = _number(actual.get("result_r"))
        if demo_r is None and planned_risk and planned_risk > 0:
            amount = _number(actual.get("result_amount"))
            demo_r = amount / planned_risk if amount is not None else None
        matches.append({
            "candidate_id": str(expected.get("candidate_id") or ""),
            "demo_candidate_id": str(actual.get("candidate_id") or ""),
            "symbol": expected.get("symbol"),
            "side": side,
            "backtest_entry": planned_entry,
            "demo_entry": actual_entry,
            "adverse_slippage_price": adverse,
            "adverse_slippage_bps": adverse_bps,
            "backtest_result_r": _number(expected.get("result_r")),
            "demo_result_r": demo_r,
            "mt5_deal_id": actual.get("mt5_deal_id"),
        })

    expected_count = sum(isinstance(row, dict) for row in backtest_trades)
    matched_count = len(matches)
    fill_rate = matched_count / expected_count if expected_count else 0.0
    rejection_rate = 1.0 - fill_rate if expected_count else 1.0
    adverse_values = [
        max(0.0, float(row["adverse_slippage_bps"]))
        for row in matches if row["adverse_slippage_bps"] is not None
    ]
    paired = [
        row for row in matches
        if row["backtest_result_r"] is not None and row["demo_result_r"] is not None
    ]
    backtest_expectancy = mean(row["backtest_result_r"] for row in paired) if paired else 0.0
    demo_expectancy = mean(row["demo_result_r"] for row in paired) if paired else 0.0
    degradation = _degradation(backtest_expectancy, demo_expectancy)
    metrics = {
        "backtest_candidates": expected_count,
        "demo_trades": len(available),
        "matched_trades": matched_count,
        "correlated_matches": sum(
            bool(row.get("demo_candidate_id")) for row in matches
        ),
        "fill_rate": round(fill_rate, 6),
        "rejection_rate": round(rejection_rate, 6),
        "average_adverse_slippage_bps": round(mean(adverse_values), 6) if adverse_values else 0.0,
        "backtest_expectancy_r": round(backtest_expectancy, 6),
        "demo_expectancy_r": round(demo_expectancy, 6),
        "performance_degradation_pct": round(degradation, 6),
    }
    blocks: list[str] = []
    if matched_count < int(cfg["min_forward_samples"]):
        blocks.append("FORWARD_SAMPLE_TOO_SMALL")
    if metrics["correlated_matches"] < matched_count:
        blocks.append("FORWARD_CORRELATION_MISSING")
    if fill_rate < float(cfg["min_fill_rate"]):
        blocks.append("FORWARD_FILL_RATE_TOO_LOW")
    if rejection_rate > float(cfg["max_rejection_rate"]):
        blocks.append("FORWARD_REJECTION_RATE_TOO_HIGH")
    if metrics["average_adverse_slippage_bps"] > float(cfg["max_average_adverse_slippage_bps"]):
        blocks.append("FORWARD_SLIPPAGE_TOO_HIGH")
    if degradation > float(cfg["max_performance_degradation_pct"]):
        blocks.append("FORWARD_PERFORMANCE_DEGRADATION_TOO_HIGH")
    return {
        "version": BACKTEST_FORWARD_RECONCILIATION_VERSION,
        "ready": not blocks,
        "block_codes": blocks,
        "thresholds": cfg,
        "metrics": metrics,
        "matches": matches,
    }


def compare_engine_shadow(
    legacy_trades: list[dict[str, Any]],
    current_trades: list[dict[str, Any]],
    *,
    thresholds: dict[str, float | int] | None = None,
) -> dict[str, Any]:
    cfg = _thresholds(thresholds)
    legacy = {_trade_identity(row): row for row in legacy_trades if isinstance(row, dict)}
    current = {_trade_identity(row): row for row in current_trades if isinstance(row, dict)}
    identities = set(legacy) | set(current)
    disagreements = 0
    details: list[dict[str, Any]] = []
    for identity in sorted(identities):
        old = legacy.get(identity)
        new = current.get(identity)
        codes: list[str] = []
        if old is None:
            codes.append("CURRENT_ONLY_TRADE")
        elif new is None:
            codes.append("LEGACY_ONLY_TRADE")
        elif str(old.get("result") or "") != str(new.get("result") or ""):
            codes.append("OUTCOME_DISAGREEMENT")
        if codes:
            disagreements += 1
        details.append({"identity": identity, "disagreement_codes": codes})
    samples = len(identities)
    rate = disagreements / samples if samples else 1.0
    legacy_expectancy = _expectancy(list(legacy.values()))
    current_expectancy = _expectancy(list(current.values()))
    degradation = _degradation(legacy_expectancy, current_expectancy)
    blocks: list[str] = []
    if samples < int(cfg["min_shadow_samples"]):
        blocks.append("ENGINE_SHADOW_SAMPLE_TOO_SMALL")
    if rate > float(cfg["max_shadow_disagreement_rate"]):
        blocks.append("ENGINE_SHADOW_DISAGREEMENT_TOO_HIGH")
    if degradation > float(cfg["max_performance_degradation_pct"]):
        blocks.append("ENGINE_SHADOW_PERFORMANCE_DEGRADATION_TOO_HIGH")
    return {
        "version": BACKTEST_SHADOW_REPORT_VERSION,
        "ready": not blocks,
        "block_codes": blocks,
        "samples": samples,
        "disagreements": disagreements,
        "disagreement_rate": round(rate, 6),
        "legacy_expectancy_r": round(legacy_expectancy, 6),
        "current_expectancy_r": round(current_expectancy, 6),
        "performance_degradation_pct": round(degradation, 6),
        "comparisons": details,
    }


def build_release_report(
    snapshot: dict[str, Any],
    *,
    demo_trades: list[dict[str, Any]],
    forward_trades: list[dict[str, Any]] | None = None,
    golden_report: dict[str, Any],
    shadow_report: dict[str, Any],
    reviewed_by: str,
    approved: bool,
    reviewed_at: datetime | None = None,
    thresholds: dict[str, float | int] | None = None,
) -> dict[str, Any]:
    evidence = _release_evidence(snapshot)
    forward_evidence = (
        [dict(row) for row in forward_trades if isinstance(row, dict)]
        if isinstance(forward_trades, list)
        else evidence["trades"]
    )
    reconciliation = reconcile_forward_demo(
        forward_evidence, demo_trades, thresholds=thresholds
    )
    blocks: list[str] = []
    if evidence["engine_version"] != VALIDATION_BACKTEST_ENGINE_VERSION:
        blocks.append("CURRENT_VALIDATION_ENGINE_REQUIRED")
    if not evidence["dataset_hash"]:
        blocks.append("RELEASE_DATASET_HASH_MISSING")
    if not evidence["provenance_fingerprint"]:
        blocks.append("RELEASE_PROVENANCE_MISSING")
    if golden_report.get("passed") is not True:
        blocks.append("GOLDEN_REPLAY_NOT_PASSED")
    if reconciliation.get("ready") is not True:
        blocks.extend(reconciliation.get("block_codes", []))
    if shadow_report.get("ready") is not True:
        blocks.extend(shadow_report.get("block_codes", ["ENGINE_SHADOW_NOT_READY"]))
    if not str(reviewed_by or "").strip():
        blocks.append("RELEASE_REVIEWER_REQUIRED")
    if approved is not True:
        blocks.append("RELEASE_REVIEW_NOT_APPROVED")
    report = {
        "version": BACKTEST_RELEASE_REPORT_VERSION,
        "ready": not blocks,
        "approved": bool(approved),
        "reviewed_by": str(reviewed_by or "").strip(),
        "reviewed_at": (reviewed_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec="seconds"),
        "dataset_hash": evidence["dataset_hash"],
        "provenance_fingerprint": evidence["provenance_fingerprint"],
        "engine_version": evidence["engine_version"],
        "forward_evidence_fingerprint": canonical_fingerprint(
            forward_evidence
        ),
        "demo_evidence_fingerprint": canonical_fingerprint(demo_trades),
        "golden_replay": dict(golden_report),
        "forward_demo": reconciliation,
        "engine_shadow": dict(shadow_report),
        "block_codes": list(dict.fromkeys(blocks)),
    }
    report["report_fingerprint"] = release_report_fingerprint(report)
    return report


def validate_release_report(
    report: object,
    *,
    dataset_hash: str = "",
    provenance_fingerprint: str = "",
) -> list[str]:
    if not isinstance(report, dict) or not report:
        return ["BACKTEST_RELEASE_REPORT_MISSING"]
    reasons: list[str] = []
    if str(report.get("version") or "") != BACKTEST_RELEASE_REPORT_VERSION:
        reasons.append("BACKTEST_RELEASE_REPORT_VERSION_MISMATCH")
    if report.get("ready") is not True or report.get("approved") is not True:
        reasons.append("BACKTEST_RELEASE_REPORT_NOT_READY")
    if report.get("block_codes") not in ([], ()):
        reasons.append("BACKTEST_RELEASE_REPORT_HAS_BLOCKS")
    if not str(report.get("reviewed_by") or "").strip():
        reasons.append("BACKTEST_RELEASE_REVIEWER_MISSING")
    if _trade_time({"time": report.get("reviewed_at")}) is None:
        reasons.append("BACKTEST_RELEASE_REVIEW_TIME_INVALID")
    if str(report.get("engine_version") or "") != (
        VALIDATION_BACKTEST_ENGINE_VERSION
    ):
        reasons.append("BACKTEST_RELEASE_ENGINE_VERSION_MISMATCH")
    for field in (
        "forward_evidence_fingerprint",
        "demo_evidence_fingerprint",
    ):
        fingerprint = str(report.get(field) or "").lower()
        if len(fingerprint) != 64 or any(
            character not in "0123456789abcdef"
            for character in fingerprint
        ):
            reasons.append(f"BACKTEST_RELEASE_{field.upper()}_INVALID")
    if str(report.get("report_fingerprint") or "") != release_report_fingerprint(report):
        reasons.append("BACKTEST_RELEASE_REPORT_FINGERPRINT_INVALID")
    if dataset_hash and str(report.get("dataset_hash") or "") != dataset_hash:
        reasons.append("BACKTEST_RELEASE_DATASET_MISMATCH")
    if provenance_fingerprint and str(report.get("provenance_fingerprint") or "") != provenance_fingerprint:
        reasons.append("BACKTEST_RELEASE_PROVENANCE_MISMATCH")
    golden = report.get("golden_replay")
    if (
        not isinstance(golden, dict)
        or golden.get("version") != GOLDEN_REPLAY_VERSION
        or golden.get("passed") is not True
        or golden.get("result_fingerprint") != GOLDEN_RESULT_FINGERPRINT
        or golden.get("mismatches") not in ([], ())
    ):
        reasons.append("BACKTEST_RELEASE_GOLDEN_REPLAY_REQUIRED")
    forward = report.get("forward_demo")
    if (
        not isinstance(forward, dict)
        or forward.get("version") != BACKTEST_FORWARD_RECONCILIATION_VERSION
        or forward.get("ready") is not True
        or not _forward_metrics_within_policy(forward.get("metrics"))
    ):
        reasons.append("BACKTEST_RELEASE_FORWARD_DEMO_REQUIRED")
    shadow = report.get("engine_shadow")
    if (
        not isinstance(shadow, dict)
        or shadow.get("version") != BACKTEST_SHADOW_REPORT_VERSION
        or shadow.get("ready") is not True
        or not _shadow_metrics_within_policy(shadow)
    ):
        reasons.append("BACKTEST_RELEASE_ENGINE_SHADOW_REQUIRED")
    return list(dict.fromkeys(reasons))


def release_report_fingerprint(report: dict[str, Any]) -> str:
    payload = dict(report)
    payload.pop("report_fingerprint", None)
    return canonical_fingerprint(payload)


def _release_evidence(snapshot: dict[str, Any]) -> dict[str, Any]:
    replay = snapshot.get("validation_replay")
    source = replay if isinstance(replay, dict) and replay.get("status") == "COMPLETE" else snapshot
    contract = source.get("backtest_contract") if isinstance(source.get("backtest_contract"), dict) else {}
    manifest = source.get("data_manifest") if isinstance(source.get("data_manifest"), dict) else {}
    provenance = source.get("backtest_provenance") if isinstance(source.get("backtest_provenance"), dict) else {}
    trades = source.get("oos_trades") if isinstance(source.get("oos_trades"), list) else source.get("trades", [])
    return {
        "engine_version": str(contract.get("engine_version") or ""),
        "dataset_hash": str(manifest.get("dataset_hash") or provenance.get("dataset_hash") or ""),
        "provenance_fingerprint": str(provenance.get("provenance_fingerprint") or ""),
        "trades": [row for row in trades if isinstance(row, dict)],
    }


def _find_demo_match(expected, demo, used, *, tolerance):
    candidate_id = str(expected.get("candidate_id") or "")
    expected_time = _trade_time(expected)
    for index, actual in enumerate(demo):
        if index in used:
            continue
        if candidate_id and str(actual.get("candidate_id") or "") == candidate_id:
            return index, actual
        if _normalize_symbol(actual.get("symbol")) != _normalize_symbol(expected.get("symbol")):
            continue
        if str(actual.get("side") or "").lower() != str(expected.get("side") or "").lower():
            continue
        actual_time = _trade_time(actual)
        if expected_time and actual_time and abs(actual_time - expected_time) <= tolerance:
            return index, actual
    return None


def _trade_identity(row: dict[str, Any]) -> str:
    moment = _trade_time(row)
    market_identity = "|".join((
        _normalize_symbol(row.get("symbol")),
        str(row.get("side") or "").lower(),
        moment.isoformat() if moment else "",
    ))
    if moment is not None:
        return market_identity
    candidate = str(row.get("candidate_id") or "")
    return candidate or market_identity


def _trade_time(row: dict[str, Any]) -> datetime | None:
    for key in ("entry_time", "opened_at", "time"):
        value = row.get(key)
        if not value:
            continue
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _expectancy(rows: list[dict[str, Any]]) -> float:
    values = [_number(row.get("result_r")) for row in rows]
    clean = [value for value in values if value is not None]
    return mean(clean) if clean else 0.0


def _degradation(reference: float, observed: float) -> float:
    if reference > 0:
        return max(0.0, (reference - observed) / abs(reference) * 100.0)
    return 0.0 if observed >= reference else 100.0


def _thresholds(values: dict[str, float | int] | None) -> dict[str, float | int]:
    result = dict(DEFAULT_RELEASE_THRESHOLDS)
    if isinstance(values, dict):
        candidate = dict(result)
        candidate.update({
            key: value for key, value in values.items() if key in candidate
        })
        try:
            result.update({
                "min_forward_samples": max(
                    int(result["min_forward_samples"]),
                    int(candidate["min_forward_samples"]),
                ),
                "min_fill_rate": max(
                    float(result["min_fill_rate"]),
                    float(candidate["min_fill_rate"]),
                ),
                "max_rejection_rate": min(
                    float(result["max_rejection_rate"]),
                    float(candidate["max_rejection_rate"]),
                ),
                "max_average_adverse_slippage_bps": min(
                    float(result["max_average_adverse_slippage_bps"]),
                    float(candidate["max_average_adverse_slippage_bps"]),
                ),
                "max_performance_degradation_pct": min(
                    float(result["max_performance_degradation_pct"]),
                    float(candidate["max_performance_degradation_pct"]),
                ),
                "min_shadow_samples": max(
                    int(result["min_shadow_samples"]),
                    int(candidate["min_shadow_samples"]),
                ),
                "max_shadow_disagreement_rate": min(
                    float(result["max_shadow_disagreement_rate"]),
                    float(candidate["max_shadow_disagreement_rate"]),
                ),
            })
        except (TypeError, ValueError, OverflowError):
            pass
    return result


def _forward_metrics_within_policy(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        int(_metric(value, "matched_trades", 0.0))
        >= int(DEFAULT_RELEASE_THRESHOLDS["min_forward_samples"])
        and int(_metric(value, "correlated_matches", 0.0))
        >= int(_metric(value, "matched_trades", 0.0))
        and _metric(value, "fill_rate", 0.0)
        >= float(DEFAULT_RELEASE_THRESHOLDS["min_fill_rate"])
        and _metric(value, "rejection_rate", 1.0)
        <= float(DEFAULT_RELEASE_THRESHOLDS["max_rejection_rate"])
        and _metric(value, "average_adverse_slippage_bps", float("inf"))
        <= float(
            DEFAULT_RELEASE_THRESHOLDS["max_average_adverse_slippage_bps"]
        )
        and _metric(value, "performance_degradation_pct", float("inf"))
        <= float(
            DEFAULT_RELEASE_THRESHOLDS["max_performance_degradation_pct"]
        )
    )


def _shadow_metrics_within_policy(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        int(_metric(value, "samples", 0.0))
        >= int(DEFAULT_RELEASE_THRESHOLDS["min_shadow_samples"])
        and _metric(value, "disagreement_rate", 1.0)
        <= float(DEFAULT_RELEASE_THRESHOLDS["max_shadow_disagreement_rate"])
        and _metric(value, "performance_degradation_pct", float("inf"))
        <= float(
            DEFAULT_RELEASE_THRESHOLDS["max_performance_degradation_pct"]
        )
    )


def _normalize_symbol(value: object) -> str:
    return "".join(char for char in str(value or "").upper() if char.isalnum())


def _number(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _metric(payload: dict[str, Any], key: str, default: float) -> float:
    value = _number(payload.get(key))
    return default if value is None else value
