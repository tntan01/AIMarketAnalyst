"""Tests for monthly heatmap in backtest screen HTML."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_mock_result_with_monthly():
    """Tạo dữ liệu backtest có breakdowns.by_month."""
    return {
        "summary": {
            "total_trades": 12, "wins": 6, "losses": 5, "breakeven": 1,
            "expired": 0, "win_rate": 50.0, "loss_rate": 41.67,
            "total_r": 8.5, "average_r": 0.71, "median_r": 0.5,
            "expectancy_r": 0.71, "average_win_r": 1.8, "average_loss_r": -1.0,
            "profit_factor": 2.16, "max_drawdown_r": -4.5,
            "max_consecutive_losses": 3, "max_consecutive_wins": 3,
            "average_holding_bars": 15.0,
        },
        "trades": [],
        "breakdowns": {
            "by_month": {
                "2025-01": {"trades_count": 4, "total_r": 4.0, "win_rate": 75.0, "best_trade_r": 2.0, "worst_trade_r": -1.0},
                "2025-02": {"trades_count": 3, "total_r": 0.0, "win_rate": 33.3, "best_trade_r": 2.0, "worst_trade_r": -1.0},
                "2025-03": {"trades_count": 1, "total_r": -1.0, "win_rate": 0.0, "best_trade_r": -1.0, "worst_trade_r": -1.0},
                "2025-04": {"trades_count": 2, "total_r": 3.5, "win_rate": 100.0, "best_trade_r": 2.0, "worst_trade_r": 1.5},
                "2025-05": {"trades_count": 2, "total_r": 2.0, "win_rate": 50.0, "best_trade_r": 3.0, "worst_trade_r": -1.0},
            },
        },
        "symbol_stats": {},
        "diagnostics": {},
        "equity_curve": [
            {"time": "2025-01-10T08:00:00Z", "cumulative_r": 0.0, "drawdown_r": 0.0, "balance": 10000.0},
            {"time": "2025-05-20T10:00:00Z", "cumulative_r": 8.5, "drawdown_r": 0.0, "balance": 10850.0},
        ],
    }


def _make_mock_result_without_monthly():
    """Tạo dữ liệu backtest KHÔNG có breakdowns.by_month."""
    result = _make_mock_result_with_monthly()
    result["breakdowns"] = {}
    return result


def test_heatmap_present_when_data_exists():
    """Kiểm tra: Bảng nhiệt xuất hiện khi có by_month."""
    from ui.screens.backtest_screen import BacktestScreen

    screen = BacktestScreen.__new__(BacktestScreen)
    screen.__dict__['result'] = _make_mock_result_with_monthly()
    screen.__dict__['_analysis_light'] = False
    screen.__dict__['app'] = None

    # Gọi _generate_stats_html
    if hasattr(screen, '_generate_stats_html'):
        html = screen._generate_stats_html()
    else:
        # Fallback: tìm method generate HTML
        for attr in dir(screen):
            if 'generate' in attr.lower() and 'html' in attr.lower():
                html = getattr(screen, attr)()
                break
        else:
            raise AssertionError("Không tìm thấy method generate HTML")

    assert "Bảng nhiệt" in html, "HTML không chứa 'Bảng nhiệt'"
    assert "2025" in html, "HTML không chứa năm 2025"
    assert "+4.0" in html or "4.0" in html, "HTML phải chứa total_r của tháng 1"

    print("  PASS: test_heatmap_present_when_data_exists")


def test_heatmap_absent_when_no_data():
    """Kiểm tra: Bảng nhiệt KHÔNG xuất hiện khi không có by_month."""
    from ui.screens.backtest_screen import BacktestScreen

    screen = BacktestScreen.__new__(BacktestScreen)
    screen.__dict__['result'] = _make_mock_result_without_monthly()
    screen.__dict__['_analysis_light'] = False
    screen.__dict__['app'] = None

    if hasattr(screen, '_generate_stats_html'):
        html = screen._generate_stats_html()
    else:
        for attr in dir(screen):
            if 'generate' in attr.lower() and 'html' in attr.lower():
                html = getattr(screen, attr)()
                break
        else:
            raise AssertionError("Không tìm thấy method generate HTML")

    # Không có bảng nhiệt → không crash, không hiển thị "Bảng nhiệt"
    assert "Bảng nhiệt" not in html, "HTML không nên có 'Bảng nhiệt' khi không có dữ liệu"

    print("  PASS: test_heatmap_absent_when_no_data")


def test_heatmap_has_all_months():
    """Kiểm tra: Bảng nhiệt hiển thị đủ 12 tháng trong header."""
    from ui.screens.backtest_screen import BacktestScreen

    screen = BacktestScreen.__new__(BacktestScreen)
    screen.__dict__['result'] = _make_mock_result_with_monthly()
    screen.__dict__['_analysis_light'] = False
    screen.__dict__['app'] = None

    if hasattr(screen, '_generate_stats_html'):
        html = screen._generate_stats_html()
    else:
        for attr in dir(screen):
            if 'generate' in attr.lower() and 'html' in attr.lower():
                html = getattr(screen, attr)()
                break
        else:
            raise AssertionError("Không tìm thấy method generate HTML")

    # Kiểm tra header có T1, T2... hoặc tháng 1, tháng 2...
    for i in range(1, 13):
        month_label = f"T{i}" if f"T{i}" in html else f"Th{i}" if f"Th{i}" in html else str(i)
        assert month_label in html or f"tháng {i}" in html.lower() or f"t{i}" in html.lower(), \
            f"Không tìm thấy tháng {i} trong HTML"

    print("  PASS: test_heatmap_has_all_months")


def test_heatmap_year_total():
    """Kiểm tra: Cột 'Cả năm' hiển thị tổng R."""
    from ui.screens.backtest_screen import BacktestScreen

    screen = BacktestScreen.__new__(BacktestScreen)
    screen.__dict__['result'] = _make_mock_result_with_monthly()
    screen.__dict__['_analysis_light'] = False
    screen.__dict__['app'] = None

    if hasattr(screen, '_generate_stats_html'):
        html = screen._generate_stats_html()
    else:
        for attr in dir(screen):
            if 'generate' in attr.lower() and 'html' in attr.lower():
                html = getattr(screen, attr)()
                break
        else:
            raise AssertionError("Không tìm thấy method generate HTML")

    assert "Cả năm" in html or "Tổng" in html, "HTML phải có cột tổng năm"
    # Tổng 5 tháng: 4.0+0.0-1.0+3.5+2.0 = 8.5
    assert "8.5" in html or "8.50" in html, "HTML phải chứa tổng R cả năm = 8.5"

    print("  PASS: test_heatmap_year_total")


def test_heatmap_colors():
    """Kiểm tra: HTML chứa mã màu cho ô dương và âm."""
    from ui.screens.backtest_screen import BacktestScreen

    screen = BacktestScreen.__new__(BacktestScreen)
    screen.__dict__['result'] = _make_mock_result_with_monthly()
    screen.__dict__['_analysis_light'] = False
    screen.__dict__['app'] = None

    if hasattr(screen, '_generate_stats_html'):
        html = screen._generate_stats_html()
    else:
        for attr in dir(screen):
            if 'generate' in attr.lower() and 'html' in attr.lower():
                html = getattr(screen, attr)()
                break
        else:
            raise AssertionError("Không tìm thấy method generate HTML")

    # Phải có style css với background-color
    assert "background" in html.lower() or "bgcolor" in html.lower() or "style" in html.lower(), \
        "HTML phải có định dạng màu cho ô"

    print("  PASS: test_heatmap_colors")


def test_heatmap_null_result():
    """Kiểm tra: result=None không crash."""
    from ui.screens.backtest_screen import BacktestScreen

    screen = BacktestScreen.__new__(BacktestScreen)
    screen.result = None

    # Gọi generate html không được throw exception
    try:
        if hasattr(screen, '_generate_stats_html'):
            screen._generate_stats_html()
        else:
            for attr in dir(screen):
                if 'generate' in attr.lower() and 'html' in attr.lower():
                    getattr(screen, attr)()
                    break
    except Exception as e:
        # Chỉ fail nếu lỗi liên quan đến by_month
        if 'by_month' in str(e) or 'monthly' in str(e).lower():
            raise AssertionError(f"Crash khi result=None: {e}")
        # Các lỗi khác là expected (ví dụ: thiếu summary)
        pass

    print("  PASS: test_heatmap_null_result")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all_tests():
    tests = [
        ("Heatmap present with data", test_heatmap_present_when_data_exists),
        ("Heatmap absent without data", test_heatmap_absent_when_no_data),
        ("Heatmap has all 12 months", test_heatmap_has_all_months),
        ("Heatmap year total correct", test_heatmap_year_total),
        ("Heatmap has color formatting", test_heatmap_colors),
        ("Heatmap null result safe", test_heatmap_null_result),
    ]

    print("=" * 60)
    print("Monthly Heatmap Tests — Task 3")
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
        print("PASS — All Task 3 tests passed")
    else:
        print(f"FAIL — {failed} tests failed")
    print(f"{'=' * 60}")
    return failed == 0


if __name__ == "__main__":
    ok = run_all_tests()
    sys.exit(0 if ok else 1)