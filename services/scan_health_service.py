"""Persistent scan health counters (rollout-independent).

Replaces the removed Phase-8 rollout metrics service (removed 2026-08-15,
fully live). Only operational health counters survive here — no release/canary
readiness semantics, no demo/canary order evidence. Stored at
``app_data_dir()/scan_health/scan-health.json``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from config.paths import app_data_dir
from core.scan_health import build_scorer_performance
from services.storage_service import JsonStorage


SCAN_HEALTH_METRICS_VERSION = "scan-health-metrics-v1"


class ScanHealthService:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (
            app_data_dir() / "scan_health" / "scan-health.json"
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
        scan_health: dict[str, Any],
        auto_trade_results: dict[str, Any],
        closed_trades: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            metrics = self._normalized(self.load())
            metrics["scans"] += 1
            for metric_name in (
                "smc_no_zone_sides",
                "smc_side_samples",
                "data_unavailable",
                "analysis_errors",
                "analysis_latency_samples",
            ):
                metrics[metric_name] += int(
                    scan_health.get(metric_name, 0) or 0
                )
            metrics["analysis_latency_ms_total"] += float(
                scan_health.get("analysis_latency_ms_total", 0.0) or 0.0
            )
            metrics["analysis_latency_ms_max"] = max(
                float(metrics["analysis_latency_ms_max"]),
                float(
                    scan_health.get(
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
            metrics["last_scan_id"] = str(scan_id or "")
            if closed_trades is not None:
                metrics["scorer_performance"] = build_scorer_performance(
                    closed_trades
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

    @staticmethod
    def _normalized(payload: dict[str, Any]) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "metrics_version": SCAN_HEALTH_METRICS_VERSION,
            "scans": 0,
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
            "premature_orders": 0,
            "portfolio_violations": 0,
            "last_scan_id": "",
            "updated_at": "",
        }
        if (
            payload
            and payload.get("metrics_version")
            != SCAN_HEALTH_METRICS_VERSION
        ):
            # Foreign/legacy payload (e.g. the old rollout metrics file was
            # pointed here): keep it for audit but start fresh counters.
            defaults["legacy_metrics"] = dict(payload)
            return defaults
        defaults.update(payload)
        return defaults


scan_health_service = ScanHealthService()
