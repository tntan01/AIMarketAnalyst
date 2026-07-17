#!/usr/bin/env python3
"""Test tất cả 6 task nâng cấp Quản lý lệnh (Orders Screen)."""

from pathlib import Path
_src_path = Path("/mnt/d/Projects/AIMarketAnalyst/ui/screens/orders_screen.py")
if not _src_path.exists():
    _src_path = Path(__file__).resolve().parent.parent / "ui" / "screens" / "orders_screen.py"

with open(_src_path, "r", encoding="utf-8") as f:
    code = f.read()

passed = 0
failed = 0
task_results = {}

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name}: {detail}")

# ===== Task 1: Fix AI prompt =====
print("=" * 60)
print("TASK 1: Fix AI prompt (no formula injection, real context)")
print("=" * 60)
ai_section = code.split("def _ai_suggest_trail")[1].split("def _get_selected_position")[0]
t1 = 0

check("Prompt không chứa formula_pips trong JSON template", "{formula_pips}" not in ai_section); t1 += 1
check("max_tokens >= 400", "max_tokens=500" in ai_section or "max_tokens = 500" in ai_section); t1 += 1
check("Prompt có context volatility/trend", any(w in ai_section.lower() for w in ["regime", "xu hướng", "volatility", "biến động", "atr_h1"])); t1 += 1
check("Prompt yêu cầu trail_mode trong JSON response", "trail_mode" in ai_section.lower()); t1 += 1
check("Prompt yêu cầu reason trong JSON response", "reason" in ai_section.lower()); t1 += 1
task_results["1. Fix AI prompt"] = t1

# ===== Task 2: Fix _apply_trailing =====
print("\n" + "=" * 60)
print("TASK 2: Fix _apply_trailing (open_price, real ATR)")
print("=" * 60)
apply_section = code.split("def _apply_trailing")[1].split("def _toggle_trailing")[0]
t2 = 0

check("Dùng open_price thay vì chỉ 'price'", "open_price" in apply_section); t2 += 1
check("Fallback 'price' nếu open_price không có", '"price"' in apply_section or "'price'" in apply_section); t2 += 1
check("Lấy ATR H1 thực từ MT5", "copy_rates_from_pos" in apply_section or ("atr_h1" in apply_section and "mt5" in apply_section.lower())); t2 += 1
check("ATR không hardcoded 0.0", '"atr_h1": 0.0' not in apply_section and "atr_h1': 0.0" not in apply_section); t2 += 1
check("be_trigger_price = 2*entry - sl", "2.0 * entry_price - initial_sl" in apply_section or "2*entry_price - initial_sl" in apply_section); t2 += 1
task_results["2. Fix _apply_trailing"] = t2

# ===== Task 3: Dialog preview =====
print("\n" + "=" * 60)
print("TASK 3: Dialog preview BE + trailing info")
print("=" * 60)
dialog_section = code.split("def _show_trailing_dialog")[1].split("def _apply_trailing")[0]
t3 = 0

check("Dialog có preview (Xem trước / BE sẽ dời về)", "Xem trước" in dialog_section or "BE sẽ" in dialog_section); t3 += 1
check("Preview hiển thị giá BE trigger", "chạm" in dialog_section or "trigger" in dialog_section.lower()); t3 += 1
check("Preview hiển thị trail distance", "ATR" in dialog_section or "trail" in dialog_section.lower()); t3 += 1
check("Spinbox valueChanged cập nhật preview", "valueChanged" in dialog_section and ("preview" in dialog_section.lower() or "_update" in dialog_section.lower())); t3 += 1
task_results["3. Dialog preview"] = t3

# ===== Task 4: Trail mode choice =====
print("\n" + "=" * 60)
print("TASK 4: Trail mode choice (Wide/Tight/Fixed)")
print("=" * 60)
t4 = 0

check("Dialog có Wide/Tight/Fixed selector", ("QRadioButton" in dialog_section or "QComboBox" in dialog_section) and ("wide" in dialog_section.lower() or "cố định" in dialog_section.lower())); t4 += 1
check("Spinbox disable khi Wide/Tight mode", "setEnabled" in dialog_section); t4 += 1
check("trail_mode trong _apply_trailing config", "trail_mode" in apply_section); t4 += 1
check("_trailing_tick xử lý trail_mode='fixed'", '"fixed"' in code.split("def _trailing_tick")[1].split("def _show_trailing_dialog")[0] or "'fixed'" in code.split("def _trailing_tick")[1].split("def _show_trailing_dialog")[0]); t4 += 1
task_results["4. Trail mode choice"] = t4

# ===== Task 5: Persistence =====
print("\n" + "=" * 60)
print("TASK 5: Persistence (save/load trailing state JSON)")
print("=" * 60)
t5 = 0

check("File path tham chiếu be_trailing_state.json", "be_trailing_state" in code or "trailing_state" in code); t5 += 1
check("Save function dùng json.dump", "json.dump" in code or "json.dumps" in code); t5 += 1
check("Debounce save (QTimer/delay)", ("QTimer" in code and "save" in code.lower()) or ("timer" in code.lower() and "trailing" in code.lower())); t5 += 1
check("Chỉ giữ config của vị thế đang mở khi load", "open_ids" in code or "positions" in code.split("load")[1] if "load" in code else False); t5 += 1
task_results["5. Persistence"] = t5

# ===== Task 6: Dead code + R column =====
print("\n" + "=" * 60)
print("TASK 6: Xóa continue thừa + cột R")
print("=" * 60)
tick_section = code.split("def _trailing_tick")[1].split("def _show_trailing_dialog")[0]
table_section = code.split("def _build_order_table")[1].split("def _build_action_bar")[0]
render_section = code.split("def _render_position_row")[1].split("def _render_pending_row")[0]
t6 = 0

check("Không còn double continue", "\n                continue\n                continue" not in tick_section and "\n            continue\n            continue" not in tick_section); t6 += 1
check("Table columnCount = 11", "setColumnCount(11)" in table_section); t6 += 1
check('Header có "R"', '"R"' in table_section or "'R'" in table_section); t6 += 1
check("R value được tính trong render (initial_sl/risk)", "initial_sl" in render_section or "risk" in render_section.lower()); t6 += 1
check("R hiển thị '--' khi không có SL", '"--"' in render_section); t6 += 1
task_results["6. Dead code + R column"] = t6

# ===== SUMMARY =====
print("\n" + "=" * 60)
print("TỔNG KẾT")
print("=" * 60)
for task_name, count in task_results.items():
    thresholds = {"1. Fix AI prompt": 3, "2. Fix _apply_trailing": 3, "3. Dialog preview": 2, "4. Trail mode choice": 2, "5. Persistence": 2, "6. Dead code + R column": 3}
    status = "✅" if count >= thresholds.get(task_name, 2) else "❌"
    print(f"  {status} {task_name}: {count} checks")

total = passed + failed
print(f"\n  Tổng: {passed}/{total} passed")
if failed == 0:
    print("✅ PASS — Tất cả task hoàn thành!")
else:
    print(f"❌ FAIL — {failed} checks failed")
    exit(1)
