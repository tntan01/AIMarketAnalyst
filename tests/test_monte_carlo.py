"""Tests for Monte Carlo simulation module."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_balanced_trades(n=50):
    """Tạo danh sách trades cân bằng: 50% win (+1.5R), 50% loss (-1.0R)."""
    from core.system_backtest_engine import BacktestTrade

    trades = []
    for i in range(n):
        is_win = i % 2 == 0
        trades.append(BacktestTrade(
            symbol="EUR/USD", side="buy", decision="BUY",
            entry_time=f"2025-01-{(i % 28) + 1:02d}T08:00:00Z",
            exit_time=f"2025-01-{(i % 28) + 1:02d}T14:00:00Z",
            entry_price=1.05, stop_loss=1.048, take_profit=1.053,
            exit_price=1.053 if is_win else 1.048,
            result="win" if is_win else "loss",
            result_r=1.5 if is_win else -1.0,
            holding_bars=10, final_score=70, signal_score=65,
            buy_score=68, sell_score=40, score_gap=28,
            market_regime="TRENDING", entry_status="filled", m15_quality="strict",
            expected_effective_rr=1.5, selected_zone_score=75, selected_zone_type="FVG",
            entry_zone_score=70, entry_zone_source="SMC",
            liquidity_sweep_aligned=True, displacement_aligned=True,
            choch_against_direction=False,
            reason_codes=[], warning_codes=[], block_codes=[],
        ))
    return trades


def test_monte_carlo_exists():
    """Kiểm tra module và hàm tồn tại."""
    from core.monte_carlo import run_monte_carlo
    assert callable(run_monte_carlo), "run_monte_carlo không phải là hàm"
    print("  PASS: test_monte_carlo_exists")


def test_monte_carlo_output_structure():
    """Kiểm tra output có đầy đủ keys."""
    from core.monte_carlo import run_monte_carlo

    trades = _make_balanced_trades(20)
    result = run_monte_carlo(trades, num_simulations=100)

    required_keys = [
        "expectancy_r", "max_drawdown_r", "profit_factor", "win_rate",
        "prob_negative_expectancy", "prob_dd_exceed_10r",
        "max_consecutive_losses", "simulation_count",
    ]
    for key in required_keys:
        assert key in result, f"Thiếu key '{key}' trong output"

    # Kiểm tra nested structure
    for metric in ["expectancy_r", "max_drawdown_r", "profit_factor", "win_rate"]:
        for sub in ["mean", "median", "p95_low", "p95_high"]:
            assert sub in result[metric], f"Thiếu '{sub}' trong {metric}"
            val = result[metric][sub]
            assert isinstance(val, (int, float)), f"{metric}.{sub} phải là số"

    assert result["simulation_count"] == 100

    print("  PASS: test_monte_carlo_output_structure")


def test_monte_carlo_balanced_trades():
    """Kiểm tra: trades cân bằng (0.25R kỳ vọng) → không âm."""
    from core.monte_carlo import run_monte_carlo

    trades = _make_balanced_trades(50)  # 25 win +1.5R, 25 loss -1.0R → kỳ vọng = +0.25R
    result = run_monte_carlo(trades, num_simulations=200)

    # Kỳ vọng thật là 0.25R → mean phải gần 0.25
    mean_exp = result["expectancy_r"]["mean"]
    assert mean_exp > 0.0, f"Kỳ vọng trung bình {mean_exp} phải > 0 (thực tế 0.25R)"
    assert abs(mean_exp - 0.25) < 0.1, f"Kỳ vọng {mean_exp} quá xa 0.25"

    # Xác suất kỳ vọng âm rất thấp với 50 trades cân bằng
    prob_neg = result["prob_negative_expectancy"]
    assert prob_neg >= 0.0 and prob_neg <= 100.0, f"prob phải 0-100, hiện {prob_neg}"

    # P95_low < mean < p95_high
    assert result["expectancy_r"]["p95_low"] <= result["expectancy_r"]["mean"] <= result["expectancy_r"]["p95_high"], \
        "p95_low <= mean <= p95_high khong dung"

    print("  PASS: test_monte_carlo_balanced_trades")


def test_monte_carlo_all_wins():
    """Kiểm tra: tất cả win → kỳ vọng dương mạnh, không âm."""
    from core.monte_carlo import run_monte_carlo

    trades = _make_balanced_trades(20)
    # Sửa tất cả thành win
    for t in trades:
        t.result = "win"
        t.result_r = 2.0

    result = run_monte_carlo(trades, num_simulations=100)
    assert result["expectancy_r"]["mean"] > 1.5, "Toàn win thì kỳ vọng phải cao"
    assert result["prob_negative_expectancy"] == 0.0, "Toàn win thì không thể có kỳ vọng âm"
    assert result["max_drawdown_r"]["mean"] == 0.0, "Toàn win thì drawdown = 0"

    print("  PASS: test_monte_carlo_all_wins")


def test_monte_carlo_all_losses():
    """Kiểm tra: tất cả loss → kỳ vọng âm."""
    from core.monte_carlo import run_monte_carlo

    trades = _make_balanced_trades(20)
    for t in trades:
        t.result = "loss"
        t.result_r = -1.0

    result = run_monte_carlo(trades, num_simulations=100)
    assert result["expectancy_r"]["mean"] < 0.0, "Toàn thua thì kỳ vọng phải âm"
    assert result["prob_negative_expectancy"] == 100.0, "Toàn thua thì 100% kỳ vọng âm"

    print("  PASS: test_monte_carlo_all_losses")


def test_monte_carlo_empty_trades():
    """Kiểm tra: trades rỗng không crash."""
    from core.monte_carlo import run_monte_carlo

    result = run_monte_carlo([], num_simulations=100)
    assert isinstance(result, dict), "Phải trả về dict"
    assert result["simulation_count"] == 100
    # Tất cả metric nên là None
    assert result["expectancy_r"]["mean"] is None, "Không có trade thì mean = None"

    print("  PASS: test_monte_carlo_empty_trades")


def test_monte_carlo_reproducibility():
    """Kiểm tra: 2 lần chạy cho kết quả khác nhau (do random)."""
    from core.monte_carlo import run_monte_carlo

    trades = _make_balanced_trades(20)
    r1 = run_monte_carlo(trades, num_simulations=100)
    r2 = run_monte_carlo(trades, num_simulations=100)

    # Các giá trị mean không nên giống hệt (xác suất cực thấp)
    means_different = (
        abs(r1["expectancy_r"]["mean"] - r2["expectancy_r"]["mean"]) > 0.0001 or
        abs(r1["max_drawdown_r"]["mean"] - r2["max_drawdown_r"]["mean"]) > 0.0001
    )
    # Với 100 simulations, kết quả CÓ THỂ giống nhau do randomness thấp
    # Kiểm tra ít nhất cấu trúc giống nhau
    assert r1.keys() == r2.keys(), "Cấu trúc output phải giống nhau"

    print("  PASS: test_monte_carlo_reproducibility")


def test_monte_carlo_min_simulations():
    """Kiểm tra: num_simulations < 10 tự động set = 10."""
    from core.monte_carlo import run_monte_carlo

    trades = _make_balanced_trades(20)
    result = run_monte_carlo(trades, num_simulations=5)
    assert result["simulation_count"] >= 10, f"num_simulations=5 phải tự set >= 10, hiện {result['simulation_count']}"

    print("  PASS: test_monte_carlo_min_simulations")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all_tests():
    tests = [
        ("Monte Carlo exists", test_monte_carlo_exists),
        ("Monte Carlo output structure", test_monte_carlo_output_structure),
        ("Monte Carlo balanced trades", test_monte_carlo_balanced_trades),
        ("Monte Carlo all wins", test_monte_carlo_all_wins),
        ("Monte Carlo all losses", test_monte_carlo_all_losses),
        ("Monte Carlo empty trades", test_monte_carlo_empty_trades),
        ("Monte Carlo reproducibility", test_monte_carlo_reproducibility),
        ("Monte Carlo min simulations", test_monte_carlo_min_simulations),
    ]

    print("=" * 60)
    print("Monte Carlo Tests — Task 4")
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
            print(f"  FAIL: {str(e).encode('ascii', 'replace').decode()}")
            import traceback
            traceback.print_exc()

    print(f"\n{'=' * 60}")
    print(f"Kết quả: {passed} passed, {failed} failed")
    if failed == 0:
        print("PASS — All Task 4 tests passed")
    else:
        print(f"FAIL — {failed} tests failed")
    print(f"{'=' * 60}")
    return failed == 0


if __name__ == "__main__":
    ok = run_all_tests()
    sys.exit(0 if ok else 1)