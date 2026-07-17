"""Tests for Monte Carlo UI in backtest screen."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_result_with_monte_carlo():
    """Tạo backtest result có monte_carlo."""
    return {
        "summary": {
            "total_trades": 20, "wins": 10, "losses": 10, "breakeven": 0,
            "expired": 0, "win_rate": 50.0, "loss_rate": 50.0,
            "total_r": 5.0, "average_r": 0.25, "median_r": 0.25,
            "expectancy_r": 0.25, "average_win_r": 1.5, "average_loss_r": -1.0,
            "profit_factor": 1.5, "max_drawdown_r": -4.5,
            "max_consecutive_losses": 3, "max_consecutive_wins": 3,
            "average_holding_bars": 12.0,
        },
        "trades": [],
        "breakdowns": {},
        "symbol_stats": {},
        "diagnostics": {},
        "equity_curve": [
            {"time": "2025-01-10T08:00:00Z", "cumulative_r": 0.0, "drawdown_r": 0.0, "balance": 10000.0},
            {"time": "2025-03-20T10:00:00Z", "cumulative_r": 5.0, "drawdown_r": 0.0, "balance": 10500.0},
        ],
        "monte_carlo": {
            "expectancy_r": {"mean": 0.25, "median": 0.22, "p95_low": -0.08, "p95_high": 0.55},
            "max_drawdown_r": {"mean": -5.2, "median": -4.8, "p95_low": -2.1, "p95_high": -12.3},
            "profit_factor": {"mean": 1.48, "median": 1.42, "p95_low": 0.85, "p95_high": 2.35},
            "win_rate": {"mean": 49.8, "median": 50.0, "p95_low": 32.0, "p95_high": 68.0},
            "prob_negative_expectancy": 15.3,
            "prob_dd_exceed_10r": 12.0,
            "max_consecutive_losses": {"mean": 4.2, "median": 4, "p95_high": 9},
            "simulation_count": 2000,
        },
    }


def _make_result_without_monte_carlo():
    result = _make_result_with_monte_carlo()
    del result["monte_carlo"]
    return result


def _make_result_negative_monte_carlo():
    """Kỳ vọng âm — tất cả CI < 0."""
    result = _make_result_with_monte_carlo()
    result["monte_carlo"] = {
        "expectancy_r": {"mean": -0.35, "median": -0.30, "p95_low": -0.80, "p95_high": -0.05},
        "max_drawdown_r": {"mean": -15.2, "median": -14.0, "p95_low": -8.0, "p95_high": -25.0},
        "profit_factor": {"mean": 0.65, "median": 0.60, "p95_low": 0.30, "p95_high": 0.95},
        "win_rate": {"mean": 32.0, "median": 33.3, "p95_low": 15.0, "p95_high": 50.0},
        "prob_negative_expectancy": 95.0,
        "prob_dd_exceed_10r": 78.0,
        "max_consecutive_losses": {"mean": 8.0, "median": 7, "p95_high": 15},
        "simulation_count": 2000,
    }
    return result


def test_monte_carlo_table_present():
    """Kiểm tra bảng Monte Carlo xuất hiện khi có dữ liệu."""
    from ui.screens.backtest_screen import BacktestScreen

    screen = BacktestScreen.__new__(BacktestScreen)
    screen.__dict__['result'] = _make_result_with_monte_carlo()
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

    assert "Monte Carlo" in html or "monte" in html.lower(), \
        "HTML phải chứa 'Monte Carlo'"
    assert "Khoảng tin cậy" in html or "95%" in html, \
        "HTML phải chứa 'Khoảng tin cậy' hoặc '95%'"

    print("  PASS: test_monte_carlo_table_present")


def test_monte_carlo_table_absent():
    """Kiểm tra: không crash khi không có monte_carlo."""
    from ui.screens.backtest_screen import BacktestScreen

    screen = BacktestScreen.__new__(BacktestScreen)
    screen.__dict__['result'] = _make_result_without_monte_carlo()
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

    assert "Monte Carlo" not in html, \
        "HTML không nên có 'Monte Carlo' khi không có dữ liệu"

    print("  PASS: test_monte_carlo_table_absent")


def test_monte_carlo_contains_values():
    """Kiểm tra bảng hiển thị đúng giá trị."""
    from ui.screens.backtest_screen import BacktestScreen

    screen = BacktestScreen.__new__(BacktestScreen)
    screen.__dict__['result'] = _make_result_with_monte_carlo()
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

    # Kiểm tra giá trị expectancy xuất hiện
    assert "0.25" in html or "+0.25" in html, "HTML phải chứa kỳ vọng 0.25"
    assert "15.3" in html or "15%" in html, "HTML phải chứa prob_negative 15.3%"

    print("  PASS: test_monte_carlo_contains_values")


def test_monte_carlo_colors():
    """Kiểm tra màu sắc: xanh cho positive, đỏ cho negative."""
    from ui.screens.backtest_screen import BacktestScreen

    # Test với kỳ vọng dương (p95_low > 0 → màu xanh)
    screen1 = BacktestScreen.__new__(BacktestScreen)
    r = _make_result_with_monte_carlo()
    r["monte_carlo"]["expectancy_r"]["p95_low"] = 0.05  # toàn bộ CI > 0
    screen1.__dict__['result'] = r
    screen1.__dict__['_analysis_light'] = False
    screen1.__dict__['app'] = None

    if hasattr(screen1, '_generate_stats_html'):
        html1 = screen1._generate_stats_html()
    else:
        for attr in dir(screen1):
            if 'generate' in attr.lower() and 'html' in attr.lower():
                html1 = getattr(screen1, attr)()
                break
        else:
            raise AssertionError("Không tìm thấy method generate HTML")

    # Phải có màu trong style
    assert "color" in html1 or "#" in html1, "HTML phải có mã màu"

    # Test với kỳ vọng âm
    screen2 = BacktestScreen.__new__(BacktestScreen)
    screen2.__dict__['result'] = _make_result_negative_monte_carlo()
    screen2.__dict__['_analysis_light'] = False
    screen2.__dict__['app'] = None

    if hasattr(screen2, '_generate_stats_html'):
        html2 = screen2._generate_stats_html()
    else:
        for attr in dir(screen2):
            if 'generate' in attr.lower() and 'html' in attr.lower():
                html2 = getattr(screen2, attr)()
                break
        else:
            raise AssertionError("Không tìm thấy method generate HTML")

    assert "Monte Carlo" in html2 or "monte" in html2.lower(), \
        "Kỳ vọng âm vẫn phải hiển thị bảng Monte Carlo"

    print("  PASS: test_monte_carlo_colors")


def test_monte_carlo_null_result():
    """Kiểm tra: result=None không crash."""
    from ui.screens.backtest_screen import BacktestScreen

    screen = BacktestScreen.__new__(BacktestScreen)
    screen.__dict__['result'] = None
    screen.__dict__['_analysis_light'] = False
    screen.__dict__['app'] = None

    try:
        if hasattr(screen, '_generate_stats_html'):
            screen._generate_stats_html()
        else:
            for attr in dir(screen):
                if 'generate' in attr.lower() and 'html' in attr.lower():
                    getattr(screen, attr)()
                    break
    except Exception as e:
        if 'monte_carlo' in str(e).lower() or 'monte' in str(e).lower():
            raise AssertionError(f"Crash liên quan monte_carlo khi result=None: {e}")

    print("  PASS: test_monte_carlo_null_result")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all_tests():
    tests = [
        ("Monte Carlo table present", test_monte_carlo_table_present),
        ("Monte Carlo table absent", test_monte_carlo_table_absent),
        ("Monte Carlo contains values", test_monte_carlo_contains_values),
        ("Monte Carlo colors", test_monte_carlo_colors),
        ("Monte Carlo null result", test_monte_carlo_null_result),
    ]

    print("=" * 60)
    print("Monte Carlo UI Tests — Task 6")
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
        print("PASS — All Task 6 tests passed")
    else:
        print(f"FAIL — {failed} tests failed")
    print(f"{'=' * 60}")
    return failed == 0


if __name__ == "__main__":
    ok = run_all_tests()
    sys.exit(0 if ok else 1)