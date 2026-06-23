"""Tests for minimum journal sample threshold (>= 8) before overriding live decisions.

Covers:
1. classify_scanner_group — journal cap ignored when sample < 8
2. calculate_opportunity_score — journal penalty = 0 when sample < 8
3. append_journal_feedback_reason — "chưa đủ mẫu" vs full feedback
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Test 1: append_journal_feedback_reason — chưa đủ mẫu
# ---------------------------------------------------------------------------

def test_feedback_reason_insufficient_sample():
    from core.scanner import append_journal_feedback_reason

    # 2 mẫu âm — vẫn chỉ cảnh báo "chưa đủ mẫu", không phán xét
    feedback = {"sample_size": 2, "expectancy_r": -1.0}
    result = append_journal_feedback_reason("Score thấp.", feedback)
    assert "chưa đủ mẫu" in result
    assert "2 lệnh" in result
    assert "kỳ vọng" not in result  # không hiển thị expectancy khi chưa đủ mẫu

    # 0 mẫu — không thêm gì
    feedback_zero = {"sample_size": 0, "expectancy_r": 0.0}
    result = append_journal_feedback_reason("Score thấp.", feedback_zero)
    assert result == "Score thấp."

    print("  PASS: test_feedback_reason_insufficient_sample")


# ---------------------------------------------------------------------------
# Test 2: append_journal_feedback_reason — đủ mẫu, expectancy âm
# ---------------------------------------------------------------------------

def test_feedback_reason_sufficient_sample_negative():
    from core.scanner import append_journal_feedback_reason

    # 10 mẫu, expectancy -0.30 — đủ để hiển thị kết luận
    feedback = {"sample_size": 10, "expectancy_r": -0.30}
    result = append_journal_feedback_reason("Score thấp.", feedback)
    assert "10 mẫu" in result
    assert "kỳ vọng -0.30R" in result
    assert "chưa đủ mẫu" not in result

    print("  PASS: test_feedback_reason_sufficient_sample_negative")


# ---------------------------------------------------------------------------
# Test 3: append_journal_feedback_reason — đủ mẫu, expectancy dương nhẹ
# ---------------------------------------------------------------------------

def test_feedback_reason_sufficient_sample_neutral():
    from core.scanner import append_journal_feedback_reason

    # 15 mẫu, expectancy +0.05 — không âm, không cap → giữ nguyên reason
    feedback = {"sample_size": 15, "expectancy_r": 0.05}
    result = append_journal_feedback_reason("Điểm TB.", feedback)
    assert result == "Điểm TB."  # không thêm gì

    print("  PASS: test_feedback_reason_sufficient_sample_neutral")


# ---------------------------------------------------------------------------
# Test 4: append_journal_feedback_reason — đủ mẫu, có decision_cap
# ---------------------------------------------------------------------------

def test_feedback_reason_with_cap():
    from core.scanner import append_journal_feedback_reason

    # 12 mẫu, expectancy +0.10 nhưng decision_cap = TRADE_BLOCKED
    feedback = {"sample_size": 12, "expectancy_r": 0.10, "decision_cap": "TRADE_BLOCKED"}
    result = append_journal_feedback_reason("OK.", feedback)
    assert "12 mẫu" in result

    print("  PASS: test_feedback_reason_with_cap")


# ---------------------------------------------------------------------------
# Test 5: classify_scanner_group — journal cap ignored when sample < 8
# ---------------------------------------------------------------------------

def test_group_not_downgraded_when_insufficient_sample():
    from core.scanner_ranking_engine import calculate_opportunity_score, READY_NOW

    # row ready_now, journal có TRADE_BLOCKED nhưng chỉ 3 mẫu
    row = {
        "scanner_action": "ready",
        "scanner_decision": "READY_TO_TRADE",
        "trade_permission": "allowed",
        "entry_status": "confirmed_entry",
        "ready_to_trade": True,
        "final_score": 72,
        "best_score": 72,
        "score_gap": 15,
        "best_side": "buy",
        "risk_reward": "1:2.0",
        "expected_effective_rr": 2.0,
        "price_vs_zone": "in_zone",
        "m15_quality": "strict",
        "journal_feedback": {
            "sample_size": 3,  # < 8
            "decision_cap": "TRADE_BLOCKED",
            "expectancy_r": -0.50,
            "opportunity_penalty": -15,
        },
    }
    result = calculate_opportunity_score(row)
    # Group should still be READY_NOW (not downgraded)
    assert result["scanner_group"] == READY_NOW, (
        f"Expected READY_NOW (journal ignored due to sample<8), got {result['scanner_group']}"
    )
    # Penalty should be 0
    assert result["score_breakdown"]["journal_feedback_penalty"] == 0

    print("  PASS: test_group_not_downgraded_when_insufficient_sample")


# ---------------------------------------------------------------------------
# Test 6: classify_scanner_group — journal cap applied when sample >= 8
# ---------------------------------------------------------------------------

def test_group_downgraded_when_sufficient_sample():
    from core.scanner_ranking_engine import calculate_opportunity_score, WATCH_ZONE

    row = {
        "scanner_action": "ready",
        "scanner_decision": "READY_TO_TRADE",
        "trade_permission": "allowed",
        "entry_status": "confirmed_entry",
        "ready_to_trade": True,
        "final_score": 72,
        "best_score": 72,
        "score_gap": 15,
        "best_side": "buy",
        "risk_reward": "1:2.0",
        "expected_effective_rr": 2.0,
        "price_vs_zone": "in_zone",
        "m15_quality": "strict",
        "journal_feedback": {
            "sample_size": 12,  # >= 8
            "decision_cap": "TRADE_BLOCKED",
            "expectancy_r": -0.50,
            "opportunity_penalty": -15,
        },
    }
    result = calculate_opportunity_score(row)
    # Should be BLOCKED (journal TRADE_BLOCKED overrides)
    assert result["scanner_group"] == "blocked", (
        f"Expected BLOCKED (journal applied), got {result['scanner_group']}"
    )
    # Penalty should be applied
    assert result["score_breakdown"]["journal_feedback_penalty"] == -15

    print("  PASS: test_group_downgraded_when_sufficient_sample")


# ---------------------------------------------------------------------------
# Test 7: WATCH_ONLY cap applied with sufficient sample
# ---------------------------------------------------------------------------

def test_watch_only_cap_with_sufficient_sample():
    from core.scanner_ranking_engine import calculate_opportunity_score, WATCH_ZONE

    row = {
        "scanner_action": "ready",
        "scanner_decision": "READY_TO_TRADE",
        "trade_permission": "allowed",
        "entry_status": "confirmed_entry",
        "ready_to_trade": True,
        "final_score": 75,
        "best_score": 75,
        "score_gap": 20,
        "best_side": "buy",
        "risk_reward": "1:2.0",
        "expected_effective_rr": 2.0,
        "price_vs_zone": "in_zone",
        "m15_quality": "strict",
        "journal_feedback": {
            "sample_size": 10,  # >= 8
            "decision_cap": "WATCH_ONLY",
            "expectancy_r": -0.10,
            "opportunity_penalty": -5,
        },
    }
    result = calculate_opportunity_score(row)
    assert result["scanner_group"] == WATCH_ZONE
    assert result["score_breakdown"]["journal_feedback_penalty"] == -5

    print("  PASS: test_watch_only_cap_with_sufficient_sample")


# ---------------------------------------------------------------------------
# Test 8: Sample >= 8 but cap empty — no override
# ---------------------------------------------------------------------------

def test_sufficient_sample_no_cap():
    from core.scanner_ranking_engine import calculate_opportunity_score, READY_NOW

    row = {
        "scanner_action": "ready",
        "scanner_decision": "READY_TO_TRADE",
        "trade_permission": "allowed",
        "entry_status": "confirmed_entry",
        "ready_to_trade": True,
        "final_score": 72,
        "best_score": 72,
        "score_gap": 15,
        "best_side": "buy",
        "risk_reward": "1:2.0",
        "expected_effective_rr": 2.0,
        "price_vs_zone": "in_zone",
        "m15_quality": "strict",
        "journal_feedback": {
            "sample_size": 20,  # >= 8
            "decision_cap": "",  # no cap
            "expectancy_r": 0.30,
            "opportunity_penalty": 0,
        },
    }
    result = calculate_opportunity_score(row)
    assert result["scanner_group"] == READY_NOW
    assert result["score_breakdown"]["journal_feedback_penalty"] == 0

    print("  PASS: test_sufficient_sample_no_cap")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all_tests():
    tests = [
        ("Feedback reason insufficient sample", test_feedback_reason_insufficient_sample),
        ("Feedback reason sufficient negative", test_feedback_reason_sufficient_sample_negative),
        ("Feedback reason sufficient neutral", test_feedback_reason_sufficient_sample_neutral),
        ("Feedback reason with cap", test_feedback_reason_with_cap),
        ("Group not downgraded < 8 samples", test_group_not_downgraded_when_insufficient_sample),
        ("Group downgraded >= 8 samples", test_group_downgraded_when_sufficient_sample),
        ("WATCH_ONLY cap sufficient sample", test_watch_only_cap_with_sufficient_sample),
        ("Sufficient sample no cap", test_sufficient_sample_no_cap),
    ]

    print("=" * 60)
    print("Journal Sample Threshold Tests")
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
