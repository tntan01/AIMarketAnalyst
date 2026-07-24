"""Compatibility facade for the permanent scanner safety boundary.

Phase 1 moved the implementation into canonical domain models and Phase 2
introduced the Strategy Router. Existing callers keep this import path so the
Phase-0 safety contract remains continuously enforced during migration.
"""

from __future__ import annotations

from typing import Any

from core.scanner_candidate_engine import evaluate_scanner_candidate
from core.scanner_models import (
    BRANCH_BACKTEST_INVALID,
    BRANCH_BACKTEST_VALIDATED,
    BRANCH_BACKTEST_CONFIGURED,
    BRANCH_DEFAULT_RULES,
    SCANNER_SCORER_VERSION,
    SETUP_SCORE_METRIC,
    ScannerCandidateDecision,
)


AutoTradeSafetyDecision = ScannerCandidateDecision


def evaluate_auto_trade_safety(
    row: dict[str, Any],
    backtest_config: dict[str, object] | None = None,
) -> ScannerCandidateDecision:
    """Evaluate using the canonical model while preserving the Phase-0 API."""

    return evaluate_scanner_candidate(row, backtest_config)
