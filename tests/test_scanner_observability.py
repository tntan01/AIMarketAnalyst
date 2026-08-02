"""Phase-7 provenance, structured event and replay tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from unittest.mock import patch

from controllers.scanner_controller import ScannerController
from core.backtest_contract import validation_engine_contract
from core.backtest_config_validation import (
    BACKTEST_CONFIG_SCHEMA_VERSION,
    BACKTEST_VALIDATION_VERSION,
    validation_fingerprint,
)
from core.scanner_candidate_engine import (
    build_candidate_order_payload,
    evaluate_scanner_candidate,
)
from core.scanner_models import SCANNER_FEATURE_VERSION, SCANNER_SCORER_VERSION
from core.scanner_observability import (
    SCANNER_OBSERVABILITY_VERSION,
    attach_row_observability,
    build_analysis_document,
    create_scan_context,
    input_timestamps_from_candles,
    replay_candidate_decision,
    stable_hash,
)
from core.scanner_ranking_engine import rank_scanner_rows
from core.scanner_rollout import build_shadow_report
from services.observability_service import StructuredObservabilityService
from services.storage_service import JsonStorage
from services.scanner_persistence_service import ScannerPersistenceService
from tests.phase7_helpers import ready_release_report


def _scenario(side: str) -> dict:
    return {
        "type": side,
        "entry_zone": [1.0850, 1.0875],
        "entry_status": "confirmed_entry",
        "ready_to_trade": True,
        "m15_quality": "strict",
        "stop_loss": 1.0820 if side == "buy" else 1.0910,
        "take_profit": [1.0940] if side == "buy" else [1.0800],
        "expected_effective_rr": 2.0 if side == "buy" else 1.6,
    }


def _row() -> dict:
    return {
        "symbol": "EUR/USD",
        "broker_symbol": "EURUSD",
        "best_side": "buy",
        "buy_score": 78,
        "sell_score": 61,
        "best_score": 78,
        "setup_score": 72,
        "final_score": 72,
        "min_score": 65,
        "min_rr": 1.3,
        "market_regime": "range",
        "scanner_action": "ready",
        "scanner_decision": "READY_TO_TRADE",
        "scanner_group": "ready_now",
        "trade_permission": "allowed",
        "price_vs_zone": "in_zone",
        "direction_bias": {
            "best_side": "buy",
            "score_gap": 17,
            "is_clear_bias": True,
            "min_gap": 10,
        },
        "score_gap": 17,
        "analysis_result": {
            "timestamp": "2026-07-24T08:00:00+00:00",
            "side_scores": {
                "buy": {"signal_score": 78, "setup_score": 72},
                "sell": {"signal_score": 61, "setup_score": 64},
            },
            "scenario_scores": {
                "buy": {"signal_score": 78},
                "sell": {"signal_score": 61},
            },
            "decision_engine": {"decision": "READY_TO_TRADE"},
            "trade_gate": {"allowed": True, "block_codes": []},
            "data_quality": {
                "spread_status": "normal",
                "terminal_connected": True,
                "broker_logged_in": True,
                "macro_freshness": {"confidence_multiplier": 1.0},
            },
            "technical": {"price": 1.0860},
            "scenarios": [_scenario("buy"), _scenario("sell")],
            "final_score_detail": {
                "final_score": 72,
                "weighted_components": {"signal": 40},
            },
        },
        "input_timestamps": {
            "D1": "2026-07-23T00:00:00+00:00",
            "H4": "2026-07-24T04:00:00+00:00",
            "H1": "2026-07-24T07:00:00+00:00",
            "M15": "2026-07-24T07:45:00+00:00",
        },
    }


def _validated_config() -> dict:
    engine_contract = validation_engine_contract()
    config = {
        "schema_version": BACKTEST_CONFIG_SCHEMA_VERSION,
        "validation_version": BACKTEST_VALIDATION_VERSION,
        "engine_contract_version": engine_contract["contract_version"],
        "engine_version": engine_contract["engine_version"],
        "purpose": engine_contract["purpose"],
        "execution_parity": engine_contract["execution_parity"],
        "data_manifest_version": engine_contract[
            "data_manifest_version"
        ],
        "point_in_time_data": engine_contract["point_in_time_data"],
        "dataset_hash": "a" * 64,
        "data_quality_status": "OK",
        "execution_policy_version": engine_contract[
            "execution_policy_version"
        ],
        "entry_fill_model": engine_contract["entry_fill_model"],
        "exit_evaluation_model": engine_contract[
            "exit_evaluation_model"
        ],
        "same_bar_ambiguity_policy": engine_contract[
            "same_bar_ambiguity_policy"
        ],
        "execution_timeframe": engine_contract["execution_timeframe"],
        "synthetic_trades_allowed": engine_contract[
            "synthetic_trades_allowed"
        ],
        "execution_mode": engine_contract["execution_mode"],
        "execution_model_version": engine_contract[
            "execution_model_version"
        ],
        "cost_model_version": engine_contract["cost_model_version"],
        "quote_conversion_model_version": engine_contract[
            "quote_conversion_model_version"
        ],
        "cost_model_fingerprint": engine_contract[
            "cost_model_fingerprint"
        ],
        "quote_conversion_fingerprint": engine_contract[
            "quote_conversion_fingerprint"
        ],
        "candidate_ledger_version": engine_contract["candidate_ledger_version"],
        "candidate_replay_version": engine_contract["candidate_replay_version"],
        "frozen_strategy_version": engine_contract["frozen_strategy_version"],
        "frozen_strategy_applied": engine_contract["frozen_strategy_applied"],
        "oos_replay": engine_contract["oos_replay"],
        "provenance_version": "backtest-provenance-v1",
        "code_revision": "b" * 40,
        "request_fingerprint": "c" * 64,
        "execution_fingerprint": "d" * 64,
        "provenance_fingerprint": "e" * 64,
        "config_id": "EURUSD-range-buy-v3",
        "status": "VALIDATED",
        "symbol": "EUR/USD",
        "allowed_regimes": ["range"],
        "regime": "range",
        "side": "buy",
        "score_metric": "setup_score",
        "min_score": 65,
        "min_rr": 1.5,
        "scorer_version": SCANNER_SCORER_VERSION,
        "feature_version": SCANNER_FEATURE_VERSION,
        "smc_scorer_version": "smc-v2",
        "trained_from": "2025-01-01T00:00:00+00:00",
        "trained_to": "2025-06-30T00:00:00+00:00",
        "validated_from": "2025-07-01T00:00:00+00:00",
        "validated_to": "2025-12-31T00:00:00+00:00",
        "in_sample_trades": 120,
        "out_of_sample_trades": 46,
        "oos_expectancy_r": 0.24,
        "oos_profit_factor": 1.42,
        "oos_max_drawdown_r": 5.8,
        "expectancy_ci_low": 0.05,
        "expectancy_ci_high": 0.43,
        "statistics_version": "backtest-statistics-v1",
        "probability_positive_edge_pct": 97.5,
        "one_sided_p_value": 0.025,
        "minimum_required_trades": 8,
        "statistical_power_passed": True,
        "walk_forward_windows": 3,
        "walk_forward_verdict": "ROBUST",
        "validated_at": "2026-07-24T00:00:00+00:00",
        "expires_at": "2027-07-24T00:00:00+00:00",
        "release_report": ready_release_report(),
    }
    config["validation_fingerprint"] = validation_fingerprint(config)
    return config


def _observed_row(config: dict | None = None) -> tuple[dict, object]:
    row = _row()
    if config is not None:
        row["auto_trade_config"] = dict(config)
    decision = evaluate_scanner_candidate(
        row,
        config,
        now=datetime(2026, 7, 24, 8, tzinfo=timezone.utc),
    )
    row.update({
        "candidate_status": decision.status,
        "selected_side": decision.selected_side,
        "auto_trade_branch": decision.branch,
        "strategy_config_status": decision.strategy.config_status,
        "expected_effective_rr": decision.strategy.expected_effective_rr,
        "execution_ready": decision.execution_ready,
        "trade_allowed": decision.trade_allowed,
        "scanner_candidate_decision": decision.to_dict(),
    })
    row["candidate_order_payload"] = build_candidate_order_payload(
        row,
        decision,
    )
    ranked = rank_scanner_rows([row])[0]
    context = create_scan_context(
        {"trading": {"max_risk_percent": 2}, "ai": {"api_key": "secret-a"}},
        {
            "symbols": ["EUR/USD"],
            "feature_flags": {},
        },
        now=datetime(2026, 7, 24, 8, tzinfo=timezone.utc),
    )
    observed = attach_row_observability(
        ranked,
        context,
        portfolio_state={"available": True, "account_balance": 10_000},
    )
    return observed, context


def test_settings_hash_is_stable_and_never_depends_on_secret_value():
    first = stable_hash({
        "risk": 1,
        "api_key": "secret-a",
        "telegram_bot_token": "token-a",
    })
    second = stable_hash({
        "risk": 1,
        "api_key": "secret-b",
        "telegram_bot_token": "token-b",
    })
    changed = stable_hash({"risk": 2, "api_key": "secret-a"})

    assert first == second
    assert first != changed
    assert len(first) == 64


def test_scan_context_contains_all_runtime_versions_and_hashes():
    _row_value, context = _observed_row()
    payload = context.to_dict()

    assert payload["observability_version"] == SCANNER_OBSERVABILITY_VERSION
    assert payload["scan_id"].startswith("20260724T080000")
    assert payload["scanner_version"] == "scanner-runtime-v2"
    assert payload["scorer_version"] == "scanner-v3"
    assert payload["ranking_version"] == "phase6-ranking-v1"
    assert len(payload["settings_hash"]) == 64
    assert len(payload["request_hash"]) == 64


@dataclass
class _Candle:
    time: datetime


def test_new_telemetry_has_no_smc_mode_or_decision_source_keys():
    """Bước 18: telemetry mới chỉ có SMC canonical provenance.

    Event/context/payload mới không chứa smc_scoring_mode hay
    smc_decision_source; reader vẫn chịu được event lịch sử có field cũ.
    """
    from core.scoring_provenance import build_scoring_provenance

    provenance = build_scoring_provenance()
    assert "smc_scoring_mode" not in provenance
    assert "smc_decision_source" not in provenance

    _row_value, context = _observed_row()
    context_payload = context.to_dict()
    assert "smc_scoring_mode" not in context_payload
    assert "smc_scoring_mode" not in _row_value["observability"]
    assert "smc_scoring_mode" not in _row_value["candidate_order_payload"]
    assert "smc_scoring_mode" not in _row_value
    assert "smc_decision_source" not in _row_value["observability"]

    # Historical event có field cũ vẫn đọc được (reader không chọn nhánh v1).
    historical_context = create_scan_context(
        {"trading": {"max_risk_percent": 2}, "ai": {"api_key": "secret-a"}},
        {
            "symbols": ["EUR/USD"],
            "feature_flags": {},
            "smc_scoring_mode": "legacy",
        },
        now=datetime(2026, 7, 24, 8, tzinfo=timezone.utc),
    )
    assert historical_context.smc_scorer_version == "smc-v2"


def test_input_timestamps_capture_last_bar_per_timeframe():
    timestamps = input_timestamps_from_candles({
        "H1": [
            _Candle(datetime(2026, 7, 24, 6, tzinfo=timezone.utc)),
            _Candle(datetime(2026, 7, 24, 7, tzinfo=timezone.utc)),
        ],
        "M15": [],
    })

    assert timestamps == {"H1": "2026-07-24T07:00:00+00:00"}


def test_row_observability_contains_complete_decision_trace():
    row, context = _observed_row()
    trace = row["observability"]

    assert trace["scan_id"] == context.scan_id
    assert trace["selected_branch"] == "DEFAULT_RULES"
    assert trace["selected_side"] == "buy"
    assert trace["score_inputs"]["setup_score"] == 72
    assert trace["weighted_components"]["ranking"]["status"] == "READY_NOW"
    assert trace["gate_results"]["analysis_trade_gate"]["allowed"] is True
    assert trace["portfolio_state"]["account_balance"] == 10_000
    assert trace["final_candidate_decision"]["status"] == "READY_NOW"
    order = row["candidate_order_payload"]
    assert order["scan_id"] == context.scan_id
    assert order["row_id"] == row["row_id"]
    assert order["settings_hash"] == context.settings_hash
    assert order["scorer_version"] == "scanner-v3"


def test_analysis_document_replays_the_same_candidate_decision():
    row, context = _observed_row()
    document = build_analysis_document(row, context)

    replay = replay_candidate_decision(document)

    assert replay["replayable"] is True
    assert replay["match"] is True
    assert all(replay["comparisons"].values())


def test_analysis_document_replays_validated_backtest_branch():
    row, context = _observed_row(_validated_config())
    document = build_analysis_document(row, context)

    replay = replay_candidate_decision(document)

    assert document["candidate_decision"]["branch"] == "BACKTEST_VALIDATED"
    assert replay["replayed_decision"]["branch"] == "BACKTEST_VALIDATED"
    assert replay["match"] is True


def test_replay_detects_tampered_score_input():
    row, context = _observed_row()
    document = build_analysis_document(row, context)
    document["row_summary"]["setup_score"] = 10
    document["analysis_result"]["side_scores"]["buy"]["setup_score"] = 10

    replay = replay_candidate_decision(document)

    assert replay["replayable"] is True
    assert replay["match"] is False
    assert "REPLAY_DECISION_MISMATCH" in replay["reason_codes"]


def test_snapshot_splits_summary_and_full_symbol_analysis(tmp_path):
    row, context = _observed_row()
    result = {
        "scan_id": context.scan_id,
        "timestamp": context.started_at,
        "scan_context": context.to_dict(),
        "rows": [row],
        "summary": {"ready_now_count": 1},
    }
    controller = ScannerController.__new__(ScannerController)

    with patch(
        "controllers.scanner_controller.app_data_dir",
        return_value=tmp_path,
    ):
        summary_path = controller.save_snapshot(result)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    analysis_path = tmp_path / "scanner_analysis" / context.scan_id / "EURUSD.json.gz"
    analysis = JsonStorage(analysis_path).load()
    assert "analysis_result" not in summary["rows"][0]
    assert summary["rows"][0]["analysis_ref"] == str(analysis_path)
    assert summary["analysis_manifest"]["EUR/USD"] == str(analysis_path)
    assert analysis["analysis_result"]["technical"]["price"] == 1.086
    assert analysis["candidate_decision"]["status"] == "READY_NOW"


def test_summary_snapshot_avoids_full_analysis_for_routine_auto_scan(tmp_path):
    row, context = _observed_row()
    # A ready/allowed row is deliberately a material event and therefore must
    # persist full evidence.  This fixture models the non-actionable routine
    # scan that the summary mode contract is intended to cover.
    row["scanner_action"] = "stand_aside"
    row["trade_permission"] = "blocked"
    row["observability"] = {"large": ["x"] * 100}
    result = {
        "scan_id": context.scan_id,
        "timestamp": context.started_at,
        "scan_context": context.to_dict(),
        "rows": [row],
        "summary": {"ready_now_count": 0},
        "persistence_mode": "summary",
    }
    controller = ScannerController.__new__(ScannerController)
    ScannerPersistenceService(tmp_path).record("full")

    with patch("controllers.scanner_controller.app_data_dir", return_value=tmp_path):
        summary_path = controller.save_snapshot(result)

    summary = JsonStorage(summary_path).load()
    assert summary["persistence_mode"] == "summary"
    assert "analysis_manifest" not in summary
    assert summary["rows"][0]["analysis_ref"] == ""
    assert "observability" not in summary["rows"][0]
    assert not (tmp_path / "scanner_analysis" / context.scan_id).exists()


def test_structured_event_log_is_jsonl_and_redacts_secrets(tmp_path):
    path = tmp_path / "events.jsonl"
    service = StructuredObservabilityService(path)

    event = service.emit(
        "order_request",
        scan_id="scan-1",
        symbol="EUR/USD",
        payload={"api_key": "secret", "side": "buy"},
    )

    saved = json.loads(path.read_text(encoding="utf-8").strip())
    assert event["event_type"] == "ORDER_REQUEST"
    assert saved["payload"]["api_key"] == "<redacted>"
    assert saved["payload"]["side"] == "buy"
    assert saved["scan_id"] == "scan-1"


def test_structured_event_log_rotates_without_propagating_to_app_log(tmp_path):
    events_path = tmp_path / "events.jsonl"
    app_log_path = tmp_path / "app.log"
    root_logger = logging.getLogger()
    app_handler = logging.FileHandler(app_log_path, encoding="utf-8")
    root_logger.addHandler(app_handler)
    service = StructuredObservabilityService(
        events_path,
        max_bytes=300,
        backup_count=2,
    )

    try:
        for number in range(4):
            service.emit(
                "SCAN_STARTED",
                payload={"summary": "x" * 120, "number": number},
            )
    finally:
        root_logger.removeHandler(app_handler)
        app_handler.close()

    assert events_path.exists()
    assert events_path.with_name("events.jsonl.1").exists()
    assert events_path.with_name("events.jsonl.2").exists()
    assert app_log_path.read_text(encoding="utf-8") == ""


class _EventRecorder:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event_type: str, **kwargs) -> None:
        self.events.append({"event_type": event_type, **kwargs})


def test_candidate_events_cover_strategy_gate_and_v1_v2_disagreement():
    recorder = _EventRecorder()
    controller = ScannerController.__new__(ScannerController)
    controller.observability = recorder
    row = {
        "symbol": "EUR/USD",
        "legacy_candidate_status": "READY_NOW",
        "candidate_status": "BLOCKED",
        "selected_side": "buy",
        "auto_trade_reason_codes": ["SETUP_SCORE_BELOW_MINIMUM"],
        "scanner_candidate_decision": {
            "branch": "DEFAULT_RULES",
            "status": "BLOCKED",
            "strategy": {
                "eligible": False,
                "reason_codes": ["SETUP_SCORE_BELOW_MINIMUM"],
            },
            "execution": {
                "entry_ready": False,
                "trade_allowed": False,
                "reason_codes": ["ENTRY_NOT_READY"],
                "block_codes": ["ENTRY_NOT_READY"],
            },
        },
    }

    controller._emit_candidate_events(row, "scan-1")

    event_types = [event["event_type"] for event in recorder.events]
    assert event_types == [
        "STRATEGY_REJECTION",
        "GATE_REJECTION",
        "DECISION_DISAGREEMENT",
    ]
    assert all(event["scan_id"] == "scan-1" for event in recorder.events)
    assert all(event["symbol"] == "EUR/USD" for event in recorder.events)


def test_generic_shadow_comparison_feeds_candidate_not_smc_payload():
    """The SHADOW_DECISION_COMPARISON event sources the generic candidate
    comparison, never the SMC scorer shadow/comparison payload."""

    row = {
        "scan_id": "scan-1",
        "row_id": "row-1",
        "symbol": "EUR/USD",
        "legacy_candidate_status": "READY_NOW",
        "candidate_status": "BLOCKED",
        "best_side": "buy",
        "selected_side": "sell",
        "best_score": 75,
        "min_score": 65,
        "legacy_candidate_input": {
            "scanner_action": "ready",
            "scanner_group": "ready_now",
            "trade_permission": "allowed",
            "best_side": "buy",
            "best_score": 75,
            "expected_effective_rr": 2.0,
            "market_regime": "range",
        },
        "analysis_result": {
            "scenarios": [{"type": "buy", "entry_zone": [1.0, 1.1]}],
            "smc_scoring": {
                "policy": {"shadow_enabled": True, "effective_mode": "v2"},
                "shadow_status": "available",
                "comparison": {"best_side_changed": True},
            },
        },
        "scanner_candidate_decision": {
            "auto_trade_candidate": False,
            "reason_codes": ["SETUP_SCORE_BELOW_MINIMUM"],
            "strategy": {
                "eligible": False,
                "score_value": 50,
                "min_score": 65,
            },
        },
    }

    report = build_shadow_report([row], enabled=True, suppress_v2_orders=True)

    assert report["enabled"] is True
    comparison = report["comparisons"][0]
    assert comparison["disagreement"] is True
    # Generic candidate-engine comparison fields.
    assert set(comparison).issuperset(
        {"v1", "v2", "disagreement_codes", "v2_order_suppressed"}
    )
    assert comparison["v1"]["status"] == "READY_NOW"
    assert comparison["v2"]["status"] == "BLOCKED"
    # The comparison is NOT the SMC shadow payload; it only summarizes the
    # candidate decision and must never carry the SMC shadow router shape.
    for forbidden in (
        "shadow_status",
        "legacy_smc_quality",
        "v2_smc_quality",
        "active",
        "legacy",
        "comparison",
        "decision",
    ):
        assert forbidden not in comparison, forbidden
