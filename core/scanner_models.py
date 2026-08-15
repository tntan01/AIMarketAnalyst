"""Canonical domain models for scanner strategy and execution decisions.

The scanner pipeline still receives dictionaries from analysis engines, but
controllers and UI should consume these immutable models instead of deriving
side, score, scenario, or readiness independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any



BUY = "buy"
SELL = "sell"
VALID_SIDES = frozenset({BUY, SELL})

SCANNER_SCORER_VERSION = "scanner-v3"
SCANNER_FEATURE_VERSION = "scanner-features-v3"
STRATEGY_ROUTER_VERSION = "phase2-router-v1"
EXECUTION_REVALIDATION_VERSION = "phase3-revalidation-v1"
SCANNER_RANKING_VERSION = "phase6-ranking-v1"

BRANCH_BACKTEST_VALIDATED = "BACKTEST_VALIDATED"
BRANCH_BACKTEST_INVALID = "BACKTEST_INVALID"
BRANCH_DEFAULT_RULES = "DEFAULT_RULES"
# Compatibility alias for callers compiled against the Phase-0/1 name.
BRANCH_BACKTEST_CONFIGURED = BRANCH_BACKTEST_VALIDATED

CONFIG_VALIDATED = "VALIDATED"
CONFIG_DRAFT = "DRAFT"
CONFIG_DISABLED = "DISABLED"
CONFIG_INVALID = "INVALID"
CONFIG_EXPIRED = "EXPIRED"
CONFIG_VERSION_MISMATCH = "VERSION_MISMATCH"
CONFIG_NOT_CONFIGURED = "NOT_CONFIGURED"
# Compatibility alias; new decisions always emit one of the statuses above.
CONFIG_CONFIGURED = CONFIG_VALIDATED

SETUP_SCORE_METRIC = "setup_score"

READY_NOW = "READY_NOW"
WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
WATCH_ZONE = "WATCH_ZONE"
OUT_OF_STRATEGY = "OUT_OF_STRATEGY"
BLOCKED = "BLOCKED"
DATA_UNAVAILABLE = "DATA_UNAVAILABLE"

VALID_CANDIDATE_STATUSES = frozenset({
    READY_NOW,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
    OUT_OF_STRATEGY,
    BLOCKED,
    DATA_UNAVAILABLE,
})


@dataclass(frozen=True, slots=True)
class SideEvaluation:
    """All setup data belonging to exactly one BUY or SELL side."""

    side: str
    signal_score: float | None
    final_score: float | None
    expected_effective_rr: float | None
    scenario: dict[str, Any] | None
    entry_status: str
    m15_quality: str
    gate_result: dict[str, Any]
    reason_codes: tuple[str, ...] = ()

    @property
    def setup_score(self) -> float | None:
        """Canonical live/backtest score; currently aliases final_score."""
        return self.final_score

    @property
    def stop_loss(self) -> object:
        return self.scenario.get("stop_loss") if self.scenario is not None else None

    @property
    def take_profit(self) -> object:
        return self.scenario.get("take_profit") if self.scenario is not None else None

    @property
    def entry_zone(self) -> object:
        return self.scenario.get("entry_zone") if self.scenario is not None else None

    def to_dict(self, *, include_scenario: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "side": self.side,
            "signal_score": self.signal_score,
            "final_score": self.final_score,
            "setup_score": self.setup_score,
            "expected_effective_rr": self.expected_effective_rr,
            "entry_status": self.entry_status,
            "m15_quality": self.m15_quality,
            "gate_result": dict(self.gate_result),
            "reason_codes": list(self.reason_codes),
            "entry_zone": self.entry_zone,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
        }
        if include_scenario:
            payload["scenario"] = (
                dict(self.scenario) if self.scenario is not None else None
            )
        return payload


@dataclass(frozen=True, slots=True)
class StrategyEvaluation:
    """Result of selecting and checking one strategy branch."""

    branch: str
    config_status: str
    selected_side: str | None
    score_metric: str
    score_value: float | None
    min_score: float | None
    expected_effective_rr: float | None
    min_rr: float | None
    eligible: bool
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "config_status": self.config_status,
            "selected_side": self.selected_side,
            "score_metric": self.score_metric,
            "score_value": self.score_value,
            "min_score": self.min_score,
            "expected_effective_rr": self.expected_effective_rr,
            "min_rr": self.min_rr,
            "eligible": self.eligible,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class ExecutionEvaluation:
    """Current setup readiness and permission checks.

    This model is scan-time only, so ``live_price_valid`` and
    ``portfolio_allowed`` remain ``None`` here. Final execution uses
    :class:`ExecutionRevalidation` and Phase-4 ``PortfolioEvaluation``;
    ``None`` must never be interpreted as an affirmative result.
    """

    entry_ready: bool
    trade_allowed: bool
    live_price_valid: bool | None
    portfolio_allowed: bool | None
    reason_codes: tuple[str, ...] = ()
    block_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_ready": self.entry_ready,
            "trade_allowed": self.trade_allowed,
            "live_price_valid": self.live_price_valid,
            "portfolio_allowed": self.portfolio_allowed,
            "reason_codes": list(self.reason_codes),
            "block_codes": list(self.block_codes),
        }


@dataclass(frozen=True, slots=True)
class ExecutionMarketSnapshot:
    """One immutable broker snapshot captured immediately before an order."""

    broker_symbol: str
    captured_at: datetime
    connected: bool
    logged_in: bool
    trade_allowed: bool
    symbol_available: bool
    symbol_trade_mode: int | None
    bid: float | None
    ask: float | None
    point: float | None
    spread_points: float | None
    spread_price: float | None
    tick_time: datetime | None
    volume_min: float | None
    volume_max: float | None
    volume_step: float | None
    symbol_state_available: bool
    has_open_position_or_order: bool | None
    trade_tick_size: float | None = None
    trade_tick_value_loss: float | None = None
    contract_size: float | None = None
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "broker_symbol": self.broker_symbol,
            "captured_at": self.captured_at.isoformat(),
            "connected": self.connected,
            "logged_in": self.logged_in,
            "trade_allowed": self.trade_allowed,
            "symbol_available": self.symbol_available,
            "symbol_trade_mode": self.symbol_trade_mode,
            "bid": self.bid,
            "ask": self.ask,
            "point": self.point,
            "spread_points": self.spread_points,
            "spread_price": self.spread_price,
            "tick_time": self.tick_time.isoformat() if self.tick_time else None,
            "volume_min": self.volume_min,
            "volume_max": self.volume_max,
            "volume_step": self.volume_step,
            "symbol_state_available": self.symbol_state_available,
            "has_open_position_or_order": self.has_open_position_or_order,
            "trade_tick_size": self.trade_tick_size,
            "trade_tick_value_loss": self.trade_tick_value_loss,
            "contract_size": self.contract_size,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class ExecutionRevalidation:
    """Structured result of the last fail-closed check before order_send."""

    allowed: bool
    side: str | None
    execution_price: float | None
    expected_effective_rr: float | None
    required_min_rr: float | None
    volume: float | None
    live_price_valid: bool
    news_allowed: bool
    account_allowed: bool
    portfolio_allowed: bool
    checked_at: datetime
    reason_codes: tuple[str, ...] = ()
    block_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_revalidation_version": EXECUTION_REVALIDATION_VERSION,
            "allowed": self.allowed,
            "side": self.side,
            "execution_price": self.execution_price,
            "expected_effective_rr": self.expected_effective_rr,
            "required_min_rr": self.required_min_rr,
            "volume": self.volume,
            "live_price_valid": self.live_price_valid,
            "news_allowed": self.news_allowed,
            "account_allowed": self.account_allowed,
            "portfolio_allowed": self.portfolio_allowed,
            "checked_at": self.checked_at.isoformat(),
            "reason_codes": list(self.reason_codes),
            "block_codes": list(self.block_codes),
        }


@dataclass(frozen=True, slots=True)
class ScannerCandidateDecision:
    """Single source of truth consumed by controller, UI and alerts."""

    status: str
    side_evaluation: SideEvaluation | None
    side_evaluations: tuple[SideEvaluation, ...]
    strategy: StrategyEvaluation
    execution: ExecutionEvaluation
    auto_trade_candidate: bool
    reason_codes: tuple[str, ...] = ()

    @property
    def branch(self) -> str:
        return self.strategy.branch

    @property
    def selected_side(self) -> str | None:
        return self.strategy.selected_side

    @property
    def setup_score(self) -> float | None:
        return self.strategy.score_value

    @property
    def strategy_eligible(self) -> bool:
        return self.strategy.eligible

    @property
    def execution_ready(self) -> bool:
        return self.execution.entry_ready

    @property
    def trade_allowed(self) -> bool:
        return self.execution.trade_allowed

    @property
    def scenario(self) -> dict[str, Any] | None:
        return (
            self.side_evaluation.scenario
            if self.side_evaluation is not None
            else None
        )

    def to_dict(self, *, include_scenario: bool = False) -> dict[str, Any]:
        return {
            "strategy_router_version": STRATEGY_ROUTER_VERSION,
            "status": self.status,
            "branch": self.branch,
            "selected_side": self.selected_side,
            "setup_score": self.setup_score,
            "strategy_eligible": self.strategy_eligible,
            "execution_ready": self.execution_ready,
            "trade_allowed": self.trade_allowed,
            "auto_trade_candidate": self.auto_trade_candidate,
            "reason_codes": list(self.reason_codes),
            "strategy": self.strategy.to_dict(),
            "execution": self.execution.to_dict(),
            "side_evaluation": (
                self.side_evaluation.to_dict(include_scenario=include_scenario)
                if self.side_evaluation is not None
                else None
            ),
            "side_evaluations": {
                item.side: item.to_dict(include_scenario=include_scenario)
                for item in self.side_evaluations
            },
            **(
                {"scenario": dict(self.scenario)}
                if include_scenario and self.scenario is not None
                else {}
            ),
        }


@dataclass(frozen=True, slots=True)
class ScannerRankingEvaluation:
    """Canonical ranking values computed only after candidate filtering."""

    status: str
    status_priority: int
    opportunity_rank: float
    evidence_confidence: float
    strategy_confidence: float
    execution_readiness: float
    effective_rr: float | None
    expected_value_r: float | None
    breakdown: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ranking_version": SCANNER_RANKING_VERSION,
            "status": self.status,
            "status_priority": self.status_priority,
            "opportunity_rank": self.opportunity_rank,
            "evidence_confidence": self.evidence_confidence,
            "strategy_confidence": self.strategy_confidence,
            "execution_readiness": self.execution_readiness,
            "effective_rr": self.effective_rr,
            "expected_value_r": self.expected_value_r,
            "breakdown": dict(self.breakdown),
        }


# Target-only Scanner V4 contract exports.  Keeping these imports after all
# executable V3 definitions prevents target identities from changing the current
# runtime constants or serialization paths before direct cutover.
from core.scanner_v4_models import (  # noqa: E402
    CanonicalPairSnapshot,
    DecisionResult,
    GateCheck,
    MacroAssessment,
    MacroGateResult,
    MarketSafetyResult,
    PAYLOAD_INVALID,
    PAYLOAD_LEGACY_V3,
    PAYLOAD_V4,
    SCANNER_V4_FEATURE_VERSION,
    SCANNER_V4_MACRO_POLICY_VERSION,
    SCANNER_V4_OUTPUT_SCHEMA_VERSION,
    SCANNER_V4_RANKING_VERSION,
    SCANNER_V4_SAFETY_POLICY_VERSION,
    SCANNER_V4_SCORING_VERSION,
    SCANNER_V4_SNAPSHOT_VERSION,
    SCANNER_V4_VERSION_FIELDS,
    ScannerPayloadClassification,
    ScannerV4ContractError,
    SideScore,
    TechnicalBreakdown,
    TechnicalComponent,
    classify_scanner_payload,
    classify_scanner_payload_json,
    deserialize_canonical_pair_snapshot,
    serialize_canonical_pair_snapshot,
    validate_canonical_pair_snapshot,
)
