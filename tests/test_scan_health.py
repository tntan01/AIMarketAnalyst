"""Scan health report + persistent scan-health counters (rollout-free).

Rebuilt from ``tests/test_smc_phase8_rollout.py`` after the Phase-8 rollout
machinery was removed (2026-08-15, fully live). The health metrics themselves
never depended on any rollout logic: SMC no-zone rate, data availability,
analysis latency, and closed-trade expectancy per scorer version.
"""

from __future__ import annotations

from core.scan_health import (
    SCAN_HEALTH_VERSION,
    build_scan_health_report,
    build_scorer_performance,
)
from services.scan_health_service import (
    SCAN_HEALTH_METRICS_VERSION,
    ScanHealthService,
)


def test_scan_health_report_collects_health_metrics():
    report = build_scan_health_report(
        [{
            "symbol": "EUR/USD",
            "candidate_status": "DATA_UNAVAILABLE",
            "selected_side": "buy",
            "analysis_error": True,
            "analysis_latency_ms": 12.5,
            "analysis_result": {
                "smc_scoring": {
                    "sides": {"buy": {}, "sell": {}},
                },
                "scenarios": [],
            },
            "scanner_candidate_decision": {
                "auto_trade_candidate": False,
                "strategy": {},
            },
        }],
    )

    assert report["scan_health_version"] == SCAN_HEALTH_VERSION
    assert report["data_unavailable"] == 1
    assert report["analysis_errors"] == 1
    assert report["analysis_latency_ms_total"] == 12.5
    assert report["analysis_latency_samples"] == 1
    assert report["analysis_latency_ms_max"] == 12.5
    assert report["smc_side_samples"] == 2
    assert report["smc_no_zone_sides"] == 2


def test_scan_health_report_counts_zoned_sides_as_healthy():
    report = build_scan_health_report(
        [{
            "symbol": "EUR/USD",
            "candidate_status": "READY_NOW",
            "analysis_latency_ms": 5.0,
            "analysis_result": {
                "smc_scoring": {
                    "sides": {
                        "buy": {"selected_zone_id": "zone-1"},
                        "sell": {},
                    },
                },
            },
        }],
    )

    assert report["smc_side_samples"] == 2
    assert report["smc_no_zone_sides"] == 1
    assert report["data_unavailable"] == 0
    assert report["analysis_errors"] == 0


def test_scan_health_report_handles_missing_rows():
    report = build_scan_health_report(None)
    assert report["scan_health_version"] == SCAN_HEALTH_VERSION
    assert report["smc_side_samples"] == 0
    assert report["analysis_latency_samples"] == 0
    assert report["analysis_latency_ms_max"] == 0.0


def test_scorer_performance_groups_by_scorer_version():
    performance = build_scorer_performance([
        {
            "smc_scorer_version": "smc-v1",
            "result_r": 1.0,
            "closed_at": "2026-01-01",
        },
        {
            "smc_scorer_version": "smc-v2",
            "result_r": -1.0,
            "closed_at": "2026-01-01",
        },
        {
            "smc_scorer_version": "smc-v2",
            "result_r": 2.0,
            "closed_at": "2026-01-02",
        },
    ])

    assert performance["smc-v1"]["expectancy_r"] == 1.0
    assert performance["smc-v2"]["trades"] == 2
    assert performance["smc-v2"]["expectancy_r"] == 0.5
    assert performance["smc-v2"]["max_drawdown_r"] == 1.0


def test_record_scan_accumulates_health_counters(tmp_path):
    service = ScanHealthService(tmp_path / "scan-health.json")
    scan_health = build_scan_health_report(
        [{
            "candidate_status": "DATA_UNAVAILABLE",
            "analysis_error": True,
            "analysis_latency_ms": 10.0,
            "analysis_result": {
                "smc_scoring": {"sides": {"buy": {}, "sell": {}}},
            },
        }],
    )

    metrics = service.record_scan(
        scan_id="scan-1",
        scan_health=scan_health,
        auto_trade_results={"orders": []},
    )

    assert metrics["metrics_version"] == SCAN_HEALTH_METRICS_VERSION
    assert metrics["scans"] == 1
    assert metrics["data_unavailable"] == 1
    assert metrics["analysis_errors"] == 1
    assert metrics["smc_side_samples"] == 2
    assert metrics["smc_no_zone_rate"] == 1.0
    assert metrics["analysis_latency_ms_average"] == 10.0
    assert metrics["last_scan_id"] == "scan-1"
    assert metrics["updated_at"]

    # A second scan accumulates.
    metrics = service.record_scan(
        scan_id="scan-2",
        scan_health=scan_health,
        auto_trade_results={"orders": []},
    )
    assert metrics["scans"] == 2
    assert metrics["data_unavailable"] == 2
    assert metrics["last_scan_id"] == "scan-2"


def test_record_scan_tracks_revalidation_and_guard_violations(tmp_path):
    service = ScanHealthService(tmp_path / "scan-health.json")

    metrics = service.record_scan(
        scan_id="scan-1",
        scan_health={},
        auto_trade_results={
            "orders": [
                {
                    "success": True,
                    "revalidation": {"allowed": True},
                },
                {
                    # An order that succeeded WITHOUT an allowed revalidation
                    # is a premature order and a revalidation failure.
                    "success": True,
                    "revalidation": {"allowed": False},
                },
                {
                    "success": True,
                    "revalidation": {"allowed": True},
                    "portfolio_guard": {"allowed": False},
                },
            ],
        },
    )

    assert metrics["revalidation_attempts"] == 3
    assert metrics["revalidation_failures"] == 1
    assert metrics["premature_orders"] == 1
    assert metrics["portfolio_violations"] == 1


def test_record_scan_updates_scorer_performance_from_closed_trades(tmp_path):
    service = ScanHealthService(tmp_path / "scan-health.json")

    metrics = service.record_scan(
        scan_id="scan-1",
        scan_health={},
        auto_trade_results={"orders": []},
        closed_trades=[
            {
                "smc_scorer_version": "smc-v2",
                "result_r": 2.0,
                "closed_at": "2026-01-01",
            },
        ],
    )

    assert metrics["scorer_performance"]["smc-v2"]["trades"] == 1
    assert metrics["scorer_performance"]["smc-v2"]["expectancy_r"] == 2.0


def test_foreign_payload_is_archived_instead_of_mixed(tmp_path):
    # The old rollout metrics file (different version identity) must never be
    # mixed into scan-health counters: archive it, then start fresh.
    service = ScanHealthService(tmp_path / "scan-health.json")
    service.storage.save({
        "metrics_version": "phase8-smc-rollout-metrics-v4",
        "scans": 99,
        "demo_orders": 20,
        "rollback_tested": True,
    })

    metrics = service.record_scan(
        scan_id="scan-1",
        scan_health={},
        auto_trade_results={"orders": []},
    )

    assert metrics["metrics_version"] == SCAN_HEALTH_METRICS_VERSION
    assert metrics["scans"] == 1  # NOT 100
    assert "demo_orders" not in metrics
    assert metrics["legacy_metrics"]["scans"] == 99
