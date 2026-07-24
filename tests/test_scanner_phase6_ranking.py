"""Phase-6 canonical ranking and consumer-order tests."""

from __future__ import annotations

import inspect
import json

from core.scanner import ScannerRequest, build_scanner_output, scanner_summary
from core.scanner_ranking_engine import (
    calculate_canonical_ranking,
    rank_scanner_rows,
)
from core.scanner_session_review import build_market_brief_prompt
from controllers.scanner_controller import ScannerController
from ui.screens.scanner_screen import ScannerScreen, ScannerTableModel


def _row(
    symbol: str,
    status: str,
    *,
    setup_score: float = 70,
    rr: float = 1.5,
) -> dict:
    return {
        "symbol": symbol,
        "candidate_status": status,
        "setup_score": setup_score,
        "final_score": setup_score,
        "expected_effective_rr": rr,
        "price_vs_zone": "near_zone",
        "strategy_config_status": "NOT_CONFIGURED",
        "execution_ready": status == "READY_NOW",
        "trade_allowed": status not in {"BLOCKED", "DATA_UNAVAILABLE"},
        "analysis_result": {},
    }


def test_status_priority_is_the_primary_sort_key():
    rows = [
        _row("DATA", "DATA_UNAVAILABLE", setup_score=100, rr=5),
        _row("BLOCK", "BLOCKED", setup_score=100, rr=5),
        _row("OUT", "OUT_OF_STRATEGY", setup_score=100, rr=5),
        _row("WATCH", "WATCH_ZONE", setup_score=20, rr=1),
        _row("WAIT", "WAITING_CONFIRMATION", setup_score=20, rr=1),
        _row("READY", "READY_NOW", setup_score=20, rr=1),
    ]

    ranked = rank_scanner_rows(rows)

    assert [row["candidate_status"] for row in ranked] == [
        "READY_NOW",
        "WAITING_CONFIRMATION",
        "WATCH_ZONE",
        "OUT_OF_STRATEGY",
        "BLOCKED",
        "DATA_UNAVAILABLE",
    ]
    assert [row["rank"] for row in ranked] == [1, 2, 3, 4, 5, 6]


def test_same_status_uses_opportunity_then_symbol_tie_break():
    rows = [
        _row("ZZZ", "WATCH_ZONE", setup_score=60),
        _row("BBB", "WATCH_ZONE", setup_score=80),
        _row("AAA", "WATCH_ZONE", setup_score=80),
    ]

    ranked = rank_scanner_rows(rows)

    assert [row["symbol"] for row in ranked] == ["AAA", "BBB", "ZZZ"]
    assert ranked[0]["opportunity_rank"] > ranked[2]["opportunity_rank"]


def test_strategy_confidence_breaks_equal_opportunity_rank_before_symbol():
    evidence_row = _row("ZZZ", "WATCH_ZONE", setup_score=60)
    evidence_row.update({
        "strategy_config_status": "VALIDATED",
        "auto_trade_config": {
            "out_of_sample_trades": 40,
            "oos_expectancy_r": 0.5,
            "oos_profit_factor": 2.0,
            "expectancy_ci_low": 0.1,
        },
    })
    no_evidence_row = _row("AAA", "WATCH_ZONE", setup_score=78.18)

    ranked = rank_scanner_rows([no_evidence_row, evidence_row])

    assert ranked[0]["opportunity_rank"] == ranked[1]["opportunity_rank"]
    assert ranked[0]["symbol"] == "ZZZ"
    assert ranked[0]["strategy_confidence"] == 100


def test_blocked_never_receives_execution_readiness_bonus():
    evaluation = calculate_canonical_ranking(
        _row("EUR/USD", "BLOCKED", setup_score=95, rr=3.0)
    )

    assert evaluation.execution_readiness == 0
    assert evaluation.breakdown["execution_component"] == 0
    assert evaluation.breakdown["readiness_bonus_applied"] is False
    assert 0 <= evaluation.opportunity_rank <= 100


def test_validated_oos_evidence_is_separate_from_setup_score():
    row = _row("EUR/USD", "READY_NOW", setup_score=72, rr=2.0)
    row.update({
        "strategy_config_status": "VALIDATED",
        "auto_trade_config": {
            "out_of_sample_trades": 40,
            "oos_expectancy_r": 0.25,
            "oos_profit_factor": 1.5,
            "expectancy_ci_low": 0.05,
        },
    })

    ranked = rank_scanner_rows([row])[0]

    assert ranked["setup_score"] == 72
    assert ranked["evidence_confidence"] == 75
    assert ranked["ranking_score_breakdown"]["evidence_source"] == "backtest_oos"


def test_market_brief_preserves_backend_rank_order():
    rows = rank_scanner_rows([
        _row("GBP/USD", "READY_NOW", setup_score=70),
        _row("EUR/USD", "READY_NOW", setup_score=80),
        _row("USD/JPY", "WAITING_CONFIRMATION", setup_score=90),
    ])

    prompt = build_market_brief_prompt(rows)
    payload = json.loads(prompt[prompt.find("{"):])

    assert [item["symbol"] for item in payload["top_setups"]] == [
        row["symbol"] for row in rows
    ]
    assert [item["rank"] for item in payload["top_setups"]] == [1, 2, 3]


def test_telegram_candidates_preserve_the_same_backend_order():
    rows = rank_scanner_rows([
        _row("GBP/USD", "READY_NOW", setup_score=70),
        _row("EUR/USD", "READY_NOW", setup_score=80),
    ])
    for row in rows:
        row["candidate_order_payload"] = {
            "symbol": row["symbol"],
            "setup_score": row["setup_score"],
        }
    controller = ScannerController.__new__(ScannerController)

    candidates = controller._get_alert_order_candidates(rows)

    assert [item["symbol"] for item in candidates] == [
        row["symbol"] for row in rows
    ]
    assert [item["rank"] for item in candidates] == [1, 2]
    assert all(
        item["ranking_version"] == "phase6-ranking-v1"
        for item in candidates
    )


def test_ui_does_not_sort_or_reassign_backend_rank():
    source = inspect.getsource(ScannerScreen._scan_finished)
    assert "rows.sort" not in source
    assert 'row["rank"]' not in source


def test_ui_exposes_each_canonical_ranking_dimension_separately():
    columns = {key for key, _label in ScannerTableModel.COLUMNS}
    assert {
        "candidate_status",
        "setup_score",
        "opportunity_rank",
        "evidence_confidence",
        "execution_readiness",
        "expected_effective_rr",
        "auto_trade_branch",
        "strategy_config_status",
    } <= columns


def test_ui_order_dialog_reuses_backend_candidate_payload():
    rows = rank_scanner_rows([
        _row("EUR/USD", "READY_NOW", setup_score=80),
        _row("GBP/USD", "READY_NOW", setup_score=70),
    ])
    for row in rows:
        row["candidate_order_payload"] = {"symbol": row["symbol"]}
    screen = ScannerScreen.__new__(ScannerScreen)

    orders = screen._build_order_rows(rows, False, {})

    assert [order["symbol"] for order in orders] == [
        row["symbol"] for row in rows
    ]
    assert [order["rank"] for order in orders] == [1, 2]


def test_output_exposes_ranking_contract_and_summary_uses_canonical_status():
    rows = rank_scanner_rows([
        _row("EUR/USD", "READY_NOW"),
        _row("GBP/USD", "OUT_OF_STRATEGY"),
        _row("USD/JPY", "DATA_UNAVAILABLE"),
    ])
    request = ScannerRequest(
        symbols=["EUR/USD", "GBP/USD", "USD/JPY"],
        account_balance=10_000,
        risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh",
    )

    summary = scanner_summary(rows)
    output = build_scanner_output(rows, request, 0)

    assert output["ranking_version"] == "phase6-ranking-v1"
    assert summary["ready_now_count"] == 1
    assert summary["out_of_strategy_count"] == 1
    assert summary["data_unavailable_count"] == 1
    assert all(row["ranking_version"] == "phase6-ranking-v1" for row in rows)


def test_controller_recalculates_stale_ranking_after_candidate_filter():
    stale = _row("EUR/USD", "READY_NOW", setup_score=99, rr=4.0)
    stale["opportunity_rank"] = 100
    controller = ScannerController.__new__(ScannerController)
    request = ScannerRequest(
        symbols=["EUR/USD"],
        account_balance=10_000,
        risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh",
    )

    rows = controller._apply_scanner_filters([stale], request)

    assert rows[0]["candidate_status"] == "DATA_UNAVAILABLE"
    assert rows[0]["opportunity_rank"] == 0
    assert rows[0]["ranking_score_breakdown"]["status"] == "DATA_UNAVAILABLE"
    assert rows[0]["rank"] == 1
