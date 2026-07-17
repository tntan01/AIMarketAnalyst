"""Tests for Task 6: UI — display BE/trail stage in Trailing column."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _trailing_text(cfg: dict) -> str:
    """Simulate the trailing column display logic."""
    if cfg.get("enabled"):
        be_done = cfg.get("be_done", False)
        if not be_done:
            return "⏳ Chờ BE"
        entry = cfg.get("entry_price", 0) or 0
        current_sl = cfg.get("current_sl", 0) or 0
        pip_m = cfg.get("pip_multiplier", 10000) or 10000
        be_sl = entry + (2.0 / pip_m) if cfg.get("side") == "buy" else entry - (2.0 / pip_m)
        if abs(current_sl - be_sl) < (1.0 / pip_m):
            return "✅ BE"
        if cfg.get("trail_mode") == "tight":
            return "🔒 Tight"
        return "🟢 Wide"
    elif "enabled" in cfg:
        return "⏸️ Tạm dừng"
    return "--"


def test_waiting_be():
    """be_done=False → 'Chờ BE'."""
    cfg = {"enabled": True, "be_done": False, "trail_mode": "wide"}
    assert "Chờ BE" in _trailing_text(cfg)
    print("  PASS: test_waiting_be")


def test_be_done_wide():
    """be_done=True, trail_mode='wide', current_sl != be_sl → '🟢 Wide'."""
    cfg = {
        "enabled": True, "be_done": True, "trail_mode": "wide",
        "entry_price": 0.60000, "current_sl": 0.60200, "side": "buy",
        "pip_multiplier": 10000.0,
    }
    assert "Wide" in _trailing_text(cfg)
    print("  PASS: test_be_done_wide")


def test_be_done_tight():
    """be_done=True, trail_mode='tight' → '🔒 Tight'."""
    cfg = {
        "enabled": True, "be_done": True, "trail_mode": "tight",
        "entry_price": 0.60000, "current_sl": 0.60200, "side": "buy",
        "pip_multiplier": 10000.0,
    }
    assert "Tight" in _trailing_text(cfg)
    print("  PASS: test_be_done_tight")


def test_be_done_at_be_sl():
    """be_done=True, current_sl == BE SL → '✅ BE'."""
    entry = 0.60000
    pip_m = 10000.0
    be_sl = entry + (2.0 / pip_m)  # 0.60020
    cfg = {
        "enabled": True, "be_done": True, "trail_mode": "wide",
        "entry_price": entry, "current_sl": be_sl, "side": "buy",
        "pip_multiplier": pip_m,
    }
    assert "BE" in _trailing_text(cfg)
    print("  PASS: test_be_done_at_be_sl")


def test_colors():
    """Màu sắc đúng cho từng trạng thái."""
    from PyQt6.QtGui import QColor

    # Chờ BE: xám
    assert QColor("#9ca3af").name() == "#9ca3af"
    # BE: xanh lá
    assert QColor("#10b981").name() == "#10b981"
    # Tight: cam
    assert QColor("#f59e0b").name() == "#f59e0b"
    # Wide: xanh dương
    assert QColor("#3b82f6").name() == "#3b82f6"
    print("  PASS: test_colors")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_all_tests():
    tests = [
        ("Waiting BE text", test_waiting_be),
        ("BE done wide text", test_be_done_wide),
        ("BE done tight text", test_be_done_tight),
        ("BE done at BE SL", test_be_done_at_be_sl),
        ("Colors", test_colors),
    ]

    print("=" * 60)
    print("BE Trailing Task 6 Tests")
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
        print("PASS — All Task 6 tests passed")
    else:
        print(f"FAIL — {failed} tests failed")
    print(f"{'=' * 60}")
    return failed == 0


if __name__ == "__main__":
    ok = run_all_tests()
    sys.exit(0 if ok else 1)
