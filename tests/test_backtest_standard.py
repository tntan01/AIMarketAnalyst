"""Tests for simplified Standard backtest engine and scanner config mapping."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.system_backtest_engine import trade_open_block_reason, should_open_trade, build_fallback_scenario, select_trade_scenario
from core.backtest_to_scanner_config import recommend_scanner_configs, _normalize_trades, _summarize
from config.settings import SymbolScanSettings


# ---------------------------------------------------------------------------
# 1. trade_open_block_reason() — Standard unified logic
# ---------------------------------------------------------------------------

def _make_analysis(*, gate_allowed=True, permission="allowed", decision="READY_TO_TRADE",
                   entry_status="confirmed_entry", final_score=None):
    return {
        "trade_gate": {"allowed": gate_allowed},
        "trade_permission": {"status": permission},
        "decision_engine": {"decision": decision},
        "final_score": final_score,
    }


def _make_scenario(entry_status="confirmed_entry"):
    return {"entry_status": entry_status, "type": "buy"}


def test_gate_not_allowed_blocks():
    analysis = _make_analysis(gate_allowed=False)
    scenario = _make_scenario()
    assert trade_open_block_reason(analysis, scenario) == "blocked_by_trade_gate"


def test_gate_allowed_true_but_not_explicitly_true_blocks():
    """gate.allowed must be True (not truthy)."""
    analysis = _make_analysis(gate_allowed="yes")
    scenario = _make_scenario()
    # "yes" is truthy but not True
    assert trade_open_block_reason(analysis, scenario) == "blocked_by_trade_gate"


def test_permission_denied_blocks():
    analysis = _make_analysis(permission="denied")
    scenario = _make_scenario()
    assert trade_open_block_reason(analysis, scenario) == "blocked_by_permission"


def test_permission_caution_allows():
    """caution is allowed in Standard mode."""
    analysis = _make_analysis(permission="caution")
    scenario = _make_scenario()
    assert trade_open_block_reason(analysis, scenario) is None


def test_decision_not_ready_blocks():
    """Only truly blocked decisions (STAND_ASIDE, TRADE_BLOCKED) are blocked."""
    analysis = _make_analysis(decision="STAND_ASIDE")
    scenario = _make_scenario()
    assert trade_open_block_reason(analysis, scenario) == "blocked_by_decision"


def test_decision_watch_only_allows():
    """WATCH_ONLY is allowed in Standard backtest mode."""
    analysis = _make_analysis(decision="WATCH_ONLY")
    scenario = _make_scenario()
    assert trade_open_block_reason(analysis, scenario) is None


def test_decision_aggressive_setup_allows():
    """AGGRESSIVE_SETUP is allowed in Standard mode."""
    analysis = _make_analysis(decision="AGGRESSIVE_SETUP", permission="caution")
    scenario = _make_scenario()
    assert trade_open_block_reason(analysis, scenario) is None


def test_decision_waiting_confirmation_allows():
    """WAITING_CONFIRMATION is allowed in Standard mode."""
    analysis = _make_analysis(decision="WAITING_CONFIRMATION")
    scenario = _make_scenario(entry_status="waiting_confirmation")
    assert trade_open_block_reason(analysis, scenario) is None


def test_entry_status_watch_zone_allows():
    """watch_zone is allowed in Standard mode."""
    analysis = _make_analysis()
    scenario = _make_scenario(entry_status="watch_zone")
    assert trade_open_block_reason(analysis, scenario) is None


def test_entry_status_invalid_blocks():
    analysis = _make_analysis()
    scenario = _make_scenario(entry_status="pending")
    assert trade_open_block_reason(analysis, scenario) == "blocked_by_entry_status"


def test_min_score_filter_blocks_when_below_threshold():
    """min_final_score filter blocks when score is below threshold."""
    analysis = _make_analysis(final_score=55)
    scenario = _make_scenario()
    assert trade_open_block_reason(analysis, scenario, min_final_score=60) == "blocked_by_score"


def test_min_score_filter_passes_when_above_threshold():
    analysis = _make_analysis(final_score=70)
    scenario = _make_scenario()
    assert trade_open_block_reason(analysis, scenario, min_final_score=60) is None


def test_min_score_zero_never_blocks():
    """min_final_score=0 means no score filter."""
    analysis = _make_analysis(final_score=10)
    scenario = _make_scenario()
    assert trade_open_block_reason(analysis, scenario, min_final_score=0) is None


def test_should_open_trade_delegates():
    analysis = _make_analysis()
    scenario = _make_scenario()
    assert should_open_trade(analysis, scenario) is True

    analysis_blocked = _make_analysis(gate_allowed=False)
    assert should_open_trade(analysis_blocked, scenario) is False


def test_all_standard_pipeline_passes():
    """Full pipeline: gate → permission → decision → entry → score → pass."""
    analysis = _make_analysis(
        gate_allowed=True,
        permission="caution",
        decision="AGGRESSIVE_SETUP",
        entry_status="watch_zone",
        final_score=75,
    )
    scenario = _make_scenario(entry_status="watch_zone")
    assert trade_open_block_reason(analysis, scenario, min_final_score=50) is None


def test_missing_fields_default_safely():
    """Missing analysis fields should not crash; gate.allowed=None → blocked."""
    analysis = {}
    scenario = {}
    assert trade_open_block_reason(analysis, scenario) == "blocked_by_trade_gate"


# ---------------------------------------------------------------------------
# 2. recommend_scanner_configs() — returns correct format
# ---------------------------------------------------------------------------

def _make_backtest_result(trades: list[dict]) -> dict:
    return {"trades": trades, "summary": _summarize(trades)}


def test_recommend_returns_dict_with_symbol_keys():
    trades = [
        {"symbol": "EUR/USD", "side": "buy", "market_regime": "trend_up",
         "signal_score": 80, "final_score": 75, "expected_effective_rr": 1.8,
         "result": "win", "result_r": 1.5},
        {"symbol": "EUR/USD", "side": "buy", "market_regime": "trend_up",
         "signal_score": 78, "final_score": 72, "expected_effective_rr": 1.6,
         "result": "win", "result_r": 1.3},
        {"symbol": "EUR/USD", "side": "buy", "market_regime": "trend_up",
         "signal_score": 82, "final_score": 76, "expected_effective_rr": 1.9,
         "result": "win", "result_r": 1.6},
        {"symbol": "EUR/USD", "side": "buy", "market_regime": "trend_up",
         "signal_score": 75, "final_score": 70, "expected_effective_rr": 1.5,
         "result": "loss", "result_r": -1.0},
        {"symbol": "EUR/USD", "side": "buy", "market_regime": "trend_up",
         "signal_score": 79, "final_score": 74, "expected_effective_rr": 1.7,
         "result": "loss", "result_r": -1.0},
        {"symbol": "EUR/USD", "side": "buy", "market_regime": "trend_up",
         "signal_score": 81, "final_score": 77, "expected_effective_rr": 2.0,
         "result": "win", "result_r": 1.4},
        {"symbol": "EUR/USD", "side": "buy", "market_regime": "trend_up",
         "signal_score": 77, "final_score": 71, "expected_effective_rr": 1.4,
         "result": "win", "result_r": 1.2},
        {"symbol": "EUR/USD", "side": "buy", "market_regime": "trend_up",
         "signal_score": 83, "final_score": 78, "expected_effective_rr": 2.1,
         "result": "win", "result_r": 1.7},
        {"symbol": "EUR/USD", "side": "buy", "market_regime": "trend_up",
         "signal_score": 76, "final_score": 73, "expected_effective_rr": 1.3,
         "result": "loss", "result_r": -1.0},
        {"symbol": "EUR/USD", "side": "buy", "market_regime": "trend_up",
         "signal_score": 80, "final_score": 75, "expected_effective_rr": 1.8,
         "result": "win", "result_r": 1.5},
    ]
    result = _make_backtest_result(_normalize_trades(trades))
    recs = recommend_scanner_configs(result)

    assert "EUR/USD" in recs
    cfg = recs["EUR/USD"]
    assert cfg is not None, "Should have recommendation with 10 trades"
    assert "regime" in cfg
    assert "side" in cfg
    assert "min_score" in cfg
    assert "min_rr" in cfg
    assert "_evidence" in cfg
    assert cfg["regime"] == "trend_up"
    assert cfg["side"] == "buy"


def test_recommend_none_for_too_few_trades():
    trades = [
        {"symbol": "GBP/USD", "side": "buy", "market_regime": "range",
         "signal_score": 70, "final_score": 65, "expected_effective_rr": 1.5,
         "result": "win", "result_r": 1.0},
    ]
    result = _make_backtest_result(_normalize_trades(trades))
    recs = recommend_scanner_configs(result)
    assert recs.get("GBP/USD") is None, "Should be None with < 10 trades"


def test_recommend_empty_for_no_trades():
    result = {"trades": [], "summary": {}}
    recs = recommend_scanner_configs(result)
    assert recs == {}


# ---------------------------------------------------------------------------
# 3. Field mapping: backtest recommendation → SymbolScanSettings
# ---------------------------------------------------------------------------

def test_field_mapping_regime_to_auto_trade_regime():
    """regime → auto_trade_regime"""
    cfg = {"regime": "trend_up", "side": "buy", "min_score": 65, "min_rr": 1.5}
    settings = SymbolScanSettings()
    settings.auto_trade_regime = cfg["regime"]
    assert settings.auto_trade_regime == "trend_up"


def test_field_mapping_side_to_auto_trade_side():
    """side → auto_trade_side"""
    cfg = {"regime": "range", "side": "sell", "min_score": 70, "min_rr": 1.3}
    settings = SymbolScanSettings()
    settings.auto_trade_side = cfg["side"]
    assert settings.auto_trade_side == "sell"


def test_field_mapping_min_score():
    """min_score → min_score (direct)"""
    cfg = {"regime": "trend_down", "side": "sell", "min_score": 75, "min_rr": 2.0}
    settings = SymbolScanSettings()
    settings.min_score = int(cfg["min_score"])
    assert settings.min_score == 75


def test_field_mapping_min_rr_to_min_expected_rr():
    """min_rr → min_expected_rr"""
    cfg = {"regime": "range", "side": "buy", "min_score": 60, "min_rr": 1.8}
    settings = SymbolScanSettings()
    settings.min_expected_rr = float(cfg["min_rr"])
    assert settings.min_expected_rr == 1.8


def test_full_mapping_roundtrip():
    """Verify all 4 fields map correctly from recommendation to settings."""
    rec_cfg = {
        "regime": "trend_up",
        "side": "buy",
        "min_score": 70,
        "min_rr": 1.5,
        "_evidence": "12 lệnh, kỳ vọng +0.35R, PF 1.80, win rate 58.3%",
    }

    settings = SymbolScanSettings()
    settings.backtest = True
    settings.auto_trade_regime = rec_cfg["regime"]
    settings.auto_trade_side = rec_cfg["side"]
    settings.min_score = int(rec_cfg["min_score"])
    settings.min_expected_rr = float(rec_cfg["min_rr"])

    assert settings.backtest is True
    assert settings.auto_trade_regime == "trend_up"
    assert settings.auto_trade_side == "buy"
    assert settings.min_score == 70
    assert settings.min_expected_rr == 1.5


def test_symbol_scan_settings_defaults():
    """SymbolScanSettings has sensible defaults."""
    s = SymbolScanSettings()
    assert s.backtest is False
    assert s.min_score == 0
    assert s.auto_trade_regime == ""
    assert s.auto_trade_side == ""
    assert s.min_expected_rr == 1.3


# ---------------------------------------------------------------------------
# 4. _normalize_trades — handles edge cases
# ---------------------------------------------------------------------------

def test_normalize_trades_handles_missing_fields():
    raw = [{"symbol": "EUR/USD"}]  # minimal
    normalized = _normalize_trades(raw)
    assert len(normalized) == 1
    t = normalized[0]
    assert t["symbol"] == "EUR/USD"
    assert t["side"] == ""
    assert t["market_regime"] == ""
    assert t["signal_score"] == 0
    assert t["final_score"] == 0
    assert t["expected_effective_rr"] is None
    assert t["result"] == ""
    assert t["result_r"] == 0.0


def test_normalize_trades_filters_non_dicts():
    raw = [{"symbol": "EUR/USD", "side": "buy"}, "not_a_dict", None, 42]
    normalized = _normalize_trades(raw)
    assert len(normalized) == 1
    assert normalized[0]["symbol"] == "EUR/USD"


# ---------------------------------------------------------------------------
# 5. build_fallback_scenario — synthetic scenario when analysis has no plan
# ---------------------------------------------------------------------------

class FakeCandle:
    def __init__(self, close):
        self.close = close
        self.time = None


def _make_fallback_analysis(best_side="buy", atr_h4=0.0050, regime="trend_up"):
    return {
        "decision_summary": {"best_side": best_side, "best_score": 55},
        "technical": {"atr_h4": atr_h4},
        "market_regime": {"primary": regime},
    }


def test_fallback_creates_buy_scenario():
    analysis = _make_fallback_analysis(best_side="buy", atr_h4=0.0050)
    candle = FakeCandle(close=1.0800)
    scenario = build_fallback_scenario(analysis, candle)

    assert scenario is not None
    assert scenario["type"] == "buy"
    assert scenario["entry_status"] == "watch_zone"
    assert scenario["_fallback"] is True
    assert len(scenario["entry_zone"]) == 2
    assert scenario["entry_zone"][0] < scenario["entry_zone"][1]
    assert scenario["stop_loss"] < 1.0800  # SL below price for buy
    assert scenario["take_profit"][0] > 1.0800  # TP above price for buy


def test_fallback_creates_sell_scenario():
    analysis = _make_fallback_analysis(best_side="sell", atr_h4=0.0050)
    candle = FakeCandle(close=1.0800)
    scenario = build_fallback_scenario(analysis, candle)

    assert scenario is not None
    assert scenario["type"] == "sell"
    assert scenario["stop_loss"] > 1.0800  # SL above price for sell
    assert scenario["take_profit"][0] < 1.0800  # TP below price for sell


def test_fallback_returns_none_for_neutral():
    analysis = _make_fallback_analysis(best_side="neutral")
    candle = FakeCandle(close=1.0800)
    assert build_fallback_scenario(analysis, candle) is None


def test_fallback_returns_none_for_invalid_side():
    analysis = _make_fallback_analysis(best_side="hold")
    candle = FakeCandle(close=1.0800)
    assert build_fallback_scenario(analysis, candle) is None


def test_fallback_uses_default_atr_when_zero():
    analysis = _make_fallback_analysis(best_side="buy", atr_h4=0)
    candle = FakeCandle(close=1.0800)
    scenario = build_fallback_scenario(analysis, candle)
    assert scenario is not None
    # Should use fallback ATR ~0.3% of price
    assert scenario["stop_loss"] < 1.0800


def test_fallback_no_atr_uses_price_fallback():
    analysis = {
        "decision_summary": {"best_side": "buy"},
        "technical": {},
    }
    candle = FakeCandle(close=1.0800)
    scenario = build_fallback_scenario(analysis, candle)
    assert scenario is not None
    assert scenario["stop_loss"] < 1.0800


def test_fallback_scenario_passes_standard_gate():
    """Fallback scenario should pass trade_open_block_reason."""
    analysis = _make_fallback_analysis(best_side="buy")
    analysis.update({
        "trade_gate": {"allowed": True},
        "trade_permission": {"status": "caution"},
        "decision_engine": {"decision": "AGGRESSIVE_SETUP"},
    })
    candle = FakeCandle(close=1.0800)
    scenario = build_fallback_scenario(analysis, candle)
    assert scenario is not None
    assert trade_open_block_reason(analysis, scenario, min_final_score=0) is None


def test_fallback_scenario_blocked_by_score():
    """min_final_score filter still applies to fallback scenarios."""
    analysis = _make_fallback_analysis(best_side="buy")
    analysis.update({
        "trade_gate": {"allowed": True},
        "trade_permission": {"status": "allowed"},
        "decision_engine": {"decision": "READY_TO_TRADE"},
        "final_score": 55,
    })
    candle = FakeCandle(close=1.0800)
    scenario = build_fallback_scenario(analysis, candle)
    assert scenario is not None
    assert trade_open_block_reason(analysis, scenario, min_final_score=60) == "blocked_by_score"


def test_fallback_handles_invalid_candle():
    analysis = _make_fallback_analysis()
    assert build_fallback_scenario(analysis, None) is None
    assert build_fallback_scenario(analysis, "not_a_candle") is None


def test_fallback_entry_zone_reasonable_size():
    """Entry zone should be ATR * 0.5 wide (0.25 each side)."""
    analysis = _make_fallback_analysis(atr_h4=0.0040)
    candle = FakeCandle(close=1.0800)
    scenario = build_fallback_scenario(analysis, candle)
    zone_low, zone_high = scenario["entry_zone"]
    # zone should be roughly 0.0010 wide (0.0005 each side)
    assert 0.0005 < (zone_high - zone_low) < 0.0030


def test_select_trade_scenario_still_works_with_normal_scenarios():
    """select_trade_scenario should work normally when analysis has scenarios."""
    analysis = {
        "decision_summary": {"best_side": "buy"},
        "scenarios": [
            {"type": "buy", "entry_status": "confirmed_entry",
             "stop_loss": 1.0750, "take_profit": [1.0900]},
        ],
    }
    scenario = select_trade_scenario(analysis)
    assert scenario is not None
    assert scenario["type"] == "buy"


def test_select_trade_scenario_fallback_not_automatic():
    """select_trade_scenario should NOT auto-fallback — that's the caller's job."""
    analysis = {
        "decision_summary": {"best_side": "buy"},
        "scenarios": [],  # empty
    }
    # select_trade_scenario doesn't call build_fallback_scenario itself
    assert select_trade_scenario(analysis) is None
