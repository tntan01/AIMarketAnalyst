"""Phase-8 shadow comparison, rollout guard and release-readiness contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any


SCANNER_ROLLOUT_VERSION = "phase8-rollout-v1"
ROLLBACK_DRILL_VERSION = "phase8-rollback-drill-v1"

ROLLOUT_DISABLED = "DISABLED"
ROLLOUT_SHADOW = "SHADOW"
ROLLOUT_DEMO_LIMITED = "DEMO_LIMITED"
ROLLOUT_DEMO_FULL = "DEMO_FULL"
ROLLOUT_CANARY = "CANARY"
ROLLOUT_PRODUCTION = "PRODUCTION"

ROLLOUT_STAGES = frozenset({
    ROLLOUT_DISABLED,
    ROLLOUT_SHADOW,
    ROLLOUT_DEMO_LIMITED,
    ROLLOUT_DEMO_FULL,
    ROLLOUT_CANARY,
    ROLLOUT_PRODUCTION,
})


@dataclass(frozen=True, slots=True)
class RolloutOrderDecision:
    allowed: bool
    stage: str
    symbol: str
    risk_cap_percent: float | None
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["rollout_version"] = SCANNER_ROLLOUT_VERSION
        payload["reason_codes"] = list(self.reason_codes)
        return payload


@dataclass(frozen=True, slots=True)
class ScannerRolloutPolicy:
    stage: str
    kill_switch: bool
    shadow_compare_enabled: bool
    allowed_symbols: tuple[str, ...]
    canary_risk_percent: float
    require_demo_account: bool
    production_approved: bool
    canary_ready: bool
    release_ready: bool
    server: str
    account_is_demo: bool

    def order_decision(
        self,
        symbol: str,
        *,
        requested: bool = True,
    ) -> RolloutOrderDecision:
        normalized_symbol = _normalize_symbol(symbol)
        reasons: list[str] = []
        allowed = True
        risk_cap: float | None = None

        if not requested:
            allowed = False
            reasons.append("USER_AUTO_TRADE_DISABLED")
        if self.kill_switch:
            allowed = False
            reasons.append("ROLLOUT_KILL_SWITCH_ACTIVE")
        if self.stage == ROLLOUT_DISABLED:
            allowed = False
            reasons.append("ROLLOUT_DISABLED")
        elif self.stage == ROLLOUT_SHADOW:
            allowed = False
            reasons.append("SHADOW_MODE_ORDER_SUPPRESSED")
        elif self.stage in {ROLLOUT_DEMO_LIMITED, ROLLOUT_DEMO_FULL}:
            if not self.account_is_demo:
                allowed = False
                reasons.append("DEMO_ACCOUNT_REQUIRED")
            if (
                self.stage == ROLLOUT_DEMO_LIMITED
                and normalized_symbol not in self.allowed_symbols
            ):
                allowed = False
                reasons.append("SYMBOL_NOT_IN_LIMITED_ROLLOUT")
        elif self.stage == ROLLOUT_CANARY:
            risk_cap = self.canary_risk_percent
            if not self.canary_ready:
                allowed = False
                reasons.append("CANARY_GATE_NOT_READY")
            if self.require_demo_account and not self.account_is_demo:
                allowed = False
                reasons.append("DEMO_ACCOUNT_REQUIRED")
        elif self.stage == ROLLOUT_PRODUCTION:
            if not self.production_approved:
                allowed = False
                reasons.append("PRODUCTION_APPROVAL_REQUIRED")
            if not self.release_ready:
                allowed = False
                reasons.append("RELEASE_GATE_NOT_READY")
        else:
            allowed = False
            reasons.append("ROLLOUT_STAGE_INVALID")

        return RolloutOrderDecision(
            allowed=allowed and not reasons,
            stage=self.stage,
            symbol=normalized_symbol,
            risk_cap_percent=risk_cap,
            reason_codes=tuple(dict.fromkeys(reasons)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rollout_version": SCANNER_ROLLOUT_VERSION,
            "stage": self.stage,
            "kill_switch": self.kill_switch,
            "shadow_compare_enabled": self.shadow_compare_enabled,
            "allowed_symbols": list(self.allowed_symbols),
            "canary_risk_percent": self.canary_risk_percent,
            "require_demo_account": self.require_demo_account,
            "production_approved": self.production_approved,
            "canary_ready": self.canary_ready,
            "release_ready": self.release_ready,
            "server": self.server,
            "account_is_demo": self.account_is_demo,
        }


@dataclass(frozen=True, slots=True)
class ReleaseReadiness:
    ready: bool
    block_codes: tuple[str, ...]
    metrics: dict[str, Any]
    thresholds: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rollout_version": SCANNER_ROLLOUT_VERSION,
            "ready": self.ready,
            "block_codes": list(self.block_codes),
            "metrics": dict(self.metrics),
            "thresholds": dict(self.thresholds),
        }


def build_rollout_policy(
    settings: object,
    *,
    server: object = "",
    canary_ready: bool = False,
    release_ready: bool = False,
) -> ScannerRolloutPolicy:
    stage = str(getattr(settings, "stage", ROLLOUT_SHADOW) or "").upper()
    if stage not in ROLLOUT_STAGES:
        stage = "INVALID"
    raw_symbols = getattr(settings, "allowed_symbols", ())
    allowed_symbols = (
        tuple(
            dict.fromkeys(
                _normalize_symbol(symbol)
                for symbol in raw_symbols
                if _normalize_symbol(symbol)
            )
        )
        if isinstance(raw_symbols, (list, tuple, set))
        else ()
    )
    server_text = str(server or "")
    return ScannerRolloutPolicy(
        stage=stage,
        kill_switch=bool(getattr(settings, "kill_switch", False)),
        shadow_compare_enabled=bool(
            getattr(settings, "shadow_compare_enabled", True)
        ),
        allowed_symbols=allowed_symbols,
        canary_risk_percent=min(
            max(
                _finite_float(
                    getattr(settings, "canary_risk_percent", 0.1),
                    0.1,
                ),
                0.01,
            ),
            1.0,
        ),
        require_demo_account=bool(
            getattr(settings, "require_demo_account", True)
        ),
        production_approved=bool(
            getattr(settings, "production_approved", False)
        ),
        canary_ready=bool(canary_ready),
        release_ready=bool(release_ready),
        server=server_text,
        account_is_demo=is_demo_server(server_text),
    )


def is_demo_server(server: object) -> bool:
    normalized = str(server or "").strip().lower()
    return bool(
        re.search(
            r"(^|[^a-z])(?:demo|trial|practice|contest)\d*($|[^a-z])",
            normalized,
        )
    )


def build_shadow_report(
    rows: list[dict[str, Any]] | None,
    *,
    enabled: bool,
    suppress_v2_orders: bool = True,
) -> dict[str, Any]:
    comparisons: list[dict[str, Any]] = []
    if not enabled:
        return {
            "rollout_version": SCANNER_ROLLOUT_VERSION,
            "enabled": False,
            "samples": 0,
            "disagreements": 0,
            "disagreement_rate": 0.0,
            "side_mismatches": 0,
            "false_ready_removed": 0,
            "new_trade_candidates": 0,
            "unsafe_disagreements": 0,
            "smc_direction_changes": 0,
            "smc_zone_changes": 0,
            "smc_score_delta_abs_sum": 0.0,
            "smc_score_delta_samples": 0,
            "smc_no_zone_sides": 0,
            "smc_side_samples": 0,
            "data_unavailable": 0,
            "analysis_errors": 0,
            "analysis_latency_ms_total": 0.0,
            "analysis_latency_samples": 0,
            "analysis_latency_ms_max": 0.0,
            "comparisons": [],
        }

    false_ready_removed = 0
    new_trade_candidates = 0
    unsafe_disagreements = 0
    smc_direction_changes = 0
    smc_zone_changes = 0
    smc_score_delta_abs_sum = 0.0
    smc_score_delta_samples = 0
    smc_no_zone_sides = 0
    smc_side_samples = 0
    data_unavailable = 0
    analysis_errors = 0
    latency_values: list[float] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        v1 = evaluate_legacy_v1(row)
        v1_status = str(v1["status"])
        v2_status = str(
            row.get("candidate_status", "DATA_UNAVAILABLE") or
            "DATA_UNAVAILABLE"
        ).upper()
        v1_side = str(v1.get("side", "") or "").lower()
        v2_side = str(row.get("selected_side", "") or "").lower()
        v1_trade = bool(v1["trade"])
        decision = (
            row.get("scanner_candidate_decision")
            if isinstance(row.get("scanner_candidate_decision"), dict)
            else {}
        )
        strategy = (
            decision.get("strategy")
            if isinstance(decision.get("strategy"), dict)
            else {}
        )
        v2_trade = bool(decision.get("auto_trade_candidate", False))
        v1_score_passed = bool(v1["score_passed"])
        v2_score = strategy.get("score_value")
        v2_min_score = strategy.get("min_score")
        v2_score_passed = (
            v2_score is not None
            and v2_min_score is not None
            and _finite_float(v2_score, float("-inf"))
            >= _finite_float(v2_min_score, float("inf"))
        )
        codes: list[str] = []
        if v1_trade != v2_trade:
            codes.append("TRADE_WAIT_DISAGREEMENT")
        if (
            v1_side in {"buy", "sell"}
            and v2_side in {"buy", "sell"}
            and v1_side != v2_side
        ):
            codes.append("SIDE_DISAGREEMENT")
        if v1_status != v2_status:
            codes.append("STATUS_DISAGREEMENT")
        if v1_score_passed != v2_score_passed:
            codes.append("SCORE_GATE_DISAGREEMENT")
        if v1.get("side_scenario_mismatch") is True:
            codes.append("V1_SIDE_SCENARIO_MISMATCH")
        if v1_trade and not v2_trade:
            false_ready_removed += 1
        if not v1_trade and v2_trade:
            new_trade_candidates += 1
            unsafe_disagreements += 1

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
        smc_comparison = (
            smc_diagnostics.get("comparison")
            if isinstance(smc_diagnostics.get("comparison"), dict)
            else {}
        )
        score_delta = (
            smc_comparison.get("score_delta")
            if isinstance(smc_comparison.get("score_delta"), dict)
            else {}
        )
        selected_zone_changed = (
            smc_comparison.get("selected_zone_changed")
            if isinstance(
                smc_comparison.get("selected_zone_changed"),
                dict,
            )
            else {}
        )
        direction_changed = bool(
            smc_comparison.get("direction_changed")
        )
        if direction_changed:
            smc_direction_changes += 1
        smc_zone_changes += sum(
            1
            for side in ("buy", "sell")
            if selected_zone_changed.get(side) is True
        )
        for side in ("buy", "sell"):
            if side in score_delta:
                smc_score_delta_abs_sum += abs(
                    _finite_float(score_delta.get(side), 0.0)
                )
                smc_score_delta_samples += 1

        decision_snapshots = (
            smc_diagnostics.get("decision")
            if isinstance(smc_diagnostics.get("decision"), dict)
            else {}
        )
        for side in ("buy", "sell"):
            snapshot = (
                decision_snapshots.get(side)
                if isinstance(decision_snapshots.get(side), dict)
                else None
            )
            if snapshot is None:
                continue
            smc_side_samples += 1
            if not snapshot.get("selected_zone_id"):
                smc_no_zone_sides += 1

        if v2_status == "DATA_UNAVAILABLE":
            data_unavailable += 1
        if row.get("analysis_error") is True:
            analysis_errors += 1
        latency = _finite_float(
            row.get("analysis_latency_ms"),
            -1.0,
        )
        if latency >= 0:
            latency_values.append(latency)

        comparisons.append({
            "scan_id": row.get("scan_id"),
            "row_id": row.get("row_id"),
            "symbol": row.get("symbol"),
            "v1": v1,
            "v2": {
                "status": v2_status,
                "side": v2_side or None,
                "trade": v2_trade,
                "score_passed": v2_score_passed,
                "score_metric": strategy.get("score_metric"),
                "score_value": v2_score,
                "min_score": v2_min_score,
                "reason_codes": decision.get("reason_codes", []),
            },
            "disagreement": bool(codes),
            "disagreement_codes": codes,
            "v2_order_suppressed": suppress_v2_orders,
            "smc": {
                "score_delta": dict(score_delta),
                "selected_zone_changed": dict(
                    selected_zone_changed
                ),
                "direction_changed": direction_changed,
                "decision_changed": bool(
                    smc_comparison.get("decision_changed")
                ),
                "decision_input_changed": bool(
                    smc_comparison.get("decision_input_changed")
                ),
            },
        })

    samples = len(comparisons)
    disagreements = sum(
        1 for item in comparisons if item["disagreement"]
    )
    side_mismatches = sum(
        1
        for item in comparisons
        if "SIDE_DISAGREEMENT" in item["disagreement_codes"]
    )
    return {
        "rollout_version": SCANNER_ROLLOUT_VERSION,
        "enabled": True,
        "samples": samples,
        "disagreements": disagreements,
        "disagreement_rate": round(
            disagreements / samples if samples else 0.0,
            6,
        ),
        "side_mismatches": side_mismatches,
        "false_ready_removed": false_ready_removed,
        "new_trade_candidates": new_trade_candidates,
        "unsafe_disagreements": unsafe_disagreements,
        "smc_direction_changes": smc_direction_changes,
        "smc_zone_changes": smc_zone_changes,
        "smc_score_delta_abs_sum": round(
            smc_score_delta_abs_sum,
            6,
        ),
        "smc_score_delta_samples": smc_score_delta_samples,
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
        "comparisons": comparisons,
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


def run_rollback_drill() -> dict[str, Any]:
    """Exercise the safe rollback path without touching a broker.

    There is no v1 scorer to restore any more; rollback is the kill switch and
    the Scanner SHADOW order-suppression stage.
    """

    class _Settings:
        stage = ROLLOUT_PRODUCTION
        kill_switch = True
        shadow_compare_enabled = True
        allowed_symbols: tuple[str, ...] = ()
        canary_risk_percent = 0.1
        require_demo_account = False
        production_approved = True

    kill_decision = build_rollout_policy(
        _Settings(),
        server="Rollback-Drill-Live",
        canary_ready=True,
        release_ready=True,
    ).order_decision("EUR/USD")

    class _ShadowSettings(_Settings):
        stage = ROLLOUT_SHADOW
        kill_switch = False

    shadow_decision = build_rollout_policy(
        _ShadowSettings(),
        server="Rollback-Drill-Live",
        canary_ready=True,
        release_ready=True,
    ).order_decision("EUR/USD")

    checks = {
        "kill_switch_blocks_order": (
            kill_decision.allowed is False
            and "ROLLOUT_KILL_SWITCH_ACTIVE"
            in kill_decision.reason_codes
        ),
        "shadow_stage_blocks_order": (
            shadow_decision.allowed is False
            and "SHADOW_MODE_ORDER_SUPPRESSED"
            in shadow_decision.reason_codes
        ),
    }
    return {
        "drill_version": ROLLBACK_DRILL_VERSION,
        "passed": all(checks.values()),
        "checks": checks,
        "order_decision": kill_decision.to_dict(),
        "shadow_order_decision": shadow_decision.to_dict(),
    }


def evaluate_legacy_v1(row: dict[str, Any]) -> dict[str, Any]:
    """Reproduce the pre-migration V1 auto-trade candidate behavior."""

    source = (
        row.get("legacy_candidate_input")
        if isinstance(row.get("legacy_candidate_input"), dict)
        else row
    )
    analysis = (
        row.get("analysis_result")
        if isinstance(row.get("analysis_result"), dict)
        else None
    )
    status = str(
        row.get("legacy_candidate_status", "DATA_UNAVAILABLE")
        or "DATA_UNAVAILABLE"
    ).upper()
    best_side = str(source.get("best_side", "") or "").lower()
    selected_side = best_side
    reasons: list[str] = []
    score_passed = False
    scenario: dict[str, Any] | None = None

    if analysis is None:
        reasons.append("V1_MISSING_ANALYSIS")
    if status == "BLOCKED":
        reasons.append("V1_SCANNER_GROUP_BLOCKED")
    if str(source.get("trade_permission", "") or "").lower() == "blocked":
        reasons.append("V1_TRADE_PERMISSION_BLOCKED")
    journal = (
        row.get("journal_feedback")
        if isinstance(row.get("journal_feedback"), dict)
        else {}
    )
    if journal.get("decision_cap") in {"TRADE_BLOCKED", "WATCH_ONLY"}:
        reasons.append("V1_JOURNAL_CAP_BLOCKED")

    config = (
        row.get("auto_trade_config")
        if isinstance(row.get("auto_trade_config"), dict)
        else None
    )
    if config is None:
        score_passed = True
        if str(source.get("scanner_action", "") or "") != "ready":
            reasons.append("V1_SCANNER_ACTION_NOT_READY")
        if str(source.get("trade_permission", "") or "") != "allowed":
            reasons.append("V1_TRADE_PERMISSION_NOT_ALLOWED")
        scenario = _legacy_scenario(row, best_side)
    else:
        configured_regime = str(
            config.get("regime", "") or ""
        ).strip().lower()
        configured_side = str(
            config.get("side", "") or ""
        ).strip().lower()
        if configured_side in {"buy", "sell"}:
            selected_side = configured_side
        if (
            configured_regime
            and str(source.get("market_regime", "") or "").lower()
            != configured_regime
        ):
            reasons.append("V1_REGIME_MISMATCH")
        min_rr = _finite_float(config.get("min_rr"), 0.0)
        effective_rr = _finite_float(
            source.get("expected_effective_rr"),
            -1.0,
        )
        if min_rr > 0 and effective_rr < min_rr:
            reasons.append("V1_RR_BELOW_MINIMUM")
        min_score = _finite_float(config.get("min_score"), 0.0)
        if min_score <= 0:
            min_score = 65.0
        score_passed = (
            _finite_float(source.get("best_score"), 0.0) >= min_score
        )
        if not score_passed:
            reasons.append("V1_SCORE_BELOW_MINIMUM")
        scenario = _legacy_scenario(
            row,
            selected_side,
            fallback_side=best_side,
        )

    if scenario is None:
        reasons.append("V1_SCENARIO_MISSING")
    scenario_side = (
        str(scenario.get("type", "") or "").lower()
        if isinstance(scenario, dict)
        else ""
    )
    side_mismatch = bool(
        scenario_side in {"buy", "sell"}
        and selected_side in {"buy", "sell"}
        and scenario_side != selected_side
    )
    return {
        "status": status,
        "side": selected_side or None,
        "scenario_side": scenario_side or None,
        "side_scenario_mismatch": side_mismatch,
        "trade": not reasons,
        "score_passed": score_passed,
        "reason_codes": reasons,
    }


def evaluate_release_readiness(
    metrics: dict[str, Any] | None,
    settings: object,
) -> ReleaseReadiness:
    values = dict(metrics or {})
    shadow_samples = max(int(values.get("shadow_samples", 0) or 0), 0)
    disagreements = max(int(values.get("disagreements", 0) or 0), 0)
    unsafe_disagreements = max(
        int(
            values.get(
                "unsafe_disagreements",
                disagreements,
            )
            or 0
        ),
        0,
    )
    revalidation_attempts = max(
        int(values.get("revalidation_attempts", 0) or 0),
        0,
    )
    revalidation_failures = max(
        int(values.get("revalidation_failures", 0) or 0),
        0,
    )
    disagreement_rate = (
        disagreements / shadow_samples if shadow_samples else 0.0
    )
    unsafe_disagreement_rate = (
        unsafe_disagreements / shadow_samples if shadow_samples else 0.0
    )
    revalidation_failure_rate = (
        revalidation_failures / revalidation_attempts
        if revalidation_attempts
        else 0.0
    )
    thresholds = {
        "min_shadow_samples": max(
            int(getattr(settings, "min_shadow_samples", 100) or 100),
            1,
        ),
        "min_demo_orders": max(
            int(getattr(settings, "min_demo_orders", 20) or 20),
            1,
        ),
        "min_canary_orders": max(
            int(getattr(settings, "min_canary_orders", 5) or 5),
            1,
        ),
        "max_disagreement_rate": _finite_float(
            getattr(settings, "max_disagreement_rate", 0.1),
            0.1,
        ),
        "max_revalidation_failure_rate": _finite_float(
            getattr(settings, "max_revalidation_failure_rate", 0.05),
            0.05,
        ),
        "max_performance_degradation_pct": _finite_float(
            getattr(settings, "max_performance_degradation_pct", 15.0),
            15.0,
        ),
    }
    normalized_metrics = {
        **values,
        "shadow_samples": shadow_samples,
        "disagreements": disagreements,
        "disagreement_rate": round(disagreement_rate, 6),
        "unsafe_disagreements": unsafe_disagreements,
        "unsafe_disagreement_rate": round(
            unsafe_disagreement_rate,
            6,
        ),
        "revalidation_attempts": revalidation_attempts,
        "revalidation_failures": revalidation_failures,
        "revalidation_failure_rate": round(
            revalidation_failure_rate,
            6,
        ),
    }
    blocks: list[str] = []
    if shadow_samples < thresholds["min_shadow_samples"]:
        blocks.append("SHADOW_SAMPLE_INSUFFICIENT")
    if int(values.get("demo_orders", 0) or 0) < thresholds["min_demo_orders"]:
        blocks.append("DEMO_ORDER_SAMPLE_INSUFFICIENT")
    if (
        int(values.get("canary_orders", 0) or 0)
        < thresholds["min_canary_orders"]
    ):
        blocks.append("CANARY_ORDER_SAMPLE_INSUFFICIENT")
    if unsafe_disagreement_rate > thresholds["max_disagreement_rate"]:
        blocks.append("DISAGREEMENT_RATE_EXCEEDED")
    if int(values.get("side_mismatches", 0) or 0) > 0:
        blocks.append("SIDE_MISMATCH_DETECTED")
    if int(values.get("premature_orders", 0) or 0) > 0:
        blocks.append("PREMATURE_ORDER_DETECTED")
    if int(values.get("portfolio_violations", 0) or 0) > 0:
        blocks.append("PORTFOLIO_VIOLATION_DETECTED")
    if (
        revalidation_failure_rate
        > thresholds["max_revalidation_failure_rate"]
    ):
        blocks.append("REVALIDATION_FAILURE_RATE_EXCEEDED")
    for metric_name, block_code in (
        ("oos_degradation_pct", "OOS_PERFORMANCE_DEGRADED"),
        ("demo_degradation_pct", "DEMO_PERFORMANCE_DEGRADED"),
    ):
        if _finite_float(values.get(metric_name), 0.0) > thresholds[
            "max_performance_degradation_pct"
        ]:
            blocks.append(block_code)
    if values.get("oos_evidence_recorded") is not True:
        blocks.append("OOS_EVIDENCE_MISSING")
    if values.get("demo_evidence_recorded") is not True:
        blocks.append("DEMO_EVIDENCE_MISSING")
    if values.get("rollback_tested") is not True:
        blocks.append("ROLLBACK_NOT_VERIFIED")
    return ReleaseReadiness(
        ready=not blocks,
        block_codes=tuple(dict.fromkeys(blocks)),
        metrics=normalized_metrics,
        thresholds=thresholds,
    )


def evaluate_canary_readiness(
    metrics: dict[str, Any] | None,
    settings: object,
) -> ReleaseReadiness:
    """Use all release gates except the evidence produced by canary itself."""

    release = evaluate_release_readiness(metrics, settings)
    blocks = tuple(
        code
        for code in release.block_codes
        if code != "CANARY_ORDER_SAMPLE_INSUFFICIENT"
    )
    return ReleaseReadiness(
        ready=not blocks,
        block_codes=blocks,
        metrics=release.metrics,
        thresholds=release.thresholds,
    )


def _normalize_symbol(symbol: object) -> str:
    return "".join(
        character
        for character in str(symbol or "").upper()
        if character.isalnum()
    )


def _legacy_scenario(
    row: dict[str, Any],
    side: str,
    *,
    fallback_side: str = "",
) -> dict[str, Any] | None:
    analysis = (
        row.get("analysis_result")
        if isinstance(row.get("analysis_result"), dict)
        else {}
    )
    scenarios = (
        analysis.get("scenarios")
        if isinstance(analysis.get("scenarios"), list)
        else []
    )
    for target_side in (side, fallback_side):
        if target_side not in {"buy", "sell"}:
            continue
        for scenario in scenarios:
            if (
                isinstance(scenario, dict)
                and scenario.get("type") == target_side
                and scenario.get("entry_zone_source") != "fallback"
            ):
                return scenario
    return None


def _finite_float(value: object, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if number == number and abs(number) != float("inf") else default
