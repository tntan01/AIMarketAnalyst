"""Tests for auto-trade candidate logic: Branch A vs Branch B.

Branch A (no backtest config): requires scanner_action == "ready"
Branch B (backtest config): checks filters only, ignores scanner_action entirely.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_row(**overrides) -> dict:
    row = {
        "symbol": "EUR/USD",
        "broker_symbol": "EURUSD",
        "scanner_action": "stand_aside",
        "scanner_group": "stand_aside",
        "trade_permission": "caution",
        "best_side": "buy",
        "best_score": 68,
        "final_score": 68,
        "market_regime": "range",
        "expected_effective_rr": 2.5,
        "journal_feedback": {},
        "analysis_result": {
            "scenarios": [
                {
                    "type": "buy",
                    "entry_zone": [1.0850, 1.0875],
                    "stop_loss": 1.0820,
                    "take_profit": [1.0920],
                    "risk_reward": "1:2.5",
                    "position_sizing": {"suggested_lot": 0.1},
                }
            ]
        },
    }
    row.update(overrides)
    return row


def _make_controller():
    from controllers.scanner_controller import ScannerController
    return ScannerController.__new__(ScannerController)


# ---------------------------------------------------------------------------
# Test 1: Branch A — stand_aside with no config → fails
# ---------------------------------------------------------------------------

def test_branch_a_stand_aside_fails():
    ctrl = _make_controller()
    row = _make_row(scanner_action="stand_aside", trade_permission="allowed")
    result = ctrl._is_auto_trade_candidate(row, None)
    assert result is False, "Branch A: stand_aside should NOT auto-trade"
    print("  PASS")


# ---------------------------------------------------------------------------
# Test 2: Branch A — ready + allowed → passes
# ---------------------------------------------------------------------------

def test_branch_a_ready_passes():
    ctrl = _make_controller()
    row = _make_row(scanner_action="ready", trade_permission="allowed")
    result = ctrl._is_auto_trade_candidate(row, None)
    assert result is True, "Branch A: ready + allowed should auto-trade"
    print("  PASS")


# ---------------------------------------------------------------------------
# Test 3: Branch A — watch with no config → fails
# ---------------------------------------------------------------------------

def test_branch_a_watch_fails():
    ctrl = _make_controller()
    row = _make_row(scanner_action="watch", trade_permission="allowed")
    result = ctrl._is_auto_trade_candidate(row, None)
    assert result is False, "Branch A: watch should NOT auto-trade"
    print("  PASS")


# ---------------------------------------------------------------------------
# Test 4: Branch B — stand_aside with matching config → passes!
# ---------------------------------------------------------------------------

def test_branch_b_stand_aside_passes():
    ctrl = _make_controller()
    row = _make_row(scanner_action="stand_aside")
    cfg = {"regime": "range", "side": "buy", "min_rr": 2.0, "min_score": 65}
    result = ctrl._is_auto_trade_candidate(row, cfg)
    assert result is True, "Branch B: stand_aside with matching filters should pass"
    print("  PASS")


# ---------------------------------------------------------------------------
# Test 5: Branch B — watch with matching config → passes
# ---------------------------------------------------------------------------

def test_branch_b_watch_passes():
    ctrl = _make_controller()
    row = _make_row(scanner_action="watch")
    cfg = {"regime": "range", "side": "buy", "min_rr": 2.0, "min_score": 65}
    result = ctrl._is_auto_trade_candidate(row, cfg)
    assert result is True, "Branch B: watch with matching filters should pass"
    print("  PASS")


# ---------------------------------------------------------------------------
# Test 6: Branch B — wait with matching config → passes
# ---------------------------------------------------------------------------

def test_branch_b_wait_passes():
    ctrl = _make_controller()
    row = _make_row(scanner_action="wait")
    cfg = {"regime": "range", "side": "buy", "min_rr": 2.0, "min_score": 65}
    result = ctrl._is_auto_trade_candidate(row, cfg)
    assert result is True, "Branch B: wait with matching filters should pass"
    print("  PASS")


# ---------------------------------------------------------------------------
# Test 7: Branch B — regime mismatch → fails
# ---------------------------------------------------------------------------

def test_branch_b_regime_mismatch():
    ctrl = _make_controller()
    row = _make_row(market_regime="trend_up")
    cfg = {"regime": "range", "side": "buy", "min_rr": 2.0}
    result = ctrl._is_auto_trade_candidate(row, cfg)
    assert result is False, "Branch B: wrong regime should fail"
    print("  PASS")


# ---------------------------------------------------------------------------
# Test 8: Branch B — side=buy forces buy trade, even if best_side=sell
#          (config "side" is an override, not a filter)
# ---------------------------------------------------------------------------

def test_branch_b_side_override():
    ctrl = _make_controller()
    # Pipeline says sell, but config says buy → overrides to buy
    row = _make_row(best_side="sell")
    cfg = {"regime": "range", "side": "buy", "min_rr": 2.0}
    result = ctrl._is_auto_trade_candidate(row, cfg)
    # Should pass because config overrides side to "buy" and a buy scenario exists
    assert result is True, "Branch B: side config overrides best_side, should find buy scenario"
    print("  PASS")


# ---------------------------------------------------------------------------
# Test 9: Branch B — side=buy but no buy scenario -> falls back to best_side
# ---------------------------------------------------------------------------

def test_branch_b_side_override_fallback():
    ctrl = _make_controller()
    # Config forces "buy" but only "sell" scenario exists
    # _best_scenario falls back to best_side ("sell") if forced side not found
    row = _make_row(best_side="sell", analysis_result={"scenarios": [
        {"type": "sell", "entry_zone": [1.0900, 1.0920], "stop_loss": 1.0950,
         "take_profit": [1.0850], "risk_reward": "1:2.0", "position_sizing": {"suggested_lot": 0.1}}
    ]})
    cfg = {"regime": "range", "side": "buy", "min_rr": 2.0}
    result = ctrl._is_auto_trade_candidate(row, cfg)
    # Falls back to best_side="sell" scenario -> passes
    assert result is True, "Branch B: side=buy no scenario -> falls back to best_side sell -> should pass"
    print("  PASS")


# ---------------------------------------------------------------------------
# Test 10: Branch B — RR too low -> fails
# ---------------------------------------------------------------------------

def test_branch_b_rr_too_low():
    ctrl = _make_controller()
    row = _make_row(expected_effective_rr=1.2)
    cfg = {"regime": "range", "side": "buy", "min_rr": 2.0}
    result = ctrl._is_auto_trade_candidate(row, cfg)
    assert result is False, "Branch B: RR too low should fail"
    print("  PASS")


# ---------------------------------------------------------------------------
# Test 10: Branch B — score too low → fails
# ---------------------------------------------------------------------------

def test_branch_b_score_too_low():
    ctrl = _make_controller()
    row = _make_row(best_score=50, final_score=50)
    cfg = {"regime": "range", "side": "buy", "min_score": 65}
    result = ctrl._is_auto_trade_candidate(row, cfg)
    assert result is False, "Branch B: score too low should fail"
    print("  PASS")


# ---------------------------------------------------------------------------
# Test 11: Branch B — blocked permission → fails (regardless of config)
# ---------------------------------------------------------------------------

def test_branch_b_blocked_fails():
    ctrl = _make_controller()
    row = _make_row(trade_permission="blocked")
    cfg = {"regime": "range", "side": "buy", "min_rr": 2.0, "min_score": 65}
    result = ctrl._is_auto_trade_candidate(row, cfg)
    assert result is False, "Branch B: blocked permission should fail"
    print("  PASS")


# ---------------------------------------------------------------------------
# Test 12: Branch B — blocked scanner_group → fails
# ---------------------------------------------------------------------------

def test_branch_b_scanner_group_blocked():
    ctrl = _make_controller()
    row = _make_row(scanner_group="blocked")
    cfg = {"regime": "range", "side": "buy", "min_rr": 2.0, "min_score": 65}
    result = ctrl._is_auto_trade_candidate(row, cfg)
    assert result is False, "Branch B: blocked scanner_group should fail"
    print("  PASS")


# ---------------------------------------------------------------------------
# Test 13: Branch B — empty config returns None → Branch A fallback
# ---------------------------------------------------------------------------

def test_empty_config_falls_to_branch_a():
    from core.scanner import ScannerRequest
    ctrl = _make_controller()

    # No filters set → _auto_trade_config returns None
    req = ScannerRequest(
        symbols=["EUR/USD"], account_balance=10000, risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh",
        symbol_auto_trade={"EUR/USD": {"regime": "", "side": "", "min_rr": 0}},
        thresholds={}, min_scores={},
    )
    at_cfg = ctrl._auto_trade_config(req, "EUR/USD")
    assert at_cfg is None, "Empty filters → should return None → Branch A"
    print("  PASS")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all_tests():
    tests = [
        ("Branch A: stand_aside fails", test_branch_a_stand_aside_fails),
        ("Branch A: ready passes", test_branch_a_ready_passes),
        ("Branch A: watch fails", test_branch_a_watch_fails),
        ("Branch B: stand_aside passes", test_branch_b_stand_aside_passes),
        ("Branch B: watch passes", test_branch_b_watch_passes),
        ("Branch B: wait passes", test_branch_b_wait_passes),
        ("Branch B: regime mismatch", test_branch_b_regime_mismatch),
        ("Branch B: side override", test_branch_b_side_override),
        ("Branch B: side override fallback", test_branch_b_side_override_fallback),
        ("Branch B: RR too low", test_branch_b_rr_too_low),
        ("Branch B: score too low", test_branch_b_score_too_low),
        ("Branch B: blocked permission", test_branch_b_blocked_fails),
        ("Branch B: scanner_group blocked", test_branch_b_scanner_group_blocked),
        ("Empty config -> Branch A", test_empty_config_falls_to_branch_a),
    ]

    print("=" * 60)
    print("Auto-Trade Branch A/B Tests")
    print("=" * 60)

    passed = 0
    failed = 0
    for name, test_fn in tests:
        try:
            print(f"\n[{name}]")
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  FAIL: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'=' * 60}")
    return failed == 0


if __name__ == "__main__":
    ok = run_all_tests()
    sys.exit(0 if ok else 1)
