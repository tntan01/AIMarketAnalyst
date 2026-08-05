"""Phase-8 rollout guard, scan health metrics and release-readiness contracts.

The V1/V2 shadow decision comparison was removed once the SMC migration
finished and only one runtime remained; independent scan health metrics
(no-zone rate, latency, data availability) are still collected here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any


SCANNER_ROLLOUT_VERSION = "phase8-rollout-v2"
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
) -> dict[str, Any]:
    """Collect independent scan health metrics.

    The V1/V2 decision comparison was removed with the SMC migration; this
    report keeps only the health metrics that do not depend on any legacy
    logic: SMC no-zone rate, data availability and analysis latency.
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
        "rollout_version": SCANNER_ROLLOUT_VERSION,
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


def run_rollback_drill() -> dict[str, Any]:
    """Exercise the safe rollback path without touching a broker.

    There is no v1 scorer to restore any more; rollback is the kill switch and
    the Scanner SHADOW order-suppression stage.
    """

    class _Settings:
        stage = ROLLOUT_PRODUCTION
        kill_switch = True
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


def evaluate_release_readiness(
    metrics: dict[str, Any] | None,
    settings: object,
) -> ReleaseReadiness:
    values = dict(metrics or {})
    revalidation_attempts = max(
        int(values.get("revalidation_attempts", 0) or 0),
        0,
    )
    revalidation_failures = max(
        int(values.get("revalidation_failures", 0) or 0),
        0,
    )
    revalidation_failure_rate = (
        revalidation_failures / revalidation_attempts
        if revalidation_attempts
        else 0.0
    )
    thresholds = {
        "min_demo_orders": max(
            int(getattr(settings, "min_demo_orders", 20) or 20),
            1,
        ),
        "min_canary_orders": max(
            int(getattr(settings, "min_canary_orders", 5) or 5),
            1,
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
        "revalidation_attempts": revalidation_attempts,
        "revalidation_failures": revalidation_failures,
        "revalidation_failure_rate": round(
            revalidation_failure_rate,
            6,
        ),
    }
    blocks: list[str] = []
    if int(values.get("demo_orders", 0) or 0) < thresholds["min_demo_orders"]:
        blocks.append("DEMO_ORDER_SAMPLE_INSUFFICIENT")
    if (
        int(values.get("canary_orders", 0) or 0)
        < thresholds["min_canary_orders"]
    ):
        blocks.append("CANARY_ORDER_SAMPLE_INSUFFICIENT")
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


def _finite_float(value: object, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if number == number and abs(number) != float("inf") else default
