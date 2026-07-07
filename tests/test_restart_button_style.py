"""
Test: Restart button style — no border, transparent background always, hover underline only.
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
    source_path = os.path.join(os.path.dirname(test_dir), "ui", "main_window.py")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    # Extract the restart button style block
    restart_start = source.find('QPushButton("🔄 Khởi động lại")')
    restart_end = source.find("restart_btn.clicked.connect", restart_start)
    style_block = source[restart_start:restart_end]

    # === Group 1: No border ===
    print("=" * 60)
    print("TEST GROUP 1: No border")
    print("=" * 60)

    check("1a: border: none (not transparent)",
          '"border: none"' in style_block or "border: none;" in style_block)
    check("1b: No border-color on hover",
          "border-color:" not in style_block)
    check("1c: No border-radius",
          "border-radius" not in style_block)

    # === Group 2: Transparent background always ===
    print("\n" + "=" * 60)
    print("TEST GROUP 2: Transparent background at all states")
    print("=" * 60)

    check("2a: Normal state background: transparent",
          "background: transparent" in style_block)
    check("2b: Hover state also background: transparent",
          style_block.count("background: transparent") >= 2)
    check("2c: No background color on hover",
          "background:" in style_block and "#" not in
          style_block[style_block.find("background:"):style_block.find("background:") + 50]
          if "background:" in style_block else True)

    # === Group 3: Hover style ===
    print("\n" + "=" * 60)
    print("TEST GROUP 3: Hover — text brighten + underline only")
    print("=" * 60)

    check("3a: Hover color #e2e8f0",
          "#e2e8f0" in style_block)
    check("3b: Hover text-decoration underline",
          "text-decoration: underline" in style_block)
    check("3c: Old hover #cbd5e1 removed",
          "#cbd5e1" not in style_block)
    check("3d: Old border-color #334155 removed",
          "#334155" not in style_block)

    # === Group 4: Cursor ===
    print("\n" + "=" * 60)
    print("TEST GROUP 4: Cursor and general style")
    print("=" * 60)

    check("4a: PointingHandCursor set",
          "PointingHandCursor" in style_block)
    check("4b: Font 11px",
          "font-size: 11px" in style_block)
    check("4c: Color #94a3b8 (matches footer)",
          "color: #94a3b8" in style_block)
    check("4d: Padding 4px 8px",
          "padding: 4px 8px" in style_block)
    check("4e: Margin-top 12px from footer",
          "margin-top: 12px" in style_block)

    # === Group 5: Distinct from NavButton ===
    print("\n" + "=" * 60)
    print("TEST GROUP 5: Distinct from NavButton hover style")
    print("=" * 60)

    # QSS NavButton hover: background: #1f2937; border-color: #334155;
    # Restart button: background: transparent; no border; text underline
    check("5a: No #1f2937 (NavButton hover bg)",
          "#1f2937" not in style_block)
    check("5b: No #334155 (NavButton hover border)",
          "#334155" not in style_block)
    check("5c: Restart uses underline not background for hover feedback",
          "text-decoration: underline" in style_block)

    # === Group 6: Syntax ===
    print("\n" + "=" * 60)
    print("TEST GROUP 6: Python syntax")
    print("=" * 60)

    import py_compile
    try:
        py_compile.compile(source_path, doraise=True)
        check("6a: File compiles successfully", True)
    except py_compile.PyCompileError as e:
        check("6a: File compiles successfully", False, str(e))

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


def test_restart_button_style_pytest():
    assert run_tests()
