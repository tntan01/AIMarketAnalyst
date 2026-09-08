"""Strategy Router lean — branch/routing tests cho luồng live (Bước 5).

Bước 5 loại bỏ Backtest (2026-09-09): các test evidence-lifecycle
(validate_backtest_config, apply/merge/serialize evidence, round-trip
validation metadata) đã xóa cùng engine — chúng chỉ kiểm tra tính năng
Backtest đã loại bỏ. File này giữ các test bảo vệ Scanner/auto-trade live:
DEFAULT_RULES, nhánh cấu hình riêng (lean), fail-closed, ngưỡng Decision
Engine và legacy-settings load.
"""

from __future__ import annotations

from config.settings import SymbolScanSettings
from controllers.scanner_controller import ScannerController
from core.scanner import ScannerRequest
from core.scanner_candidate_engine import evaluate_scanner_candidate
from core.scanner_models import (
    BRANCH_BACKTEST_INVALID,
    BRANCH_BACKTEST_VALIDATED,
    BRANCH_DEFAULT_RULES,
    CONFIG_VALIDATED,
    OUT_OF_STRATEGY,
    READY_NOW,
    STRATEGY_ROUTER_VERSION,
)
from core.scanner_strategy_router import route_strategy
from core.symbol_scan_config import (
    analysis_thresholds_for_symbol,
    serialize_symbol_auto_trade_config,
)
from services.settings_service import SettingsService


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


def _row(**overrides) -> dict:
    row = {
        "symbol": "EUR/USD",
        "best_side": "buy",
        "buy_score": 78,
        "sell_score": 61,
        "best_score": 78,
        "setup_score": 72,
        "min_score": 65,
        "min_rr": 1.3,
        "market_regime": "range",
        "direction_bias": {
            "best_side": "buy",
            "score_gap": 17,
            "is_clear_bias": True,
            "min_gap": 10,
        },
        "score_gap": 17,
        "scanner_action": "ready",
        "scanner_decision": "READY_TO_TRADE",
        "scanner_group": "ready_now",
        "trade_permission": "allowed",
        "journal_feedback": {},
        "scoring_provenance": {
            "smc_scorer_version": "smc-v2",
            "smc_scoring_mode": "v2",
        },
        "smc_scorer_version": "smc-v2",
        "smc_scoring_mode": "v2",
        "analysis_result": {
            "side_scores": {
                "buy": {"signal_score": 78, "setup_score": 72},
                "sell": {"signal_score": 61, "setup_score": 64},
            },
            "scenario_scores": {
                "buy": {"signal_score": 78},
                "sell": {"signal_score": 61},
            },
            "decision_engine": {"decision": "READY_TO_TRADE"},
            "trade_gate": {"allowed": True, "decision_cap": None},
            "technical": {"price": 1.0860},
            "scenarios": [_scenario("buy"), _scenario("sell")],
        },
    }
    row.update(overrides)
    return row


def _compact_config(**overrides) -> dict:
    """Cấu hình chiến lược per-symbol dạng gọn (hình dạng payload live)."""

    config = {
        "symbol": "EUR/USD",
        "config_id": "EURUSD-range-buy-v3",
        "regime": "range",
        "allowed_regimes": ["range"],
        "side": "buy",
        "min_score": 65,
        "min_rr": 1.5,
        "score_metric": "setup_score",
    }
    config.update(overrides)
    return config


# ---------------------------------------------------------------------------
# DEFAULT_RULES
# ---------------------------------------------------------------------------


def test_default_rules_pass_only_with_clear_gap_score_and_rr():
    decision = evaluate_scanner_candidate(_row())
    assert decision.branch == BRANCH_DEFAULT_RULES
    assert decision.status == READY_NOW
    assert decision.strategy_eligible is True


def test_default_rules_reject_unclear_score_gap():
    row = _row(
        score_gap=5,
        direction_bias={
            "best_side": "buy",
            "score_gap": 5,
            "is_clear_bias": False,
            "min_gap": 10,
        },
    )
    decision = evaluate_scanner_candidate(row)
    assert decision.status == OUT_OF_STRATEGY
    assert "SCORE_GAP_BELOW_MIN" in decision.reason_codes
    assert "BEST_SIDE_NOT_CLEAR" in decision.reason_codes


def test_default_rules_reject_setup_score_below_decision_threshold():
    row = _row()
    row["analysis_result"]["side_scores"]["buy"]["setup_score"] = 60
    decision = evaluate_scanner_candidate(row)
    assert decision.auto_trade_candidate is False
    assert "SETUP_SCORE_BELOW_DEFAULT_MIN" in decision.reason_codes


def test_default_rules_reject_rr_below_default_minimum():
    row = _row()
    row["analysis_result"]["scenarios"][0]["expected_effective_rr"] = 1.1
    decision = evaluate_scanner_candidate(row)
    assert decision.auto_trade_candidate is False
    assert "EXPECTED_RR_BELOW_DEFAULT_MIN" in decision.reason_codes


# ---------------------------------------------------------------------------
# Nhánh cấu hình riêng (lean — giá trị enum lịch sử BACKTEST_VALIDATED)
# ---------------------------------------------------------------------------


def test_compact_config_routes_to_configured_branch():
    decision = evaluate_scanner_candidate(_row(), _compact_config())
    assert decision.branch == BRANCH_BACKTEST_VALIDATED
    assert decision.strategy.config_status == CONFIG_VALIDATED
    assert decision.status == READY_NOW
    assert decision.to_dict()["strategy_router_version"] == STRATEGY_ROUTER_VERSION


def test_plain_strategy_config_without_evidence_routes_live():
    # Bước 4b: cấu hình chiến lược tối giản (không bằng chứng kiểm định)
    # được route — quyền do người dùng cấp qua auto_trade_permitted.
    decision = evaluate_scanner_candidate(
        _row(),
        {
            "symbol": "EUR/USD",
            "regime": "range",
            "side": "buy",
            "score_metric": "setup_score",
            "min_score": 65,
            "min_rr": 1.5,
        },
    )
    assert decision.branch == BRANCH_BACKTEST_VALIDATED
    assert decision.strategy_eligible is True
    assert decision.selected_side == "buy"


def test_side_best_locks_the_current_best_side():
    row = _row(
        best_side="sell",
        best_score=61,
        setup_score=64,
        score_gap=17,
        direction_bias={
            "best_side": "sell",
            "score_gap": 17,
            "is_clear_bias": True,
            "min_gap": 10,
        },
    )
    decision = evaluate_scanner_candidate(
        row,
        _compact_config(side="best"),
    )
    assert decision.branch == BRANCH_BACKTEST_VALIDATED
    assert decision.selected_side == "sell"
    assert decision.setup_score == 64
    assert decision.scenario is not None
    assert decision.scenario["type"] == "sell"


def test_fixed_buy_never_uses_sell_scenario():
    row = _row()
    row["analysis_result"]["scenarios"] = [_scenario("sell")]
    decision = evaluate_scanner_candidate(row, _compact_config(side="buy"))
    assert decision.branch == BRANCH_BACKTEST_VALIDATED
    assert decision.auto_trade_candidate is False
    assert decision.scenario is None
    assert "MISSING_SELECTED_SIDE_SCENARIO" in decision.reason_codes


def test_allowed_regimes_are_supported():
    config = _compact_config(regime="", allowed_regimes=["range", "trend_up"])
    decision = evaluate_scanner_candidate(_row(), config)
    assert decision.branch == BRANCH_BACKTEST_VALIDATED
    assert decision.strategy_eligible is True


def test_config_symbol_mismatch_is_invalid_not_default_branch():
    decision = evaluate_scanner_candidate(
        _row(),
        _compact_config(symbol="GBP/USD"),
    )
    assert decision.branch == BRANCH_BACKTEST_INVALID
    assert "BACKTEST_SYMBOL_MISMATCH" in decision.reason_codes


def test_side_mismatch_config_never_auto_trades():
    # Lifecycle status không còn được đọc; fail-closed đến từ kiểm tra live —
    # side cấu hình lệch best_side ⇒ không eligible.
    strategy, selected = route_strategy(
        _row(),
        {"symbol": "EUR/USD", "regime": "range", "side": "sell",
         "min_score": 65, "min_rr": 1.5},
    )
    assert strategy.branch == BRANCH_BACKTEST_VALIDATED
    assert strategy.eligible is False
    assert "CONFIG_SIDE_MISMATCH" in strategy.reason_codes
    assert selected is not None and selected.side == "sell"


def test_compact_payload_from_settings_routes_validated():
    # Payload gọn do symbol_scan_config serialize là hình dạng chuẩn live.
    cfg = SymbolScanSettings(
        scan_enabled=True,
        auto_trade_permitted=True,
        auto_trade_regime="range",
        auto_trade_side="buy",
        min_score=68,
        min_expected_rr=1.6,
    )
    payload = serialize_symbol_auto_trade_config(cfg, symbol="EUR/USD")
    assert payload is not None
    decision = evaluate_scanner_candidate(_row(), payload)
    assert decision.branch == BRANCH_BACKTEST_VALIDATED
    assert decision.strategy_eligible is True
    assert decision.selected_side == "buy"


def test_malformed_payload_fails_closed_invalid_branch():
    strategy, _selected = route_strategy(_row(), "not-a-dict")
    assert strategy.branch == BRANCH_BACKTEST_INVALID
    assert strategy.eligible is False
    assert "BACKTEST_CONFIG_MALFORMED" in strategy.reason_codes


def test_controller_exposes_invalid_config_status_for_ui():
    # Neutral auto_trade_branch (None) khi config không hợp lệ/không có —
    # quyết định phơi qua candidate_status / reason_codes, cột UI degrade "--".
    controller = ScannerController.__new__(ScannerController)
    request = ScannerRequest(
        symbols=["EUR/USD"],
        account_balance=10_000,
        risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh",
        symbol_auto_trade={
            "EUR/USD": {"side": "buy"},  # thiếu regime → INVALID lean
        },
    )
    rows = controller._apply_scanner_filters([_row()], request)
    assert rows[0]["auto_trade_branch"] is None
    assert rows[0]["backtest_config_status"] is None
    assert rows[0]["auto_trade_candidate"] is False


# ---------------------------------------------------------------------------
# Ngưỡng Decision Engine + legacy settings load
# ---------------------------------------------------------------------------


def test_decision_thresholds_come_from_explicit_analysis_min_rr():
    # Bước 4b: min_rr Decision Engine đọc từ analysis_min_rr tường minh —
    # cờ legacy `backtest` và min_expected_rr (RR chiến lược auto-trade)
    # không ảnh hưởng ngưỡng phân tích.
    settings = SymbolScanSettings(
        min_score=80,
        decision_ready=65,
        decision_watch=60,
        decision_wait=55,
        min_expected_rr=2.0,
    )
    thresholds = analysis_thresholds_for_symbol(settings)
    assert thresholds == {
        "ready": 65,
        "watch": 60,
        "wait": 55,
        "min_score_gap": 10,
        "min_rr": 1.3,
    }
    settings.analysis_min_rr = 1.9
    assert analysis_thresholds_for_symbol(settings)["min_rr"] == 1.9


def test_legacy_settings_load_raw_and_permissions_fail_closed(tmp_path):
    service = SettingsService(tmp_path / "settings.json")
    service.storage.save({
        "ai": {},
        "trading": {
            "enabled_symbols": ["EUR/USD"],
            "symbol_settings": {
                "EUR/USD": {
                    "backtest": True,
                    "min_score": 68,
                    "auto_trade_regime": "range",
                    "auto_trade_side": "buy",
                    "min_expected_rr": 1.5,
                },
            },
        },
    })
    loaded = service.load().trading.symbol_settings["EUR/USD"]
    # Bước 4b/6: không tái kiểm định khi load; khóa evidence legacy trên
    # file được đọc nguyên trạng bởi migration (model không còn field).
    stored = service.storage.load()["trading"]["symbol_settings"]["EUR/USD"]
    assert stored["backtest"] is True
    # Quyền auto-trade suy dẫn từ trạng thái hiệu lực cũ: không có
    # status VALIDATED + expiry ⇒ mặc định TẮT (không mở rộng quyền).
    assert loaded.auto_trade_permitted is False
    assert loaded.scan_enabled is True
    assert service.load().trading.enabled_symbols == ["EUR/USD"]
    # Ngưỡng Decision Engine bảo toàn theo công thức hiệu lực cũ
    # (không active ⇒ min_expected_rr).
    assert loaded.analysis_min_rr == 1.5
