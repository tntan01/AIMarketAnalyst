"""Deterministic, target-only Scanner V4 analysis pipeline and direct composition.

Step 07 of the Scanner V4 migration implements the *analysis pipeline* that
calls the Bước 03-06 modules in one deterministic order and produces the
canonical v4 artifact.  Locked before any code (Mục 8 / Bước 07 doc block):

* snapshot ID / freshness: ``v4:<symbol>:<captured_at ISO Z>:sha256(canonical
  input JSON)[:12]``; a snapshot older than ``SNAPSHOT_MAX_AGE_SECONDS`` (120s)
  is STALE and one more than ``SNAPSHOT_MAX_FUTURE_SKEW_SECONDS`` (30s) into
  the future cannot certify freshness -> full-schema ``DATA_UNAVAILABLE``.
* MacroGate evaluates ONCE on the selected side only
  (``macro_gate.assessed_side == decision.selected_side``).
* ONE composition API ``compose_scanner_v4`` shared by live and backtest;
  the two adapters differ only in ``capture_source`` provenance.

Pipeline order (exactly): immutable snapshot -> validate technical context /
SMC / regime -> MarketSafetyGate -> TechnicalScore BUY/SELL -> technical gap /
best side (TechnicalScore only) -> scenario (selected side) ->
Evidence/Execution (selected side) -> FinalScore -> MacroGate (selected side) ->
account / portfolio / journal gates -> decision.

Fail-closed rules:

* TechnicalScoreDataError / FinalScoreDataError or a stale/future snapshot
  produce the full v4 schema with ``DATA_UNAVAILABLE`` and no fake scores.
* Missing data / uncalibrated policy never produce optimistic PASS: gates
  return typed UNKNOWN with a reason code.  Safety/Macro/Account/Portfolio
  UNKNOWN are *critical* -> BLOCKED; scenario/journal UNKNOWN and any CAUTION
  mean WATCH_ZONE (no confirmation can be certified).
* Any gate BLOCK -> BLOCKED with the blocking codes recorded.
* Safety/Macro NEVER mutate Technical/Final scores: a BLOCK keeps the scores
  and scenario for explanation.
* No risk/macro/correlation/AI scored component, no ``scenario_scores.total``,
  no ``risk_score < 9``, no READY_NOW and no order payload (those are Bước 08/12).
* ``final_score`` is only the alias of the correct-side ``setup_score``.
* All scores/scenarios/evidence/execution/macro carry an explicit side.
* Evidence/Execution missing -> Bước 06 neutral-50 fallback with source/warning.

This module is not wired to runtime.  The V3 runtime is untouched until the
atomic cutover; the V3 paths to remove are ledgered in Mục 7.2/7.3.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from fractions import Fraction
from types import MappingProxyType
from typing import Any

from core.final_score_v4 import (
    FINAL_SCORE_NEUTRAL_FALLBACK_SOURCE,
    FinalScoreDataError,
    FinalScoreResult,
    score_final_score,
)
from core.macro_gate import (
    DEFAULT_MACRO_POLICY,
    MacroGate,
    MacroPolicy,
    build_macro_assessment,
)
from core.market_safety_gate import (
    MarketSafetyContext,
    MarketSafetyGate,
    SafetyPolicy,
)
from core.reason_codes import (
    COMPOSE_FLOOR_POLICY_OPEN,
    COMPOSE_SCORE_FLOOR_NOT_MET,
    GATES_ALL_PASS,
    GATE_ACCOUNT_DATA_MISSING,
    GATE_ACCOUNT_MARGIN_BLOCK,
    GATE_JOURNAL_DATA_MISSING,
    GATE_JOURNAL_DRAWDOWN_CAUTION,
    GATE_JOURNAL_POLICY_OPEN,
    GATE_JOURNAL_REVENGE_BLOCK,
    GATE_PORTFOLIO_DATA_MISSING,
    GATE_PORTFOLIO_LIMIT_BLOCK,
    GATE_PORTFOLIO_POLICY_OPEN,
    GATE_SCENARIO_PLAN_MISSING,
    GATE_SCENARIO_POLICY_OPEN,
    GATE_SCENARIO_RR_BLOCK,
    SNAPSHOT_FRESHNESS_UNKNOWN,
    SNAPSHOT_STALE,
    TECHNICAL_DATA_UNAVAILABLE,
)
from core.scanner_v4_models import (
    BUY,
    SELL,
    VALID_SIDES,
    BLOCK,
    CAUTION,
    PASS,
    UNKNOWN,
    SCANNER_V4_SAFETY_POLICY_VERSION,
    CanonicalPairSnapshot,
    DecisionResult,
    MacroAssessment,
    MacroGateResult,
    MarketSafetyResult,
    SideScore,
    TechnicalBreakdown,
    TechnicalComponent,
    deserialize_canonical_pair_snapshot,
)
from core.smc_scoring_result import SmcScoringResult
from core.technical_signal_scorer import (
    TECHNICAL_COMPONENT_RAW_MAX,
    TechnicalScoreDataError,
    TechnicalSignalScoreResult,
    VALID_TECHNICAL_REGIMES,
    score_technical_signal,
    technical_signal_score_gap,
)

COMPOSITION_POLICY_VERSION = "scanner-composition-v4"

# Locked freshness SLA (Mục 8 / Bước 07 doc block).
SNAPSHOT_MAX_AGE_SECONDS = 120
SNAPSHOT_MAX_FUTURE_SKEW_SECONDS = 30

# Locked side/tie behavior: on an exact BUY/SELL technical tie the deterministic
# selected side is BUY.  score_gap on a tie is 0 and the model's selected-side
# invariant is trivially satisfied.
_TIE_BREAK_SIDE = BUY

# Marker source for a side whose canonical technical context was unavailable.
# It documents the side state without claiming a real data feed.
_UNAVAILABLE_SOURCE = "technical_unavailable"

_VALID_CAPTURE_SOURCES = frozenset({"live", "backtest"})

_TECHNICAL_RAW_KEYS = ("trend", "momentum", "location")

_CRITICAL_GATES = frozenset({"market_safety", "macro", "account", "portfolio"})


class CompositionInputError(ValueError):
    """Typed misuse: the snapshot/options/policy shapes are invalid for composition."""

    code = "COMPOSITION_INPUT_INVALID"

    def __init__(self, path: str, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(f"{self.code} at {path}: {detail}")


class CompositionServiceError(ValueError):
    """Typed internal failure inside a gate/scorer; never fabricates PASS or a score."""

    code = "COMPOSITION_SERVICE_ERROR"

    def __init__(self, path: str, detail: str, cause: BaseException | None = None) -> None:
        self.path = path
        self.detail = detail
        self.cause = cause
        message = f"{self.code} at {path}: {detail}"
        if cause is not None:
            message = f"{message} (cause: {cause!r})"
        super().__init__(message)


# ---------------------------------------------------------------------------
# Immutable input model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ScenarioPlan:
    """One explicit-side scenario (entry/SL/TP).  Ordering validates the shape."""

    direction: str
    entry: float
    stop_loss: float
    take_profit: float
    source: str = ""

    def __post_init__(self) -> None:
        _require_side(self.direction, "scenario_plan.direction")
        entry = _require_positive(self.entry, "scenario_plan.entry")
        stop_loss = _require_positive(self.stop_loss, "scenario_plan.stop_loss")
        take_profit = _require_positive(self.take_profit, "scenario_plan.take_profit")
        if self.direction == BUY:
            if not (stop_loss < entry < take_profit):
                raise CompositionInputError(
                    "scenario_plan",
                    "buy scenario requires stop_loss < entry < take_profit",
                )
        else:
            if not (take_profit < entry < stop_loss):
                raise CompositionInputError(
                    "scenario_plan",
                    "sell scenario requires take_profit < entry < stop_loss",
                )
        if type(self.source) is not str:
            raise CompositionInputError("scenario_plan.source", "expected a string")
        object.__setattr__(self, "entry", entry)
        object.__setattr__(self, "stop_loss", stop_loss)
        object.__setattr__(self, "take_profit", take_profit)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class SideSnapshot:
    """Per-side composition input (technical raws + evidence/execution + plan).

    Evidence/Execution are strict integers in 0..100 (or None).  A score without
    a non-empty source is rejected so the canonical SideScore source contract is
    never fabricated; a source without a score is also rejected (contradictory).
    """

    technical_raws: Mapping[str, int] = field(default_factory=dict)
    evidence_score: int | None = None
    evidence_source: str = ""
    execution_quality_score: int | None = None
    execution_quality_source: str = ""
    scenario_plan: ScenarioPlan | None = None

    def __post_init__(self) -> None:
        raws = dict(self.technical_raws)
        if set(raws) != set(_TECHNICAL_RAW_KEYS):
            raise CompositionInputError(
                "side.technical_raws",
                f"must contain exactly {sorted(_TECHNICAL_RAW_KEYS)}",
            )
        for name, maximum in TECHNICAL_COMPONENT_RAW_MAX.items():
            if name == "smc":
                continue  # the SMC raw is projected from the canonical SMC
            _require_raw(raws[name], f"side.technical_raws.{name}", maximum)
        object.__setattr__(self, "technical_raws", MappingProxyType(raws))
        object.__setattr__(
            self,
            "evidence_score",
            _require_optional_score(self.evidence_score, "side.evidence_score"),
        )
        object.__setattr__(
            self,
            "execution_quality_score",
            _require_optional_score(
                self.execution_quality_score, "side.execution_quality_score"
            ),
        )
        evidence_source = _require_provenance_source(
            self.evidence_score,
            self.evidence_source,
            "side.evidence_source",
        )
        execution_source = _require_provenance_source(
            self.execution_quality_score,
            self.execution_quality_source,
            "side.execution_quality_source",
        )
        object.__setattr__(self, "evidence_source", evidence_source)
        object.__setattr__(self, "execution_quality_source", execution_source)
        if self.scenario_plan is not None and type(self.scenario_plan) is not ScenarioPlan:
            raise CompositionInputError(
                "side.scenario_plan", "expected a ScenarioPlan or null"
            )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "trend_raw": self.technical_raws["trend"],
            "momentum_raw": self.technical_raws["momentum"],
            "location_raw": self.technical_raws["location"],
            "evidence_score": self.evidence_score,
            "evidence_source": self.evidence_source,
            "execution_quality_score": self.execution_quality_score,
            "execution_quality_source": self.execution_quality_source,
            "scenario_plan": (
                None if self.scenario_plan is None else self.scenario_plan.to_canonical_dict()
            ),
        }


@dataclass(frozen=True, slots=True)
class AccountState:
    free_margin: float | None = None
    required_margin: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "free_margin",
            _require_optional_positive(self.free_margin, "account.free_margin"),
        )
        object.__setattr__(
            self,
            "required_margin",
            _require_optional_positive(
                self.required_margin, "account.required_margin"
            ),
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "free_margin": self.free_margin,
            "required_margin": self.required_margin,
        }


@dataclass(frozen=True, slots=True)
class PortfolioState:
    open_positions: int | None = None
    exposure_ratio: float | None = None

    def __post_init__(self) -> None:
        if self.open_positions is not None and (
            type(self.open_positions) is not int or self.open_positions < 0
        ):
            raise CompositionInputError(
                "portfolio.open_positions", "expected a non-negative integer or null"
            )
        object.__setattr__(
            self,
            "exposure_ratio",
            _require_optional_positive(self.exposure_ratio, "portfolio.exposure_ratio"),
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "open_positions": self.open_positions,
            "exposure_ratio": self.exposure_ratio,
        }


@dataclass(frozen=True, slots=True)
class JournalState:
    consecutive_losses: int | None = None
    recent_drawdown_ratio: float | None = None

    def __post_init__(self) -> None:
        if self.consecutive_losses is not None and (
            type(self.consecutive_losses) is not int or self.consecutive_losses < 0
        ):
            raise CompositionInputError(
                "journal.consecutive_losses", "expected a non-negative integer or null"
            )
        object.__setattr__(
            self,
            "recent_drawdown_ratio",
            _require_optional_positive(
                self.recent_drawdown_ratio, "journal.recent_drawdown_ratio"
            ),
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "consecutive_losses": self.consecutive_losses,
            "recent_drawdown_ratio": self.recent_drawdown_ratio,
        }


@dataclass(frozen=True, slots=True)
class ScannerV4Snapshot:
    """The immutable snapshot consumed by the single composition API.

    ``capture_source`` is pure provenance (live vs backtest) and participates in
    the result's provenance but NOT in the snapshot_id / canonical input, so a
    live snapshot and its backtest replay hash identically.
    """

    symbol: str
    captured_at: datetime
    capture_source: str
    regime: str
    canonical_smc: SmcScoringResult
    buy: SideSnapshot
    sell: SideSnapshot
    safety: MarketSafetyContext
    macro_raw_buy: int | None = None
    macro_raw_sell: int | None = None
    macro_confidence: float | None = None
    account: AccountState | None = None
    portfolio: PortfolioState | None = None
    journal: JournalState | None = None

    def __post_init__(self) -> None:
        if type(self.symbol) is not str or not self.symbol or self.symbol != self.symbol.strip():
            raise CompositionInputError("snapshot.symbol", "expected a non-empty string")
        if not isinstance(self.captured_at, datetime) or self.captured_at.tzinfo is None:
            raise CompositionInputError(
                "snapshot.captured_at", "expected a timezone-aware datetime"
            )
        _require_choice(
            self.capture_source, _VALID_CAPTURE_SOURCES, "snapshot.capture_source"
        )
        _require_choice(self.regime, VALID_TECHNICAL_REGIMES, "snapshot.regime")
        if type(self.canonical_smc) is not SmcScoringResult:
            raise CompositionInputError(
                "snapshot.canonical_smc", "expected an SmcScoringResult"
            )
        if type(self.buy) is not SideSnapshot:
            raise CompositionInputError("snapshot.buy", "expected a SideSnapshot")
        if type(self.sell) is not SideSnapshot:
            raise CompositionInputError("snapshot.sell", "expected a SideSnapshot")
        if type(self.safety) is not MarketSafetyContext:
            raise CompositionInputError(
                "snapshot.safety", "expected a MarketSafetyContext"
            )
        object.__setattr__(
            self,
            "macro_raw_buy",
            _require_optional_raw(self.macro_raw_buy, "snapshot.macro_raw_buy", 30),
        )
        object.__setattr__(
            self,
            "macro_raw_sell",
            _require_optional_raw(self.macro_raw_sell, "snapshot.macro_raw_sell", 30),
        )
        object.__setattr__(
            self,
            "macro_confidence",
            _require_optional_confidence(
                self.macro_confidence, "snapshot.macro_confidence"
            ),
        )
        if self.account is not None and type(self.account) is not AccountState:
            raise CompositionInputError("snapshot.account", "expected AccountState or null")
        if self.portfolio is not None and type(self.portfolio) is not PortfolioState:
            raise CompositionInputError(
                "snapshot.portfolio", "expected PortfolioState or null"
            )
        if self.journal is not None and type(self.journal) is not JournalState:
            raise CompositionInputError("snapshot.journal", "expected JournalState or null")

    def to_canonical_input_dict(self) -> dict[str, Any]:
        """Deterministic JSON-safe input fingerprint (excludes capture_source)."""
        return {
            "schema_version": COMPOSITION_POLICY_VERSION,
            "symbol": self.symbol,
            "captured_at": self.captured_at.isoformat(),
            "regime": self.regime,
            "canonical_smc": self.canonical_smc.to_dict(),
            "buy": self.buy.to_canonical_dict(),
            "sell": self.sell.to_canonical_dict(),
            "safety": _safety_to_canonical_dict(self.safety),
            "macro": {
                "raw_buy": self.macro_raw_buy,
                "raw_sell": self.macro_raw_sell,
                "confidence": self.macro_confidence,
            },
            "account": None if self.account is None else self.account.to_canonical_dict(),
            "portfolio": (
                None if self.portfolio is None else self.portfolio.to_canonical_dict()
            ),
            "journal": None if self.journal is None else self.journal.to_canonical_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "captured_at": self.captured_at.isoformat(),
            "capture_source": self.capture_source,
            "regime": self.regime,
            "buy": self.buy.to_canonical_dict(),
            "sell": self.sell.to_canonical_dict(),
            "safety": _safety_to_canonical_dict(self.safety),
            "macro_raw_buy": self.macro_raw_buy,
            "macro_raw_sell": self.macro_raw_sell,
            "macro_confidence": self.macro_confidence,
            "account": None if self.account is None else self.account.to_canonical_dict(),
            "portfolio": (
                None if self.portfolio is None else self.portfolio.to_canonical_dict()
            ),
            "journal": None if self.journal is None else self.journal.to_canonical_dict(),
        }


# ---------------------------------------------------------------------------
# Options (thresholds default to OPEN/None -> fail closed to UNKNOWN)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ComposeOptions:
    """Versioned composition thresholds.  None means "not calibrated" -> fail closed.

    - min_risk_reward: minimum scenario R:R.  None -> scenario gate UNKNOWN.
    - technical_floor / setup_floor: score floors for WAITING_CONFIRMATION.
      Either None -> can never certify a confirmation -> WATCH_ZONE.
    - portfolio_position_limit / portfolio_exposure_limit: caps.  Both None ->
      portfolio gate UNKNOWN (policy OPEN).
    - journal_max_consecutive_losses / journal_drawdown_caution_ratio: journal
      policies.  Both None -> journal gate UNKNOWN (policy OPEN).
    No production values are set here: Bước 09 performs the calibration.
    """

    snapshot_max_age_seconds: int = SNAPSHOT_MAX_AGE_SECONDS
    snapshot_max_future_skew_seconds: int = SNAPSHOT_MAX_FUTURE_SKEW_SECONDS
    min_risk_reward: Fraction | None = None
    technical_floor: int | None = None
    setup_floor: int | None = None
    portfolio_position_limit: int | None = None
    portfolio_exposure_limit: float | None = None
    journal_max_consecutive_losses: int | None = None
    journal_drawdown_caution_ratio: float | None = None

    def __post_init__(self) -> None:
        _require_positive_int(
            self.snapshot_max_age_seconds, "options.snapshot_max_age_seconds"
        )
        _require_positive_int(
            self.snapshot_max_future_skew_seconds,
            "options.snapshot_max_future_skew_seconds",
        )
        if self.min_risk_reward is not None:
            raw = self.min_risk_reward
            if isinstance(raw, int) and not isinstance(raw, bool):
                rr = Fraction(raw)
            elif isinstance(raw, Fraction):
                rr = raw
            else:
                raise CompositionInputError(
                    "options.min_risk_reward", "expected a Fraction or int or None"
                )
            if rr <= 0:
                raise CompositionInputError(
                    "options.min_risk_reward", "must be positive"
                )
            object.__setattr__(self, "min_risk_reward", rr)
        for name in ("technical_floor", "setup_floor"):
            value = getattr(self, name)
            if value is not None and (
                type(value) is not int or not 0 <= value <= 100
            ):
                raise CompositionInputError(
                    f"options.{name}", "expected an integer in 0..100 or None"
                )
        value = self.portfolio_position_limit
        if value is not None and (type(value) is not int or value < 1):
            raise CompositionInputError(
                "options.portfolio_position_limit",
                "expected a positive integer or None",
            )
        value = self.portfolio_exposure_limit
        if value is not None:
            finite = _require_positive_number("options.portfolio_exposure_limit", value)
            object.__setattr__(self, "portfolio_exposure_limit", finite)
        value = self.journal_max_consecutive_losses
        if value is not None and (type(value) is not int or value < 1):
            raise CompositionInputError(
                "options.journal_max_consecutive_losses",
                "expected a positive integer or None",
            )
        value = self.journal_drawdown_caution_ratio
        if value is not None:
            finite = _require_positive_number(
                "options.journal_drawdown_caution_ratio", value
            )
            if not 0 <= finite <= 1:
                raise CompositionInputError(
                    "options.journal_drawdown_caution_ratio",
                    "expected a ratio in 0..1 or None",
                )
            object.__setattr__(self, "journal_drawdown_caution_ratio", finite)


# ---------------------------------------------------------------------------
# Composition gate result (scenario/account/portfolio/journal)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CompositionGate:
    """One deterministic non-model gate of the composition pipeline.

    Deliberately NOT ``scanner_v4_models.GateCheck``: that model only admits the
    five safety check names.  These gates fail closed to UNKNOWN on missing data
    or uncalibrated policy, exactly like the safety/macro gates.
    """

    name: str
    status: str
    reason_codes: tuple[str, ...]
    observed: Any
    threshold: Any
    checked_at: datetime
    source: str
    provenance: Mapping[str, Any]

    def _validate(self) -> None:
        _require_choice(self.status, {PASS, CAUTION, BLOCK, UNKNOWN}, "gate.status")
        if self.status != PASS and not self.reason_codes:
            raise CompositionInputError(
                "gate.reason_codes",
                "a non-PASS composition gate requires a reason code",
            )
        # PASS is only certified with explicit observed data (never optimistic).
        if self.status == PASS and self.observed is None:
            raise CompositionInputError(
                "gate.observed",
                "PASS requires an explicit observed value; missing data must be UNKNOWN",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "observed": self.observed,
            "threshold": self.threshold,
            "checked_at": self.checked_at.isoformat(),
            "source": self.source,
            "provenance": dict(self.provenance),
        }

    @classmethod
    def from_dict(cls, value: object, *, path: str = "gate") -> CompositionGate:
        """Strict deserializer (Bước 08 reader addition)."""
        payload = _require_mapping(value, path)
        if frozenset(payload) != {
            "name",
            "status",
            "reason_codes",
            "observed",
            "threshold",
            "checked_at",
            "source",
            "provenance",
        }:
            raise CompositionInputError(path, "unexpected composition gate keys")
        status = _require_choice(payload["status"], {PASS, CAUTION, BLOCK, UNKNOWN}, f"{path}.status")
        if status != PASS and not payload["reason_codes"]:
            raise CompositionInputError(
                f"{path}.reason_codes", "a non-PASS gate requires a reason code"
            )
        if status == PASS and payload["observed"] is None:
            raise CompositionInputError(
                f"{path}.observed", "PASS requires an explicit observed value"
            )
        return cls(
            name=_require_text(payload["name"], f"{path}.name"),
            status=status,
            reason_codes=tuple(
                _require_text(code, f"{path}.reason_codes")
                for code in payload["reason_codes"]
            ),
            observed=payload["observed"],
            threshold=payload["threshold"],
            checked_at=_require_datetime(payload["checked_at"], f"{path}.checked_at"),
            source=_require_text(payload["source"], f"{path}.source"),
            provenance=_require_mapping(payload["provenance"], f"{path}.provenance"),
        )


def _composition_gate(
    name: str,
    status: str,
    codes: tuple[str, ...],
    observed: Any,
    threshold: Any,
    *,
    now: datetime,
    source: str,
    provenance: Mapping[str, Any],
) -> CompositionGate:
    gate = CompositionGate(
        name=name,
        status=status,
        reason_codes=codes,
        observed=observed,
        threshold=threshold,
        checked_at=now,
        source=source,
        provenance=provenance,
    )
    gate._validate()
    return gate


# ---------------------------------------------------------------------------
# Scenario R:R
# ---------------------------------------------------------------------------


def compute_scenario_rr(plan: ScenarioPlan | None, side: str) -> Fraction | None:
    """Exact R:R of one side's scenario plan (Fraction; deterministic).

    Returns None only when there is no plan.  Plan ordering is validated at
    construction, so risk/reward are always positive and the ratio is exact.
    """
    if plan is None:
        return None
    if side not in VALID_SIDES:
        raise CompositionInputError("side", "must be exactly 'buy' or 'sell'")
    if plan.direction != side:
        raise CompositionInputError(
            "scenario_plan",
            f"plan direction {plan.direction!r} does not match side {side!r}"
            " — the pipeline never borrows a plan from another side",
        )
    if side == BUY:
        risk = plan.entry - plan.stop_loss
        reward = plan.take_profit - plan.entry
    else:
        risk = plan.stop_loss - plan.entry
        reward = plan.entry - plan.take_profit
    return Fraction(reward) / Fraction(risk)


# ---------------------------------------------------------------------------
# Gate implementations (deterministic; fail closed to UNKNOWN)
# ---------------------------------------------------------------------------


def _scenario_gate(
    plan: ScenarioPlan | None,
    rr: Fraction | None,
    options: ComposeOptions,
    *,
    now: datetime,
) -> CompositionGate:
    if plan is None:
        return _composition_gate(
            "scenario",
            UNKNOWN,
            (GATE_SCENARIO_PLAN_MISSING,),
            None,
            None,
            now=now,
            source="scanner_v4_composition",
            provenance={"side": "none"},
        )
    if rr is None:
        raise CompositionServiceError(
            "scenario", "a present plan must yield an exact R:R"
        )
    if options.min_risk_reward is None:
        return _composition_gate(
            "scenario",
            UNKNOWN,
            (GATE_SCENARIO_POLICY_OPEN,),
            float(rr),
            None,
            now=now,
            source="scanner_v4_composition",
            provenance={"side": plan.direction},
        )
    if rr < options.min_risk_reward:
        return _composition_gate(
            "scenario",
            BLOCK,
            (GATE_SCENARIO_RR_BLOCK,),
            float(rr),
            float(options.min_risk_reward),
            now=now,
            source="scanner_v4_composition",
            provenance={"side": plan.direction},
        )
    return _composition_gate(
        "scenario",
        PASS,
        (),
        float(rr),
        float(options.min_risk_reward),
        now=now,
        source="scanner_v4_composition",
        provenance={"side": plan.direction},
    )


def _account_gate(state: AccountState | None, *, now: datetime) -> CompositionGate:
    if state is None or state.free_margin is None or state.required_margin is None:
        return _composition_gate(
            "account",
            UNKNOWN,
            (GATE_ACCOUNT_DATA_MISSING,),
            None,
            None,
            now=now,
            source="scanner_v4_composition",
            provenance={},
        )
    if state.free_margin < state.required_margin:
        return _composition_gate(
            "account",
            BLOCK,
            (GATE_ACCOUNT_MARGIN_BLOCK,),
            state.free_margin,
            state.required_margin,
            now=now,
            source="account_risk_engine",
            provenance={},
        )
    return _composition_gate(
        "account",
        PASS,
        (),
        state.free_margin,
        state.required_margin,
        now=now,
        source="account_risk_engine",
        provenance={},
    )


def _portfolio_gate(
    state: PortfolioState | None,
    options: ComposeOptions,
    *,
    now: datetime,
) -> CompositionGate:
    if state is None:
        return _composition_gate(
            "portfolio",
            UNKNOWN,
            (GATE_PORTFOLIO_DATA_MISSING,),
            None,
            None,
            now=now,
            source="portfolio_risk_engine",
            provenance={},
        )
    if options.portfolio_position_limit is None and options.portfolio_exposure_limit is None:
        return _composition_gate(
            "portfolio",
            UNKNOWN,
            (GATE_PORTFOLIO_POLICY_OPEN,),
            None,
            None,
            now=now,
            source="portfolio_risk_engine",
            provenance={},
        )
    if (
        options.portfolio_position_limit is not None
        and state.open_positions is None
    ) or (
        options.portfolio_exposure_limit is not None
        and state.exposure_ratio is None
    ):
        return _composition_gate(
            "portfolio",
            UNKNOWN,
            (GATE_PORTFOLIO_DATA_MISSING,),
            None,
            None,
            now=now,
            source="portfolio_risk_engine",
            provenance={},
        )
    status = PASS
    codes: list[str] = []
    if (
        options.portfolio_position_limit is not None
        and state.open_positions >= options.portfolio_position_limit
    ):
        status = BLOCK
        codes.append(GATE_PORTFOLIO_LIMIT_BLOCK)
    if (
        options.portfolio_exposure_limit is not None
        and state.exposure_ratio >= options.portfolio_exposure_limit
    ):
        status = BLOCK
        codes.append(GATE_PORTFOLIO_LIMIT_BLOCK)
    return _composition_gate(
        "portfolio",
        status,
        tuple(codes),
        {"open_positions": state.open_positions, "exposure_ratio": state.exposure_ratio},
        {
            "position_limit": options.portfolio_position_limit,
            "exposure_limit": options.portfolio_exposure_limit,
        },
        now=now,
        source="portfolio_risk_engine",
        provenance={},
    )


def _journal_gate(
    state: JournalState | None,
    options: ComposeOptions,
    *,
    now: datetime,
) -> CompositionGate:
    if state is None:
        return _composition_gate(
            "journal",
            UNKNOWN,
            (GATE_JOURNAL_DATA_MISSING,),
            None,
            None,
            now=now,
            source="trading_journal",
            provenance={},
        )
    if (
        options.journal_max_consecutive_losses is None
        and options.journal_drawdown_caution_ratio is None
    ):
        return _composition_gate(
            "journal",
            UNKNOWN,
            (GATE_JOURNAL_POLICY_OPEN,),
            None,
            None,
            now=now,
            source="trading_journal",
            provenance={},
        )
    if (
        options.journal_max_consecutive_losses is not None
        and state.consecutive_losses is None
    ) or (
        options.journal_drawdown_caution_ratio is not None
        and state.recent_drawdown_ratio is None
    ):
        return _composition_gate(
            "journal",
            UNKNOWN,
            (GATE_JOURNAL_DATA_MISSING,),
            None,
            None,
            now=now,
            source="trading_journal",
            provenance={},
        )
    if (
        options.journal_max_consecutive_losses is not None
        and state.consecutive_losses >= options.journal_max_consecutive_losses
    ):
        return _composition_gate(
            "journal",
            BLOCK,
            (GATE_JOURNAL_REVENGE_BLOCK,),
            state.consecutive_losses,
            options.journal_max_consecutive_losses,
            now=now,
            source="trading_journal",
            provenance={},
        )
    if (
        options.journal_drawdown_caution_ratio is not None
        and state.recent_drawdown_ratio >= options.journal_drawdown_caution_ratio
    ):
        return _composition_gate(
            "journal",
            CAUTION,
            (GATE_JOURNAL_DRAWDOWN_CAUTION,),
            state.recent_drawdown_ratio,
            options.journal_drawdown_caution_ratio,
            now=now,
            source="trading_journal",
            provenance={},
        )
    return _composition_gate(
        "journal",
        PASS,
        (),
        {"consecutive_losses": state.consecutive_losses,
         "recent_drawdown_ratio": state.recent_drawdown_ratio},
        {
            "max_consecutive_losses": options.journal_max_consecutive_losses,
            "drawdown_caution_ratio": options.journal_drawdown_caution_ratio,
        },
        now=now,
        source="trading_journal",
        provenance={},
    )


# ---------------------------------------------------------------------------
# Scenario evaluation carrier
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ScenarioEvaluation:
    """Selected-side scenario evidence: plan, exact R:R and its gate result."""

    side: str | None
    plan: ScenarioPlan | None
    risk_reward_ratio: Fraction | None
    gate: CompositionGate

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "plan": None if self.plan is None else self.plan.to_canonical_dict(),
            "risk_reward_ratio": (
                None if self.risk_reward_ratio is None else str(self.risk_reward_ratio)
            ),
            "gate": self.gate.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: object, *, path: str = "scenario") -> ScenarioEvaluation:
        """Strict deserializer (Bước 08 reader addition)."""
        payload = _require_mapping(value, path)
        if frozenset(payload) != {"side", "plan", "risk_reward_ratio", "gate"}:
            raise CompositionInputError(
                path, "expected exactly {side, plan, risk_reward_ratio, gate}"
            )
        side = payload["side"]
        plan_value = payload["plan"]
        plan = (
            None
            if plan_value is None
            else _scenario_plan_from_dict(plan_value, path=f"{path}.plan")
        )
        rr_value = payload["risk_reward_ratio"]
        rr = None if rr_value is None else Fraction(str(rr_value))
        return cls(
            side=None if side is None else _require_side(side, f"{path}.side"),
            plan=plan,
            risk_reward_ratio=rr,
            gate=CompositionGate.from_dict(payload["gate"], path=f"{path}.gate"),
        )


def _scenario_plan_from_dict(value: object, *, path: str) -> ScenarioPlan:
    payload = _require_mapping(value, path)
    if frozenset(payload) != {"direction", "entry", "stop_loss", "take_profit", "source"}:
        raise CompositionInputError(path, "unexpected scenario plan keys")
    return ScenarioPlan(
        direction=_require_side(payload["direction"], f"{path}.direction"),
        entry=_require_positive_number(f"{path}.entry", payload["entry"]),
        stop_loss=_require_positive_number(f"{path}.stop_loss", payload["stop_loss"]),
        take_profit=_require_positive_number(f"{path}.take_profit", payload["take_profit"]),
        source=_require_text(payload["source"], f"{path}.source"),
    )


# ---------------------------------------------------------------------------
# Snapshot identity
# ---------------------------------------------------------------------------


def snapshot_id_of(snapshot: ScannerV4Snapshot) -> str:
    """Locked snapshot ID: ``v4:<symbol>:<captured_at ISO Z>:<sha256(canonical input)>[:12]``.

    The digest is over the canonical input JSON (capture_source excluded), so a
    replay of the same backtest bar and a live tick produce the SAME id.  The
    label ``captured_at`` is normalized to UTC with the ``Z`` suffix.
    """
    canonical_text = json.dumps(
        snapshot.to_canonical_input_dict(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(canonical_text).hexdigest()[:12]
    captured_label = snapshot.captured_at.astimezone(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    return f"v4:{snapshot.symbol}:{captured_label}:{digest}"


# ---------------------------------------------------------------------------
# The single composition API (live and backtest share it)
# ---------------------------------------------------------------------------


def compose_scanner_v4(
    snapshot: object,
    *,
    now: object,
    safety_policy: object = None,
    macro_policy: object = None,
    options: object = None,
) -> "ScannerV4CompositionResult":
    """Run the deterministic V4 pipeline over one immutable snapshot.

    ``now`` is a required tz-aware wall clock: the freshness SLA is evaluated
    against it, and every gate stamps it as ``checked_at`` so the whole run is
    reproducible.  Live and backtest call this same API on the same input.
    """
    if type(snapshot) is not ScannerV4Snapshot:
        raise CompositionInputError(
            "snapshot", "expected a ScannerV4Snapshot (build it via an adapter)"
        )
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise CompositionInputError("now", "expected a timezone-aware datetime")
    if safety_policy is None:
        safety_policy = SafetyPolicy(policy_version=SCANNER_V4_SAFETY_POLICY_VERSION)
    if type(safety_policy) is not SafetyPolicy:
        raise CompositionInputError("safety_policy", "expected a SafetyPolicy")
    if safety_policy.policy_version != SCANNER_V4_SAFETY_POLICY_VERSION:
        raise CompositionInputError(
            "safety_policy.policy_version",
            "the composition only stamps the canonical V4 safety policy",
        )
    if macro_policy is None:
        macro_policy = DEFAULT_MACRO_POLICY
    if type(macro_policy) is not MacroPolicy:
        raise CompositionInputError("macro_policy", "expected a MacroPolicy")
    if options is None:
        options = ComposeOptions()
    if type(options) is not ComposeOptions:
        raise CompositionInputError("options", "expected a ComposeOptions")

    # --- 1. freshness SLA (Mục 8) -----------------------------------------
    captured_at = snapshot.captured_at
    stale = (now - captured_at).total_seconds() > options.snapshot_max_age_seconds
    future_skew = (
        captured_at - now
    ).total_seconds() > options.snapshot_max_future_skew_seconds
    fresh_ok = not stale and not future_skew

    # --- 2. per-side TechnicalScore (TechnicalScoreDataError -> unavailable) -
    buy_technical, buy_error = _score_side(snapshot, BUY)
    sell_technical, sell_error = _score_side(snapshot, SELL)
    both_technical = buy_technical is not None and sell_technical is not None

    # --- 3. MarketSafetyGate (never mutates scores) -------------------------
    try:
        safety_result = MarketSafetyGate().evaluate(
            snapshot.safety, safety_policy, now=now
        )
    except ValueError as exc:
        raise CompositionServiceError(
            "market_safety", "safety gate failed closed with a service error", exc
        ) from exc

    # --- 4. gap / best side (TechnicalScore only; locked tie -> BUY) --------
    gap = (
        technical_signal_score_gap(buy_technical, sell_technical)
        if both_technical
        else None
    )
    if both_technical and fresh_ok:
        if buy_technical.technical_signal_score >= sell_technical.technical_signal_score:
            selected_side = BUY
        else:
            selected_side = SELL
    else:
        selected_side = None

    # --- 5. scenario (selected side only; never borrow from the other side) -
    plan = _plan_for(snapshot, selected_side)
    rr = compute_scenario_rr(plan, selected_side) if selected_side is not None else None
    scenario_gate = _scenario_gate(plan, rr, options, now=now)
    scenario = ScenarioEvaluation(
        side=selected_side,
        plan=plan,
        risk_reward_ratio=rr,
        gate=scenario_gate,
    )

    # --- 6. FinalScore per side (technical required; evidence/execution -> 50) -
    final_scores: dict[str, FinalScoreResult | None] = {}
    if buy_technical is not None:
        final_scores[BUY] = _final_for(side_snapshot=snapshot.buy,
                                       technical=buy_technical,
                                       side=BUY)
    else:
        final_scores[BUY] = None
    if sell_technical is not None:
        final_scores[SELL] = _final_for(side_snapshot=snapshot.sell,
                                        technical=sell_technical,
                                        side=SELL)
    else:
        final_scores[SELL] = None

    # --- 7. MacroGate ONCE on the selected side only -------------------------
    assessment = build_macro_assessment(
        symbol=snapshot.symbol,
        captured_at=captured_at,
        raw_buy=snapshot.macro_raw_buy,
        raw_sell=snapshot.macro_raw_sell,
        confidence=snapshot.macro_confidence,
        assessed_side=selected_side,
        deadband_points=macro_policy.deadband_points,
    )
    try:
        macro_result = MacroGate().evaluate(
            assessment, assessed_side=selected_side, policy=macro_policy, now=now
        )
    except ValueError as exc:
        raise CompositionServiceError(
            "macro_gate", "macro gate failed closed with a service error", exc
        ) from exc

    # --- 8. account / portfolio / journal gates ------------------------------
    account_gate = _account_gate(snapshot.account, now=now)
    portfolio_gate = _portfolio_gate(snapshot.portfolio, options, now=now)
    journal_gate = _journal_gate(snapshot.journal, options, now=now)
    composition_gates = (scenario_gate, account_gate, portfolio_gate, journal_gate)

    # --- 9. minimal decision (no READY_NOW / OUT_OF_STRATEGY / order payload) -
    selected_technical_score: int | None = None
    selected_setup_score: int | None = None
    if selected_side is not None and final_scores[selected_side] is not None:
        selected_technical = (
            buy_technical if selected_side == BUY else sell_technical
        )
        if selected_technical is not None:
            selected_technical_score = selected_technical.technical_signal_score
        selected_setup_score = final_scores[selected_side].setup_score
    decision = _build_decision(
        both_technical=both_technical,
        fresh_ok=fresh_ok,
        stale=stale,
        future_skew=future_skew,
        selected_side=selected_side,
        gap=gap,
        safety=safety_result,
        macro=macro_result,
        composition_gates=composition_gates,
        options=options,
        selected_technical_score=selected_technical_score,
        selected_setup_score=selected_setup_score,
    )

    # --- 10. canonical artifact ----------------------------------------------
    side_scores = (
        _build_side_score(BUY, buy_technical, final_scores[BUY]),
        _build_side_score(SELL, sell_technical, final_scores[SELL]),
    )
    canonical = CanonicalPairSnapshot.create(
        snapshot_id=snapshot_id_of(snapshot),
        symbol=snapshot.symbol,
        captured_at=captured_at,
        side_scores=side_scores,
        market_safety=safety_result,
        macro_assessment=assessment,
        macro_gate=macro_result,
        decision=decision,
        provenance={
            "capture_source": snapshot.capture_source,
            "composition_version": COMPOSITION_POLICY_VERSION,
            "pipeline": (
                "snapshot->safety->technical->scenario->"
                "final_score->macro->account->portfolio->journal->decision"
            ),
            "freshness": {
                "stale": stale,
                "future_skew": future_skew,
                "ok": fresh_ok,
            },
        },
    )

    return ScannerV4CompositionResult(
        snapshot_id=canonical.snapshot_id,
        symbol=canonical.symbol,
        captured_at=captured_at,
        capture_source=snapshot.capture_source,
        technical={
            BUY: buy_technical,
            SELL: sell_technical,
        },
        technical_errors={
            BUY: buy_error,
            SELL: sell_error,
        },
        safety=safety_result,
        macro_assessment=assessment,
        macro_gate=macro_result,
        scenario=scenario,
        final_scores=MappingProxyType(final_scores),
        composition_gates=composition_gates,
        decision=decision,
        canonical=canonical,
    )


def _score_side(
    snapshot: ScannerV4Snapshot, side: str
) -> tuple[TechnicalSignalScoreResult | None, dict[str, Any] | None]:
    """Score one side; on TechnicalScoreDataError return (None, error meta)."""
    side_snapshot = snapshot.buy if side == BUY else snapshot.sell
    try:
        result = score_technical_signal(
            side,
            trend_raw=side_snapshot.technical_raws["trend"],
            momentum_raw=side_snapshot.technical_raws["momentum"],
            location_raw=side_snapshot.technical_raws["location"],
            canonical_smc=snapshot.canonical_smc,
            regime=snapshot.regime,
        )
    except TechnicalScoreDataError as exc:
        return None, {"code": exc.code, "path": exc.path, "detail": exc.detail}
    except Exception as exc:  # unexpected scorer failure never fabricates a score
        raise CompositionServiceError(
            f"technical.{side}", "technical scorer failed unexpectedly", exc
        ) from exc
    return result, None


def _final_for(
    *, side_snapshot: SideSnapshot, technical: TechnicalSignalScoreResult, side: str
) -> FinalScoreResult:
    """Blend the side's FinalScore with Bước 06 fallback semantics."""
    try:
        return score_final_score(
            technical.technical_signal_score,
            side_snapshot.evidence_score,
            side_snapshot.execution_quality_score,
            side=side,
            evidence_source=side_snapshot.evidence_source,
            execution_quality_source=side_snapshot.execution_quality_source,
        )
    except FinalScoreDataError as exc:
        raise CompositionServiceError(
            f"final_score.{side}",
            "technical was valid but FinalScore failed closed",
            exc,
        ) from exc


def _plan_for(snapshot: ScannerV4Snapshot, side: str | None) -> ScenarioPlan | None:
    if side is None:
        return None
    return snapshot.buy.scenario_plan if side == BUY else snapshot.sell.scenario_plan


def _build_side_score(
    side: str,
    technical: TechnicalSignalScoreResult | None,
    final: FinalScoreResult | None,
) -> SideScore:
    if technical is None or final is None:
        return SideScore(
            side=side,
            technical_signal_score=None,
            technical_breakdown=_unavailable_breakdown(),
            evidence_score=None,
            evidence_source=_UNAVAILABLE_SOURCE,
            execution_quality_score=None,
            execution_quality_source=_UNAVAILABLE_SOURCE,
            setup_score=None,
            final_score=None,
            reason_codes=(TECHNICAL_DATA_UNAVAILABLE,),
        )
    # Evidence/Execution are strict ints (validated) so the clamped values are
    # exact integers safe for the canonical SideScore contract.
    return SideScore(
        side=side,
        technical_signal_score=technical.technical_signal_score,
        technical_breakdown=technical.technical_breakdown,
        evidence_score=int(final.evidence_score),
        evidence_source=final.evidence_source,
        execution_quality_score=int(final.execution_quality_score),
        execution_quality_source=final.execution_quality_source,
        setup_score=final.setup_score,
        final_score=final.final_score,
        reason_codes=final.fallback_warnings,
    )


def _unavailable_breakdown() -> TechnicalBreakdown:
    """All-null (allowed) breakdown: the side documents why nothing was scored."""
    components = (
        ("trend", 25),
        ("momentum", 20),
        ("location", 25),
        ("smc", 15),
    )
    return TechnicalBreakdown(
        **{
            name: TechnicalComponent(None, raw_max, None, None)
            for name, raw_max in components
        }
    )


def _build_decision(
    *,
    both_technical: bool,
    fresh_ok: bool,
    stale: bool,
    future_skew: bool,
    selected_side: str | None,
    gap: int | None,
    safety: MarketSafetyResult,
    macro: MacroGateResult,
    composition_gates: tuple[CompositionGate, ...],
    options: ComposeOptions,
    selected_technical_score: int | None,
    selected_setup_score: int | None,
) -> DecisionResult:
    freshness_codes: list[str] = []
    if stale:
        freshness_codes.append(SNAPSHOT_STALE)
    if future_skew:
        freshness_codes.append(SNAPSHOT_FRESHNESS_UNKNOWN)

    gate_row: list[tuple[str, str, tuple[str, ...]]] = [
        ("market_safety", safety.status, safety.reason_codes),
        ("macro", macro.status, macro.reason_codes),
        *(
            (gate.name, gate.status, gate.reason_codes)
            for gate in composition_gates
        ),
    ]
    gate_codes = _dedupe(code for _, _, codes in gate_row for code in codes)

    if (not fresh_ok) or (not both_technical):
        decision_codes: list[str] = []
        decision_codes.extend(freshness_codes)
        if not both_technical:
            decision_codes.append(TECHNICAL_DATA_UNAVAILABLE)
        return DecisionResult(
            selected_side=None,
            score_gap=gap if both_technical else None,
            candidate_status="DATA_UNAVAILABLE",
            decision_cap=macro.decision_cap,
            gate_codes=gate_codes,
            reason_codes=_dedupe(decision_codes),
            block_codes=(),
        )

    block_codes: list[str] = []
    block_gates = [name for name, status, _ in gate_row if status == BLOCK]
    critical_unknown = [
        name for name, status, _ in gate_row
        if name in _CRITICAL_GATES and status == UNKNOWN
    ]
    cautions = [name for name, status, _ in gate_row if status == CAUTION]
    noncritical_unknown = [
        name for name, status, _ in gate_row
        if name not in _CRITICAL_GATES and status == UNKNOWN
    ]

    if block_gates or critical_unknown:
        for name, status, codes in gate_row:
            if status == BLOCK or (name in _CRITICAL_GATES and status == UNKNOWN):
                block_codes.extend(codes)
        return DecisionResult(
            selected_side=selected_side,
            score_gap=gap,
            candidate_status="BLOCKED",
            decision_cap=macro.decision_cap,
            gate_codes=gate_codes,
            reason_codes=_dedupe(block_codes),
            block_codes=_dedupe(block_codes),
        )

    if cautions or noncritical_unknown:
        return DecisionResult(
            selected_side=selected_side,
            score_gap=gap,
            candidate_status="WATCH_ZONE",
            decision_cap=macro.decision_cap,
            gate_codes=gate_codes,
            reason_codes=(),
            block_codes=(),
        )

    # Every gate PASS: score floors must be calibrated to confirm waiting state.
    if options.technical_floor is None or options.setup_floor is None:
        return DecisionResult(
            selected_side=selected_side,
            score_gap=gap,
            candidate_status="WATCH_ZONE",
            decision_cap=macro.decision_cap,
            gate_codes=gate_codes,
            reason_codes=(COMPOSE_FLOOR_POLICY_OPEN,),
            block_codes=(),
        )
    if (
        selected_technical_score is None
        or selected_setup_score is None
        or selected_technical_score < options.technical_floor
        or selected_setup_score < options.setup_floor
    ):
        return DecisionResult(
            selected_side=selected_side,
            score_gap=gap,
            candidate_status="WATCH_ZONE",
            decision_cap=macro.decision_cap,
            gate_codes=gate_codes,
            reason_codes=(COMPOSE_SCORE_FLOOR_NOT_MET,),
            block_codes=(),
        )
    return DecisionResult(
        selected_side=selected_side,
        score_gap=gap,
        candidate_status="WAITING_CONFIRMATION",
        decision_cap=macro.decision_cap,
        gate_codes=gate_codes,
        reason_codes=(GATES_ALL_PASS,),
        block_codes=(),
    )


# ---------------------------------------------------------------------------
# Composition result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ScannerV4CompositionResult:
    """Immutable full-schema output of one composition run."""

    snapshot_id: str
    symbol: str
    captured_at: datetime
    capture_source: str
    technical: Mapping[str, TechnicalSignalScoreResult | None]
    technical_errors: Mapping[str, dict[str, Any] | None]
    safety: MarketSafetyResult
    macro_assessment: MacroAssessment
    macro_gate: MacroGateResult
    scenario: ScenarioEvaluation
    final_scores: Mapping[str, FinalScoreResult | None]
    composition_gates: tuple[CompositionGate, ...]
    decision: DecisionResult
    canonical: CanonicalPairSnapshot

    def to_dict(self) -> dict[str, Any]:
        return {
            "composition_version": COMPOSITION_POLICY_VERSION,
            "snapshot_id": self.snapshot_id,
            "symbol": self.symbol,
            "captured_at": self.captured_at.isoformat(),
            "capture_source": self.capture_source,
            "technical": {
                BUY: (
                    None if self.technical[BUY] is None else self.technical[BUY].to_dict()
                ),
                SELL: (
                    None if self.technical[SELL] is None else self.technical[SELL].to_dict()
                ),
            },
            "technical_errors": {
                BUY: self.technical_errors[BUY],
                SELL: self.technical_errors[SELL],
            },
            "safety": self.safety.to_dict(),
            "macro_assessment": self.macro_assessment.to_dict(),
            "macro_gate": self.macro_gate.to_dict(),
            "scenario": self.scenario.to_dict(),
            "final_scores": {
                BUY: (
                    None
                    if self.final_scores[BUY] is None
                    else self.final_scores[BUY].to_dict()
                ),
                SELL: (
                    None
                    if self.final_scores[SELL] is None
                    else self.final_scores[SELL].to_dict()
                ),
            },
            "composition_gates": [gate.to_dict() for gate in self.composition_gates],
            "decision": self.decision.to_dict(),
            "canonical": _canonical_to_jsonable(self.canonical),
        }

    @classmethod
    def from_dict(cls, value: object) -> ScannerV4CompositionResult:
        """Strict full-schema deserializer (Bước 08 reader addition).

        Re-validates every nested contract fail-closed: the canonical artifact
        via the strict model reader, the gates via their model readers, and the
        side scores via the scorer readers.  Nothing is ever trusted from the
        payload alone.
        """
        payload = _require_mapping(value, "composition_result")
        if frozenset(payload) != {
            "composition_version",
            "snapshot_id",
            "symbol",
            "captured_at",
            "capture_source",
            "technical",
            "technical_errors",
            "safety",
            "macro_assessment",
            "macro_gate",
            "scenario",
            "final_scores",
            "composition_gates",
            "decision",
            "canonical",
        }:
            raise CompositionInputError("composition_result", "unexpected result keys")
        composition_version = _require_text(
            payload["composition_version"], "composition_result.composition_version"
        )
        if composition_version != COMPOSITION_POLICY_VERSION:
            raise CompositionInputError(
                "composition_result.composition_version",
                f"expected the locked {COMPOSITION_POLICY_VERSION!r}, got "
                f"{composition_version!r}",
            )
        technical_raw = _require_mapping(payload["technical"], "composition_result.technical")
        if frozenset(technical_raw) != {BUY, SELL}:
            raise CompositionInputError("composition_result.technical", "expected buy/sell")
        errors_raw = _require_mapping(
            payload["technical_errors"], "composition_result.technical_errors"
        )
        if frozenset(errors_raw) != {BUY, SELL}:
            raise CompositionInputError(
                "composition_result.technical_errors", "expected buy/sell"
            )
        final_raw = _require_mapping(
            payload["final_scores"], "composition_result.final_scores"
        )
        if frozenset(final_raw) != {BUY, SELL}:
            raise CompositionInputError(
                "composition_result.final_scores", "expected buy/sell"
            )
        gates_raw = payload["composition_gates"]
        if type(gates_raw) is not list:
            raise CompositionInputError(
                "composition_result.composition_gates", "expected a list"
            )
        return cls(
            snapshot_id=_require_text(
                payload["snapshot_id"], "composition_result.snapshot_id"
            ),
            symbol=_require_text(payload["symbol"], "composition_result.symbol"),
            captured_at=_require_datetime(
                payload["captured_at"], "composition_result.captured_at"
            ),
            capture_source=_require_choice(
                payload["capture_source"],
                _VALID_CAPTURE_SOURCES,
                "composition_result.capture_source",
            ),
            technical={
                side: (
                    None
                    if technical_raw[side] is None
                    else _technical_result_from_dict(technical_raw[side], side=side)
                )
                for side in (BUY, SELL)
            },
            technical_errors={
                side: (errors_raw[side] if errors_raw[side] is None else dict(errors_raw[side]))
                for side in (BUY, SELL)
            },
            safety=MarketSafetyResult.from_dict(
                payload["safety"], path="composition_result.safety"
            ),
            macro_assessment=MacroAssessment.from_dict(
                payload["macro_assessment"], path="composition_result.macro_assessment"
            ),
            macro_gate=MacroGateResult.from_dict(
                payload["macro_gate"], path="composition_result.macro_gate"
            ),
            scenario=ScenarioEvaluation.from_dict(
                payload["scenario"], path="composition_result.scenario"
            ),
            final_scores={
                side: (
                    None
                    if final_raw[side] is None
                    else FinalScoreResult.from_dict(
                        final_raw[side], path=f"composition_result.final_scores.{side}"
                    )
                )
                for side in (BUY, SELL)
            },
            composition_gates=tuple(
                CompositionGate.from_dict(
                    gate, path=f"composition_result.composition_gates[{index}]"
                )
                for index, gate in enumerate(gates_raw)
            ),
            decision=DecisionResult.from_dict(
                payload["decision"], path="composition_result.decision"
            ),
            canonical=deserialize_canonical_pair_snapshot(payload["canonical"]),
        )


def _technical_result_from_dict(value: object, *, side: str) -> TechnicalSignalScoreResult:
    payload = _require_mapping(value, "technical")
    if payload.get("side") != side:
        raise CompositionInputError(
            "technical", f"side mismatch: expected {side!r}, got {payload.get('side')!r}"
        )
    return TechnicalSignalScoreResult.from_dict(payload, path="technical")


# ---------------------------------------------------------------------------
# Adapters (single API shared by live and backtest; differ only in provenance)
# ---------------------------------------------------------------------------


def build_live_snapshot(
    *,
    symbol: str,
    captured_at: object,
    regime: str,
    canonical_smc: object,
    buy: object,
    sell: object,
    safety_context: object,
    macro_raw_buy: int | None = None,
    macro_raw_sell: int | None = None,
    macro_confidence: float | None = None,
    account: object = None,
    portfolio: object = None,
    journal: object = None,
) -> ScannerV4Snapshot:
    """Wrap a live tick into the immutable composition snapshot."""
    return ScannerV4Snapshot(
        symbol=symbol,
        captured_at=captured_at,
        capture_source="live",
        regime=regime,
        canonical_smc=canonical_smc,
        buy=buy,
        sell=sell,
        safety=safety_context,
        macro_raw_buy=macro_raw_buy,
        macro_raw_sell=macro_raw_sell,
        macro_confidence=macro_confidence,
        account=account,
        portfolio=portfolio,
        journal=journal,
    )


def build_backtest_snapshot(
    *,
    symbol: str,
    captured_at: object,
    regime: str,
    canonical_smc: object,
    buy: object,
    sell: object,
    safety_context: object,
    macro_raw_buy: int | None = None,
    macro_raw_sell: int | None = None,
    macro_confidence: float | None = None,
    account: object = None,
    portfolio: object = None,
    journal: object = None,
) -> ScannerV4Snapshot:
    """Wrap a backtest bar into the immutable composition snapshot.

    Backtest only differs from live in ``capture_source`` provenance: the
    snapshot_id and every score/gate/decision are byte-identical.
    """
    return ScannerV4Snapshot(
        symbol=symbol,
        captured_at=captured_at,
        capture_source="backtest",
        regime=regime,
        canonical_smc=canonical_smc,
        buy=buy,
        sell=sell,
        safety=safety_context,
        macro_raw_buy=macro_raw_buy,
        macro_raw_sell=macro_raw_sell,
        macro_confidence=macro_confidence,
        account=account,
        portfolio=portfolio,
        journal=journal,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_side(value: object, path: str) -> str:
    if type(value) is not str or value not in VALID_SIDES:
        raise CompositionInputError(path, "must be exactly 'buy' or 'sell'")
    return value


def _require_mapping(value: object, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise CompositionInputError(path, "expected a mapping")
    return value


def _require_text(value: object, path: str) -> str:
    if type(value) is not str or not value:
        raise CompositionInputError(path, "expected a non-empty string")
    return value


def _require_datetime(value: object, path: str) -> datetime:
    if type(value) is datetime:
        return value
    if type(value) is not str:
        raise CompositionInputError(path, "expected an ISO-8601 datetime")
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise CompositionInputError(path, f"invalid ISO-8601 datetime: {exc}") from exc


def _require_choice(value: object, choices: frozenset[str], path: str) -> str:
    if type(value) is not str or value not in choices:
        raise CompositionInputError(
            path, f"expected one of {sorted(choices)}"
        )
    return value


def _require_positive_int(value: object, path: str) -> int:
    if type(value) is not int or isinstance(value, bool) or value <= 0:
        raise CompositionInputError(path, "expected a positive integer")
    return value


def _require_positive(value: object, path: str) -> float:
    number = _require_positive_number(path, value)
    if number <= 0:
        raise CompositionInputError(path, "must be positive")
    return number


def _require_positive_number(path: str, value: object) -> float:
    if type(value) not in (int, float) or isinstance(value, bool):
        raise CompositionInputError(path, "expected a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise CompositionInputError(path, "number must be finite")
    if number < 0:
        raise CompositionInputError(path, "must be >= 0")
    return number


def _require_raw(value: object, path: str, maximum: int) -> int:
    if type(value) is not int or isinstance(value, bool) or not 0 <= value <= maximum:
        raise CompositionInputError(path, f"expected an integer in 0..{maximum}")
    return value


def _require_optional_raw(value: object, path: str, maximum: int) -> int | None:
    if value is None:
        return None
    return _require_raw(value, path, maximum)


def _require_optional_score(value: object, path: str) -> int | None:
    if value is None:
        return None
    return _require_raw(value, path, 100)


def _require_optional_confidence(value: object, path: str) -> float | None:
    if value is None:
        return None
    number = _require_positive_number(path, value)
    if number > 1:
        raise CompositionInputError(path, "must be within 0..1")
    return number


def _require_optional_positive(value: object, path: str) -> float | None:
    if value is None:
        return None
    return _require_positive_number(path, value)


def _require_provenance_source(
    score: int | None, source: object, path: str
) -> str:
    """A score requires a non-empty source; a source without a score is rejected."""
    if type(source) is not str:
        raise CompositionInputError(path, "expected a string")
    if score is not None:
        if not source:
            raise CompositionInputError(
                f"{path}.source",
                "a valid evidence/execution score requires a non-empty source",
            )
        return source
    if source:
        raise CompositionInputError(
            f"{path}.source",
            "a source without a score is a contradictory input",
        )
    return ""


def _dedupe(values: list[str]) -> tuple[str, ...]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return tuple(seen)


def _safety_to_canonical_dict(context: MarketSafetyContext) -> dict[str, Any]:
    def _source_dict(source: Any) -> dict[str, Any]:
        base = {
            "availability": source.availability,
            "source": source.source,
            "checked_at": (
                None
                if source.checked_at is None
                else source.checked_at.isoformat()
            ),
            "provenance": _jsonable(source.provenance),
        }
        for name in (
            "terminal_connected",
            "broker_logged_in",
            "last_candle_time_utc",
            "spread_points",
            "symbol",
            "source_verified",
            "events",
            "volatility_ratio",
            "metric",
            "intended_timeframe",
        ):
            if hasattr(source, name):
                base[name] = _jsonable(getattr(source, name))
        return base

    return {
        "symbol": context.symbol,
        "captured_at": context.captured_at.isoformat(),
        "connectivity": _source_dict(context.connectivity),
        "data": _source_dict(context.data),
        "spread": _source_dict(context.spread),
        "news": _source_dict(context.news),
        "volatility": _source_dict(context.volatility),
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _canonical_to_jsonable(canonical: CanonicalPairSnapshot) -> dict[str, Any]:
    """Deterministic JSON version of the canonical artifact (to_dict may be enough)."""
    return _jsonable(canonical.to_dict())


__all__ = [
    "COMPOSITION_POLICY_VERSION",
    "SNAPSHOT_MAX_AGE_SECONDS",
    "SNAPSHOT_MAX_FUTURE_SKEW_SECONDS",
    "CompositionInputError",
    "CompositionServiceError",
    "ComposeOptions",
    "CompositionGate",
    "ScenarioEvaluation",
    "AccountState",
    "PortfolioState",
    "JournalState",
    "ScannerV4CompositionResult",
    "ScenarioPlan",
    "ScannerV4Snapshot",
    "SideSnapshot",
    "build_backtest_snapshot",
    "build_live_snapshot",
    "compose_scanner_v4",
    "compute_scenario_rr",
    "snapshot_id_of",
]