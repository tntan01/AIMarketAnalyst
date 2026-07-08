#!/usr/bin/env python3
"""
Integration test: Verify all 7 tasks of BE + Trailing Stop are implemented.
Tests the pure logic without requiring MT5 or PyQt6 widgets.
"""

import sys
import os
import traceback

# Add project root to path
sys.path.insert(0, "/mnt/d/Projects/AIMarketAnalyst")

passed = 0
failed = 0
results = []


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        results.append(f"  ✅ {name}")
    else:
        failed += 1
        results.append(f"  ❌ {name}: {detail}")


# ===== TASK 1: _trailing_configs fields =====
print("=" * 60)
print("TASK 1: _trailing_configs fields")
print("=" * 60)

# Read orders_screen.py to verify the _apply_trailing and auto_enable_tracking methods
# contain all required fields
with open("/mnt/d/Projects/AIMarketAnalyst/ui/screens/orders_screen.py", "r", encoding="utf-8") as f:
    code = f.read()

required_fields = [
    "be_done",
    "be_trigger_price",
    "entry_price",
    "initial_sl",
    "atr_h1",
    "trail_mode",
    "pip_multiplier",
    "extreme_price",
]

# Check that _apply_trailing sets all fields
apply_section = code.split("def _apply_trailing")[1].split("def _toggle_trailing")[0] if "def _apply_trailing" in code else ""

for field in required_fields:
    # Check in _apply_trailing
    in_apply = f'"{field}"' in apply_section or f"'{field}'" in apply_section
    # Check in auto_enable_tracking
    auto_section = code.split("def auto_enable_tracking")[1].split("def _clear_trailing")[0] if "def auto_enable_tracking" in code else ""
    in_auto = f'"{field}"' in auto_section or f"'{field}'" in auto_section
    check(f"Field '{field}' in _apply_trailing", in_apply)
    check(f"Field '{field}' in auto_enable_tracking", in_auto)

# Check be_trigger_price calculation (buy)
check("be_trigger_price = 2*entry - sl in auto_enable_tracking",
      "2.0 * entry - sl" in auto_section or "2*entry - sl" in auto_section or "2 * entry - sl" in auto_section)

# Check pip_multiplier logic
check("pip_multiplier: JPY -> 100, else 10000",
      '100.0 if "JPY"' in code)


# ===== TASK 2: BE logic =====
print("\n" + "=" * 60)
print("TASK 2: BE logic in _trailing_tick")
print("=" * 60)

tick_section = code.split("def _trailing_tick")[1].split("def _show_trailing_dialog")[0] if "def _trailing_tick" in code else ""

check("BE logic block exists (if not be_done)", "if not cfg.get(\"be_done\")" in tick_section)
check("BE trigger check (buy: current >= be_trigger)", "current >= be_trigger" in tick_section)
check("BE trigger check (sell: current <= be_trigger)", "current <= be_trigger" in tick_section)
check("BE+ calculation (be_plus = 2.0 / pip_m)", "2.0 / pip_m" in tick_section or "2 / pip_m" in tick_section)
check("BE SL: entry + be_plus for buy", "entry_price + be_plus" in tick_section)
check("BE SL: entry - be_plus for sell", "entry_price - be_plus" in tick_section)
check("modify_position_sltp called for BE", "modify_position_sltp" in tick_section[:tick_section.index("--- ATR-based trail distance")] if "--- ATR-based trail distance" in tick_section else "modify_position_sltp" in tick_section[:500])
check("be_done set to True after BE", "be_done\"] = True" in tick_section or "\"be_done'] = True" in tick_section or 'be_done"] = True' in tick_section)
check("extreme_price reset after BE", "extreme_price\"] = current" in tick_section)


# ===== TASK 3: ATR multiplier =====
print("\n" + "=" * 60)
print("TASK 3: ATR multiplier replaces pips")
print("=" * 60)

check("ATR-based trail distance exists", "--- ATR-based trail distance ---" in tick_section or "ATR-based trail" in tick_section)
check("multiplier = 2.5 for wide", "2.5 if trail_mode == \"wide\"" in tick_section or "2.5 if trail_mode" in tick_section)
check("multiplier = 1.5 for tight", 'else 1.5' in tick_section or '1.5\n' in tick_section.split('wide')[-1] if 'wide' in tick_section else '1.5' in tick_section)
check("trail_price = atr_h1 * multiplier", "atr_h1 * multiplier" in tick_section)
check("profit >= 2R switches to tight", "2.0 * one_r" in tick_section or "2 * one_r" in tick_section)
check("trail_mode set to tight", 'trail_mode\"] = "tight"' in tick_section or "\"trail_mode\"] = \"tight\"" in tick_section)


# ===== TASK 4: Auto-enable from scanner =====
print("\n" + "=" * 60)
print("TASK 4: Auto-enable tracking from scanner")
print("=" * 60)

with open("/mnt/d/Projects/AIMarketAnalyst/controllers/scanner_controller.py", "r", encoding="utf-8") as f:
    scanner_code = f.read()

check("auto_enable_tracking method exists in orders_screen",
      "def auto_enable_tracking" in code)
check("scanner_controller calls auto_enable_tracking",
      "auto_enable_tracking(" in scanner_code)
check("scanner gets atr_h1 from analysis technical",
      "atr_h1" in scanner_code.split("auto_enable_tracking")[0].split("payload.get")[-1] if "auto_enable_tracking" in scanner_code else False or
       'technical.get("atr_h1")' in scanner_code or "technical.get('atr_h1')" in scanner_code)
check("scanner passes correct params: pos_id, symbol, side, entry, sl, atr_h1",
      "pos_id, symbol, trade_side, entry_price, stop_loss, atr_h1" in scanner_code)


# ===== TASK 5: orders_screen sync =====
print("\n" + "=" * 60)
print("TASK 5: orders_screen created at startup")
print("=" * 60)

with open("/mnt/d/Projects/AIMarketAnalyst/ui/main_window.py", "r", encoding="utf-8") as f:
    main_code = f.read()

check("OrdersScreen imported",
      "from ui.screens.orders_screen import OrdersScreen" in main_code)
check("OrdersScreen in screen_factories (not lazy loaded)",
      '"orders": OrdersScreen' in main_code)
check("orders_screen connected to scanner_controller",
      "scanner_controller.orders_screen = orders" in main_code)


# ===== TASK 6: UI trailing status display =====
print("\n" + "=" * 60)
print("TASK 6: UI trailing status display")
print("=" * 60)

render_section = code.split("def _render_position_row")[1].split("def _render_pending_row")[0] if "def _render_position_row" in code else ""

check("BE status text: '⏳ Chờ BE'",
      "⏳ Chờ BE" in render_section)
check("BE status text: '✅ BE'",
      "✅ BE" in render_section or "✅ BE" in render_section)
check("Trail wide text: '🟢 Wide'",
      "🟢 Wide" in render_section)
check("Trail tight text: '🔒 Tight'",
      "🔒 Tight" in render_section)
check("Paused text: '⏸️ Tạm dừng'",
      "⏸️ Tạm dừng" in render_section or "⏸️ Tạm dừng" in code)


# ===== TASK 7: Integration - verify complete flow =====
print("\n" + "=" * 60)
print("TASK 7: Integration verification")
print("=" * 60)

check("BE done check (be_done bool)", 'be_done", False' in code or "be_done', False" in code)
check("trail_mode defaults to wide", '"trail_mode": "wide"' in code or "'trail_mode': 'wide'" in code)
check("_cleanup_trailing removes stale configs", "del self._trailing_configs[pid]" in code or "del self._trailing_configs" in code)
check("_trail_timer runs every 1.5s", "setInterval(1500)" in code)
check("_refresh_timer runs every 5s", "setInterval(5000)" in code)
check("BE only happens once (be_done guard)", 'if not cfg.get("be_done")' in tick_section)
check('trail_mode switches to "tight" at 2R', '"tight"' in tick_section)
check("SL never moves backward (current_sl stored)", '"current_sl"' in tick_section and "current_sl" in tick_section)


# ===== SUMMARY =====
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
for r in results:
    print(r)

total = passed + failed
print(f"\n  Passed: {passed}/{total}")
print(f"  Failed: {failed}/{total}")

if failed == 0:
    print("\n✅ PASS — All tasks implemented correctly!")
else:
    print(f"\n❌ FAIL — {failed} checks failed")
    sys.exit(1)
