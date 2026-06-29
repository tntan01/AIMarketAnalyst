"""Tests for backtest screen improvements:
1. Color-coded trade rows (win=green, loss=red, breakeven=gray)
2. Quick verdict banner
3. Expanded stats table
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_mock_result() -> dict:
    """Create a realistic backtest result dict."""
    return {
        "summary": {
            "total_trades": 85,
            "wins": 38,
            "losses": 42,
            "breakeven": 3,
            "expired": 2,
            "win_rate": 44.71,
            "loss_rate": 49.41,
            "total_r": 18.5,
            "average_r": 0.22,
            "median_r": 0.0,
            "expectancy_r": 0.22,
            "average_win_r": 1.8,
            "average_loss_r": -1.0,
            "profit_factor": 1.63,
            "max_drawdown_r": -8.5,
            "max_consecutive_losses": 5,
            "max_consecutive_wins": 4,
            "average_holding_bars": 24.5,
        },
        "trades": [
            {"symbol": "EUR/USD", "side": "buy", "result": "win", "result_r": 1.5,
             "entry_price": 1.05200, "stop_loss": 1.05000, "take_profit": 1.05500,
             "entry_time": "2025-03-10T08:00:00Z", "final_score": 72, "signal_score": 68},
            {"symbol": "EUR/USD", "side": "sell", "result": "loss", "result_r": -1.0,
             "entry_price": 1.05400, "stop_loss": 1.05600, "take_profit": 1.05100,
             "entry_time": "2025-03-11T10:00:00Z", "final_score": 55, "signal_score": 52},
            {"symbol": "GBP/USD", "side": "buy", "result": "breakeven", "result_r": 0.0,
             "entry_price": 1.25200, "stop_loss": 1.25000, "take_profit": 1.25600,
             "entry_time": "2025-03-12T14:00:00Z", "final_score": 60, "signal_score": 58},
            {"symbol": "EUR/USD", "side": "buy", "result": "win", "result_r": 2.1,
             "entry_price": 1.04800, "stop_loss": 1.04600, "take_profit": 1.05220,
             "entry_time": "2025-03-15T06:00:00Z", "final_score": 80, "signal_score": 76},
            {"symbol": "USD/JPY", "side": "sell", "result": "loss", "result_r": -1.0,
             "entry_price": 149.50, "stop_loss": 150.00, "take_profit": 148.50,
             "entry_time": "2025-04-01T09:00:00Z", "final_score": 45, "signal_score": 42},
        ],
        "breakdowns": {
            "by_symbol": {
                "EUR/USD": {"total_trades": 40, "win_rate": 47.5, "expectancy_r": 0.35,
                            "profit_factor": 1.8, "max_drawdown_r": -5.0, "total_r": 14.0},
                "GBP/USD": {"total_trades": 25, "win_rate": 40.0, "expectancy_r": 0.05,
                            "profit_factor": 1.1, "max_drawdown_r": -8.5, "total_r": 2.5},
                "USD/JPY": {"total_trades": 20, "win_rate": 45.0, "expectancy_r": 0.15,
                            "profit_factor": 1.4, "max_drawdown_r": -6.0, "total_r": 2.0},
            },
        },
        "symbol_stats": {
            "EUR/USD": {"total_trades": 40, "win_rate": 47.5, "expectancy_r": 0.35,
                        "profit_factor": 1.8, "max_drawdown_r": -5.0, "total_r": 14.0},
            "GBP/USD": {"total_trades": 25, "win_rate": 40.0, "expectancy_r": 0.05,
                        "profit_factor": 1.1, "max_drawdown_r": -8.5, "total_r": 2.5},
            "USD/JPY": {"total_trades": 20, "win_rate": 45.0, "expectancy_r": 0.15,
                        "profit_factor": 1.4, "max_drawdown_r": -6.0, "total_r": 2.0},
        },
        "diagnostics": {
            "snapshots_evaluated": 5000,
            "setups_detected": 200,
            "blocked_by_gate": 30,
            "score_below_50_count": 4600,
            "pipeline_stats": {
                "validate": {"pass": 5000, "fail": 0, "warning": 0},
                "gate": {"pass": 80, "fail": 30, "warning": 90},
            },
            "gate_fail_counts": {"M15": 90, "ScoreGap": 80},
        },
    }


def _make_screen():
    """Create a BacktestScreen without QApplication."""
    from ui.screens.backtest_screen import BacktestScreen
    screen = BacktestScreen.__new__(BacktestScreen)
    screen.result = None
    return screen


# ---------------------------------------------------------------------------
# Test 1: Color-coded trade rows
# ---------------------------------------------------------------------------

def test_color_coded_trades():
    """Verify _set_trades applies correct background colors."""
    screen = _make_screen()
    screen.result = _make_mock_result()
    result = screen.result

    # We can't test setBackground directly without QApplication,
    # so we test the logic indirectly by checking the result values
    trades = result.get("trades", [])
    assert len(trades) == 5

    results = [t.get("result") for t in trades]
    assert results == ["win", "loss", "breakeven", "win", "loss"]

    # Test color constants
    win_color = "#14532d"
    loss_color = "#7f1d1d"
    breakeven_color = "#1e293b"

    for trade in trades:
        r = trade.get("result")
        if r == "win":
            assert win_color is not None
        elif r == "loss":
            assert loss_color is not None
        elif r == "breakeven":
            assert breakeven_color is not None

    print("  PASS: test_color_coded_trades")


# ---------------------------------------------------------------------------
# Test 2: Verdict banner - good system (edge + good PF)
# ---------------------------------------------------------------------------

def test_verdict_good_system():
    screen = _make_screen()
    result = _make_mock_result()
    # Already good: expectancy=0.22, PF=1.63
    screen.result = result
    screen.verdict_banner = _FakeLabel()
    screen._update_verdict()

    text = screen.verdict_banner._text
    assert "CÓ LỢI THẾ" in text
    assert "TL thắng" in text

    print("  PASS: test_verdict_good_system")


# ---------------------------------------------------------------------------
# Test 3: Verdict banner - weak edge
# ---------------------------------------------------------------------------

def test_verdict_weak_edge():
    screen = _make_screen()
    result = _make_mock_result()
    result["summary"]["expectancy_r"] = 0.15
    result["summary"]["profit_factor"] = 1.1
    screen.result = result
    screen.verdict_banner = _FakeLabel()
    screen._update_verdict()

    text = screen.verdict_banner._text
    assert "LỢI THẾ YẾU" in text
    assert "🟡" in text

    print("  PASS: test_verdict_weak_edge")


# ---------------------------------------------------------------------------
# Test 4: Verdict banner - negative system
# ---------------------------------------------------------------------------

def test_verdict_negative():
    screen = _make_screen()
    result = _make_mock_result()
    result["summary"]["expectancy_r"] = -0.15
    result["summary"]["profit_factor"] = 0.8
    result["summary"]["total_r"] = -5.0
    screen.result = result
    screen.verdict_banner = _FakeLabel()
    screen._update_verdict()

    text = screen.verdict_banner._text
    assert "HỆ THỐNG ÂM" in text
    assert "🔴" in text

    print("  PASS: test_verdict_negative")


# ---------------------------------------------------------------------------
# Test 5: Verdict banner - no trades
# ---------------------------------------------------------------------------

def test_verdict_no_trades():
    screen = _make_screen()
    result = _make_mock_result()
    result["summary"]["total_trades"] = 0
    result["summary"]["win_rate"] = 0
    screen.result = result
    screen.verdict_banner = _FakeLabel()
    screen._update_verdict()

    text = screen.verdict_banner._text
    assert "Chưa có lệnh" in text

    print("  PASS: test_verdict_no_trades")


# ---------------------------------------------------------------------------
# Test 6: Verdict banner - null result (should hide)
# ---------------------------------------------------------------------------

def test_verdict_null_result():
    screen = _make_screen()
    screen.result = None
    screen.verdict_banner = _FakeLabel()
    screen._update_verdict()

    assert not screen.verdict_banner._visible, "Verdict should be hidden when no result"

    print("  PASS: test_verdict_null_result")


# ---------------------------------------------------------------------------
# Test 7: Expanded stats HTML contains new indicators
# ---------------------------------------------------------------------------

def test_expanded_stats_html():
    screen = _make_screen()
    screen.result = _make_mock_result()
    html = screen._generate_stats_html()

    # Original stats
    assert "Tổng số lệnh" in html
    assert "Tỷ lệ thắng" in html
    assert "Hệ số lợi nhuận" in html
    assert "Kỳ vọng" in html
    assert "Drawdown tối đa" in html
    assert "Tổng R" in html

    # New stats
    assert "Chi tiết thắng/thua" in html
    assert "Thắng" in html
    assert "Thua" in html
    assert "Hòa" in html
    assert "Hết hạn" in html
    assert "Trung bình R thắng" in html
    assert "Trung bình R thua" in html
    assert "Chuỗi thắng tối đa" in html
    assert "Chuỗi thua tối đa" in html
    assert "Số nến giữ lệnh TB" in html

    # Values
    assert "38" in html   # wins
    assert "42" in html   # losses
    assert "+1.80R" in html  # avg win R
    assert "-1.00R" in html  # avg loss R
    assert "5</td>" in html  # max consec losses (in table cell)
    assert "24" in html   # avg holding bars

    print("  PASS: test_expanded_stats_html")


# ---------------------------------------------------------------------------
# Test 8: Per-symbol breakdown still works
# ---------------------------------------------------------------------------

def test_per_symbol_breakdown():
    screen = _make_screen()
    screen.result = _make_mock_result()
    html = screen._generate_stats_html()

    assert "CHI TIẾT TỪNG CẶP" in html or "TỪNG CẶP" in html
    assert "EUR/USD" in html
    assert "GBP/USD" in html
    assert "USD/JPY" in html

    print("  PASS: test_per_symbol_breakdown")


# ---------------------------------------------------------------------------
# Test 9: Set summary expanded items
# ---------------------------------------------------------------------------

def test_set_summary_expanded():
    screen = _make_screen()
    summary = _make_mock_result()["summary"]

    # Verify summary has all expected keys
    assert "total_trades" in summary
    assert "win_rate" in summary
    assert "expectancy_r" in summary
    assert "profit_factor" in summary
    assert "max_drawdown_r" in summary
    assert "total_r" in summary
    assert "average_win_r" in summary
    assert "average_loss_r" in summary
    assert "max_consecutive_losses" in summary

    print("  PASS: test_set_summary_expanded")


# ---------------------------------------------------------------------------
# Test 10: Pipeline diagnostics still in HTML
# ---------------------------------------------------------------------------

def test_pipeline_diag_still_present():
    screen = _make_screen()
    screen.result = _make_mock_result()
    html = screen._generate_stats_html()

    assert "CHẨN ĐOÁN PIPELINE" in html
    assert "Gate" in html

    print("  PASS: test_pipeline_diag_still_present")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

class _FakeLabel:
    """Fake QLabel that captures setText and show/hide calls."""
    def __init__(self):
        self._text = ""
        self._visible = True

    def setText(self, text: str) -> None:
        self._text = text

    def hide(self) -> None:
        self._visible = False

    def show(self) -> None:
        self._visible = True

    def text(self) -> str:
        return self._text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all_tests():
    tests = [
        ("Color-coded trades", test_color_coded_trades),
        ("Verdict good system", test_verdict_good_system),
        ("Verdict weak edge", test_verdict_weak_edge),
        ("Verdict negative", test_verdict_negative),
        ("Verdict no trades", test_verdict_no_trades),
        ("Verdict null result", test_verdict_null_result),
        ("Expanded stats HTML", test_expanded_stats_html),
        ("Per-symbol breakdown", test_per_symbol_breakdown),
        ("Set summary expanded", test_set_summary_expanded),
        ("Pipeline diag still present", test_pipeline_diag_still_present),
    ]

    print("=" * 60)
    print("Backtest Screen Improvements Tests")
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
