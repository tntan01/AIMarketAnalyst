"""
Test script for: remove Entry Checklist card + rename button.
"""
import os
import sys

def run_tests():
    results = []
    passed = 0
    failed = 0

    def check(test_name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            passed += 1
            results.append(f"  PASS: {test_name}")
        else:
            failed += 1
            results.append(f"  FAIL: {test_name} — {detail}")

    # Read source
    test_dir = os.path.dirname(os.path.abspath(__file__))
    source_path = os.path.join(os.path.dirname(test_dir), "ui", "screens", "scanner_detail_screen.py")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    # === Group 1: Button text changed ===
    print("=" * 60)
    print("TEST GROUP 1: Nút 'Xem đầy đủ'")
    print("=" * 60)

    check("1a: Button text is 'Xem đầy đủ' (without '16 chỉ số')",
          'action_button("📋 Xem đầy đủ"' in source)
    check("1b: Old button text 'Xem đầy đủ (16 chỉ số)' is gone",
          'Xem đầy đủ (16 chỉ số)' not in source)

    # === Group 2: Entry checklist card removed from _build_ui ===
    print("\n" + "=" * 60)
    print("TEST GROUP 2: Card 'Điều kiện vào lệnh' removed from _build_ui")
    print("=" * 60)

    check("2a: entry_checklist_card not in _build_ui",
          "entry_checklist_card" not in source)
    check("2b: entry_checklist_layout not in _build_ui",
          "entry_checklist_layout" not in source)
    check("2c: 'Điều kiện vào lệnh' comment removed from _build_ui",
          "Panel: Điều kiện vào lệnh" not in source)

    # === Group 3: _refresh_entry_checklist deleted ===
    print("\n" + "=" * 60)
    print("TEST GROUP 3: _refresh_entry_checklist method deleted")
    print("=" * 60)

    check("3a: _refresh_entry_checklist method removed",
          "def _refresh_entry_checklist(self)" not in source)
    check("3b: _refresh_entry_checklist call removed from _render",
          "self._refresh_entry_checklist()" not in source)

    # === Group 4: _build_entry_checklist preserved ===
    print("\n" + "=" * 60)
    print("TEST GROUP 4: _build_entry_checklist KEPT (used by dialog)")
    print("=" * 60)

    check("4a: _build_entry_checklist still exists",
          "def _build_entry_checklist(self)" in source)
    check("4b: _build_entry_checklist still called in dialog",
          "self._build_entry_checklist()" in source)

    # === Group 5: _show_scan_detail_dialog still intact ===
    print("\n" + "=" * 60)
    print("TEST GROUP 5: Dialog _show_scan_detail_dialog intact")
    print("=" * 60)

    check("5a: Dialog method still exists",
          "def _show_scan_detail_dialog(self)" in source)
    check("5b: Dialog still references checklist",
          "_build_entry_checklist" in source)

    # === Group 6: Verify no residual UI references ===
    print("\n" + "=" * 60)
    print("TEST GROUP 6: No orphan references")
    print("=" * 60)

    check("6a: No EntryChecklistCard object name",
          "EntryChecklistCard" not in source)
    check("6b: No entry_checklist_card attribute",
          "self.entry_checklist_card" not in source)
    check("6c: No entry_checklist_layout attribute",
          "self.entry_checklist_layout" not in source)

    # === Group 7: Syntax check ===
    print("\n" + "=" * 60)
    print("TEST GROUP 7: Python syntax")
    print("=" * 60)

    import py_compile
    try:
        py_compile.compile(source_path, doraise=True)
        check("7a: File compiles successfully", True)
    except py_compile.PyCompileError as e:
        check("7a: File compiles successfully", False, str(e))

    # === Summary ===
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} PASSED, {failed} FAILED out of {passed + failed} tests")
    print("=" * 60)

    for r in results:
        print(r)

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
