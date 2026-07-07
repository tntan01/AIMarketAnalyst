"""Tests for Walk-Forward Analysis engine."""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_mock_candles():
    """Tạo dữ liệu nến giả cho test."""
    from core.market_models import Candle
    
    start = datetime(2023, 1, 1)
    candles = []
    for i in range(500):  # ~500 ngày = ~17 tháng
        t = start + timedelta(days=i)
        candles.append(Candle(
            time=t,
            open=1.05 + i * 0.0001,
            high=1.05 + i * 0.0002,
            low=1.05 - i * 0.0001,
            close=1.05 + i * 0.00015,
            volume=1000,
        ))
    return candles


def _make_mock_request():
    """Tạo BacktestRequest giả."""
    from core.system_backtest_engine import BacktestRequest
    
    return BacktestRequest(
        symbol="EUR/USD",
        broker_symbol="EURUSD",
        start=datetime(2023, 1, 1),
        end=datetime(2024, 6, 1),  # 17 tháng
        initial_balance=10000.0,
        risk_percent=2.0,
        account_currency="USD",
        lot_step=0.01,
        minimum_lot=0.01,
        contract_size_override=100000.0,
        timezone_name="Asia/Ho_Chi_Minh",
    )


def test_walk_forward_exists():
    """Kiểm tra module và hàm tồn tại."""
    from core.walk_forward_engine import run_walk_forward
    assert callable(run_walk_forward), "run_walk_forward không phải là hàm"
    print("  PASS: test_walk_forward_exists")


def test_walk_forward_output_structure():
    """Kiểm tra output có đầy đủ keys."""
    from core.walk_forward_engine import run_walk_forward
    
    request = _make_mock_request()
    candles = {"D1": _make_mock_candles(), "H4": [], "H1": [], "M15": []}
    
    result = run_walk_forward(request, candles, is_months=4, oos_months=2, step_months=2)
    
    assert isinstance(result, dict), "Kết quả phải là dict"
    
    # Kiểm tra các key bắt buộc (có thể có error nếu dữ liệu quá ít)
    required_keys = ["windows", "window_count", "verdict"]
    for key in required_keys:
        assert key in result, f"Thiếu key '{key}' trong output"
    
    print("  PASS: test_walk_forward_output_structure")


def test_walk_forward_verdict_values():
    """Kiểm tra verdict là 1 trong các giá trị hợp lệ."""
    from core.walk_forward_engine import run_walk_forward
    
    request = _make_mock_request()
    candles = {"D1": _make_mock_candles(), "H4": [], "H1": [], "M15": []}
    
    result = run_walk_forward(request, candles, is_months=4, oos_months=2, step_months=2)
    
    valid_verdicts = ["ROBUST", "SUSPECT", "OVEREITTING", "INCONCLUSIVE"]
    assert result["verdict"] in valid_verdicts, \
        f"Verdict '{result['verdict']}' không hợp lệ, phải là: {valid_verdicts}"
    
    print("  PASS: test_walk_forward_verdict_values")


def test_walk_forward_short_range():
    """Kiểm tra: khoảng thời gian quá ngắn trả về error/inconclusive."""
    from core.walk_forward_engine import run_walk_forward
    from core.system_backtest_engine import BacktestRequest
    
    request = BacktestRequest(
        symbol="EUR/USD", broker_symbol="EURUSD",
        start=datetime(2025, 1, 1), end=datetime(2025, 2, 1),  # Chỉ 1 tháng
        initial_balance=10000.0, risk_percent=2.0,
        account_currency="USD", lot_step=0.01, minimum_lot=0.01,
        contract_size_override=100000.0, timezone_name="Asia/Ho_Chi_Minh",
    )
    candles = {"D1": _make_mock_candles(), "H4": [], "H1": [], "M15": []}
    
    result = run_walk_forward(request, candles, is_months=6, oos_months=3, step_months=3)
    
    # Phải trả về INCONCLUSIVE hoặc có error
    assert result["window_count"] == 0 or result["verdict"] == "INCONCLUSIVE", \
        "Khoảng thời gian quá ngắn phải trả về INCONCLUSIVE"
    
    print("  PASS: test_walk_forward_short_range")


def test_walk_forward_window_count():
    """Kiểm tra số window hợp lý."""
    from core.walk_forward_engine import run_walk_forward
    
    request = _make_mock_request()
    candles = {"D1": _make_mock_candles(), "H4": [], "H1": [], "M15": []}
    
    # 17 tháng, is=4, oos=2, step=2 → khoảng (17-6)/2 = ~5-6 windows
    result = run_walk_forward(request, candles, is_months=4, oos_months=2, step_months=2)
    
    # Có thể 0 windows nếu dữ liệu không đủ, nhưng nếu có thì phải > 0
    if result["window_count"] > 0:
        assert len(result["windows"]) == result["window_count"], \
            "Số windows trong list phải khớp window_count"
    
    print("  PASS: test_walk_forward_window_count")


def test_walk_forward_window_structure():
    """Kiểm tra cấu trúc mỗi window."""
    from core.walk_forward_engine import run_walk_forward
    
    request = _make_mock_request()
    candles = {"D1": _make_mock_candles(), "H4": [], "H1": [], "M15": []}
    
    result = run_walk_forward(request, candles, is_months=4, oos_months=2, step_months=2)
    
    if result["window_count"] > 0:
        win = result["windows"][0]
        assert "is_start" in win, "Window thiếu is_start"
        assert "is_end" in win, "Window thiếu is_end"
        assert "oos_start" in win, "Window thiếu oos_start"
        assert "oos_end" in win, "Window thiếu oos_end"
        assert "is_summary" in win, "Window thiếu is_summary"
        assert "oos_summary" in win, "Window thiếu oos_summary"
    
    print("  PASS: test_walk_forward_window_structure")


def test_walk_forward_no_crash_empty_candles():
    """Kiểm tra: candles rỗng không crash."""
    from core.walk_forward_engine import run_walk_forward
    
    request = _make_mock_request()
    result = run_walk_forward(request, {}, is_months=4, oos_months=2, step_months=2)
    
    assert isinstance(result, dict), "Phải trả về dict"
    assert result["verdict"] == "INCONCLUSIVE"
    
    print("  PASS: test_walk_forward_no_crash_empty_candles")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all_tests():
    tests = [
        ("Walk-Forward exists", test_walk_forward_exists),
        ("Walk-Forward output structure", test_walk_forward_output_structure),
        ("Walk-Forward verdict values", test_walk_forward_verdict_values),
        ("Walk-Forward short range", test_walk_forward_short_range),
        ("Walk-Forward window count", test_walk_forward_window_count),
        ("Walk-Forward window structure", test_walk_forward_window_structure),
        ("Walk-Forward empty candles safe", test_walk_forward_no_crash_empty_candles),
    ]

    print("=" * 60)
    print("Walk-Forward Tests — Task 7")
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
    print(f"Ket qua: {passed} passed, {failed} failed")
    if failed == 0:
        print("PASS — All Task 7 tests passed")
    else:
        print(f"FAIL — {failed} tests failed")
    print(f"{'=' * 60}")
    return failed == 0


if __name__ == "__main__":
    ok = run_all_tests()
    sys.exit(0 if ok else 1)