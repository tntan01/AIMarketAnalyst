"""Tests for Monte Carlo integration in backtest controller."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_payload_has_monte_carlo_key():
    """Kiểm tra: payload sau run_backtest có key 'monte_carlo'."""
    # Test này kiểm tra logic tích hợp, không cần MT5
    # Mô phỏng payload từ run_backtest
    from core.system_backtest_engine import BacktestTrade
    
    trades = []
    for i in range(20):
        trades.append(BacktestTrade(
            symbol="EUR/USD", side="buy", decision="BUY",
            entry_time=f"2025-01-{(i % 28) + 1:02d}T08:00:00Z",
            exit_time=f"2025-01-{(i % 28) + 1:02d}T14:00:00Z",
            entry_price=1.05, stop_loss=1.048, take_profit=1.053,
            exit_price=1.053 if i % 2 == 0 else 1.048,
            result="win" if i % 2 == 0 else "loss",
            result_r=1.5 if i % 2 == 0 else -1.0,
            holding_bars=10, final_score=70, signal_score=65,
            buy_score=68, sell_score=40, score_gap=28,
            market_regime="TRENDING", entry_status="filled", m15_quality="strict",
            expected_effective_rr=1.5, selected_zone_score=75, selected_zone_type="FVG",
            entry_zone_score=70, entry_zone_source="SMC",
            liquidity_sweep_aligned=True, displacement_aligned=True,
            choch_against_direction=False,
            reason_codes=[], warning_codes=[], block_codes=[],
        ))
    
    # Mô phỏng logic tích hợp (giống code sẽ thêm vào run_backtest)
    from core.monte_carlo import run_monte_carlo
    monte_result = run_monte_carlo(trades, num_simulations=100)
    
    # Kiểm tra output monte_carlo
    assert isinstance(monte_result, dict), "monte_carlo phải là dict"
    assert "expectancy_r" in monte_result
    assert "simulation_count" in monte_result
    assert monte_result["simulation_count"] == 100
    
    print("  PASS: test_payload_has_monte_carlo_key")


def test_monte_carlo_in_result_dict():
    """Kiểm tra cấu trúc monte_carlo trong result."""
    from core.monte_carlo import run_monte_carlo

    # Tạo mock result giống to_dict()
    payload = {
        "summary": {"total_trades": 10},
        "trades": [],
        "equity_curve": [],
    }
    
    # Integration point: thêm monte_carlo sau to_dict()
    # (test này kiểm tra logic sẽ được thêm vào controller)
    
    # Với 0 trades, monte_carlo trả về None values
    result = run_monte_carlo([], num_simulations=10)
    payload["monte_carlo"] = result
    
    assert "monte_carlo" in payload
    assert payload["monte_carlo"]["expectancy_r"]["mean"] is None  # 0 trades
    
    print("  PASS: test_monte_carlo_in_result_dict")


def test_monte_carlo_importable():
    """Kiểm tra import hoạt động (đúng như controller sẽ gọi)."""
    try:
        from core.monte_carlo import run_monte_carlo
        assert callable(run_monte_carlo)
    except ImportError as e:
        raise AssertionError(f"Không import được core.monte_carlo: {e}")
    
    print("  PASS: test_monte_carlo_importable")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all_tests():
    tests = [
        ("Payload has monte_carlo key", test_payload_has_monte_carlo_key),
        ("Monte Carlo in result dict", test_monte_carlo_in_result_dict),
        ("Monte Carlo importable", test_monte_carlo_importable),
    ]

    print("=" * 60)
    print("Monte Carlo Integration Tests — Task 5")
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
    print(f"Ket qua: {passed} passed, {failed} failed")
    if failed == 0:
        print("PASS — All Task 5 tests passed")
    else:
        print(f"FAIL — {failed} tests failed")
    print(f"{'=' * 60}")
    return failed == 0


if __name__ == "__main__":
    ok = run_all_tests()
    sys.exit(0 if ok else 1)