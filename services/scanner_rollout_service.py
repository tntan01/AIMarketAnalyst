"""Persistent Phase-8 rollout evidence and release-readiness reporting."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from config.paths import app_data_dir
from core.scanner_rollout import (
    ROLLOUT_CANARY,
    build_scorer_performance,
    evaluate_canary_readiness,
    evaluate_release_readiness,
    run_rollback_drill,
)
from services.storage_service import JsonStorage


ROLLOUT_METRICS_VERSION = "phase8-smc-rollout-metrics-v2"


class ScannerRolloutMetricsService:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (
            app_data_dir() / "rollout" / "scanner-rollout-metrics.json"
        )
        self.storage = JsonStorage(self.path)
        self._lock = RLock()

    def load(self) -> dict[str, Any]:
        payload = self.storage.load(default={})
        return dict(payload) if isinstance(payload, dict) else {}

    def record_scan(
        self,
        *,
        scan_id: str,
        shadow_report: dict[str, Any],
        auto_trade_results: dict[str, Any],
        rollout_policy: dict[str, Any],
        closed_trades: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            metrics = self._normalized(self.load())
            metrics["scans"] += 1
            metrics["shadow_samples"] += int(
                shadow_report.get("samples", 0) or 0
            )
            metrics["disagreements"] += int(
                shadow_report.get("disagreements", 0) or 0
            )
            metrics["side_mismatches"] += int(
                shadow_report.get("side_mismatches", 0) or 0
            )
            for metric_name in (
                "false_ready_removed",
                "new_trade_candidates",
                "unsafe_disagreements",
                "smc_direction_changes",
                "smc_zone_changes",
                "smc_score_delta_samples",
                "smc_no_zone_sides",
                "smc_side_samples",
                "data_unavailable",
                "analysis_errors",
                "analysis_latency_samples",
            ):
                metrics[metric_name] += int(
                    shadow_report.get(metric_name, 0) or 0
                )
            metrics["smc_score_delta_abs_sum"] += float(
                shadow_report.get("smc_score_delta_abs_sum", 0.0) or 0.0
            )
            metrics["analysis_latency_ms_total"] += float(
                shadow_report.get("analysis_latency_ms_total", 0.0) or 0.0
            )
            metrics["analysis_latency_ms_max"] = max(
                float(metrics["analysis_latency_ms_max"]),
                float(
                    shadow_report.get(
                        "analysis_latency_ms_max",
                        0.0,
                    )
                    or 0.0
                ),
            )
            orders = (
                auto_trade_results.get("orders", [])
                if isinstance(auto_trade_results, dict)
                else []
            )
            revalidation_orders = [
                order
                for order in orders
                if isinstance(order, dict)
                and isinstance(order.get("revalidation"), dict)
            ]
            metrics["revalidation_attempts"] += len(revalidation_orders)
            metrics["revalidation_failures"] += sum(
                1
                for order in revalidation_orders
                if order["revalidation"].get("allowed") is not True
            )
            if rollout_policy.get("account_is_demo") is True:
                metrics["demo_orders"] += int(
                    auto_trade_results.get("opened", 0) or 0
                )
            if rollout_policy.get("stage") == ROLLOUT_CANARY:
                metrics["canary_orders"] += int(
                    auto_trade_results.get("opened", 0) or 0
                )
            metrics["premature_orders"] += sum(
                1
                for order in orders
                if isinstance(order, dict)
                and order.get("success") is True
                and (
                    not isinstance(order.get("revalidation"), dict)
                    or order["revalidation"].get("allowed") is not True
                )
            )
            metrics["portfolio_violations"] += sum(
                1
                for order in orders
                if isinstance(order, dict)
                and order.get("success") is True
                and isinstance(order.get("portfolio_guard"), dict)
                and order["portfolio_guard"].get("allowed") is not True
            )
            if (
                rollout_policy.get("kill_switch") is True
                and int(
                    auto_trade_results.get("rollout_blocked", 0) or 0
                ) > 0
            ):
                metrics["rollback_tested"] = True
            metrics["last_scan_id"] = str(scan_id or "")
            metrics["last_stage"] = str(
                rollout_policy.get("stage", "") or ""
            )
            if closed_trades is not None:
                metrics["scorer_performance"] = build_scorer_performance(
                    closed_trades
                )
            metrics["smc_score_delta_abs_average"] = round(
                metrics["smc_score_delta_abs_sum"]
                / metrics["smc_score_delta_samples"]
                if metrics["smc_score_delta_samples"]
                else 0.0,
                6,
            )
            metrics["smc_no_zone_rate"] = round(
                metrics["smc_no_zone_sides"]
                / metrics["smc_side_samples"]
                if metrics["smc_side_samples"]
                else 0.0,
                6,
            )
            metrics["analysis_latency_ms_average"] = round(
                metrics["analysis_latency_ms_total"]
                / metrics["analysis_latency_samples"]
                if metrics["analysis_latency_samples"]
                else 0.0,
                3,
            )
            metrics["updated_at"] = datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            )
            self.storage.save(metrics)
            return metrics

    def update_release_evidence(
        self,
        *,
        oos_degradation_pct: float | None = None,
        demo_degradation_pct: float | None = None,
        rollback_tested: bool | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            metrics = self._normalized(self.load())
            if oos_degradation_pct is not None:
                metrics["oos_degradation_pct"] = float(
                    oos_degradation_pct
                )
                metrics["oos_evidence_recorded"] = True
            if demo_degradation_pct is not None:
                metrics["demo_degradation_pct"] = float(
                    demo_degradation_pct
                )
                metrics["demo_evidence_recorded"] = True
            if rollback_tested is not None:
                metrics["rollback_tested"] = bool(rollback_tested)
            metrics["updated_at"] = datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            )
            self.storage.save(metrics)
            return metrics

    def perform_rollback_drill(self) -> dict[str, Any]:
        """Run a broker-free rollback drill and persist only a passing result."""

        report = run_rollback_drill()
        with self._lock:
            metrics = self._normalized(self.load())
            metrics["rollback_tested"] = report.get("passed") is True
            metrics["rollback_drill"] = dict(report)
            metrics["rollback_drill_at"] = datetime.now(
                timezone.utc
            ).isoformat(timespec="seconds")
            metrics["updated_at"] = metrics["rollback_drill_at"]
            self.storage.save(metrics)
        return report

    def readiness(self, rollout_settings: object) -> dict[str, Any]:
        return evaluate_release_readiness(
            self._normalized(self.load()),
            rollout_settings,
        ).to_dict()

    def canary_readiness(
        self,
        rollout_settings: object,
    ) -> dict[str, Any]:
        return evaluate_canary_readiness(
            self._normalized(self.load()),
            rollout_settings,
        ).to_dict()

    @staticmethod
    def _normalized(payload: dict[str, Any]) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "metrics_version": ROLLOUT_METRICS_VERSION,
            "scans": 0,
            "shadow_samples": 0,
            "disagreements": 0,
            "side_mismatches": 0,
            "false_ready_removed": 0,
            "new_trade_candidates": 0,
            "unsafe_disagreements": 0,
            "smc_direction_changes": 0,
            "smc_zone_changes": 0,
            "smc_score_delta_abs_sum": 0.0,
            "smc_score_delta_samples": 0,
            "smc_score_delta_abs_average": 0.0,
            "smc_no_zone_sides": 0,
            "smc_side_samples": 0,
            "smc_no_zone_rate": 0.0,
            "data_unavailable": 0,
            "analysis_errors": 0,
            "analysis_latency_ms_total": 0.0,
            "analysis_latency_samples": 0,
            "analysis_latency_ms_average": 0.0,
            "analysis_latency_ms_max": 0.0,
            "scorer_performance": {},
            "revalidation_attempts": 0,
            "revalidation_failures": 0,
            "demo_orders": 0,
            "canary_orders": 0,
            "premature_orders": 0,
            "portfolio_violations": 0,
            "oos_degradation_pct": 0.0,
            "demo_degradation_pct": 0.0,
            "oos_evidence_recorded": False,
            "demo_evidence_recorded": False,
            "rollback_tested": False,
            "rollback_drill": {},
            "rollback_drill_at": "",
            "last_scan_id": "",
            "last_stage": "",
            "updated_at": "",
        }
        if (
            payload
            and payload.get("metrics_version")
            != ROLLOUT_METRICS_VERSION
        ):
            defaults["legacy_metrics"] = dict(payload)
            legacy_drill = payload.get("rollback_drill")
            if (
                isinstance(legacy_drill, dict)
                and legacy_drill.get("passed") is True
            ):
                defaults["rollback_tested"] = True
                defaults["rollback_drill"] = dict(legacy_drill)
                defaults["rollback_drill_at"] = str(
                    payload.get("rollback_drill_at", "") or ""
                )
            return defaults
        defaults.update(payload)
        return defaults


scanner_rollout_metrics = ScannerRolloutMetricsService()
