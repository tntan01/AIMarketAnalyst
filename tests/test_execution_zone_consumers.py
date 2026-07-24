from __future__ import annotations

from unittest.mock import MagicMock

import core.analysis_pipeline as analysis_pipeline_module
from controllers.scanner_controller import ScannerController
from core.analysis_pipeline import AnalysisPipeline, _find_scenario
from core.chart_payload import build_full_chart_payload
from core.risk_engine import AnalysisInput
from core.scanner_ranking_engine import _find_scenario_for_side
from tests.test_current_rr_execution_guard import (
    FakeMT5,
    _make_controller,
    _patch_controller,
    _request,
    _row,
    _scenario,
)
from ui.scanner_rr_formatters import (
    format_execution_zone_text,
    format_execution_zone_width,
    format_order_entry_tooltip,
    format_rr_trim_reason,
    format_source_zone_text,
)
from ui.screens.scanner_detail_screen import ScannerDetailScreen


def _zone_diagnostics() -> dict:
    return {
        "source_zone": {
            "original_low": 1.0950,
            "original_high": 1.1000,
        },
        "structural_execution_zone": [1.0970, 1.0990],
        "entry_zone": [1.0970, 1.0980],
        "entry_zone_width_atr": 0.5,
        "rr_trimmed": True,
        "rr_trim_diagnostics": {
            "status": "trimmed",
            "pre_trim_effective_rr_worst": 1.1,
            "post_trim_effective_rr_worst": 1.3,
            "min_effective_rr": 1.3,
        },
    }


def test_strict_scenario_selection_never_falls_back_to_opposite_side() -> None:
    buy = {"type": "buy", "entry_zone": [1.0, 2.0]}

    assert _find_scenario_for_side([buy], "sell") is buy
    assert (
        _find_scenario_for_side(
            [buy],
            "sell",
            fallback_to_first=False,
        )
        is None
    )


def test_gate_side_helper_returns_no_opposite_scenario() -> None:
    buy = {"type": "buy", "entry_zone": [1.0, 2.0]}

    assert _find_scenario([buy], "sell") == {}


def test_gate_context_does_not_borrow_opposite_rr(monkeypatch) -> None:
    captured: dict = {}

    def fake_gate(context: dict) -> dict:
        captured.update(context)
        return {
            "allowed": True,
            "decision_cap": None,
            "block_codes": [],
            "warning_codes": [],
            "reasons": [],
        }

    monkeypatch.setattr(analysis_pipeline_module, "check_trade_gates", fake_gate)
    monkeypatch.setattr(
        analysis_pipeline_module,
        "check_account_guard",
        lambda **_kwargs: {"blocked": False, "block_codes": [], "warning_codes": []},
    )
    pipeline = AnalysisPipeline()
    buy = {
        "type": "buy",
        "entry_zone": [1.0970, 1.0980],
        "stop_loss": 1.0940,
        "take_profit": [1.1050],
        "expected_effective_rr": 2.5,
        "expected_effective_rr_base": 2.0,
    }
    pipeline._thresholds = {"ready": 65, "min_rr": 1.3}
    pipeline._data_quality = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "spread_price": 0.0001,
    }
    pipeline._risk_score = 15
    pipeline._best_score = 80
    pipeline._market_regime = {"primary": "trend_down"}
    pipeline._closed_trades = []
    pipeline._open_trades = []
    pipeline._account_guard_settings = {}
    pipeline._trade_date = None
    pipeline._request = AnalysisInput(
        symbol="EUR/USD",
        broker_symbol="EURUSD",
        account_balance=10000,
        risk_percent=1,
    )
    pipeline._best_side = "sell"
    pipeline._scenarios = [buy]
    pipeline._primary_scenario = buy
    pipeline._smc_trade_flags = {}
    pipeline._direction_bias = {"score_gap": 20, "min_gap": 10}
    pipeline._diag = []

    pipeline._step_apply_gates()

    assert captured["expected_effective_rr"] is None
    assert captured["expected_effective_rr_base"] is None
    assert captured["expected_effective_rr_for_gate"] is None


def test_controller_never_uses_source_zone_as_execution_fallback() -> None:
    ctrl = ScannerController.__new__(ScannerController)
    scenario = {
        "type": "buy",
        "entry_zone": None,
        "source_zone": {"original_low": 1.095, "original_high": 1.100},
    }
    row = {
        "best_side": "buy",
        "analysis_result": {"scenarios": [scenario]},
    }

    assert ctrl._best_scenario(row) is scenario
    assert ctrl._final_execution_zone(scenario) is None


def test_execution_zone_never_expands_to_source_zone() -> None:
    ctrl = ScannerController.__new__(ScannerController)
    scenario = _scenario(entry_zone=[1.0970, 1.0980])
    scenario.update(_zone_diagnostics())

    assert ctrl._final_execution_zone(scenario) == (1.0970, 1.0980)
    assert not 1.0970 <= 1.0990 <= 1.0980


def test_execution_zone_missing_stays_missing_despite_source_zone() -> None:
    ctrl = ScannerController.__new__(ScannerController)
    scenario = _scenario(entry_zone=[1.0970, 1.0980])
    scenario["entry_zone"] = None
    scenario["source_zone"] = {
        "original_low": 1.0950,
        "original_high": 1.1000,
    }
    assert ctrl._final_execution_zone(scenario) is None


def test_alert_candidate_uses_all_fields_from_matching_sell_scenario() -> None:
    ctrl = ScannerController.__new__(ScannerController)
    ctrl.settings_service = MagicMock()
    ctrl.settings_service.load.side_effect = RuntimeError("no settings")
    buy = _scenario(entry_zone=[1.0900, 1.0910])
    buy["expected_effective_rr"] = 9.0
    sell = {
        **_scenario(entry_zone=[1.1000, 1.1010]),
        "type": "sell",
        "entry_price": 1.1010,
        "stop_loss": 1.1050,
        "take_profit": [1.0920],
        "expected_effective_rr": 2.0,
        "expected_effective_rr_base": 1.6,
        **_zone_diagnostics(),
    }
    sell["entry_zone"] = [1.1000, 1.1010]
    row = _row(best_side="sell", scenario=buy)
    row["analysis_result"]["scenarios"] = [buy, sell]
    row["analysis_result"]["technical"]["price"] = 1.1005
    row["expected_effective_rr"] = 9.0

    candidates = ctrl._get_alert_order_candidates([row])

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["side"] == "sell"
    assert candidate["entry_zone"] == [1.1, 1.101]
    assert candidate["expected_effective_rr"] == 2.0
    assert candidate["source_zone"] == sell["source_zone"]


def test_zone_formatters_show_execution_source_width_and_trim_reason() -> None:
    item = {"symbol": "EURUSD", **_zone_diagnostics()}

    assert format_execution_zone_text(item) == "[1.09700 - 1.09800]"
    assert format_source_zone_text(item) == "[1.09500 - 1.10000]"
    assert format_execution_zone_width(item) == "10.0 pips | 0.500 ATR"
    assert "1.10 -> 1.30" in format_rr_trim_reason(item)
    tooltip = format_order_entry_tooltip(item)
    assert "Execution:" in tooltip
    assert "Source (reference):" in tooltip
    assert "Width:" in tooltip
    assert "RR trim:" in tooltip


def test_rejected_zone_formatter_keeps_source_reference_but_no_execution() -> None:
    item = {
        "symbol": "GBPJPY",
        "entry_zone": None,
        "source_zone": {
            "original_low": 218.003,
            "original_high": 218.215,
        },
        "rr_trim_diagnostics": {"status": "empty"},
        "invalid_reason": "No final price meets RR floor",
    }

    tooltip = format_order_entry_tooltip(item)

    assert "Execution: --" in tooltip
    assert "Source (reference): [218.003 - 218.215]" in tooltip
    assert "No final price meets RR floor" in tooltip


def test_detail_screen_does_not_fall_back_to_opposite_scenario() -> None:
    screen = ScannerDetailScreen.__new__(ScannerDetailScreen)
    screen.row = {
        "best_side": "sell",
        "entry_zone": [1.0900, 1.0910],
        "risk_reward": "1:9.0",
        "analysis_result": {
            "scenarios": [{
                "type": "buy",
                "entry_zone": [1.0900, 1.0910],
                "risk_reward": "1:9.0",
            }],
        },
    }

    assert screen._best_detail_scenario() == {}
    assert screen._plan_field("entry_zone") is None
    assert screen._rr_field("risk_reward") is None


def test_chart_payload_uses_matching_side_and_marks_source_reference_only() -> None:
    buy = {
        "type": "buy",
        "entry_zone": [1.0900, 1.0910],
        "stop_loss": 1.0850,
        "take_profit": [1.1000],
        "entry_zone_source": "smc",
    }
    sell = {
        "type": "sell",
        "entry_zone": [1.1000, 1.1010],
        "stop_loss": 1.1050,
        "take_profit": [1.0920],
        "entry_zone_source": "smc",
        **_zone_diagnostics(),
    }
    sell["entry_zone"] = [1.1000, 1.1010]
    result = {
        "decision_summary": {"best_side": "sell"},
        "scenarios": [buy, sell],
        "technical": {"price": 1.1005},
        "chart_payload": {},
    }

    payload = build_full_chart_payload("EURUSD", result)

    assert payload["trade_plan"]["side"] == "sell"
    assert payload["trade_plan"]["entry_zone"] == [1.1, 1.101]
    source = next(z for z in payload["zones"] if z["type"] == "source_zone")
    execution = next(z for z in payload["zones"] if z["type"] == "entry_zone")
    assert source["execution_eligible"] is False
    assert execution["execution_eligible"] is True
    assert [execution["from"], execution["to"]] == [1.1, 1.101]


def test_chart_payload_does_not_borrow_buy_when_best_side_sell_missing() -> None:
    result = {
        "decision_summary": {"best_side": "sell"},
        "scenarios": [{
            "type": "buy",
            "entry_zone": [1.0900, 1.0910],
            "stop_loss": 1.0850,
            "take_profit": [1.1000],
            "entry_zone_source": "smc",
        }],
        "chart_payload": {},
    }

    payload = build_full_chart_payload("EURUSD", result)

    assert payload["trade_plan"]["side"] == "neutral"
    assert payload["trade_plan"]["entry_zone"] is None
    assert payload["zones"] == []


def test_chart_rejected_plan_draws_source_only_and_exposes_reason() -> None:
    rejected = {
        "type": "buy",
        "entry_zone": None,
        "entry_zone_source": "smc",
        "source_zone": {"original_low": 1.0950, "original_high": 1.1000},
        "rr_trim_diagnostics": {"status": "empty"},
        "invalid_reason": "No final price meets RR floor",
        "entry_status": "watch_zone",
    }
    result = {
        "decision_summary": {"best_side": "buy"},
        "scenarios": [rejected],
        "chart_payload": {},
    }

    payload = build_full_chart_payload("EURUSD", result)

    assert payload["trade_plan"]["entry_zone"] is None
    assert payload["trade_plan"]["rr_trim_diagnostics"]["status"] == "empty"
    assert payload["trade_plan"]["invalid_reason"] == "No final price meets RR floor"
    assert len(payload["zones"]) == 1
    assert payload["zones"][0]["type"] == "source_zone"
    assert payload["zones"][0]["execution_eligible"] is False
