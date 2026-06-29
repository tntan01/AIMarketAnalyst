"""Tests for Scanner Detail diagnostics tab feature.

Covers:
1. _diag_score_breakdown_html — BUY/SELL component table
2. _diag_gate_html — gate checks from pipeline diagnostics
3. _build_gate_checks_from_result — fallback gate builder
4. _diag_checklist_html — entry checklist table
5. _diag_pipeline_steps_html — pipeline step status table
6. _diag_final_score_html — final score breakdown
7. _refresh_diagnostics — integration with mock row data
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_mock_analysis() -> dict:
    """Create a realistic mock analysis_result dict."""
    return {
        "symbol": "EUR/USD",
        "scenario_scores": {
            "buy": {
                "trend_alignment": 18, "momentum_alignment": 14,
                "location_quality": 20, "smc_quality": 10,
                "risk_condition": 3, "macro_alignment": 7,
                "signal_score": 60, "total": 60,
                "macro_status": "neutral",
                "correlation_adjustment": 2.0,
                "penalty_codes": [],
                "reason_codes": ["MACRO_ALIGNED"],
                "smc_reason": "H4 BOS + displacement",
            },
            "sell": {
                "trend_alignment": 8, "momentum_alignment": 10,
                "location_quality": 12, "smc_quality": 4,
                "risk_condition": 3, "macro_alignment": 7,
                "signal_score": 36, "total": 36,
                "macro_status": "conflict",
                "correlation_adjustment": -3.0,
                "penalty_codes": ["CHOCH_AGAINST_DIRECTION"],
                "reason_codes": [],
                "smc_reason": "CHOCH against direction",
            },
        },
        "trade_gate": {
            "allowed": True,
            "decision_cap": "WAITING_CONFIRMATION",
            "block_codes": [],
            "warning_codes": ["M15_LOOSE_CONFIRMATION", "BUY_SELL_SCORE_GAP_LOW"],
            "reasons": ["M15 xác nhận lỏng, cần theo dõi thêm.", "Gap mua-bán chưa đạt tối thiểu."],
        },
        "trade_permission": {"status": "caution", "reason": "M15 chưa xác nhận chặt"},
        "data_quality": {"spread_status": "normal", "terminal_connected": True, "broker_logged_in": True},
        "direction_bias": {"best_side": "buy", "buy_score": 60, "sell_score": 36, "score_gap": 24, "min_gap": 10, "is_clear_bias": True},
        "entry_checklist": [
            {"label": "Xu hướng", "status": "pass", "value": "trend_up", "note": "Xu hướng tăng phù hợp với kịch bản mua."},
            {"label": "Vùng POI", "status": "pass", "value": "1.05200-1.05280", "note": "Có vùng entry/POI hợp lệ."},
            {"label": "Xác nhận H1", "status": "wait", "value": "none", "note": "Cần nến H1 xác nhận tại vùng."},
            {"label": "Tin tức", "status": "pass", "value": "Không có tin gần", "note": "Tránh vào lệnh gần tin tác động cao."},
            {"label": "Spread", "status": "pass", "value": "normal", "note": "Spread phải bình thường."},
            {"label": "R:R", "status": "pass", "value": "1:2.1", "note": "R:R tối thiểu là 1:1.3."},
            {"label": "Lot", "status": "pass", "value": "0.02", "note": "Lot chỉ tính khi entry đã xác nhận."},
        ],
        "pipeline_diagnostics": [
            {"step": "validate", "status": "pass", "summary": "D1=245, H4=980, H1=3920 | Regime: trend_up | Risk: 3/15"},
            {"step": "correlation", "status": "pass", "summary": "DXY=yes, VIX=yes, US10Y=yes | Buy adj: +2 | Sell adj: -3"},
            {"step": "score", "status": "pass", "summary": "BUY=60/100 (T=18 M=14 L=20 S=10 R=3 Ma=7) | SELL=36/100 (T=8 M=10 L=12 S=4 R=3 Ma=7)"},
            {"step": "scenarios", "status": "pass", "summary": "2 scenarios: buy(entry=confirmed_entry, m15=loose, RR=2.1) ..."},
            {"step": "direction", "status": "pass", "summary": "BUY=60 vs SELL=36 | Gap=24 | Best: BUY | Clear bias: yes"},
            {"step": "gate", "status": "warning", "summary": "Allowed: yes | Cap: WAITING_CONFIRMATION | Blocks: 0 | Warnings: 2",
             "details": {"gate_checks": [
                 {"gate": "MT5", "status": "pass", "detail": "Terminal & broker OK"},
                 {"gate": "Spread", "status": "pass", "detail": "spread=normal"},
                 {"gate": "DataQuality", "status": "pass", "detail": "no warning"},
                 {"gate": "News", "status": "pass", "detail": "no news nearby"},
                 {"gate": "DailyWeeklyLoss", "status": "pass", "detail": "within limits"},
                 {"gate": "AccountGuard", "status": "pass", "detail": "guard OK"},
                 {"gate": "Journal", "status": "pass", "detail": "no issues"},
                 {"gate": "M15", "status": "warning", "detail": "M15 loose (→WAITING_CONFIRMATION)"},
                 {"gate": "ExpectedRR", "status": "pass", "detail": "RR=2.1 vs min=1.3"},
                 {"gate": "ScoreGap", "status": "warning", "detail": "gap=10 vs min=10"},
                 {"gate": "ZoneBroken", "status": "pass", "detail": "zone intact"},
             ]},
            },
            {"step": "final_score", "status": "pass", "summary": "Signal=60 Evidence=60 Exec=60 | Final=60/100 | Decision: WAITING_CONFIRMATION"},
        ],
        "final_score": 60,
        "final_score_detail": {
            "signal_score": 60, "evidence_score": 60, "execution_quality_score": 60,
            "final_score": 60,
        },
        "decision_engine": {"decision": "WAITING_CONFIRMATION", "legacy_action": "wait"},
        "scenarios": [
            {"type": "buy", "entry_status": "confirmed_entry", "m15_quality": "loose",
             "expected_effective_rr": 2.1, "trigger_type": "bos", "ready_to_trade": False},
            {"type": "sell", "entry_status": "watch_zone", "m15_quality": "none",
             "expected_effective_rr": None, "trigger_type": "none", "ready_to_trade": False},
        ],
    }


def _make_screen():
    """Create a ScannerDetailScreen without QApplication (test only methods)."""
    from ui.screens.scanner_detail_screen import ScannerDetailScreen
    screen = ScannerDetailScreen.__new__(ScannerDetailScreen)
    screen.row = {}
    return screen


# ---------------------------------------------------------------------------
# Test 1: Score breakdown HTML
# ---------------------------------------------------------------------------

def test_score_breakdown_html():
    screen = _make_screen()
    analysis = _make_mock_analysis()
    html = screen._diag_score_breakdown_html(analysis)

    assert "Phân rã điểm số" in html
    assert "MUA" in html
    assert "BÁN" in html
    assert "Xu hướng" in html
    assert "Động lượng" in html
    assert "Vị trí" in html
    assert "SMC" in html
    assert "Rủi ro" in html
    assert "Vĩ mô" in html
    assert "TỔNG" in html
    assert "60" in html  # BUY total
    assert "36" in html  # SELL total
    assert "TRUNG" in html  # BUY rating 60 (50-64)
    assert "YẾU" in html  # SELL rating 36 (<50)
    # Note: KHÁ >= 65, MẠNH >= 80
    assert "trung lập" in html.lower()
    assert "xung đột" in html.lower()
    assert "Vĩ mô thuận" in html
    assert "CHOCH ngược hướng" in html
    assert "H4 BOS + displacement" in html

    print("  PASS: test_score_breakdown_html")


# ---------------------------------------------------------------------------
# Test 2: Gate diagnostics from pipeline diagnostics
# ---------------------------------------------------------------------------

def test_gate_html_from_pipeline_diagnostics():
    screen = _make_screen()
    analysis = _make_mock_analysis()
    html = screen._diag_gate_html(analysis)

    assert "Gate kiểm tra" in html
    assert "MT5 (kết nối)" in html
    assert "Spread (chênh lệch)" in html
    assert "M15 (xác nhận)" in html
    assert "R:R kỳ vọng" in html
    assert "Chênh lệch điểm" in html
    assert "Vùng bị phá" in html
    assert "C.BÁO" in html
    assert "CẢNH BÁO" in html  # gate.allowed = True but capped
    assert "WAITING_CONFIRMATION" in html
    assert "M15 xác nhận lỏng" in html

    print("  PASS: test_gate_html_from_pipeline_diagnostics")


# ---------------------------------------------------------------------------
# Test 3: Gate diagnostics fallback (no pipeline diagnostics)
# ---------------------------------------------------------------------------

def test_gate_html_fallback():
    screen = _make_screen()
    analysis = _make_mock_analysis()
    # Remove pipeline diagnostics to force fallback
    analysis.pop("pipeline_diagnostics", None)
    html = screen._diag_gate_html(analysis)

    assert "Gate kiểm tra" in html
    assert "MT5" in html
    assert "Spread" in html
    assert "M15" in html
    assert "C.BÁO" in html
    assert "CẢNH BÁO" in html

    print("  PASS: test_gate_html_fallback")


# ---------------------------------------------------------------------------
# Test 4: _build_gate_checks_from_result
# ---------------------------------------------------------------------------

def test_build_gate_checks_from_result():
    screen = _make_screen()
    analysis = _make_mock_analysis()
    analysis.pop("pipeline_diagnostics", None)

    checks = screen._build_gate_checks_from_result(analysis)
    assert isinstance(checks, list)
    assert len(checks) == 11

    found_gates = {c["gate"] for c in checks}
    expected = {"MT5", "Spread", "DataQuality", "News", "DailyWeeklyLoss",
                "AccountGuard", "Journal", "M15", "ExpectedRR", "ScoreGap", "ZoneBroken"}
    assert found_gates == expected

    # M15 should be warning (M15_LOOSE_CONFIRMATION in warning_codes)
    m15 = [c for c in checks if c["gate"] == "M15"][0]
    assert m15["status"] == "warning"

    # ScoreGap should be warning
    gap = [c for c in checks if c["gate"] == "ScoreGap"][0]
    assert gap["status"] == "warning"

    # MT5 should be pass
    mt5 = [c for c in checks if c["gate"] == "MT5"][0]
    assert mt5["status"] == "pass"

    print("  PASS: test_build_gate_checks_from_result")


# ---------------------------------------------------------------------------
# Test 5: Blocked gate scenario
# ---------------------------------------------------------------------------

def test_gate_html_blocked():
    screen = _make_screen()
    analysis = _make_mock_analysis()
    analysis["trade_gate"]["allowed"] = False
    analysis["trade_gate"]["decision_cap"] = "TRADE_BLOCKED"
    analysis["trade_gate"]["block_codes"] = ["SPREAD_ABNORMAL"]
    analysis["trade_gate"]["warning_codes"] = []
    analysis["trade_gate"]["reasons"] = ["Spread bất thường, không nên giao dịch."]

    # Update pipeline diag gate check too
    for d in analysis["pipeline_diagnostics"]:
        if d.get("step") == "gate":
            d["status"] = "fail"
            d["details"]["gate_checks"][1]["status"] = "block"
            d["details"]["gate_checks"][1]["detail"] = "spread=abnormal"

    html = screen._diag_gate_html(analysis)
    assert "CHẶN" in html  # blocked
    assert "bất thường" in html
    assert "BỊ CHẶN" in html

    print("  PASS: test_gate_html_blocked")


# ---------------------------------------------------------------------------
# Test 6: Entry checklist HTML
# ---------------------------------------------------------------------------

def test_checklist_html():
    screen = _make_screen()
    analysis = _make_mock_analysis()
    html = screen._diag_checklist_html(analysis)

    assert "Điều kiện vào lệnh" in html
    assert "Xu hướng" in html
    assert "Vùng POI" in html
    assert "Xác nhận H1" in html
    assert "Tin tức" in html
    assert "Spread" in html
    assert "R:R" in html
    assert "Lot" in html
    assert "Đạt" in html
    assert "Chờ" in html  # H1 waiting
    assert "trend_up" in html
    assert "1.05200-1.05280" in html

    print("  PASS: test_checklist_html")


# ---------------------------------------------------------------------------
# Test 7: Pipeline steps HTML
# ---------------------------------------------------------------------------

def test_pipeline_steps_html():
    screen = _make_screen()
    analysis = _make_mock_analysis()
    html = screen._diag_pipeline_steps_html(analysis)

    assert "Pipeline từng bước" in html
    assert "Kiểm tra DL" in html
    assert "Tương quan" in html
    assert "Chấm điểm" in html
    assert "Kế hoạch" in html
    assert "Chọn hướng" in html
    assert "Gate" in html
    assert "Điểm cuối" in html
    assert "QUA" in html
    assert "C.BÁO" in html  # gate step is warning

    print("  PASS: test_pipeline_steps_html")


# ---------------------------------------------------------------------------
# Test 8: Final score HTML
# ---------------------------------------------------------------------------

def test_final_score_html():
    screen = _make_screen()
    analysis = _make_mock_analysis()
    html = screen._diag_final_score_html(analysis)

    assert "Điểm cuối cùng" in html
    assert "Tín hiệu" in html
    assert "Bằng chứng (NK)" in html
    assert "Chất lượng thực thi" in html
    assert "65%" in html
    assert "20%" in html
    assert "15%" in html
    assert "WAITING_CONFIRMATION" in html
    assert "60" in html

    print("  PASS: test_final_score_html")


# ---------------------------------------------------------------------------
# Test 9: Empty state (no analysis)
# ---------------------------------------------------------------------------

def test_diagnostics_empty_state():
    screen = _make_screen()
    screen.row = {}
    screen.diag_text = _FakeTextEdit()
    screen._refresh_diagnostics()
    html = screen.diag_text._html
    assert "Chọn một dòng" in html

    print("  PASS: test_diagnostics_empty_state")


# ---------------------------------------------------------------------------
# Test 10: No pipeline diagnostics in analysis
# ---------------------------------------------------------------------------

def test_diagnostics_no_pipeline():
    screen = _make_screen()
    analysis = _make_mock_analysis()
    analysis.pop("pipeline_diagnostics", None)
    screen.row = {"symbol": "EUR/USD", "analysis_result": analysis}
    screen.diag_text = _FakeTextEdit()
    screen._refresh_diagnostics()

    html = screen.diag_text._html
    assert "Phân rã điểm số" in html
    assert "Gate kiểm tra" in html
    assert "Điều kiện vào lệnh" in html
    assert "Điểm cuối cùng" in html
    # Pipeline steps should be absent
    assert "Pipeline từng bước" not in html

    print("  PASS: test_diagnostics_no_pipeline")


# ---------------------------------------------------------------------------
# Test 11: Failing validate step in pipeline diagnostics
# ---------------------------------------------------------------------------

def test_pipeline_with_failure():
    screen = _make_screen()
    analysis = _make_mock_analysis()
    analysis["pipeline_diagnostics"] = [
        {"step": "validate", "status": "fail",
         "summary": "VALIDATION FAILED: insufficient candles (D1=10, H4=10, H1=10)"},
    ]
    html = screen._diag_pipeline_steps_html(analysis)

    assert "1. Kiểm tra DL" in html
    assert "FAIL" in html
    assert "D1=10" in html

    print("  PASS: test_pipeline_with_failure")


# ---------------------------------------------------------------------------
# Test 12: Empty checklist
# ---------------------------------------------------------------------------

def test_empty_checklist():
    screen = _make_screen()
    analysis = _make_mock_analysis()
    analysis["entry_checklist"] = []
    html = screen._diag_checklist_html(analysis)
    assert html == ""

    print("  PASS: test_empty_checklist")


# ---------------------------------------------------------------------------
# Test 13: AI setup audit HTML
# ---------------------------------------------------------------------------

def test_ai_audit_html():
    screen = _make_screen()
    audit = {
        "agreement": "caution",
        "confidence_score": 68,
        "trade_plan_quality": 72,
        "setup_summary": "Setup có điểm tốt nhưng M15 còn lỏng.",
        "market_context_summary": "Macro trung lập, không có tin gần.",
        "risk_flags": ["M15 chưa strict", "Cần kiểm tra spread trước khi vào"],
        "missing_confirmations": ["Đợi nến M15 xác nhận"],
        "do_not_trade_reason": "",
    }
    html = screen._ai_audit_html(audit)

    assert "AI Setup Auditor" in html
    assert "CẢNH BÁO" in html
    assert "68/100" in html
    assert "72/100" in html
    assert "Setup có điểm tốt" in html
    assert "M15 chưa strict" in html
    assert "Đợi nến M15" in html

    print("  PASS: test_ai_audit_html")


def test_ai_audit_empty_state():
    screen = _make_screen()
    screen.row = {"symbol": "EUR/USD"}
    screen.audit_text = _FakeTextEdit()
    screen.audit_btn = None  # needed for hasattr check
    screen._refresh_ai_audit()

    assert "Chưa có kết quả kiểm định AI" in screen.audit_text._html

    print("  PASS: test_ai_audit_empty_state")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

class _FakeTextEdit:
    """Fake QTextEdit that captures setHtml calls."""
    def setHtml(self, html: str) -> None:
        self._html = html


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all_tests():
    tests = [
        ("Score breakdown HTML", test_score_breakdown_html),
        ("Gate HTML from pipeline diag", test_gate_html_from_pipeline_diagnostics),
        ("Gate HTML fallback", test_gate_html_fallback),
        ("Build gate checks from result", test_build_gate_checks_from_result),
        ("Gate HTML blocked scenario", test_gate_html_blocked),
        ("Entry checklist HTML", test_checklist_html),
        ("Pipeline steps HTML", test_pipeline_steps_html),
        ("Final score HTML", test_final_score_html),
        ("Diagnostics empty state", test_diagnostics_empty_state),
        ("Diagnostics no pipeline", test_diagnostics_no_pipeline),
        ("Pipeline with failure", test_pipeline_with_failure),
        ("Empty checklist", test_empty_checklist),
        ("AI audit HTML", test_ai_audit_html),
        ("AI audit empty state", test_ai_audit_empty_state),
    ]

    print("=" * 60)
    print("Scanner Detail Diagnostics Tests")
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
            print(f"  FAIL: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'=' * 60}")
    return failed == 0


if __name__ == "__main__":
    ok = run_all_tests()
    sys.exit(0 if ok else 1)
