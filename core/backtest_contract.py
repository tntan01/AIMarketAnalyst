"""Backtest safety contract shared by replay, validation and Scanner.

Research and validation share the execution-parity engine, while validation
additionally requires a frozen strategy and a chronological OOS replay.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from core.backtest_market_data import DATA_MANIFEST_VERSION
from core.backtest_execution import (
    BACKTEST_EXECUTION_POLICY_VERSION,
    ENTRY_FILL_MODEL,
    EXIT_EVALUATION_MODEL,
    SAME_BAR_STOP_FIRST,
)
from core.backtest_execution_parity import (
    EXECUTION_COST_MODEL_VERSION,
    EXECUTION_MODE_PARITY,
    EXECUTION_MODE_RESEARCH,
    EXECUTION_PARITY_MODEL_VERSION,
    QUOTE_CONVERSION_MODEL_VERSION,
    normalize_execution_mode,
)
from core.backtest_candidate_ledger import (
    CANDIDATE_LEDGER_VERSION,
    CANDIDATE_REPLAY_VERSION,
    FROZEN_STRATEGY_VERSION,
)


BACKTEST_CONTRACT_VERSION = "phase0-backtest-safety-v1"

BACKTEST_PURPOSE_RESEARCH = "RESEARCH"
BACKTEST_PURPOSE_VALIDATION = "VALIDATION"
VALID_BACKTEST_PURPOSES = frozenset({
    BACKTEST_PURPOSE_RESEARCH,
    BACKTEST_PURPOSE_VALIDATION,
})

CURRENT_BACKTEST_ENGINE_VERSION = (
    "system-backtest-v1.2-event-sequence-research"
)
VALIDATION_BACKTEST_ENGINE_VERSION = (
    "system-backtest-v2-execution-parity"
)

BACKTEST_RUN_POLICY_VERSION = "backtest-run-policy-v1"


@dataclass(frozen=True, slots=True)
class BacktestRunPolicy:
    """Resolved orchestration policy for one user-facing Backtest request."""

    version: str
    purpose: str
    execution_mode: str
    run_validation_replay: bool
    run_walk_forward: bool
    research_fast: bool
    release_candidate: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_backtest_purpose(value: object) -> str:
    return str(value or "").strip().upper()


def resolve_backtest_run_policy(
    purpose: object,
    execution_mode: object = EXECUTION_MODE_PARITY,
    *,
    research_validation_enabled: bool = False,
) -> BacktestRunPolicy:
    """Resolve purpose, execution model and mandatory validation evidence.

    Validation is intentionally fail-safe: callers cannot select the fast
    research model or omit frozen IS/OOS and Walk-Forward. Research defaults
    to execution parity, while its extra evidence remains opt-in and cannot
    be combined with the fast research model.
    """

    normalized_purpose = normalize_backtest_purpose(purpose)
    if normalized_purpose not in VALID_BACKTEST_PURPOSES:
        raise ValueError("Mục đích backtest phải là RESEARCH hoặc VALIDATION.")

    requested_mode = normalize_execution_mode(execution_mode)
    if requested_mode not in {EXECUTION_MODE_PARITY, EXECUTION_MODE_RESEARCH}:
        raise ValueError(
            "Execution mode phải là RESEARCH hoặc EXECUTION_PARITY."
        )

    is_validation = normalized_purpose == BACKTEST_PURPOSE_VALIDATION
    resolved_mode = EXECUTION_MODE_PARITY if is_validation else requested_mode
    research_fast = (
        not is_validation and resolved_mode == EXECUTION_MODE_RESEARCH
    )
    evidence_enabled = is_validation or (
        bool(research_validation_enabled) and not research_fast
    )
    return BacktestRunPolicy(
        version=BACKTEST_RUN_POLICY_VERSION,
        purpose=normalized_purpose,
        execution_mode=resolved_mode,
        run_validation_replay=evidence_enabled,
        run_walk_forward=evidence_enabled,
        research_fast=research_fast,
        release_candidate=is_validation,
    )


def build_research_backtest_contract(purpose: object) -> dict[str, Any]:
    """Describe output produced by the current non-validation replay engine."""

    normalized_purpose = normalize_backtest_purpose(purpose)
    return {
        "contract_version": BACKTEST_CONTRACT_VERSION,
        "purpose": normalized_purpose,
        "engine_version": CURRENT_BACKTEST_ENGINE_VERSION,
        "data_manifest_version": DATA_MANIFEST_VERSION,
        "point_in_time_data": True,
        "execution_policy_version": BACKTEST_EXECUTION_POLICY_VERSION,
        "entry_fill_model": ENTRY_FILL_MODEL,
        "exit_evaluation_model": EXIT_EVALUATION_MODEL,
        "same_bar_ambiguity_policy": SAME_BAR_STOP_FIRST,
        "execution_timeframe": "M15",
        "synthetic_trades_allowed": True,
        "execution_parity": False,
        "candidate_ledger_version": CANDIDATE_LEDGER_VERSION,
        "candidate_replay_version": CANDIDATE_REPLAY_VERSION,
        "frozen_strategy_version": FROZEN_STRATEGY_VERSION,
        "frozen_strategy_applied": False,
        "oos_replay": False,
        "validation_eligible": False,
    }


def build_runtime_backtest_contract(
    purpose: object,
    execution_mode: object,
) -> dict[str, Any]:
    """Describe the actual replay engine, without overstating eligibility."""

    normalized_mode = normalize_execution_mode(execution_mode)
    if normalized_mode != EXECUTION_MODE_PARITY:
        contract = build_research_backtest_contract(purpose)
        contract["execution_mode"] = EXECUTION_MODE_RESEARCH
        return contract
    normalized_purpose = normalize_backtest_purpose(purpose)
    return {
        "contract_version": BACKTEST_CONTRACT_VERSION,
        "purpose": normalized_purpose,
        "engine_version": VALIDATION_BACKTEST_ENGINE_VERSION,
        "data_manifest_version": DATA_MANIFEST_VERSION,
        "point_in_time_data": True,
        "execution_policy_version": BACKTEST_EXECUTION_POLICY_VERSION,
        "entry_fill_model": ENTRY_FILL_MODEL,
        "exit_evaluation_model": EXIT_EVALUATION_MODEL,
        "same_bar_ambiguity_policy": SAME_BAR_STOP_FIRST,
        "execution_timeframe": "M15",
        "synthetic_trades_allowed": (
            normalized_purpose != BACKTEST_PURPOSE_VALIDATION
        ),
        "execution_mode": EXECUTION_MODE_PARITY,
        "execution_model_version": EXECUTION_PARITY_MODEL_VERSION,
        "cost_model_version": EXECUTION_COST_MODEL_VERSION,
        "quote_conversion_model_version": QUOTE_CONVERSION_MODEL_VERSION,
        "cost_model": {
            "configured": True,
            "execution_model_version": EXECUTION_PARITY_MODEL_VERSION,
            "cost_model_version": EXECUTION_COST_MODEL_VERSION,
            "quote_conversion_model_version": QUOTE_CONVERSION_MODEL_VERSION,
        },
        "cost_model_fingerprint": "0" * 64,
        "quote_conversion_fingerprint": "0" * 64,
        "execution_parity": True,
        "candidate_ledger_version": CANDIDATE_LEDGER_VERSION,
        "candidate_replay_version": CANDIDATE_REPLAY_VERSION,
        "frozen_strategy_version": FROZEN_STRATEGY_VERSION,
        "frozen_strategy_applied": False,
        "oos_replay": False,
        "validation_eligible": (
            normalized_purpose == BACKTEST_PURPOSE_VALIDATION
        ),
    }


def validation_engine_contract() -> dict[str, Any]:
    """Build the frozen OOS contract expected by validators and fixtures."""

    return {
        "contract_version": BACKTEST_CONTRACT_VERSION,
        "purpose": BACKTEST_PURPOSE_VALIDATION,
        "engine_version": VALIDATION_BACKTEST_ENGINE_VERSION,
        "data_manifest_version": DATA_MANIFEST_VERSION,
        "point_in_time_data": True,
        "execution_policy_version": BACKTEST_EXECUTION_POLICY_VERSION,
        "entry_fill_model": ENTRY_FILL_MODEL,
        "exit_evaluation_model": EXIT_EVALUATION_MODEL,
        "same_bar_ambiguity_policy": SAME_BAR_STOP_FIRST,
        "execution_timeframe": "M15",
        "synthetic_trades_allowed": False,
        "execution_mode": EXECUTION_MODE_PARITY,
        "execution_model_version": EXECUTION_PARITY_MODEL_VERSION,
        "cost_model_version": EXECUTION_COST_MODEL_VERSION,
        "quote_conversion_model_version": QUOTE_CONVERSION_MODEL_VERSION,
        "cost_model": {
            "configured": True,
            "execution_model_version": EXECUTION_PARITY_MODEL_VERSION,
            "cost_model_version": EXECUTION_COST_MODEL_VERSION,
            "quote_conversion_model_version": QUOTE_CONVERSION_MODEL_VERSION,
        },
        "cost_model_fingerprint": "0" * 64,
        "quote_conversion_fingerprint": "0" * 64,
        "execution_parity": True,
        "candidate_ledger_version": CANDIDATE_LEDGER_VERSION,
        "candidate_replay_version": CANDIDATE_REPLAY_VERSION,
        "frozen_strategy_version": FROZEN_STRATEGY_VERSION,
        "frozen_strategy_applied": True,
        "oos_replay": True,
        "validation_eligible": True,
    }
