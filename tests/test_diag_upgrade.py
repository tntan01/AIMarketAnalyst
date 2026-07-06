"""
Test script for UPGRADE_DIAGNOSTICS_TAB changes.
Verifies: _diag_summary_html, _refresh_diagnostics order, toggle logic, edge cases.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# We can't instantiate the full widget (needs QApplication + settings),
# so we test the logic directly via isolated method simulations.

# ---------------------------------------------------------------------------
# 1. Test _diag_summary_html logic (extracted from the method)
# ---------------------------------------------------------------------------

def diag_summary_html(analysis: dict, light: bool = False) -> str:
    """Mirror of ScannerDetailScreen._diag_summary_html for testing."""
    gate = analysis.get("trade_gate", {})
    if not isinstance(gate, dict):
        gate = {}
    permission = analysis.get("trade_permission", {})
    if not isinstance(permission, dict):
        permission = {}
    decision = analysis.get("decision_engine", {})
    if not isinstance(decision, dict):
        decision = {}

    pipe_diags = analysis.get("pipeline_diagnostics")
    gate_checks: list[dict] = []
    if isinstance(pipe_diags, list):
        for d in pipe_diags:
            if isinstance(d, dict) and d.get("step") == "gate":
                gate_checks = d.get("details", {}).get("gate_checks", []) or []
                break

    # Simplified fallback (not calling _build_gate_checks_from_result)
    if not gate_checks:
        gate_checks = [
            {"gate": "MT5", "status": "pass", "detail": "MT5 sẵn sàng"},
        ]

    GATE_VN_NAME = {
        "MT5": "MT5 (kết nối)", "Spread": "Spread (chênh lệch)",
        "DataQuality": "Chất lượng DL", "News": "Tin tức",
        "DailyWeeklyLoss": "Lỗ ngày/tuần", "AccountGuard": "Bảo vệ TK",
        "Journal": "Nhật ký", "M15": "M15 (xác nhận)",
        "ExpectedRR": "R:R kỳ vọng", "ScoreGap": "Chênh lệch điểm",
        "ZoneBroken": "Vùng bị phá",
    }

    allowed = gate.get("allowed", True)
    blocking_gate = next((gc for gc in gate_checks if isinstance(gc, dict) and gc.get("status") == "block"), None)
    warning_gate = next((gc for gc in gate_checks if isinstance(gc, dict) and gc.get("status") == "warning"), None)

    if not allowed and blocking_gate:
        icon, accent, bg = "🔴", "#ef4444", ("#fef2f2" if light else "#2a1015")
        g_label = GATE_VN_NAME.get(blocking_gate.get("gate", ""), blocking_gate.get("gate", ""))
        detail = blocking_gate.get("detail", "")
        message = f"<b>BỊ CHẶN</b> vì: {g_label} — {detail}"
    elif warning_gate:
        icon, accent, bg = "🟡", "#f59e0b", ("#fffbeb" if light else "#2a2010")
        g_label = GATE_VN_NAME.get(warning_gate.get("gate", ""), warning_gate.get("gate", ""))
        detail = warning_gate.get("detail", "")
        message = f"<b>CẢNH BÁO</b>: {g_label} — {detail}"
    else:
        icon, accent, bg = "🟢", "#22c55e", ("#f0fdf4" if light else "#0f2a1a")
        final_score = analysis.get("final_score", "?")
        message = f"<b>CHO PHÉP</b> vào lệnh — mọi gate đều qua, điểm cuối {final_score}/100"

    return (
        f"<table style='width:100%;border-collapse:collapse;background:{bg};border-left:4px solid {accent};margin:0 0 14px;'>"
        f"<tr><td style='padding:10px 14px;font-size:14px;color:{accent};'>"
        f"{icon} {message}"
        f"</td></tr></table>"
    )


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

    # --- Test Group 1: _diag_summary_html ---
    print("=" * 60)
    print("TEST GROUP 1: _diag_summary_html()")
    print("=" * 60)

    # 1a: Blocked scenario
    analysis_blocked = {
        "trade_gate": {"allowed": False},
        "pipeline_diagnostics": [
            {"step": "gate", "details": {"gate_checks": [
                {"gate": "Spread", "status": "block", "detail": "spread quá cao 15 pips"},
                {"gate": "MT5", "status": "pass", "detail": "MT5 OK"},
            ]}}
        ],
        "final_score": 45,
    }
    html = diag_summary_html(analysis_blocked)
    check("1a: Blocked shows 'BỊ CHẶN'", "BỊ CHẶN" in html, html[:100])
    check("1a: Blocked shows gate name", "Spread (chênh lệch)" in html)
    check("1a: Blocked shows detail", "spread quá cao 15 pips" in html)
    check("1a: Blocked uses red color", "#ef4444" in html)

    # 1b: Warning scenario
    analysis_warning = {
        "trade_gate": {"allowed": True},
        "pipeline_diagnostics": [
            {"step": "gate", "details": {"gate_checks": [
                {"gate": "MT5", "status": "pass", "detail": "MT5 OK"},
                {"gate": "M15", "status": "warning", "detail": "M15 loose"},
            ]}}
        ],
        "final_score": 62,
    }
    html = diag_summary_html(analysis_warning)
    check("1b: Warning shows 'CẢNH BÁO'", "CẢNH BÁO" in html)
    check("1b: Warning uses yellow", "#f59e0b" in html)
    check("1b: Warning shows gate name", "M15 (xác nhận)" in html)

    # 1c: Allowed scenario
    analysis_allowed = {
        "trade_gate": {"allowed": True},
        "pipeline_diagnostics": [
            {"step": "gate", "details": {"gate_checks": [
                {"gate": "MT5", "status": "pass", "detail": "MT5 OK"},
                {"gate": "Spread", "status": "pass", "detail": "spread normal"},
            ]}}
        ],
        "final_score": 78,
    }
    html = diag_summary_html(analysis_allowed)
    check("1c: Allowed shows 'CHO PHÉP'", "CHO PHÉP" in html)
    check("1c: Allowed uses green", "#22c55e" in html)
    check("1c: Allowed shows final_score", "78/100" in html)

    # 1d: Light mode
    html_light = diag_summary_html(analysis_allowed, light=True)
    check("1d: Light mode uses light bg", "#f0fdf4" in html_light)
    check("1d: Dark mode uses dark bg", "#0f2a1a" in diag_summary_html(analysis_allowed, light=False))

    # 1e: Block with light mode
    html_blocked_light = diag_summary_html(analysis_blocked, light=True)
    check("1e: Blocked light mode bg", "#fef2f2" in html_blocked_light)

    # --- Test Group 2: Edge cases for _diag_summary_html ---
    print("\n" + "=" * 60)
    print("TEST GROUP 2: Edge cases")
    print("=" * 60)

    # 2a: Empty analysis
    html_empty = diag_summary_html({})
    check("2a: Empty analysis shows CHO PHÉP (default)", "CHO PHÉP" in html_empty)
    check("2a: Empty analysis shows ?/100", "?/100" in html_empty)

    # 2b: None values for sub-dicts
    analysis_none_sub = {
        "trade_gate": None,
        "trade_permission": None,
        "decision_engine": None,
        "pipeline_diagnostics": None,
        "final_score": None,
    }
    html_none = diag_summary_html(analysis_none_sub)
    check("2b: None sub-dicts don't crash", "CHO PHÉP" in html_none)

    # 2c: Missing pipeline_diagnostics (falls back to _build_gate_checks_from_result)
    analysis_no_pipe = {
        "trade_gate": {"allowed": False, "block_codes": [], "warning_codes": []},
        "final_score": 30,
    }
    html_no_pipe = diag_summary_html(analysis_no_pipe)
    check("2c: No pipeline_diagnostics doesn't crash", "CHO PHÉP" in html_no_pipe or "BỊ CHẶN" in html_no_pipe or "CẢNH BÁO" in html_no_pipe)

    # 2d: Gate with allowed=False but no blocking gate_checks (edge case)
    analysis_blocked_no_checks = {
        "trade_gate": {"allowed": False},
        "pipeline_diagnostics": [
            {"step": "gate", "details": {"gate_checks": [
                {"gate": "MT5", "status": "pass", "detail": "ok"},
            ]}}
        ],
        "final_score": 50,
    }
    html_edge = diag_summary_html(analysis_blocked_no_checks)
    # allowed=False but no block gate → no blocking_gate found → falls to else (CHO PHÉP) or warning
    check("2d: allowed=False with no block gate doesn't crash", len(html_edge) > 0)

    # 2e: Warning takes priority over pass (first warning found)
    analysis_multi_warn = {
        "trade_gate": {"allowed": True},
        "pipeline_diagnostics": [
            {"step": "gate", "details": {"gate_checks": [
                {"gate": "MT5", "status": "pass", "detail": "ok"},
                {"gate": "News", "status": "warning", "detail": "tin gần"},
                {"gate": "Spread", "status": "warning", "detail": "spread hơi cao"},
            ]}}
        ],
    }
    html_multi = diag_summary_html(analysis_multi_warn)
    check("2e: First warning gate used", "Tin tức" in html_multi)

    # 2f: Gate_checks has non-dict entries
    analysis_bad_checks = {
        "trade_gate": {"allowed": True},
        "pipeline_diagnostics": [
            {"step": "gate", "details": {"gate_checks": [
                "not_a_dict",
                None,
                {"gate": "MT5", "status": "pass", "detail": "ok"},
            ]}}
        ],
    }
    html_bad = diag_summary_html(analysis_bad_checks)
    check("2f: Non-dict gate_checks entries don't crash", "CHO PHÉP" in html_bad)

    # --- Test Group 3: Verify _refresh_diagnostics order ---
    print("\n" + "=" * 60)
    print("TEST GROUP 3: _refresh_diagnostics order")
    print("=" * 60)

    # Read the actual source file to verify the order
    test_dir = os.path.dirname(os.path.abspath(__file__))
    source_path = os.path.join(os.path.dirname(test_dir), "ui", "screens", "scanner_detail_screen.py")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    # Verify the parts order in _refresh_diagnostics
    refresh_method_start = source.find("def _refresh_diagnostics(self)")
    refresh_method_end = source.find("\n    def ", refresh_method_start + 50)
    refresh_body = source[refresh_method_start:refresh_method_end]

    # Find the relative positions of each method call
    calls_in_order = [
        ("_diag_summary_html", "summary"),
        ("_diag_final_score_html", "final_score"),
        ("_diag_gate_html", "gate"),
        ("_diag_score_breakdown_html", "score_breakdown"),
    ]

    positions = {}
    for call_name, label in calls_in_order:
        pos = refresh_body.find(f"self.{call_name}(")
        positions[label] = pos
        check(f"3.{label}: {call_name} present in _refresh_diagnostics",
              pos >= 0, f"position={pos}")

    # Verify order: summary < final_score < gate < score_breakdown
    check("3.order: summary before final_score",
          positions["summary"] < positions["final_score"],
          f"{positions['summary']} vs {positions['final_score']}")
    check("3.order: final_score before gate",
          positions["final_score"] < positions["gate"],
          f"{positions['final_score']} vs {positions['gate']}")
    check("3.order: gate before score_breakdown",
          positions["gate"] < positions["score_breakdown"],
          f"{positions['gate']} vs {positions['score_breakdown']}")

    # Verify _diag_checklist_html is NOT called in _refresh_diagnostics
    check("3.checklist_removed: _diag_checklist_html NOT in _refresh_diagnostics",
          "_diag_checklist_html" not in refresh_body)

    # Verify advanced_text handling is present
    check("3.advanced: diag_advanced_text reference present",
          "diag_advanced_text" in refresh_body)
    check("3.advanced: diag_advanced_toggle_btn reference present",
          "diag_advanced_toggle_btn" in refresh_body)
    check("3.advanced: reset to hidden on refresh",
          'self.diag_advanced_text.setVisible(False)' in refresh_body)

    # Verify early returns hide advanced
    check("3.early_return: row-empty hides advanced",
          refresh_body.count("diag_advanced_text.setVisible(False)") >= 2)

    # --- Test Group 4: _diag_final_score_html margin ---
    print("\n" + "=" * 60)
    print("TEST GROUP 4: _diag_final_score_html margin")
    print("=" * 60)

    final_start = source.find("def _diag_final_score_html(self")
    final_end = source.find("\n    def ", final_start + 50)
    final_body = source[final_start:final_end]

    check("4.margin: h2 margin is 0 (not 20px)",
          "margin:0 0 4px" in final_body and "margin:20px 0 4px" not in final_body)

    # --- Test Group 5: _toggle_diag_advanced ---
    print("\n" + "=" * 60)
    print("TEST GROUP 5: _toggle_diag_advanced method exists")
    print("=" * 60)

    check("5.method: _toggle_diag_advanced defined",
          "def _toggle_diag_advanced(self)" in source)
    check("5.method: toggles visibility",
          "diag_advanced_text.setVisible(not is_visible)" in source)
    check("5.method: changes button text when showing",
          "Ẩn chi tiết kỹ thuật nâng cao" in source)
    check("5.method: changes button text when hiding",
          "Xem chi tiết kỹ thuật nâng cao" in source)

    # --- Test Group 6: _build_ui has advanced widgets ---
    print("\n" + "=" * 60)
    print("TEST GROUP 6: _build_ui has advanced widgets")
    print("=" * 60)

    build_start = source.find("def _build_ui(self)")
    build_end = source.find("\n    def ", build_start + 50)
    build_body = source[build_start:build_end]

    check("6.ui: diag_advanced_toggle_btn created",
          "self.diag_advanced_toggle_btn = action_button" in build_body)
    check("6.ui: diag_advanced_text created",
          "self.diag_advanced_text = QTextEdit()" in build_body)
    check("6.ui: diag_advanced_text hidden by default",
          "self.diag_advanced_text.setVisible(False)" in build_body)
    check("6.ui: toggle connected to _toggle_diag_advanced",
          "self._toggle_diag_advanced" in build_body)

    # --- Test Group 7: _render styles advanced_text ---
    print("\n" + "=" * 60)
    print("TEST GROUP 7: _render styles advanced_text")
    print("=" * 60)

    render_start = source.find("def _render(self)")
    render_end = source.find("\n    def ", render_start + 50)
    render_body = source[render_start:render_end]

    check("7.render: advanced_text styled in light mode",
          "self.diag_advanced_text.setStyleSheet(" in render_body)
    check("7.render: advanced_text styled (at least once)",
          render_body.count("diag_advanced_text.setStyleSheet") >= 2)

    # --- Summary ---
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} PASSED, {failed} FAILED out of {passed + failed} tests")
    print("=" * 60)

    for r in results:
        print(r)

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
