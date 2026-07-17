"""Tests for Task 4: Auto-enable tracking when scanner opens position."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_auto_enable_creates_config():
    """auto_enable_tracking() tạo config đầy đủ fields."""
    from ui.screens.orders_screen import OrdersScreen

    screen = OrdersScreen.__new__(OrdersScreen)
    screen._trailing_configs = {}

    screen.auto_enable_tracking(123, "NZDUSD", "buy", 0.60000, 0.59870, 0.00150)

    cfg = screen._trailing_configs[123]
    assert cfg["position_id"] == 123
    assert cfg["symbol"] == "NZDUSD"
    assert cfg["side"] == "buy"
    assert cfg["enabled"] is True
    assert not cfg["be_done"]
    assert cfg["trail_mode"] == "wide"
    assert abs(cfg["entry_price"] - 0.60000) < 0.00001
    assert abs(cfg["initial_sl"] - 0.59870) < 0.00001
    assert abs(cfg["atr_h1"] - 0.00150) < 0.00001
    assert abs(cfg["be_trigger_price"] - 0.60130) < 0.00001
    assert cfg["pip_multiplier"] == 10000.0
    print("  PASS: test_auto_enable_creates_config")


def test_auto_enable_adds_to_configs_dict():
    """Config được thêm vào _trailing_configs với key = pos_id."""
    from ui.screens.orders_screen import OrdersScreen

    screen = OrdersScreen.__new__(OrdersScreen)
    screen._trailing_configs = {}

    screen.auto_enable_tracking(456, "EURUSD", "sell", 1.08000, 1.08200, 0.00100)
    assert 456 in screen._trailing_configs
    assert len(screen._trailing_configs) == 1
    print("  PASS: test_auto_enable_adds_to_configs_dict")


def test_auto_enable_overwrites_same_pos_id():
    """Gọi 2 lần cùng pos_id → ghi đè, không duplicate."""
    from ui.screens.orders_screen import OrdersScreen

    screen = OrdersScreen.__new__(OrdersScreen)
    screen._trailing_configs = {}

    screen.auto_enable_tracking(789, "XAUUSD", "buy", 2500.00, 2492.00, 3.50)
    screen.auto_enable_tracking(789, "XAUUSD", "buy", 2510.00, 2502.00, 3.60)

    assert len(screen._trailing_configs) == 1
    cfg = screen._trailing_configs[789]
    assert abs(cfg["entry_price"] - 2510.00) < 0.01  # overwritten
    assert abs(cfg["atr_h1"] - 3.60) < 0.01
    print("  PASS: test_auto_enable_overwrites_same_pos_id")


def test_auto_enable_jpy_pip_multiplier():
    """JPY pair → pip_multiplier = 100."""
    from ui.screens.orders_screen import OrdersScreen

    screen = OrdersScreen.__new__(OrdersScreen)
    screen._trailing_configs = {}

    screen.auto_enable_tracking(111, "USDJPY", "buy", 150.000, 149.500, 0.300)
    cfg = screen._trailing_configs[111]
    assert cfg["pip_multiplier"] == 100.0
    assert abs(cfg["be_trigger_price"] - 150.500) < 0.001
    print("  PASS: test_auto_enable_jpy_pip_multiplier")


def test_auto_enable_sell_be_trigger():
    """SELL: BE trigger = 2*entry - sl."""
    from ui.screens.orders_screen import OrdersScreen

    screen = OrdersScreen.__new__(OrdersScreen)
    screen._trailing_configs = {}

    screen.auto_enable_tracking(222, "NZDUSD", "sell", 0.60000, 0.60130, 0.00150)
    cfg = screen._trailing_configs[222]
    assert abs(cfg["be_trigger_price"] - 0.59870) < 0.00001
    print("  PASS: test_auto_enable_sell_be_trigger")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_all_tests():
    tests = [
        ("Auto-enable creates config", test_auto_enable_creates_config),
        ("Auto-enable adds to config dict", test_auto_enable_adds_to_configs_dict),
        ("Auto-enable overwrites same pos_id", test_auto_enable_overwrites_same_pos_id),
        ("Auto-enable JPY pip multiplier", test_auto_enable_jpy_pip_multiplier),
        ("Auto-enable sell BE trigger", test_auto_enable_sell_be_trigger),
    ]

    print("=" * 60)
    print("BE Trailing Task 4 Tests")
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
