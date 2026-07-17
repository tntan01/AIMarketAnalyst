from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_sample_trades():
    """Tạo BacktestTrade mẫu trải đều 3 tháng."""
    from core.system_backtest_engine import BacktestTrade

    trades = []
    # Tháng 1: 3 thắng, 1 thua
    trades.append(BacktestTrade(
        symbol="EUR/USD", side="buy", decision="STRONG_BUY",
        entry_time="2025-01-10T08:00:00Z", exit_time="2025-01-10T14:00:00Z",
        entry_price=1.05200, stop_loss=1.05000, take_profit=1.05500,
        exit_price=1.05500, result="win", result_r=1.5, holding_bars=12,
        final_score=75, signal_score=70, buy_score=72, sell_score=40, score_gap=32,
        market_regime="TRENDING", entry_status="filled", m15_quality="strict",
        expected_effective_rr=1.5, selected_zone_score=80, selected_zone_type="FVG",
        entry_zone_score=75, entry_zone_source="SMC",
        liquidity_sweep_aligned=True, displacement_aligned=True,
        choch_against_direction=False, reason_codes=[], warning_codes=[], block_codes=[],
    ))
    trades.append(BacktestTrade(
        symbol="EUR/USD", side="buy", decision="BUY",
        entry_time="2025-01-15T09:00:00Z", exit_time="2025-01-15T15:00:00Z",
        entry_price=1.05400, stop_loss=1.05200, take_profit=1.05800,
        exit_price=1.05800, result="win", result_r=2.0, holding_bars=8,
        final_score=82, signal_score=78, buy_score=80, sell_score=35, score_gap=45,
        market_regime="TRENDING", entry_status="filled", m15_quality="strict",
        expected_effective_rr=2.0, selected_zone_score=85, selected_zone_type="OB",
        entry_zone_score=80, entry_zone_source="SMC",
        liquidity_sweep_aligned=True, displacement_aligned=True,
        choch_against_direction=False, reason_codes=[], warning_codes=[], block_codes=[],
    ))
    trades.append(BacktestTrade(
        symbol="EUR/USD", side="sell", decision="SELL",
        entry_time="2025-01-20T10:00:00Z", exit_time="2025-01-20T16:00:00Z",
        entry_price=1.06000, stop_loss=1.06200, take_profit=1.05700,
        exit_price=1.05700, result="win", result_r=1.5, holding_bars=10,
        final_score=68, signal_score=65, buy_score=30, sell_score=68, score_gap=38,
        market_regime="RANGING", entry_status="filled", m15_quality="loose",
        expected_effective_rr=1.5, selected_zone_score=70, selected_zone_type="BB",
        entry_zone_score=65, entry_zone_source="SMC",
        liquidity_sweep_aligned=True, displacement_aligned=False,
        choch_against_direction=True, reason_codes=[], warning_codes=[], block_codes=[],
    ))
    trades.append(BacktestTrade(
        symbol="EUR/USD", side="buy", decision="BUY",
        entry_time="2025-01-25T12:00:00Z", exit_time="2025-01-25T18:00:00Z",
        entry_price=1.05500, stop_loss=1.05300, take_profit=1.05900,
        exit_price=1.05300, result="loss", result_r=-1.0, holding_bars=14,
        final_score=55, signal_score=52, buy_score=55, sell_score=42, score_gap=13,
        market_regime="RANGING", entry_status="filled", m15_quality="loose",
        expected_effective_rr=2.0, selected_zone_score=60, selected_zone_type="FVG",
        entry_zone_score=55, entry_zone_source="SMC",
        liquidity_sweep_aligned=False, displacement_aligned=False,
        choch_against_direction=False, reason_codes=[], warning_codes=[], block_codes=[],
    ))

    # Tháng 2: 1 thắng, 2 thua
    trades.append(BacktestTrade(
        symbol="GBP/USD", side="buy", decision="BUY",
        entry_time="2025-02-05T08:00:00Z", exit_time="2025-02-05T14:00:00Z",
        entry_price=1.25200, stop_loss=1.25000, take_profit=1.25600,
        exit_price=1.25600, result="win", result_r=2.0, holding_bars=10,
        final_score=72, signal_score=68, buy_score=70, sell_score=38, score_gap=32,
        market_regime="TRENDING", entry_status="filled", m15_quality="strict",
        expected_effective_rr=2.0, selected_zone_score=78, selected_zone_type="OB",
        entry_zone_score=72, entry_zone_source="SMC",
        liquidity_sweep_aligned=True, displacement_aligned=True,
        choch_against_direction=False, reason_codes=[], warning_codes=[], block_codes=[],
    ))
    trades.append(BacktestTrade(
        symbol="GBP/USD", side="sell", decision="SELL",
        entry_time="2025-02-12T10:00:00Z", exit_time="2025-02-12T16:00:00Z",
        entry_price=1.25800, stop_loss=1.26000, take_profit=1.25400,
        exit_price=1.26000, result="loss", result_r=-1.0, holding_bars=8,
        final_score=48, signal_score=45, buy_score=35, sell_score=50, score_gap=15,
        market_regime="RANGING", entry_status="filled", m15_quality=None,
        expected_effective_rr=2.0, selected_zone_score=55, selected_zone_type="FVG",
        entry_zone_score=50, entry_zone_source="SMC",
        liquidity_sweep_aligned=False, displacement_aligned=False,
        choch_against_direction=True, reason_codes=[], warning_codes=[], block_codes=[],
    ))
    trades.append(BacktestTrade(
        symbol="GBP/USD", side="buy", decision="BUY",
        entry_time="2025-02-20T14:00:00Z", exit_time="2025-02-20T20:00:00Z",
        entry_price=1.25500, stop_loss=1.25300, take_profit=1.25900,
        exit_price=1.25300, result="loss", result_r=-1.0, holding_bars=12,
        final_score=52, signal_score=50, buy_score=52, sell_score=40, score_gap=12,
        market_regime="RANGING", entry_status="filled", m15_quality=None,
        expected_effective_rr=2.0, selected_zone_score=58, selected_zone_type="FVG",
        entry_zone_score=52, entry_zone_source="SMC",
        liquidity_sweep_aligned=False, displacement_aligned=False,
        choch_against_direction=False, reason_codes=[], warning_codes=[], block_codes=[],
    ))

    # Tháng 3: 0 lệnh (không giao dịch)
    return trades


def test_build_monthly_breakdown_exists():
    """Kiểm tra hàm build_monthly_breakdown tồn tại."""
    from core.system_backtest_engine import build_monthly_breakdown
    assert callable(build_monthly_breakdown), "build_monthly_breakdown không phải là hàm"
    print("  PASS: test_build_monthly_breakdown_exists")


def test_build_monthly_breakdown_output():
    """Kiểm tra output có đúng format."""
    from core.system_backtest_engine import build_monthly_breakdown

    trades = _make_sample_trades()
    result = build_monthly_breakdown(trades)

    assert isinstance(result, dict), "Kết quả phải là dict"
    assert len(result) > 0, "Kết quả không được rỗng"

    # Kiểm tra key format "YYYY-MM"
    for key in result:
        assert "-" in key and len(key) == 7, f"Key '{key}' không đúng format YYYY-MM"

    # Kiểm tra mỗi entry có đủ field
    first_entry = list(result.values())[0]
    required_fields = ["trades_count", "total_r", "win_rate", "best_trade_r", "worst_trade_r"]
    for field in required_fields:
        assert field in first_entry, f"Thiếu field '{field}' trong monthly breakdown"

    print("  PASS: test_build_monthly_breakdown_output")


def test_build_monthly_breakdown_values():
    """Kiểm tra giá trị tính toán đúng."""
    from core.system_backtest_engine import build_monthly_breakdown

    trades = _make_sample_trades()
    result = build_monthly_breakdown(trades)

    # Tháng 1: 4 lệnh (3 thắng 1 thua) → total_r = 1.5+2.0+1.5-1.0 = 4.0
    jan = result.get("2025-01")
    assert jan is not None, "Thiếu tháng 2025-01"
    assert jan["trades_count"] == 4, f"Tháng 1 phải có 4 lệnh, hiện {jan['trades_count']}"
    assert abs(jan["total_r"] - 4.0) < 0.01, f"Tháng 1 total_r phải = 4.0, hiện {jan['total_r']}"
    assert abs(jan["win_rate"] - 75.0) < 0.01, f"Tháng 1 win_rate phải = 75%, hiện {jan['win_rate']}"
    assert abs(jan["best_trade_r"] - 2.0) < 0.01, f"Lệnh tốt nhất tháng 1 = 2.0R"
    assert abs(jan["worst_trade_r"] + 1.0) < 0.01, f"Lệnh tệ nhất tháng 1 = -1.0R"

    # Tháng 2: 3 lệnh (1 thắng 2 thua) → total_r = 2.0-1.0-1.0 = 0.0
    feb = result.get("2025-02")
    assert feb is not None, "Thiếu tháng 2025-02"
    assert feb["trades_count"] == 3, f"Tháng 2 phải có 3 lệnh, hiện {feb['trades_count']}"
    assert abs(feb["total_r"] - 0.0) < 0.01, f"Tháng 2 total_r phải = 0.0"

    # Tháng 3: 0 lệnh → không có trong kết quả
    assert "2025-03" not in result, "Tháng 3 không có lệnh, không nên xuất hiện"

    print("  PASS: test_build_monthly_breakdown_values")


def test_by_month_in_breakdowns():
    """Kiểm tra build_breakdowns() có key by_month."""
    from core.system_backtest_engine import build_breakdowns

    trades = _make_sample_trades()
    result = build_breakdowns(trades)

    assert "by_month" in result, "build_breakdowns() thiếu key 'by_month'"
    by_month = result["by_month"]
    assert isinstance(by_month, dict), "by_month phải là dict"
    assert "2025-01" in by_month, "by_month thiếu tháng 2025-01"

    print("  PASS: test_by_month_in_breakdowns")


def test_empty_trades():
    """Kiểm tra với danh sách rỗng."""
    from core.system_backtest_engine import build_monthly_breakdown

    result = build_monthly_breakdown([])
    assert isinstance(result, dict), "Kết quả rỗng vẫn phải là dict"
    assert len(result) == 0, "Dict phải rỗng khi không có trade"

    print("  PASS: test_empty_trades")


def test_duplicate_months():
    """Kiểm tra nhiều lệnh cùng tháng được gộp đúng."""
    from core.system_backtest_engine import build_monthly_breakdown, BacktestTrade

    # 2 lệnh cùng tháng
    t1 = _make_sample_trades()[0]  # Tháng 1
    t2 = _make_sample_trades()[1]  # Tháng 1
    result = build_monthly_breakdown([t1, t2])

    jan = result["2025-01"]
    assert jan["trades_count"] == 2, "Phải gộp 2 lệnh cùng tháng"
    assert abs(jan["total_r"] - 3.5) < 0.01  # 1.5 + 2.0

    print("  PASS: test_duplicate_months")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all_tests():
    tests = [
        ("Monthly breakdown exists", test_build_monthly_breakdown_exists),
        ("Monthly breakdown output", test_build_monthly_breakdown_output),
        ("Monthly breakdown values", test_build_monthly_breakdown_values),
        ("By-month in breakdowns", test_by_month_in_breakdowns),
        ("Empty trades", test_empty_trades),
        ("Duplicate months", test_duplicate_months),
    ]

    print("=" * 60)
    print("Monthly Breakdown Tests — Task 2")
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
    print(f"Kết quả: {passed} passed, {failed} failed")
    if failed == 0:
        print("PASS — All Task 2 tests passed")
    else:
        print(f"FAIL — {failed} tests failed")
    print(f"{'=' * 60}")
    return failed == 0


if __name__ == "__main__":
    ok = run_all_tests()
    sys.exit(0 if ok else 1)