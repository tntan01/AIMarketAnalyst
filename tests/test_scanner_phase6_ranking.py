"""Phase-6 canonical ranking and consumer-order tests."""

from __future__ import annotations

import json

import pytest

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
            "broker_symbol": row["symbol"].replace("/", ""),
            "side": "buy",
            "entry_zone": [1.1000, 1.1010],
            "stop_loss": 1.0950,
            "take_profit": 1.1100,
            "setup_score": row["setup_score"],
            "candidate_status": "READY_NOW",
            "scan_id": "scan-ranking",
            "row_id": f"scan-ranking:{row['symbol']}",
            "settings_hash": "settings-hash",
            "scorer_version": "scanner-scorer-v1",
            "ranking_version": "phase6-ranking-v1",
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


def test_ui_presentation_order_does_not_mutate_execution_result():
    """UI receives presentation order, but result["rows"] keeps execution order,
    raw rank is unchanged, and canonical ranker is NOT called from UI.
    Uses mock.patch on the canonical ranker — BEHAVIOR, not source inspection."""
    from unittest.mock import MagicMock, patch

    screen = ScannerScreen.__new__(ScannerScreen)
    model = ScannerTableModel()
    screen.table_model = model
    screen.settings_service = MagicMock()

    screen.status_labels = MagicMock()
    screen.status_labels.__getitem__ = lambda self, k: MagicMock()
    screen.scan_button = MagicMock()
    screen.detail_button = MagicMock()
    screen.save_button = MagicMock()
    screen.progress_bar = MagicMock()
    screen.progress_container = MagicMock()
    screen._selected_symbols = lambda: ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"]
    screen._highlight_show_orders_button = lambda: None
    screen._update_status_summary = lambda: None
    screen._configure_table_columns = lambda: None
    screen._market_brief_text = ""

    # Input in canonical execution order: none, smc, technical, fallback
    # NOT already in presentation order (smc→technical→fallback→none)
    rows_exec = [
        {"symbol": "AUD/USD", "rank": 1, "entry_zone_source": None,              "zone_origin_class": "none"},
        {"symbol": "EUR/USD", "rank": 2, "entry_zone_source": "smc_selected", "zone_origin_class": "smc"},
        {"symbol": "GBP/USD", "rank": 3, "entry_zone_source": "technical",       "zone_origin_class": "technical"},
        {"symbol": "USD/JPY", "rank": 4, "entry_zone_source": "fallback",         "zone_origin_class": "fallback"},
    ]
    result = {"rows": rows_exec, "symbols_scanned": 4, "ai_called": 0, "timestamp": "2026-01-01T00:00:00"}

    with patch("core.scanner_ranking_engine.rank_scanner_rows") as mock_rank:
        with patch("core.scanner.sort_scanner_rows") as mock_sort:
            screen._scan_finished(result)

    # Canonical ranker must NOT be called from UI
    mock_rank.assert_not_called()
    mock_sort.assert_not_called()

    # table_model.rows = presentation order: smc → technical → fallback → none
    assert [r["symbol"] for r in model.rows] == ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"]
    assert [r["presentation_rank"] for r in model.rows] == [1, 2, 3, 4]
    assert [r["rank"] for r in model.rows] == [2, 3, 4, 1]

    # result["rows"] unchanged: execution order, no presentation_rank
    assert screen.scan_result is result
    assert result["rows"] is rows_exec
    assert [r["symbol"] for r in result["rows"]] == ["AUD/USD", "EUR/USD", "GBP/USD", "USD/JPY"]
    for r in result["rows"]:
        assert "presentation_rank" not in r


def test_ui_exposes_each_canonical_ranking_dimension_separately():
    columns = {key for key, _label in ScannerTableModel.COLUMNS}
    assert {
        "candidate_status",
        "setup_score",
        "technical_signal_score",
        "evidence_confidence",
        "execution_readiness",
        "expected_effective_rr",
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
    # A row that CLAIMS READY_NOW but carries no real V4 candidate is stale or
    # fabricated. The V4 filter demotes it to DATA_UNAVAILABLE and resets the
    # V3-only rank/opportunity fields to their documented neutrals, so it can
    # never enter the dispatch loop with an unsupported status.
    stale = {
        "symbol": "EUR/USD",
        "candidate_status": "READY_NOW",
        "setup_score": 99,
        "opportunity_rank": 100,
        "expected_effective_rr": 4.0,
    }
    controller = ScannerController.__new__(ScannerController)
    request = ScannerRequest(
        symbols=["EUR/USD"],
        account_balance=10_000,
        risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh",
    )

    rows = controller._apply_scanner_filters([stale], request)

    assert rows[0]["candidate_status"] == "DATA_UNAVAILABLE"
    assert rows[0]["auto_trade_candidate"] is False
    # V3-only rank/opportunity fields are reset to the documented neutral —
    # the stale rank is never preserved.
    assert rows[0]["opportunity_rank"] is None


# ---------------------------------------------------------------------------
# Auto-trade regression — execution order NOT presentation order
# ---------------------------------------------------------------------------


def test_auto_trade_receives_execution_order_not_presentation_order():
    """Auto-trade for-loop iterates rows in execution rank order, even when
    zone_origin_class priority would reorder them in the UI table.
    Uses unittest.mock.patch to spy on execute_order_candidate()."""
    from unittest.mock import MagicMock, patch

    def _v4_row(symbol: str, setup_score: float, zone: str) -> dict:
        return {
            "symbol": symbol,
            "broker_symbol": symbol.replace("/", ""),
            "candidate_status": "READY_NOW",
            "selected_side": "buy",
            "auto_trade_candidate": True,
            "setup_score": setup_score,
            "expected_effective_rr": 2.0,
            "score_gap": 10,
            "zone_origin_class": zone,
            "reason_codes": [],
            "block_codes": [],
            "candidate_order_payload": {
                "symbol": symbol,
                "side": "buy",
                "entry": 1.1000,
                "stop_loss": 1.0980,
                "take_profit": 1.1080,
                "scoring_version": "scanner-v4",
            },
            "analysis_result": {},
        }

    controller = ScannerController.__new__(ScannerController)
    controller.mt5 = None
    controller.settings_service = None
    controller.orders_screen = None
    controller._emit_observability = lambda *a, **kw: None  # type: ignore[method-assign]

    # Two genuine V4 READY_NOW candidates. UI presentation would put the smc
    # row first, but _execute_auto_trades must follow the execution row order.
    rows = [
        _v4_row("EUR/USD", 80, "technical"),
        _v4_row("GBP/USD", 70, "smc"),
    ]

    request = ScannerRequest(
        symbols=["EUR/USD", "GBP/USD"],
        account_balance=10000,
        risk_percent=1.0,
        timezone_name="UTC",
        auto_trade_enabled=True,
    )

    call_symbols: list[str] = []
    def spy(proposal, **__kw):
        call_symbols.append(str(proposal.get("symbol", "")))
        return {"success": True, "symbol": proposal.get("symbol", "")}

    with patch.object(controller, "execute_order_candidate", side_effect=spy) as spy_method:
        controller._execute_auto_trades(rows, request)
        assert spy_method.call_count == 2, \
            f"Expected 2 execute calls, got {spy_method.call_count}"

    assert call_symbols == ["EUR/USD", "GBP/USD"], \
        f"Auto-trade must follow execution rank order, got: {call_symbols}"


# ---------------------------------------------------------------------------
# presentation_rank must never leak into snapshot, observability, or export
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["full", "summary"])
def test_snapshot_payload_uses_execution_rows_without_presentation_rank(mode):
    """Both snapshot modes keep execution order and never receive UI-only rank."""
    from controllers.scanner_controller import ScannerController
    from ui.scanner_presentation import sort_scanner_rows_for_display

    controller = ScannerController.__new__(ScannerController)
    execution_rows = [
        {
            "symbol": "EUR/USD",
            "rank": 1,
            "entry_zone_source": "technical",
            "zone_origin_class": "technical",
        },
        {
            "symbol": "GBP/USD",
            "rank": 2,
            "entry_zone_source": "smc",
            "zone_origin_class": "smc",
        },
    ]
    result = {
        "scan_id": "test-001",
        "timestamp": "2026-01-01T00:00:00",
        "rows": execution_rows,
    }

    model = ScannerTableModel()
    model.set_rows(sort_scanner_rows_for_display(execution_rows))
    assert [row["symbol"] for row in model.rows] == ["GBP/USD", "EUR/USD"]
    assert [row["presentation_rank"] for row in model.rows] == [1, 2]

    payload = controller._snapshot_payload(result, mode=mode)

    assert [row["symbol"] for row in execution_rows] == ["EUR/USD", "GBP/USD"]
    assert [row["rank"] for row in execution_rows] == [1, 2]
    assert all("presentation_rank" not in row for row in execution_rows)
    assert payload["persistence_mode"] == mode
    assert [row["symbol"] for row in payload["rows"]] == ["EUR/USD", "GBP/USD"]
    assert [row["rank"] for row in payload["rows"]] == [1, 2]
    assert all("presentation_rank" not in row for row in payload["rows"])
    assert [row["entry_zone_source"] for row in payload["rows"]] == [
        "technical",
        "smc",
    ]
    assert [row["zone_origin_class"] for row in payload["rows"]] == [
        "technical",
        "smc",
    ]


def test_observability_document_receives_execution_row_without_ui_fields():
    """The UI copy boundary keeps presentation_rank out of observability."""
    from core.scanner_observability import build_analysis_document
    from ui.scanner_presentation import sort_scanner_rows_for_display

    execution_row = {
        "symbol": "EUR/USD",
        "rank": 1,
        "entry_zone_source": "smc",
        "zone_origin_class": "smc",
        "analysis_result": {"scenarios": [{"type": "buy"}]},
    }
    context = {"scan_id": "test-001", "started_at": "2026-01-01T00:00:00Z"}

    model = ScannerTableModel()
    model.set_rows(sort_scanner_rows_for_display([execution_row]))
    assert model.rows[0]["presentation_rank"] == 1
    assert "presentation_rank" not in execution_row

    doc = build_analysis_document(execution_row, context)

    row_summary = doc.get("row_summary", {})
    assert isinstance(row_summary, dict)
    assert "presentation_rank" not in row_summary
    assert row_summary.get("entry_zone_source") == "smc"
    assert row_summary.get("zone_origin_class") == "smc"
    assert row_summary.get("rank") == 1
    assert "analysis_result" not in row_summary


def test_detail_save_to_journal_strips_presentation_rank():
    """Journal receives a sanitized copy without constructing the whole screen."""
    from types import SimpleNamespace

    from ui.screens.scanner_detail_screen import ScannerDetailScreen

    source_row = {
        "symbol": "EUR/USD",
        "rank": 1,
        "presentation_rank": 1,
        "zone_origin_class": "smc",
        "analysis_result": {"data": "heavy"},
    }

    captured = []

    def capture(row):
        captured.append(dict(row))

    detail = SimpleNamespace(
        row=source_row,
        journal_controller=SimpleNamespace(save_scanner_row=capture),
        navigate=None,
    )
    ScannerDetailScreen._save_to_journal(detail)

    assert len(captured) == 1
    assert "presentation_rank" not in captured[0]
    assert captured[0]["rank"] == 1
    assert captured[0]["zone_origin_class"] == "smc"
    assert source_row["presentation_rank"] == 1


def test_detail_export_json_strips_presentation_rank(tmp_path):
    """Export serializes a sanitized copy without constructing the whole screen."""
    from types import SimpleNamespace
    from unittest.mock import patch
    from pathlib import Path

    from ui.screens.scanner_detail_screen import ScannerDetailScreen

    source_row = {
        "symbol": "EUR/USD",
        "rank": 1,
        "presentation_rank": 1,
        "zone_origin_class": "smc",
        "analysis_result": {"data": "heavy"},
    }
    detail = SimpleNamespace(row=source_row)

    with patch("ui.screens.scanner_detail_screen.app_data_dir", return_value=Path(tmp_path)):
        ScannerDetailScreen._export_json(detail)

    export_dir = tmp_path / "scanner_details"
    files = list(export_dir.glob("*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert "presentation_rank" not in saved
    assert "analysis_result" not in saved
    assert saved["rank"] == 1
    assert saved["zone_origin_class"] == "smc"
    assert source_row["presentation_rank"] == 1
