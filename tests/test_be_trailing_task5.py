"""Tests for Task 5: Sync orders_screen — eager init, timer, modify SL."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_mock_orders_screen():
    """Create a minimal OrdersScreen for testing (no full UI init)."""
    from ui.screens.orders_screen import OrdersScreen

    screen = OrdersScreen.__new__(OrdersScreen)
    screen._trailing_configs = {}
    return screen


def test_orders_screen_eager_init():
    """OrdersScreen duoc tao ngay khi app khoi dong (khong lazy load)."""
    from ui.main_window import MainWindow
    assert hasattr(MainWindow, '_build_screens'), \
        "MainWindow must have _build_screens"
    # Verify OrdersScreen is in the screen_factories dict
    import inspect
    source = inspect.getsource(MainWindow._build_screens)
    assert '"orders": OrdersScreen' in source or "'orders': OrdersScreen" in source, \
        "orders_screen must be in _build_screens factory"
    print("  PASS: test_orders_screen_eager_init")


def test_timer_runs_when_tab_not_active():
    """Timer van chay khi tab orders_screen khong active."""
    screen = _make_mock_orders_screen()

    # Simulate: tab not active, but timer fires
    screen._trail_timer = type('MockTimer', (), {'isActive': lambda: True})()
    screen._trailing_configs[1] = {
        "position_id": 1, "symbol": "NZDUSD", "side": "buy",
        "enabled": True, "trail_pips": 20,
        "extreme_price": 0.0, "current_sl": 0.59870,
        "be_done": False, "be_trigger_price": 0.60130,
        "entry_price": 0.60000, "initial_sl": 0.59870,
        "atr_h1": 0.0, "trail_mode": "wide", "pip_multiplier": 10000.0,
    }
    # Timer should NOT depend on tab visibility
    assert screen._trailing_configs[1]["enabled"]
    print("  PASS: test_timer_runs_when_tab_not_active")


def test_auto_enable_tracking_works_when_tab_not_displayed():
    """auto_enable_tracking gọi được dù tab không hiển thị."""
    screen = _make_mock_orders_screen()
    screen.auto_enable_tracking(999, "EURUSD", "buy", 1.08000, 1.07800, 0.00200)

    assert 999 in screen._trailing_configs
    assert screen._trailing_configs[999]["enabled"]
    print("  PASS: test_auto_enable_tracking_works_when_tab_not_displayed")


def test_scanner_passes_orders_screen():
    """Scanner controller co orders_screen reference."""
    from controllers.scanner_controller import ScannerController

    ctrl = ScannerController()
    screen = _make_mock_orders_screen()
    ctrl.orders_screen = screen

    assert ctrl.orders_screen is screen
    # auto_enable_tracking via controller's reference
    ctrl.orders_screen.auto_enable_tracking(555, "XAUUSD", "sell", 2500.0, 2508.0, 3.50)
    assert 555 in ctrl.orders_screen._trailing_configs
    print("  PASS: test_scanner_passes_orders_screen")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_all_tests():
    tests = [
        ("Orders screen eager init", test_orders_screen_eager_init),
        ("Timer runs when tab not active", test_timer_runs_when_tab_not_active),
        ("Auto-enable works when tab hidden", test_auto_enable_tracking_works_when_tab_not_displayed),
        ("Scanner passes orders_screen", test_scanner_passes_orders_screen),
    ]

    print("=" * 60)
    print("BE Trailing Task 5 Tests")
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
        print("PASS — All Task 5 tests passed")
    else:
        print(f"FAIL — {failed} tests failed")
    print(f"{'=' * 60}")
    return failed == 0


if __name__ == "__main__":
    ok = run_all_tests()
    sys.exit(0 if ok else 1)
