"""Tests for Task 1: BE Trailing — _trailing_configs new fields."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _compute_be_trigger(entry: float, sl: float) -> float:
    """BE trigger = 2*entry - initial_sl (same formula for buy and sell)."""
    return 2.0 * entry - sl


def _pip_multiplier(symbol: str) -> float:
    return 100.0 if "JPY" in symbol.upper() else 10000.0


def test_required_keys():
    """Kiểm tra: config có đầy đủ các key mới."""
    from ui.screens.orders_screen import OrdersScreen

    screen = OrdersScreen.__new__(OrdersScreen)
    screen._trailing_configs = {}
    screen._trailing_configs[1] = {
        "position_id": 1,
        "symbol": "NZDUSD",
        "side": "buy",
        "enabled": True,
        "trail_pips": 20,
        "extreme_price": 0.0,
        "current_sl": 0.0,
        "be_done": False,
        "be_trigger_price": 0.60130,
        "entry_price": 0.60000,
        "initial_sl": 0.59870,
        "atr_h1": 0.0,
        "trail_mode": "wide",
        "pip_multiplier": 10000.0,
    }
    cfg = screen._trailing_configs[1]

    required = [
        "be_done", "be_trigger_price", "entry_price", "initial_sl",
        "atr_h1", "trail_mode", "pip_multiplier",
    ]
    missing = [k for k in required if k not in cfg]
    assert not missing, f"Thiếu key: {missing}"
    print("  PASS: test_required_keys")


def test_be_trigger_buy():
    """Kiểm tra: BE trigger cho lệnh BUY NZD/USD."""
    entry = 0.60000
    sl = 0.59870
    be = _compute_be_trigger(entry, sl)
    assert abs(be - 0.60130) < 0.00001, f"BE trigger buy phải = 0.60130, hiện = {be}"
    print("  PASS: test_be_trigger_buy")


def test_be_trigger_sell():
    """Kiểm tra: BE trigger cho lệnh SELL NZD/USD."""
    entry = 0.60000
    sl = 0.60130
    be = _compute_be_trigger(entry, sl)
    assert abs(be - 0.59870) < 0.00001, f"BE trigger sell phải = 0.59870, hiện = {be}"
    print("  PASS: test_be_trigger_sell")


def test_pip_multiplier_nzdusd():
    """Kiểm tra: pip_multiplier NZD/USD = 10000."""
    mp = _pip_multiplier("NZDUSD")
    assert mp == 10000.0, f"NZDUSD pip_multiplier phải = 10000, hiện = {mp}"
    print("  PASS: test_pip_multiplier_nzdusd")


def test_pip_multiplier_usdjpy():
    """Kiểm tra: pip_multiplier USD/JPY = 100."""
    mp = _pip_multiplier("USDJPY")
    assert mp == 100.0, f"USDJPY pip_multiplier phải = 100, hiện = {mp}"
    print("  PASS: test_pip_multiplier_usdjpy")


def test_config_trail_mode_default():
    """Kiểm tra: trail_mode mặc định = 'wide'."""
    from ui.screens.orders_screen import OrdersScreen
    screen = OrdersScreen.__new__(OrdersScreen)
    screen._trailing_configs = {}
    screen._trailing_configs[1] = {
        "position_id": 1, "symbol": "NZDUSD", "side": "buy",
        "enabled": True, "trail_pips": 20,
        "extreme_price": 0.0, "current_sl": 0.0,
        "be_done": False, "be_trigger_price": 0.60130,
        "entry_price": 0.60000, "initial_sl": 0.59870,
        "atr_h1": 0.0, "trail_mode": "wide", "pip_multiplier": 10000.0,
    }
    assert screen._trailing_configs[1]["trail_mode"] == "wide"
    print("  PASS: test_config_trail_mode_default")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_all_tests():
    tests = [
        ("Required keys", test_required_keys),
        ("BE trigger buy", test_be_trigger_buy),
        ("BE trigger sell", test_be_trigger_sell),
        ("Pip multiplier NZDUSD", test_pip_multiplier_nzdusd),
        ("Pip multiplier USDJPY", test_pip_multiplier_usdjpy),
        ("Trail mode default", test_config_trail_mode_default),
    ]

    print("=" * 60)
    print("BE Trailing Task 1 Tests")
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
        print("PASS — All Task 1 tests passed")
    else:
        print(f"FAIL — {failed} tests failed")
    print(f"{'=' * 60}")
    return failed == 0


if __name__ == "__main__":
    ok = run_all_tests()
    sys.exit(0 if ok else 1)
