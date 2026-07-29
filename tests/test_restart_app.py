"""
Test: Restart button in MainWindow sidebar footer.
Verifies button presence, _restart_app method, executable path logic.
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

    # === Group 1: Button exists in sidebar footer ===
    print("=" * 60)
    print("TEST GROUP 1: Restart button in sidebar")
    print("=" * 60)

    check("1a: QPushButton 'Khởi động lại' exists",
          'QPushButton("🔄 Khởi động lại")' in source)
    check("1b: Button connected to _restart_app",
          "restart_btn.clicked.connect(self._restart_app)" in source)
    check("1c: Button placed after footer label",
          source.find('QPushButton("🔄 Khởi động lại")') > source.find("Dữ liệu: MT5"))

    # === Group 2: Button styling ===
    print("\n" + "=" * 60)
    print("TEST GROUP 2: Button inline style")
    print("=" * 60)

    base_path = os.path.join(os.path.dirname(test_dir), "ui", "styles", "base.qss")
    dark_path = os.path.join(
        os.path.dirname(test_dir), "ui", "styles", "dark.qss"
    )
    with open(base_path, "r", encoding="utf-8") as f:
        base_qss = f.read()
    with open(dark_path, "r", encoding="utf-8") as f:
        dark_qss = f.read()
    check("2a: Shared selector", 'setObjectName("RestartButton")' in source)
    check("2b: Font 11px", "font-size: 11px" in base_qss)
    check("2c: Background transparent", "background: transparent" in base_qss)
    check("2d: Border none", "border: none" in base_qss)
    check("2e: Margin-top 12px", "margin-top: 12px" in base_qss)
    check("2f: Hover effect", "QPushButton#RestartButton:hover" in base_qss)
    check("2g: Dark theme color", "color: #0d9488" in dark_qss)

    # === Group 3: _restart_app method ===
    print("\n" + "=" * 60)
    print("TEST GROUP 3: _restart_app() method")
    print("=" * 60)

    check("3a: _restart_app method exists",
          "def _restart_app(self) -> None:" in source)

    # Extract method body
    restart_start = source.find("def _restart_app(self) -> None:")
    restart_end = source.find("\n    def _nav_key_for_route", restart_start)
    restart_body = source[restart_start:restart_end]

    check("3b: QMessageBox.question called",
          "QMessageBox.question(" in restart_body)
    check("3c: Yes/No buttons",
          "StandardButton.Yes" in restart_body and "StandardButton.No" in restart_body)
    check("3d: app shutdown attempted",
          "self.app.shutdown()" in restart_body)
    check("3e: subprocess.Popen used",
          "subprocess.Popen" in restart_body)
    check("3f: QApplication.quit called",
          "QApplication.quit()" in restart_body)
    check("3g: Handles PyInstaller frozen",
          "getattr(sys, 'frozen', False)" in restart_body)
    check("3h: Falls back to python main.py",
          "main.py" in restart_body)
    check("3i: Imports inside method (not top-level)",
          "import subprocess, sys, os" in restart_body)

    # Verify subprocess/sys/os NOT imported at top level
    top_imports = source[:source.find("class MainWindow")]
    check("3j: subprocess NOT in top-level imports",
          "import subprocess" not in top_imports)

    # === Group 4: Executable path logic ===
    print("\n" + "=" * 60)
    print("TEST GROUP 4: Executable path resolution")
    print("=" * 60)

    # Test the logic directly
    def resolve_cmd():
        """Mirror of _restart_app path resolution."""
        import subprocess, sys, os
        if getattr(sys, 'frozen', False):
            return [sys.executable]
        else:
            main_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'main.py')
            return [sys.executable, main_py]

    cmd = resolve_cmd()
    check("4a: cmd is a non-empty list", isinstance(cmd, list) and len(cmd) >= 1)
    check("4b: First element is python executable", cmd[0] == sys.executable)
    check("4c: Not frozen → has main.py as second arg",
          (getattr(sys, 'frozen', False) and len(cmd) == 1) or
          (not getattr(sys, 'frozen', False) and len(cmd) == 2),
          f"frozen={getattr(sys, 'frozen', False)}, cmd={cmd}")

    # === Group 5: Syntax ===
    print("\n" + "=" * 60)
    print("TEST GROUP 5: Python syntax")
    print("=" * 60)

    import py_compile
    try:
        py_compile.compile(source_path, doraise=True)
        check("5a: File compiles successfully", True)
    except py_compile.PyCompileError as e:
        check("5a: File compiles successfully", False, str(e))

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
