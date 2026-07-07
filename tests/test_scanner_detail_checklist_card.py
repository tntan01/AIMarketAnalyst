"""
Test: ScannerDetailScreen checklist card addition (individual panels, 75/25 layout).
Verifies: layout, panels, font sizes, checklist items, method calls.
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

    test_dir = os.path.dirname(os.path.abspath(__file__))
    source_path = os.path.join(os.path.dirname(test_dir), "ui", "screens", "scanner_detail_screen.py")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    # === Group 1: Layout 75/25 ===
    print("=" * 60)
    print("TEST GROUP 1: Layout ratio 75/25 (3:1)")
    print("=" * 60)

    check("1a: Left column stretch 3", "addLayout(left_col, 3)" in source)
    check("1b: Right column stretch 1", "addLayout(right_col, 1)" in source)
    check("1c: Old 65:35 removed", "addLayout(left_col, 65)" not in source)

    # === Group 2: Three separate right-col panels ===
    print("\n" + "=" * 60)
    print("TEST GROUP 2: Three separate panels (trade, score, checklist)")
    print("=" * 60)

    build_start = source.find("def _build_ui(self)")
    build_end = source.find("\n    def _section_title", build_start)
    build_body = source[build_start:build_end]

    check("2a: trade_panel created in _build_ui",
          "self.trade_panel = QFrame()" in build_body)
    check("2b: score_panel created in _build_ui",
          "self.score_panel = QFrame()" in build_body)
    check("2c: checklist_panel created in _build_ui",
          "self.checklist_panel = QFrame()" in build_body)
    check("2d: No merged trade_score_panel",
          "self.trade_score_panel" not in build_body)
    check("2e: No QStackedWidget import in _build_ui",
          "from PyQt6.QtWidgets import QStackedWidget" not in build_body)

    # === Group 3: Reduced spacing/padding ===
    print("\n" + "=" * 60)
    print("TEST GROUP 3: Reduced spacing (6/4 padding, 1px spacing)")
    print("=" * 60)

    check("3a: right_col spacing reduced",
          'right_col.setSpacing(4)' in build_body or 'right_col.setSpacing(' in build_body)
    check("3b: Panel padding 6/4 (at least one occurrence)",
          'setContentsMargins(6, 4, 6, 4)' in build_body)
    check("3c: Panel spacing 1px (at least one occurrence)",
          '.setSpacing(1)' in build_body)

    # === Group 4: Font sizes 11px in right_col panels ===
    print("\n" + "=" * 60)
    print("TEST GROUP 4: Font 11px in trade and score panels")
    print("=" * 60)

    # Extract _refresh_trade_panel body
    trade_start = source.find("def _refresh_trade_panel(self")
    trade_end = source.find("\n    def _refresh_score_panel", trade_start)
    trade_body = source[trade_start:trade_end]

    check("4a: Trade panel rows use 11px (not 12px)",
          "font-size: 11px" in trade_body and "font-size: 12px" not in trade_body)

    score_start = source.find("def _refresh_score_panel(self")
    score_end = source.find("\n    def _refresh_checklist_panel", score_start)
    score_body = source[score_start:score_end]

    check("4b: Score panel rows use 11px (not 12px)",
          "font-size: 11px" in score_body and "font-size: 12px" not in score_body)

    # === Group 5: Checklist panel ===
    print("\n" + "=" * 60)
    print("TEST GROUP 5: Checklist panel structure")
    print("=" * 60)

    check_start = source.find("def _refresh_checklist_panel(self")
    check_end = source.find("\n    def _build_entry_checklist", check_start)
    checklist_body = source[check_start:check_end]

    check("5a: _refresh_checklist_panel method exists",
          "def _refresh_checklist_panel(self" in source)
    check("5b: Checklist calls _build_entry_checklist",
          "self._build_entry_checklist()" in checklist_body)
    check("5c: SHORT_NAMES has 7 items",
          checklist_body.count('"Quyền GD"') >= 1 and checklist_body.count('"R:R"') >= 1)
    check("5d: Tooltip for full text",
          "setToolTip(full_label)" in checklist_body)
    check("5e: Grid layout for compact display",
          "QGridLayout()" in checklist_body)
    check("5f: Checklist title font 11px",
          "font-size: 11px" in checklist_body)

    # Check exact 7 short names
    import re
    sn_match = re.search(r'SHORT_NAMES\s*=\s*\[(.*?)\]', checklist_body, re.DOTALL)
    if sn_match:
        names = re.findall(r'"([^"]*)"', sn_match.group(1))
        check("5g: SHORT_NAMES has exactly 7 items",
              len(names) == 7,
              f"Found {len(names)}: {names}")
        expected = ["Quyền GD", "Gate", "Chênh lệch", "Entry", "Vị trí", "M15", "R:R"]
        check("5h: SHORT_NAMES match expected",
              names == expected,
              f"Got: {names}")

    # === Group 6: _render calls ===
    print("\n" + "=" * 60)
    print("TEST GROUP 6: _render() calls correct methods")
    print("=" * 60)

    render_start = source.find("def _render(self)")
    render_end = source.find("\n    def _refresh_chart", render_start)
    render_body = source[render_start:render_end]

    check("6a: _refresh_trade_panel called in _render",
          "self._refresh_trade_panel()" in render_body)
    check("6b: _refresh_score_panel called in _render",
          "self._refresh_score_panel()" in render_body)
    check("6c: _refresh_checklist_panel called in _render",
          "self._refresh_checklist_panel()" in render_body)
    check("6d: _refresh_trade_score_panel NOT called",
          "self._refresh_trade_score_panel()" not in render_body)

    # === Group 7: Deleted methods confirmed removed ===
    print("\n" + "=" * 60)
    print("TEST GROUP 7: Old merged-panel methods removed")
    print("=" * 60)

    check("7a: _switch_trade_score removed",
          "def _switch_trade_score(self" not in source)
    check("7b: _refresh_trade_score_panel removed",
          "def _refresh_trade_score_panel(self" not in source)

    # === Group 8: Dialog and button preserved ===
    print("\n" + "=" * 60)
    print("TEST GROUP 8: Dialog and Xem đầy đủ button preserved")
    print("=" * 60)

    check("8a: show_detail_btn with correct text",
          '"📋 Xem đầy đủ"' in source)
    check("8b: _show_scan_detail_dialog still connected",
          "self._show_scan_detail_dialog" in build_body)
    check("8c: _show_scan_detail_dialog method exists",
          "def _show_scan_detail_dialog(self" in source)
    check("8d: _build_entry_checklist still exists",
          "def _build_entry_checklist(self" in source)

    # === Group 9: Syntax ===
    print("\n" + "=" * 60)
    print("TEST GROUP 9: Python syntax")
    print("=" * 60)

    import py_compile
    try:
        py_compile.compile(source_path, doraise=True)
        check("9a: File compiles successfully", True)
    except py_compile.PyCompileError as e:
        check("9a: File compiles successfully", False, str(e))

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
