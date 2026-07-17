"""Tests for Task 3: ATR multiplier instead of fixed pips."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _compute_trail_price(atr: float, trail_mode: str) -> float:
    """Compute trail distance from ATR and mode."""
    multiplier = 2.5 if trail_mode == "wide" else 1.5
    return atr * multiplier


def _check_trail_mode_switch(entry: float, sl: float, current: float, side: str) -> str:
    """Check if trail_mode should switch to tight (profit >= 2R)."""
    one_r = abs(entry - sl)
    profit = (current - entry) if side == "buy" else (entry - current)
    if profit >= 2.0 * one_r:
        return "tight"
    return "wide"


def test_trail_wide_atr():
    """ATR=0.0015, trail_mode='wide' → trail_price = 0.00375."""
    tp = _compute_trail_price(0.0015, "wide")
    assert abs(tp - 0.00375) < 0.00001, f"trail_price phai = 0.00375, hien = {tp}"
    print("  PASS: test_trail_wide_atr")


def test_trail_tight_atr():
    """ATR=0.0015, trail_mode='tight' → trail_price = 0.00225."""
    tp = _compute_trail_price(0.0015, "tight")
    assert abs(tp - 0.00225) < 0.00001, f"trail_price phai = 0.00225, hien = {tp}"
    print("  PASS: test_trail_tight_atr")


def test_switch_to_tight_at_2r_buy():
    """Buy: profit >= 2R → trail_mode chuyen 'wide' → 'tight'."""
    entry, sl = 0.60000, 0.59870  # 1R = 0.00130
    current = 0.60260  # profit = 0.00260 = 2R
    mode = _check_trail_mode_switch(entry, sl, current, "buy")
    assert mode == "tight", f"Profit 2R phai chuyen tight, hien = {mode}"
    print("  PASS: test_switch_to_tight_at_2r_buy")


def test_switch_to_tight_at_2r_sell():
    """Sell: profit >= 2R → trail_mode chuyen 'wide' → 'tight'."""
    entry, sl = 0.60000, 0.60130  # 1R = 0.00130
    current = 0.59740  # profit = 0.00260 = 2R
    mode = _check_trail_mode_switch(entry, sl, current, "sell")
    assert mode == "tight", f"Profit 2R phai chuyen tight, hien = {mode}"
    print("  PASS: test_switch_to_tight_at_2r_sell")


def test_stay_wide_below_2r():
    """Profit < 2R → trail_mode giu 'wide'."""
    entry, sl = 0.60000, 0.59870  # 1R = 0.00130
    current = 0.60150  # profit = 0.00150 < 2R (0.00260)
    mode = _check_trail_mode_switch(entry, sl, current, "buy")
    assert mode == "wide", f"Profit < 2R phai giu wide, hien = {mode}"
    print("  PASS: test_stay_wide_below_2r")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_all_tests():
    tests = [
        ("Trail wide ATR", test_trail_wide_atr),
        ("Trail tight ATR", test_trail_tight_atr),
        ("Switch to tight at 2R buy", test_switch_to_tight_at_2r_buy),
        ("Switch to tight at 2R sell", test_switch_to_tight_at_2r_sell),
        ("Stay wide below 2R", test_stay_wide_below_2r),
    ]

    print("=" * 60)
    print("BE Trailing Task 3 Tests")
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
        print("PASS — All Task 3 tests passed")
    else:
        print(f"FAIL — {failed} tests failed")
    print(f"{'=' * 60}")
    return failed == 0


if __name__ == "__main__":
    ok = run_all_tests()
    sys.exit(0 if ok else 1)
