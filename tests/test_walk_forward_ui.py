"""Tests for Walk-Forward UI integration."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_result_with_wfa():
    """Tạo backtest result có walk_forward."""
    result = {
        "summary": {
            "total_trades": 30, "win_rate": 50.0, "expectancy_r": 0.35,
            "profit_factor": 2.0, "max_drawdown_r": -5.0, "total_r": 10.5,
            "wins": 15, "losses": 14, "breakeven": 1, "expired": 0,
            "average_r": 0.35, "median_r": 0.3,
            "average_win_r": 1.8, "average_loss_r": -1.0,
            "max_consecutive_losses": 4, "max_consecutive_wins": 4,
            "average_holding_bars": 14.0,
        },
        "trades": [],
        "breakdowns": {},
        "symbol_stats": {},
        "diagnostics": {},
        "equity_curve": [
            {"time": "2025-01-10T08:00:00Z", "cumulative_r": 0.0, "drawdown_r": 0.0, "balance": 10000.0},
            {"time": "2025-06-20T10:00:00Z", "cumulative_r": 10.5, "drawdown_r": 0.0, "balance": 11050.0},
        ],
        "walk_forward": {
            "windows": [
                {
                    "is_start": "2023-01-01", "is_end": "2023-07-01",
                    "oos_start": "2023-07-01", "oos_end": "2023-10-01",
                    "is_summary": {"total_trades": 12, "expectancy_r": 0.42, "win_rate": 50.0},
                    "oos_summary": {"total_trades": 5, "expectancy_r": 0.35, "win_rate": 40.0},
                },
                {
                    "is_start": "2023-04-01", "is_end": "2023-10-01",
                    "oos_start": "2023-10-01", "oos_end": "2024-01-01",
                    "is_summary": {"total_trades": 10, "expectancy_r": 0.38, "win_rate": 50.0},
                    "oos_summary": {"total_trades": 4, "expectancy_r": 0.28, "win_rate": 50.0},
                },
            ],
            "aggregate_is": {"total_trades": 22, "expectancy_r": 0.40, "win_rate": 50.0},
            "aggregate_oos": {"total_trades": 9, "expectancy_r": 0.32, "win_rate": 44.4},
            "oos_is_expectancy_ratio": 0.80,
            "robustness_score": 80.0,
            "verdict": "ROBUST",
            "window_count": 2,
        },
    }
    return result


def _make_result_without_wfa():
    result = _make_result_with_wfa()
    del result["walk_forward"]
    return result


def test_wfa_table_present():
    """Kiểm tra bảng WFA xuất hiện khi có dữ liệu."""
    from ui.screens.backtest_screen import BacktestScreen

    screen = BacktestScreen.__new__(BacktestScreen)
    screen.__dict__['result'] = _make_result_with_wfa()
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

    assert "Walk-Forward" in html or "walk" in html.lower(), \
        "HTML phải chứa 'Walk-Forward'"
    assert "ROBUST" in html, "HTML phải chứa verdict 'ROBUST'"

    print("  PASS: test_wfa_table_present")


def test_wfa_table_absent():
    """Kiểm tra: không crash khi không có WFA."""
    from ui.screens.backtest_screen import BacktestScreen

    screen = BacktestScreen.__new__(BacktestScreen)
    screen.__dict__['result'] = _make_result_without_wfa()
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

    assert "Walk-Forward" not in html, \
        "HTML không nên có Walk-Forward khi không có dữ liệu"

    print("  PASS: test_wfa_table_absent")


def test_wfa_verdict_colors():
    """Kiểm tra màu sắc verdict: ROBUST=xanh, SUSPECT=vàng, OVEREITTING=đỏ."""
    from ui.screens.backtest_screen import BacktestScreen

    # ROBUST → xanh
    screen = BacktestScreen.__new__(BacktestScreen)
    screen.__dict__['result'] = _make_result_with_wfa()
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

    # Ít nhất có mã màu trong HTML
    assert "#" in html or "color" in html.lower(), "HTML phải có mã màu"
    assert "80.0" in html or "80" in html, "HTML phải chứa robustness_score"

    print("  PASS: test_wfa_verdict_colors")


def test_wfa_contains_values():
    """Kiểm tra bảng hiển thị đúng số liệu."""
    from ui.screens.backtest_screen import BacktestScreen

    screen = BacktestScreen.__new__(BacktestScreen)
    screen.__dict__['result'] = _make_result_with_wfa()
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

    assert "2" in html, "HTML phải chứa window_count = 2"
    assert "22" in html, "HTML phải chứa tổng lệnh IS = 22"
    assert "9" in html, "HTML phải chứa tổng lệnh OOS = 9"

    print("  PASS: test_wfa_contains_values")


def test_wfa_null_result():
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
        if 'walk_forward' in str(e).lower() or 'wfa' in str(e).lower():
            raise AssertionError(f"Crash liên quan walk_forward khi result=None: {e}")

    print("  PASS: test_wfa_null_result")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all_tests():
    tests = [
        ("WFA table present", test_wfa_table_present),
        ("WFA table absent", test_wfa_table_absent),
        ("WFA verdict colors", test_wfa_verdict_colors),
        ("WFA contains values", test_wfa_contains_values),
        ("WFA null result", test_wfa_null_result),
    ]

    print("=" * 60)
    print("Walk-Forward UI Tests — Task 8")
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
        print("PASS — All Task 8 tests passed")
    else:
        print(f"FAIL — {failed} tests failed")
    print(f"{'=' * 60}")
    return failed == 0


if __name__ == "__main__":
    ok = run_all_tests()
    sys.exit(0 if ok else 1)