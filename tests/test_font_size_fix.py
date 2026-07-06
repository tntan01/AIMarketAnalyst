"""
Test script for: font-size fix in Trade Panel + Score Panel.
Verifies 11px → 12px in both _refresh_trade_panel and _refresh_score_panel.
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

    # Extract method bodies
    def extract_method(source, method_name):
        start = source.find(f"def {method_name}(self")
        if start < 0:
            return ""
        # Find next method/class level def
        rest = source[start:]
        # Find the next def at same indent level (4 spaces before def)
        lines = rest.split("\n")
        body_lines = [lines[0]]
        for line in lines[1:]:
            if line.startswith("    def ") or line.startswith("    # --"):
                break
            body_lines.append(line)
        return "\n".join(body_lines)

    trade_body = extract_method(source, "_refresh_trade_panel")
    score_body = extract_method(source, "_refresh_score_panel")

    # === Group 1: Trade panel font sizes ===
    print("=" * 60)
    print("TEST GROUP 1: _refresh_trade_panel font sizes")
    print("=" * 60)

    # Count font-size occurrences
    trade_font_sizes = []
    for line in trade_body.split("\n"):
        if "font-size:" in line:
            trade_font_sizes.append(line.strip())

    check("1a: Trade panel has font-size declarations", len(trade_font_sizes) > 0)

    # Check no 11px remains
    check("1b: No 11px remains in trade panel",
          "font-size: 11px" not in trade_body)

    # Check 12px is used for row items (should be at least 2: label + value)
    count_12 = trade_body.count("font-size: 12px")
    check("1c: 12px used for row label and value (>=2 occurrences)",
          count_12 >= 2, f"found {count_12}")

    # Title should still be 13px
    check("1d: Title remains 13px",
          "font-size: 13px" in trade_body)

    # === Group 2: Score panel font sizes ===
    print("\n" + "=" * 60)
    print("TEST GROUP 2: _refresh_score_panel font sizes")
    print("=" * 60)

    score_font_sizes = []
    for line in score_body.split("\n"):
        if "font-size:" in line:
            score_font_sizes.append(line.strip())

    check("2a: Score panel has font-size declarations", len(score_font_sizes) > 0)

    check("2b: No 11px remains in score panel",
          "font-size: 11px" not in score_body)

    count_12_s = score_body.count("font-size: 12px")
    check("2c: 12px used for row label and value (>=2 occurrences)",
          count_12_s >= 2, f"found {count_12_s}")

    check("2d: Title remains 13px",
          "font-size: 13px" in score_body)

    # === Group 3: Global check — no 11px anywhere ===
    print("\n" + "=" * 60)
    print("TEST GROUP 3: No 11px leftover in entire file")
    print("=" * 60)

    # Only check within _refresh_trade_panel and _refresh_score_panel
    # (other parts of the file may legitimately use 11px)
    check("3a: No 11px in _refresh_trade_panel",
          "font-size: 11px" not in trade_body)
    check("3b: No 11px in _refresh_score_panel",
          "font-size: 11px" not in score_body)

    # === Group 4: Syntax ===
    print("\n" + "=" * 60)
    print("TEST GROUP 4: Python syntax")
    print("=" * 60)

    import py_compile
    try:
        py_compile.compile(source_path, doraise=True)
        check("4a: File compiles successfully", True)
    except py_compile.PyCompileError as e:
        check("4a: File compiles successfully", False, str(e))

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
