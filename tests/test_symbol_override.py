"""Tests for _apply_symbol_override replacing the old hard-coded
range+buy+RR>=2 override with per-symbol config from Settings."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_row(**overrides) -> dict:
    """Build a realistic stand_aside scanner row."""
    row = {
        "symbol": "EUR/USD",
        "scanner_action": "stand_aside",
        "scanner_group": "stand_aside",
        "display_action": "stand_aside",
        "scanner_decision": "STAND_ASIDE",
        "trade_permission": "caution",
        "best_side": "buy",
        "best_score": 55,
        "final_score": 55,
        "market_regime": "range",
        "expected_effective_rr": 2.5,
        "short_reason": "Score below threshold.",
        "permission_reason": "",
        "buy_score": 55,
        "sell_score": 40,
        "entry_status": "waiting_confirmation",
        "m15_quality": "loose",
        "risk_reward": "1:2.5",
    }
    row.update(overrides)
    return row


def _make_controller():
    from controllers.scanner_controller import ScannerController
    ctrl = ScannerController.__new__(ScannerController)
    return ctrl


# ---------------------------------------------------------------------------
# Test 1: No config — row unchanged
# ---------------------------------------------------------------------------

def test_no_config_passes_through():
    ctrl = _make_controller()
    row = _make_row()
    result = ctrl._apply_symbol_override(row, None)
    assert result["scanner_action"] == "stand_aside"

    result = ctrl._apply_symbol_override(row, {})
    assert result["scanner_action"] == "stand_aside"

    print("  PASS: test_no_config_passes_through")


# ---------------------------------------------------------------------------
# Test 2: Config matches all conditions — upgrades to ready
# ---------------------------------------------------------------------------

def test_config_matches_upgrades():
    ctrl = _make_controller()
    row = _make_row()
    cfg = {"regime": "range", "side": "buy", "min_rr": 2.0, "min_score": 50}

    result = ctrl._apply_symbol_override(row, cfg)
    assert result["scanner_action"] == "ready"
    assert result["scanner_group"] == "ready_now"
    assert result["scanner_decision"] == "READY_TO_TRADE"

    print("  PASS: test_config_matches_upgrades")


# ---------------------------------------------------------------------------
# Test 3: Config regime mismatch — row unchanged
# ---------------------------------------------------------------------------

def test_config_regime_mismatch():
    ctrl = _make_controller()
    row = _make_row(market_regime="trend_up")
    cfg = {"regime": "range", "side": "buy", "min_rr": 2.0}

    result = ctrl._apply_symbol_override(row, cfg)
    assert result["scanner_action"] == "stand_aside"

    print("  PASS: test_config_regime_mismatch")


# ---------------------------------------------------------------------------
# Test 4: Config side mismatch — row unchanged
# ---------------------------------------------------------------------------

def test_config_side_mismatch():
    ctrl = _make_controller()
    row = _make_row(best_side="sell")
    cfg = {"regime": "range", "side": "buy", "min_rr": 2.0}

    result = ctrl._apply_symbol_override(row, cfg)
    assert result["scanner_action"] == "stand_aside"

    print("  PASS: test_config_side_mismatch")


# ---------------------------------------------------------------------------
# Test 5: Config RR too low — row unchanged
# ---------------------------------------------------------------------------

def test_config_rr_too_low():
    ctrl = _make_controller()
    row = _make_row(expected_effective_rr=1.5)
    cfg = {"regime": "range", "side": "buy", "min_rr": 2.0}

    result = ctrl._apply_symbol_override(row, cfg)
    assert result["scanner_action"] == "stand_aside"

    print("  PASS: test_config_rr_too_low")


# ---------------------------------------------------------------------------
# Test 6: Config score too low — row unchanged
# ---------------------------------------------------------------------------

def test_config_score_too_low():
    ctrl = _make_controller()
    row = _make_row(best_score=45, final_score=45)
    cfg = {"regime": "range", "side": "buy", "min_score": 50}

    result = ctrl._apply_symbol_override(row, cfg)
    assert result["scanner_action"] == "stand_aside"

    print("  PASS: test_config_score_too_low")


# ---------------------------------------------------------------------------
# Test 7: Already ready — not downgraded
# ---------------------------------------------------------------------------

def test_already_ready_not_downgraded():
    ctrl = _make_controller()
    row = _make_row(scanner_action="ready", scanner_group="ready_now")
    cfg = {"regime": "range", "side": "buy", "min_rr": 2.0}

    result = ctrl._apply_symbol_override(row, cfg)
    assert result["scanner_action"] == "ready"  # stays ready

    print("  PASS: test_already_ready_not_downgraded")


# ---------------------------------------------------------------------------
# Test 8: Permission blocked — not upgraded
# ---------------------------------------------------------------------------

def test_permission_blocked_not_upgraded():
    ctrl = _make_controller()
    row = _make_row(trade_permission="blocked")
    cfg = {"regime": "range", "side": "buy", "min_rr": 2.0, "min_score": 50}

    result = ctrl._apply_symbol_override(row, cfg)
    assert result["scanner_action"] == "stand_aside"

    print("  PASS: test_permission_blocked_not_upgraded")


# ---------------------------------------------------------------------------
# Test 9: Blank config (all empty) — no effect
# ---------------------------------------------------------------------------

def test_blank_config_no_effect():
    ctrl = _make_controller()
    row = _make_row()
    cfg = {"regime": "", "side": "", "min_rr": 0.0, "min_score": 0}

    result = ctrl._apply_symbol_override(row, cfg)
    assert result["scanner_action"] == "stand_aside"

    print("  PASS: test_blank_config_no_effect")


# ---------------------------------------------------------------------------
# Test 10: Old hard-coded override behavior is gone
# (stand_aside + range + buy + RR>=2.0 + score>=50 should NOT auto-upgrade without config)
# ---------------------------------------------------------------------------

def test_old_hardcode_is_gone():
    """Verify the hard-coded override in scanner_row_from_analysis is removed."""
    from core.scanner import scanner_row_from_analysis

    # Build a mock analysis result matching the old hard-coded condition
    # range + buy + RR>=2.0 + score>=50, decision says stand_aside
    mock_result = {
        "symbol": "EUR/USD",
        "scenario_scores": {
            "buy": {"signal_score": 55, "total": 55, "macro_alignment": 7},
            "sell": {"signal_score": 40, "total": 40, "macro_alignment": 7},
        },
        "trade_permission": {"status": "caution", "reason": "M15 chưa xác nhận"},
        "decision_engine": {"legacy_action": "stand_aside", "decision": "STAND_ASIDE"},
        "decision_summary": {"best_side": "buy", "best_score": 55},
        "market_regime": {"primary": "range"},
        "scenarios": [
            {"type": "buy", "expected_effective_rr": 2.5, "entry_status": "waiting_confirmation",
             "m15_quality": "loose", "risk_reward": "1:2.5"},
        ],
        "final_score": 55,
    }

    row = scanner_row_from_analysis(mock_result, broker_symbol="EURUSD")
    # With the old hard-code, this would be "ready".
    # Now it should be "stand_aside" (no override without config).
    assert row["scanner_action"] == "stand_aside", (
        f"Expected stand_aside (no hard-code override), got {row['scanner_action']}"
    )

    print("  PASS: test_old_hardcode_is_gone")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all_tests():
    tests = [
        ("No config passes through", test_no_config_passes_through),
        ("Config matches upgrades", test_config_matches_upgrades),
        ("Config regime mismatch", test_config_regime_mismatch),
        ("Config side mismatch", test_config_side_mismatch),
        ("Config RR too low", test_config_rr_too_low),
        ("Config score too low", test_config_score_too_low),
        ("Already ready not downgraded", test_already_ready_not_downgraded),
        ("Permission blocked not upgraded", test_permission_blocked_not_upgraded),
        ("Blank config no effect", test_blank_config_no_effect),
        ("Old hardcode is gone", test_old_hardcode_is_gone),
    ]

    print("=" * 60)
    print("Symbol Override Config Tests")
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
