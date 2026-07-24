"""Executable smoke check for the Phase-0 two-branch safety contract.

Run with:

    python tests/verify_two_branch.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scanner_safety import (
    BRANCH_BACKTEST_CONFIGURED,
    BRANCH_DEFAULT_RULES,
    evaluate_auto_trade_safety,
)
from core.backtest_config_validation import validation_fingerprint


def scenario(side: str = "buy") -> dict:
    return {
        "type": side,
        "entry_zone": [1.0850, 1.0875],
        "entry_status": "confirmed_entry",
        "ready_to_trade": True,
        "m15_quality": "strict",
        "stop_loss": 1.0820,
        "take_profit": [1.0920],
        "expected_effective_rr": 2.0,
    }


def row(*, action: str = "ready", decision: str = "READY_TO_TRADE") -> dict:
    return {
        "symbol": "EUR/USD",
        "scanner_action": action,
        "scanner_decision": decision,
        "scanner_group": "ready_now",
        "trade_permission": "allowed",
        "best_side": "buy",
        "best_score": 80,
        "final_score": 72,
        "setup_score": 72,
        "market_regime": "range",
        "direction_bias": {
            "best_side": "buy",
            "score_gap": 20,
            "is_clear_bias": True,
            "min_gap": 10,
        },
        "score_gap": 20,
        "min_score": 65,
        "min_rr": 1.3,
        "journal_feedback": {},
        "analysis_result": {
            "decision_engine": {"decision": decision},
            "trade_gate": {"allowed": True, "decision_cap": None},
            "scenarios": [scenario()],
        },
    }


BACKTEST_CONFIG = {
    "schema_version": 4,
    "validation_version": "phase8-smc-v2-oos-v1",
    "config_id": "EURUSD-range-buy-v3",
    "status": "VALIDATED",
    "scorer_version": "scanner-v3",
    "feature_version": "scanner-features-v3",
    "smc_scorer_version": "smc-v2",
    "smc_scoring_mode": "v2",
    "symbol": "EUR/USD",
    "allowed_regimes": ["range"],
    "regime": "range",
    "side": "buy",
    "min_score": 65,
    "min_rr": 1.5,
    "score_metric": "setup_score",
    "trained_from": "2025-01-01T00:00:00+00:00",
    "trained_to": "2025-06-30T00:00:00+00:00",
    "validated_from": "2025-07-01T00:00:00+00:00",
    "validated_to": "2025-12-31T00:00:00+00:00",
    "in_sample_trades": 120,
    "out_of_sample_trades": 46,
    "oos_expectancy_r": 0.24,
    "oos_profit_factor": 1.42,
    "oos_max_drawdown_r": 5.8,
    "expectancy_ci_low": 0.05,
    "expectancy_ci_high": 0.43,
    "walk_forward_windows": 3,
    "walk_forward_verdict": "ROBUST",
    "validated_at": "2026-07-24T00:00:00+00:00",
    "expires_at": "2027-07-24T00:00:00+00:00",
}
BACKTEST_CONFIG["validation_fingerprint"] = validation_fingerprint(BACKTEST_CONFIG)


def main() -> None:
    default_ready = evaluate_auto_trade_safety(row())
    assert default_ready.branch == BRANCH_DEFAULT_RULES
    assert default_ready.auto_trade_candidate is True

    backtest_ready = evaluate_auto_trade_safety(row(), BACKTEST_CONFIG)
    assert backtest_ready.branch == BRANCH_BACKTEST_CONFIGURED
    assert backtest_ready.auto_trade_candidate is True

    for action, decision in (
        ("watch", "WATCH_ONLY"),
        ("wait_for_confirmation", "WAITING_CONFIRMATION"),
        ("stand_aside", "STAND_ASIDE"),
    ):
        blocked = evaluate_auto_trade_safety(
            row(action=action, decision=decision),
            BACKTEST_CONFIG,
        )
        assert blocked.auto_trade_candidate is False

    opposite = row()
    opposite["best_side"] = "sell"
    side_mismatch = evaluate_auto_trade_safety(opposite, BACKTEST_CONFIG)
    assert side_mismatch.auto_trade_candidate is False
    assert "CONFIG_SIDE_MISMATCH" in side_mismatch.reason_codes

    print("PASS: Phase-0 two-branch safety contract")


if __name__ == "__main__":
    main()
