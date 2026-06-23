"""Tests for scanner_session_review — AI Market Brief generation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scanner_session_review import build_market_brief_prompt


def _make_rows() -> list[dict]:
    """Build realistic scanner rows for testing."""
    return [
        {"symbol": "EUR/USD", "scanner_group": "ready_now", "scanner_action": "ready",
         "best_side": "buy", "best_score": 75, "final_score": 72, "market_regime": "trend_up",
         "trade_permission": "allowed", "entry_status": "confirmed_entry", "m15_quality": "strict",
         "risk_reward": "1:2.1", "expected_effective_rr": 2.1, "macro_bias": "aligned",
         "score_gap": 15, "price_vs_zone": "in_zone", "short_reason": "Setup đẹp.",
         "journal_sample_size": 12, "journal_expectancy_r": 0.35,
         "analysis_result": {
             "pipeline_diagnostics": [
                 {"step": "gate", "status": "pass", "details": {"gate_checks": [
                     {"gate": "M15", "status": "pass"}, {"gate": "Spread", "status": "pass"},
                 ]}},
             ],
             "macro": {"alignment_source": "AI", "driver_context": {
                 "events": [{"title": "CPI Mỹ", "currency": "USD", "impact": "HIGH", "time": "2026-06-23T12:30"}],
             }},
         }},
        {"symbol": "GBP/USD", "scanner_group": "ready_now", "scanner_action": "ready",
         "best_side": "buy", "best_score": 72, "final_score": 70, "market_regime": "trend_up",
         "trade_permission": "allowed", "entry_status": "confirmed_entry", "m15_quality": "strict",
         "risk_reward": "1:1.8", "expected_effective_rr": 1.8, "macro_bias": "aligned",
         "score_gap": 12, "price_vs_zone": "near_zone", "short_reason": "OK.",
         "journal_sample_size": 8, "journal_expectancy_r": 0.20},
        {"symbol": "USD/JPY", "scanner_group": "waiting_confirmation", "scanner_action": "wait",
         "best_side": "sell", "best_score": 68, "final_score": 65, "market_regime": "range",
         "trade_permission": "caution", "entry_status": "waiting_confirmation", "m15_quality": "loose",
         "risk_reward": "1:1.5", "expected_effective_rr": 1.5, "macro_bias": "neutral",
         "score_gap": 8, "price_vs_zone": "far", "short_reason": "Gap thấp.",
         "journal_sample_size": 3, "journal_expectancy_r": -0.10},
        {"symbol": "AUD/USD", "scanner_group": "blocked", "scanner_action": "stand_aside",
         "best_side": "buy", "best_score": 55, "final_score": 52, "market_regime": "volatile",
         "trade_permission": "blocked", "entry_status": "watch_zone", "m15_quality": "none",
         "risk_reward": "1:1.2", "expected_effective_rr": 1.2, "macro_bias": "divergent",
         "score_gap": 4, "price_vs_zone": "unknown",
         "short_reason": "M15 không xác nhận.", "permission_reason": "M15 không xác nhận"},
        {"symbol": "NZD/USD", "scanner_group": "blocked", "scanner_action": "stand_aside",
         "best_side": "sell", "best_score": 50, "final_score": 48, "market_regime": "volatile",
         "trade_permission": "blocked", "entry_status": "invalidated", "m15_quality": "none",
         "risk_reward": "1:1.0", "expected_effective_rr": 1.0, "macro_bias": "divergent",
         "score_gap": 3, "price_vs_zone": "unknown",
         "short_reason": "Score gap thấp.", "permission_reason": "Score gap thấp"},
        {"symbol": "XAU/USD", "scanner_group": "ready_now", "scanner_action": "ready",
         "best_side": "buy", "best_score": 80, "final_score": 78, "market_regime": "volatile",
         "trade_permission": "allowed", "entry_status": "confirmed_entry", "m15_quality": "strict",
         "risk_reward": "1:2.5", "expected_effective_rr": 2.5, "macro_bias": "aligned",
         "score_gap": 20, "price_vs_zone": "in_zone", "short_reason": "Vàng mạnh.",
         "journal_sample_size": 15, "journal_expectancy_r": 0.50},
        {"symbol": "EUR/JPY", "scanner_group": "waiting_confirmation", "scanner_action": "wait",
         "best_side": "sell", "best_score": 62, "final_score": 60, "market_regime": "trend_up",
         "trade_permission": "caution", "entry_status": "waiting_confirmation", "m15_quality": "loose",
         "risk_reward": "1:1.6", "expected_effective_rr": 1.6, "macro_bias": "neutral",
         "score_gap": 7, "price_vs_zone": "near_zone", "short_reason": "Chờ H1.",
         "journal_sample_size": 5, "journal_expectancy_r": 0.05},
    ]


# ---------------------------------------------------------------------------
# Test 1: Prompt contains required sections
# ---------------------------------------------------------------------------

def test_prompt_contains_all_sections():
    rows = _make_rows()
    prompt = build_market_brief_prompt(rows)

    assert "TỔNG QUAN PHIÊN" in prompt
    assert "NHÓM NÊN ƯU TIÊN" in prompt
    assert "NHÓM NÊN TRÁNH" in prompt
    assert "RỦI RO" in prompt or "RỦI RO KHUYẾN NGHỊ" in prompt
    assert "SETUP ĐANG CHỜ" in prompt

    print("  PASS: test_prompt_contains_all_sections")


# ---------------------------------------------------------------------------
# Test 2: Top setups included in JSON data
# ---------------------------------------------------------------------------

def test_top_setups_included():
    rows = _make_rows()
    prompt = build_market_brief_prompt(rows)

    # The prompt contains JSON with top_setups
    assert "EUR/USD" in prompt
    assert "GBP/USD" in prompt
    assert "XAU/USD" in prompt
    assert "ready_now" in prompt

    print("  PASS: test_top_setups_included")


# ---------------------------------------------------------------------------
# Test 3: Blocked reasons included
# ---------------------------------------------------------------------------

def test_blocked_reasons_included():
    rows = _make_rows()
    prompt = build_market_brief_prompt(rows)

    assert "blocked_reasons" in prompt
    assert "blocked_samples" in prompt

    # Parse the JSON to verify blocked data
    json_start = prompt.find("{")
    data = json.loads(prompt[json_start:])
    blocked = data.get("blocked_reasons", [])
    assert len(blocked) > 0

    print("  PASS: test_blocked_reasons_included")


# ---------------------------------------------------------------------------
# Test 4: Group summary included
# ---------------------------------------------------------------------------

def test_group_summary():
    rows = _make_rows()
    prompt = build_market_brief_prompt(rows)

    json_start = prompt.find("{")
    data = json.loads(prompt[json_start:])
    groups = data.get("group_summary", {})
    assert groups.get("ready_now", 0) >= 3
    assert groups.get("waiting_confirmation", 0) >= 2
    assert groups.get("blocked", 0) >= 2

    print("  PASS: test_group_summary")


# ---------------------------------------------------------------------------
# Test 5: Macro context included when provided
# ---------------------------------------------------------------------------

def test_macro_context():
    rows = _make_rows()
    corr = {"dxy_candles": [1, 2, 3], "vix_candles": [], "us10y_candles": [1, 2]}
    freshness = {"confidence_multiplier": 0.8}

    prompt = build_market_brief_prompt(rows, correlation_context=corr, freshness=freshness)

    json_start = prompt.find("{")
    data = json.loads(prompt[json_start:])
    macro = data.get("macro_context", {})
    assert macro.get("correlation", {}).get("has_dxy") is True
    assert macro.get("correlation", {}).get("has_vix") is False
    assert macro.get("freshness", {}).get("confidence_multiplier") == 0.8

    print("  PASS: test_macro_context")


# ---------------------------------------------------------------------------
# Test 6: Empty rows don't crash
# ---------------------------------------------------------------------------

def test_empty_rows():
    prompt = build_market_brief_prompt([])
    assert "DỮ LIỆU QUÉT THỊ TRƯỜNG" in prompt

    json_start = prompt.find("{")
    data = json.loads(prompt[json_start:])
    assert data["top_setups"] == []
    assert data["group_summary"] == {}

    print("  PASS: test_empty_rows")


# ---------------------------------------------------------------------------
# Test 7: Gate warnings collected from analysis_result
# ---------------------------------------------------------------------------

def test_gate_warnings():
    rows = _make_rows()
    # Only the first row has analysis_result with gate checks
    prompt = build_market_brief_prompt(rows)

    json_start = prompt.find("{")
    data = json.loads(prompt[json_start:])
    gate_warnings = data.get("gate_warnings", {})
    # Should be empty (all gates pass in mock data)
    assert isinstance(gate_warnings, dict)

    print("  PASS: test_gate_warnings")


# ---------------------------------------------------------------------------
# Test 8: Prompt is valid JSON parseable
# ---------------------------------------------------------------------------

def test_prompt_json_parseable():
    rows = _make_rows()
    prompt = build_market_brief_prompt(rows)

    json_start = prompt.find("{")
    data = json.loads(prompt[json_start:])
    assert "top_setups" in data
    assert "blocked_reasons" in data
    assert "group_summary" in data
    assert "timestamp" in data

    print("  PASS: test_prompt_json_parseable")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all_tests():
    tests = [
        ("Prompt contains sections", test_prompt_contains_all_sections),
        ("Top setups included", test_top_setups_included),
        ("Blocked reasons included", test_blocked_reasons_included),
        ("Group summary", test_group_summary),
        ("Macro context", test_macro_context),
        ("Empty rows", test_empty_rows),
        ("Gate warnings", test_gate_warnings),
        ("Prompt JSON parseable", test_prompt_json_parseable),
    ]

    print("=" * 60)
    print("AI Session Review Tests")
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
