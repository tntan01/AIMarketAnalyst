"""Phase-8 SMC provenance, rollout metrics and rollback tests."""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3

from core.scanner import ScannerRequest, build_scanner_output
from core.scanner_rollout import (
    build_scorer_performance,
    build_shadow_report,
    run_rollback_drill,
)
from core.scoring_provenance import build_scoring_provenance
from core.system_backtest_engine import BacktestRequest, BacktestResult
from services.journal_converters import journal_entry_from_analysis
from services.journal_service import JournalService
from services.scanner_rollout_service import ScannerRolloutMetricsService
from services.scanner_rollout_service import ROLLOUT_METRICS_VERSION


def test_scoring_provenance_is_mode_independent_and_canonical():
    provenance = build_scoring_provenance()

    assert provenance["scanner_scorer_version"] == "scanner-v3"
    assert provenance["scanner_feature_version"] == "scanner-features-v3"
    assert provenance["smc_scorer_version"] == "smc-v2"
    assert provenance["smc_decision_source"] == "smc-v2"
    assert provenance["smc_scoring_mode"] == "v2"
    assert "smc-v1" not in provenance.values()


def test_scanner_and_backtest_outputs_expose_same_v2_identity():
    request = ScannerRequest(
        symbols=["EUR/USD"],
        account_balance=10_000,
        risk_percent=1.0,
        timezone_name="UTC",
    )
    scanner_output = build_scanner_output([], request, 0)
    backtest = BacktestResult(
        request=BacktestRequest(
            symbol="EUR/USD",
            broker_symbol="EURUSD",
            start=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end=datetime(2025, 2, 1, tzinfo=timezone.utc),
            initial_balance=10_000,
            risk_percent=1.0,
        ),
        summary={},
        trades=[],
        equity_curve=[],
        breakdowns={},
        skipped_setups=[],
        diagnostics={},
    ).to_dict()

    assert scanner_output["scoring_provenance"][
        "smc_scorer_version"
    ] == "smc-v2"
    assert backtest["scoring_contract"]["smc_scorer_version"] == "smc-v2"
    assert backtest["scoring_contract"]["smc_scoring_mode"] == "v2"
    assert backtest["backtest_contract"]["purpose"] == "RESEARCH"
    assert backtest["backtest_contract"]["execution_parity"] is False
    assert backtest["backtest_contract"]["validation_eligible"] is False


def test_journal_persists_scoring_provenance_columns(tmp_path):
    db_path = tmp_path / "journal.db"
    service = JournalService(db_path=db_path)
    provenance = build_scoring_provenance()
    entry = journal_entry_from_analysis(
        {
            "symbol": "EUR/USD",
            "scoring_provenance": provenance,
        },
        mode="scanner_detail",
    )
    entry_id = service.create(entry)
    loaded = service.get_entry(entry_id)

    assert loaded is not None
    assert loaded.scanner_scorer_version == "scanner-v3"
    assert loaded.scanner_feature_version == "scanner-features-v3"
    assert loaded.smc_scorer_version == "smc-v2"
    assert loaded.smc_scoring_mode == "v2"
    with sqlite3.connect(db_path) as connection:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(journal_entries)"
            ).fetchall()
        }
    assert {
        "scanner_scorer_version",
        "scanner_feature_version",
        "smc_scorer_version",
        "smc_scoring_mode",
    }.issubset(columns)


def test_shadow_report_collects_smc_operational_metrics():
    report = build_shadow_report(
        [{
            "symbol": "EUR/USD",
            "candidate_status": "DATA_UNAVAILABLE",
            "selected_side": "buy",
            "analysis_error": True,
            "analysis_latency_ms": 12.5,
            "analysis_result": {
                "smc_scoring": {
                    "comparison": {
                        "score_delta": {"buy": 3, "sell": -2},
                        "selected_zone_changed": {
                            "buy": True,
                            "sell": False,
                        },
                        "direction_changed": True,
                        "decision_changed": True,
                        "decision_input_changed": True,
                    },
                    "decision": {
                        "buy": {"selected_zone_id": "buy-zone"},
                        "sell": {"selected_zone_id": None},
                    },
                },
                "scenarios": [],
            },
            "legacy_candidate_input": {
                "scanner_action": "stand_aside",
                "trade_permission": "blocked",
                "best_side": "buy",
            },
            "scanner_candidate_decision": {
                "auto_trade_candidate": False,
                "strategy": {},
            },
        }],
        enabled=True,
    )

    assert report["smc_direction_changes"] == 1
    assert report["smc_zone_changes"] == 1
    assert report["smc_score_delta_abs_sum"] == 5
    assert report["smc_score_delta_samples"] == 2
    assert report["smc_no_zone_sides"] == 1
    assert report["smc_side_samples"] == 2
    assert report["data_unavailable"] == 1
    assert report["analysis_errors"] == 1
    assert report["analysis_latency_ms_total"] == 12.5


def test_scorer_performance_separates_v1_and_v2():
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


def test_rollback_drill_blocks_orders_and_drops_v1_rollback(tmp_path):
    direct = run_rollback_drill()
    service = ScannerRolloutMetricsService(tmp_path / "metrics.json")
    persisted = service.perform_rollback_drill()

    assert direct["passed"] is True
    assert direct["checks"]["kill_switch_blocks_order"] is True
    assert persisted["passed"] is True
    metrics = service.load()
    assert metrics["rollback_tested"] is True
    assert metrics["rollback_drill"]["passed"] is True
    assert metrics["metrics_version"] == ROLLOUT_METRICS_VERSION


def test_old_rollout_metrics_are_archived_instead_of_mixed(tmp_path):
    service = ScannerRolloutMetricsService(tmp_path / "metrics.json")
    service.storage.save({
        "shadow_samples": 1456,
        "disagreements": 1456,
        "rollback_tested": False,
    })

    service.perform_rollback_drill()
    migrated = service.load()

    assert migrated["metrics_version"] == ROLLOUT_METRICS_VERSION
    assert migrated["shadow_samples"] == 0
    assert migrated["disagreements"] == 0
    assert migrated["legacy_metrics"]["shadow_samples"] == 1456
    assert migrated["rollback_tested"] is True
