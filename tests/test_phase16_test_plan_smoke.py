"""Phase 16.1 — smoke test: import all key modules built in Phase 1-15."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_import_signal_engine():
    import core.signal_engine
    assert hasattr(core.signal_engine, "score_scenario")
    assert hasattr(core.signal_engine, "calc_risk_condition")
    assert hasattr(core.signal_engine, "calculate_direction_bias")


def test_import_trade_gate_engine():
    import core.trade_gate_engine
    assert hasattr(core.trade_gate_engine, "check_trade_gates")


def test_import_account_guard():
    import core.account_guard
    assert hasattr(core.account_guard, "check_account_guard")


def test_import_entry_engine():
    import core.entry_engine
    assert hasattr(core.entry_engine, "evaluate_entry")


def test_import_final_score_engine():
    import core.final_score_engine
    assert hasattr(core.final_score_engine, "calculate_final_score")
    assert hasattr(core.final_score_engine, "calculate_final_score_from_payload")


def test_import_decision_engine():
    import core.decision_engine
    assert hasattr(core.decision_engine, "make_final_decision")
    assert hasattr(core.decision_engine, "calculate_decision_from_payload")


def test_import_scanner():
    import core.scanner
    assert hasattr(core.scanner, "scanner_row_from_analysis")
    assert hasattr(core.scanner, "sort_scanner_rows")
    assert hasattr(core.scanner, "scanner_summary")
    assert hasattr(core.scanner, "ai_targets")


def test_import_scanner_ranking_engine():
    import core.scanner_ranking_engine
    assert hasattr(core.scanner_ranking_engine, "calculate_opportunity_score")
    assert hasattr(core.scanner_ranking_engine, "classify_scanner_group")
    assert hasattr(core.scanner_ranking_engine, "enrich_scanner_row_with_ranking")


def test_import_trade_mistake_detector():
    import core.trade_mistake_detector
    assert hasattr(core.trade_mistake_detector, "detect_trade_mistakes")


def test_import_statistical_edge_engine():
    import core.statistical_edge_engine
    assert hasattr(core.statistical_edge_engine, "calculate_evidence_score")


def test_import_execution_quality_engine():
    import core.execution_quality_engine
    assert hasattr(core.execution_quality_engine, "calculate_execution_quality")


def test_import_reason_codes():
    import core.reason_codes
    assert hasattr(core.reason_codes, "codes_to_messages")
    assert hasattr(core.reason_codes, "TREND_D1_H4_ALIGNED")
    assert hasattr(core.reason_codes, "FINAL_SCORE_OK")
    assert hasattr(core.reason_codes, "DECISION_READY_TO_TRADE")
    assert hasattr(core.reason_codes, "SCANNER_RANKING_READY_NOW")


def test_import_risk_engine():
    import core.risk_engine
    assert hasattr(core.risk_engine, "AnalysisInput")
    assert hasattr(core.risk_engine, "calc_trade_permission")
