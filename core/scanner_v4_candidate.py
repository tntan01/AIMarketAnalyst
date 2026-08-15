"""Scanner V4 candidate decision (Bước 08; target-only, not live-wired yet).

``build_candidate`` is the **single writer** of the candidate decision.  It
consumes only the Step 07 canonical output (``ScannerV4CompositionResult``) and:

1. never promotes a Step 07 cap — ``DATA_UNAVAILABLE`` / ``BLOCKED`` stay as are,
   even with score 100 (strong score can never loosen a gate/cap);
2. re-certifies Technical/Setup floor, score gap and scenario R:R from the ONE
   versioned ``ThresholdPolicy`` (Bước 07's own floor check is only a guard);
3. promotes to ``READY_NOW`` only when every gate PASSes, the contract
   certifies, entry is ``confirmed`` and execution is fresh.  ``CAUTION`` or a
   non-critical ``UNKNOWN`` gate can never reach ``READY_NOW`` (max ``WATCH_ZONE``
   or ``WAITING_CONFIRMATION``);
4. keeps BLOCK with its scores+scenario for explanation;
5. materializes an order **payload** (never sends: ``sends_real_order=False``,
   ``revalidation_required=True``) carrying the full scorer/feature/policy/
   snapshot identity.

Every consumer (controller/UI/alert/execution-readiness/ranking) reads the
immutable ``ScannerV4CandidateDecision``; the strict readers below are the same
fail-closed contract so no consumer re-interprets or re-decides.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from typing import Any, Mapping

from core.reason_codes import (
    GATES_ALL_PASS,
    SCANNER_V4_SCHEMA_INVALID,
    SCANNER_V4_VERSION_MISMATCH,
    V4_CANDIDATE_SIDE_INCONSISTENT,
    V4_ENTRY_CONFIRMED,
    V4_ENTRY_CONFIRMATION_MISSING,
    V4_ENTRY_UNCONFIRMED,
    V4_EXECUTION_FRESH_OK,
    V4_EXECUTION_NOT_READY,
    V4_ORDER_PREPARED,
    V4_THRESHOLD_GAP_NOT_MET,
    V4_THRESHOLD_POLICY_OPEN,
    V4_THRESHOLD_RR_NOT_MET,
    V4_THRESHOLD_SCORE_FLOOR_NOT_MET,
)
from core.scanner_v4_composition import (
    COMPOSITION_POLICY_VERSION,
    ScannerV4CompositionResult,
)
from core.scanner_v4_execution_readiness import (
    ExecutionReadiness,
)
from core.scanner_v4_models import (
    BLOCKED,
    BUY,
    DATA_UNAVAILABLE,
    PASS,
    READY_NOW,
    SCANNER_V4_FEATURE_VERSION,
    SCANNER_V4_MACRO_POLICY_VERSION,
    SCANNER_V4_OUTPUT_SCHEMA_VERSION,
    SCANNER_V4_SAFETY_POLICY_VERSION,
    SCANNER_V4_SCORING_VERSION,
    SCANNER_V4_SNAPSHOT_VERSION,
    SELL,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
)
from core.scanner_v4_threshold_policy import ThresholdPolicy

VALID_ENTRY_CONFIRMATIONS = frozenset({"confirmed", "unconfirmed", "missing"})
VALID_CANDIDATE_STATUSES = frozenset(
    {READY_NOW, WAITING_CONFIRMATION, WATCH_ZONE, BLOCKED, DATA_UNAVAILABLE}
)

_SCHEMA_KEYS = frozenset(
    {
        "symbol",
        "captured_at",
        "snapshot_id",
        "composition_version",
        "scoring_version",
        "feature_version",
        "output_schema_version",
        "snapshot_version",
        "safety_policy_version",
        "macro_policy_version",
        "threshold_policy_version",
        "entry_confirmation",
        "candidate_status",
        "selected_side",
        "technical_signal_score",
        "setup_score",
        "score_gap",
        "risk_reward_ratio",
        "proximity",
        "evidence_score",
        "execution_quality_score",
        "decision_cap",
        "gate_codes",
        "reason_codes",
        "block_codes",
        "execution",
        "order_payload",
    }
)


class CandidateContractError(ValueError):
    """Typed contract failure on a candidate decision payload."""


def _error(path: str, message: str, *, code: str = SCANNER_V4_SCHEMA_INVALID) -> None:
    raise CandidateContractError(f"{code} at {path}: {message}")


def _require_mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _error(path, "expected a mapping", code=SCANNER_V4_SCHEMA_INVALID)
    return value


def _require_exact_keys(
    value: object, expected: frozenset[str], path: str
) -> Mapping[str, Any]:
    payload = _require_mapping(value, path)
    actual = frozenset(payload)
    if actual != expected:
        _error(
            path,
            f"expected exactly {sorted(expected)}, got {sorted(actual)}",
            code=SCANNER_V4_SCHEMA_INVALID,
        )
    return payload


def _require_text(value: object, path: str) -> str:
    if type(value) is not str:
        _error(path, "expected a string", code=SCANNER_V4_SCHEMA_INVALID)
    return value


def _optional_text(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, path)


def _require_datetime(value: object, path: str) -> datetime:
    if type(value) is datetime:
        return value
    if type(value) is not str:
        _error(path, "expected an ISO-8601 datetime", code=SCANNER_V4_SCHEMA_INVALID)
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        _error(path, f"invalid ISO-8601 datetime: {exc}", code=SCANNER_V4_SCHEMA_INVALID)
    return None  # pragma: no cover — _error raises


def _require_choice(value: object, choices: frozenset[str], path: str) -> str:
    if type(value) is not str or value not in choices:
        _error(path, f"expected one of {sorted(choices)}", code=SCANNER_V4_SCHEMA_INVALID)
    return value


def _optional_int(
    value: object, path: str, *, minimum: int | None = None, maximum: int | None = None
) -> int | None:
    if value is None:
        return None
    if type(value) is not int or isinstance(value, bool):
        _error(path, "expected an integer or null", code=SCANNER_V4_SCHEMA_INVALID)
    if minimum is not None and value < minimum:
        _error(path, f"expected at least {minimum}", code=SCANNER_V4_SCHEMA_INVALID)
    if maximum is not None and value > maximum:
        _error(path, f"expected at most {maximum}", code=SCANNER_V4_SCHEMA_INVALID)
    return value


def _optional_fraction(value: object, path: str) -> Fraction | None:
    if value is None:
        return None
    if isinstance(value, Fraction):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return Fraction(value)
    if type(value) is str:
        try:
            return Fraction(value)
        except ValueError as exc:
            _error(path, f"invalid fraction: {exc}", code=SCANNER_V4_SCHEMA_INVALID)
    _error(path, "expected a Fraction or a numeric string or null")
    return None  # pragma: no cover


def _require_positive_fraction(value: object, path: str) -> Fraction | None:
    rr = _optional_fraction(value, path)
    if rr is not None and rr <= 0:
        _error(path, "must be positive", code=SCANNER_V4_SCHEMA_INVALID)
    return rr


def _require_proximity(value: object) -> float | None:
    if value is None:
        return None
    if type(value) is not float or not 0 <= value <= 1:
        _error("proximity", "expected a float in 0..1 or null")
    return value


def _parse_reason_codes(value: object, path: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        _error(path, "expected a list of reason codes", code=SCANNER_V4_SCHEMA_INVALID)
    codes: list[str] = []
    for index, item in enumerate(value):
        if type(item) is not str or not item:
            _error(f"{path}[{index}]", "expected a non-empty reason code")
        if item not in codes:
            codes.append(item)
    return tuple(codes)


# ---------------------------------------------------------------------------
# Order payload (identity-carrying; NEVER sends a real order at Bước 08)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ScannerV4OrderPayload:
    """Prepared-order envelope carrying full scorer/feature/policy/snapshot identity.

    ``sends_real_order`` is structurally locked to ``False`` for Bước 08: this
    model only proves that a correct, fully-attributed order CAN be built when a
    candidate reaches ``READY_NOW``.  Execution revalidation (still
    ``revalidation_required=True``) and the atomic cutover gate real dispatch.
    """

    symbol: str
    side: str
    captured_at: datetime
    snapshot_id: str
    composition_version: str
    scoring_version: str
    feature_version: str
    output_schema_version: str
    snapshot_version: str
    safety_policy_version: str
    macro_policy_version: str
    threshold_policy_version: str
    entry: float
    stop_loss: float
    take_profit: float
    risk_reward_ratio: Fraction | None
    technical_signal_score: int
    setup_score: int
    sends_real_order: bool = False
    revalidation_required: bool = True

    def __post_init__(self) -> None:
        side = _require_choice(self.side, {BUY, SELL}, "order_payload.side")
        if self.sends_real_order is not False:
            _error(
                "order_payload.sends_real_order",
                "Step 08 never sends a real order; must be False until cutover",
            )
        entry = float(self.entry)
        stop_loss = float(self.stop_loss)
        take_profit = float(self.take_profit)
        if not (entry > 0 and stop_loss > 0 and take_profit > 0):
            _error(
                "order_payload",
                "entry/stop_loss/take_profit must be positive",
            )
        if side == BUY:
            if not (stop_loss < entry < take_profit):
                _error(
                    "order_payload",
                    "buy order requires stop_loss < entry < take_profit",
                )
        else:
            if not (take_profit < entry < stop_loss):
                _error(
                    "order_payload",
                    "sell order requires take_profit < entry < stop_loss",
                )
        rr = _require_positive_fraction(self.risk_reward_ratio, "order_payload.risk_reward_ratio")
        tech = _optional_int(
            self.technical_signal_score, "order_payload.technical_signal_score", minimum=0, maximum=100
        )
        setup = _optional_int(self.setup_score, "order_payload.setup_score", minimum=0, maximum=100)
        if tech is None or setup is None:
            _error(
                "order_payload",
                "a prepared order requires the selected-side technical and setup scores",
            )
        versions = {
            "composition_version": (self.composition_version, COMPOSITION_POLICY_VERSION),
            "scoring_version": (self.scoring_version, SCANNER_V4_SCORING_VERSION),
            "feature_version": (self.feature_version, SCANNER_V4_FEATURE_VERSION),
            "output_schema_version": (
                self.output_schema_version,
                SCANNER_V4_OUTPUT_SCHEMA_VERSION,
            ),
            "snapshot_version": (self.snapshot_version, SCANNER_V4_SNAPSHOT_VERSION),
            "safety_policy_version": (
                self.safety_policy_version,
                SCANNER_V4_SAFETY_POLICY_VERSION,
            ),
            "macro_policy_version": (
                self.macro_policy_version,
                SCANNER_V4_MACRO_POLICY_VERSION,
            ),
            "threshold_policy_version": (
                self.threshold_policy_version,
                self.threshold_policy_version,  # identity-neutral here; router locks it
            ),
            "symbol": (self.symbol, self.symbol),
            "snapshot_id": (self.snapshot_id, self.snapshot_id),
        }
        for field, (actual, expected) in versions.items():
            if type(actual) is not str or actual == "":
                _error(f"order_payload.{field}", "expected a non-empty string")
            expected_only = _V4_ONLY_VERSIONS.get(field)
            if expected_only is not None and actual != expected_only:
                _error(
                    f"order_payload.{field}",
                    f"expected the locked V4 {expected_only!r}, got {actual!r}",
                    code=SCANNER_V4_VERSION_MISMATCH,
                )
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "entry", entry)
        object.__setattr__(self, "stop_loss", stop_loss)
        object.__setattr__(self, "take_profit", take_profit)
        object.__setattr__(self, "risk_reward_ratio", rr)
        object.__setattr__(self, "technical_signal_score", tech)
        object.__setattr__(self, "setup_score", setup)
        if self.revalidation_required is not True:
            _error(
                "order_payload.revalidation_required",
                "Step 08 always requires execution revalidation",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "captured_at": self.captured_at.isoformat(),
            "snapshot_id": self.snapshot_id,
            "composition_version": self.composition_version,
            "scoring_version": self.scoring_version,
            "feature_version": self.feature_version,
            "output_schema_version": self.output_schema_version,
            "snapshot_version": self.snapshot_version,
            "safety_policy_version": self.safety_policy_version,
            "macro_policy_version": self.macro_policy_version,
            "threshold_policy_version": self.threshold_policy_version,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "risk_reward_ratio": (
                None if self.risk_reward_ratio is None else str(self.risk_reward_ratio)
            ),
            "technical_signal_score": self.technical_signal_score,
            "setup_score": self.setup_score,
            "sends_real_order": self.sends_real_order,
            "revalidation_required": self.revalidation_required,
        }

    @classmethod
    def from_dict(cls, value: object, *, path: str = "order_payload") -> ScannerV4OrderPayload:
        expected = frozenset(
            {
                "symbol",
                "side",
                "captured_at",
                "snapshot_id",
                "composition_version",
                "scoring_version",
                "feature_version",
                "output_schema_version",
                "snapshot_version",
                "safety_policy_version",
                "macro_policy_version",
                "threshold_policy_version",
                "entry",
                "stop_loss",
                "take_profit",
                "risk_reward_ratio",
                "technical_signal_score",
                "setup_score",
                "sends_real_order",
                "revalidation_required",
            }
        )
        payload = _require_exact_keys(value, expected, path)
        return cls(
            symbol=_require_text(payload["symbol"], f"{path}.symbol"),
            side=_require_text(payload["side"], f"{path}.side"),
            captured_at=_require_datetime(payload["captured_at"], f"{path}.captured_at"),
            snapshot_id=_require_text(payload["snapshot_id"], f"{path}.snapshot_id"),
            composition_version=_require_text(
                payload["composition_version"], f"{path}.composition_version"
            ),
            scoring_version=_require_text(
                payload["scoring_version"], f"{path}.scoring_version"
            ),
            feature_version=_require_text(
                payload["feature_version"], f"{path}.feature_version"
            ),
            output_schema_version=_require_text(
                payload["output_schema_version"], f"{path}.output_schema_version"
            ),
            snapshot_version=_require_text(
                payload["snapshot_version"], f"{path}.snapshot_version"
            ),
            safety_policy_version=_require_text(
                payload["safety_policy_version"], f"{path}.safety_policy_version"
            ),
            macro_policy_version=_require_text(
                payload["macro_policy_version"], f"{path}.macro_policy_version"
            ),
            threshold_policy_version=_require_text(
                payload["threshold_policy_version"], f"{path}.threshold_policy_version"
            ),
            entry=_require_positive_number(payload["entry"], f"{path}.entry"),
            stop_loss=_require_positive_number(
                payload["stop_loss"], f"{path}.stop_loss"
            ),
            take_profit=_require_positive_number(
                payload["take_profit"], f"{path}.take_profit"
            ),
            risk_reward_ratio=_require_positive_fraction(
                payload["risk_reward_ratio"], f"{path}.risk_reward_ratio"
            ),
            technical_signal_score=_optional_int(
                payload["technical_signal_score"],
                f"{path}.technical_signal_score",
                minimum=0,
                maximum=100,
            ),
            setup_score=_optional_int(
                payload["setup_score"], f"{path}.setup_score", minimum=0, maximum=100
            ),
            sends_real_order=bool(payload["sends_real_order"]),
            revalidation_required=bool(payload["revalidation_required"]),
        )


_V4_ONLY_VERSIONS = {
    "composition_version": COMPOSITION_POLICY_VERSION,
    "scoring_version": SCANNER_V4_SCORING_VERSION,
    "feature_version": SCANNER_V4_FEATURE_VERSION,
    "output_schema_version": SCANNER_V4_OUTPUT_SCHEMA_VERSION,
    "snapshot_version": SCANNER_V4_SNAPSHOT_VERSION,
    "safety_policy_version": SCANNER_V4_SAFETY_POLICY_VERSION,
    "macro_policy_version": SCANNER_V4_MACRO_POLICY_VERSION,
}


def _require_positive_number(value: object, path: str) -> float:
    if type(value) is not float and type(value) is not int:
        _error(path, "expected a number", code=SCANNER_V4_SCHEMA_INVALID)
    number = float(value)
    if number <= 0:
        _error(path, "expected a positive number", code=SCANNER_V4_SCHEMA_INVALID)
    return number


# ---------------------------------------------------------------------------
# Candidate decision (the single consumer contract)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ScannerV4CandidateDecision:
    symbol: str
    captured_at: datetime
    snapshot_id: str
    composition_version: str
    scoring_version: str
    feature_version: str
    output_schema_version: str
    snapshot_version: str
    safety_policy_version: str
    macro_policy_version: str
    threshold_policy_version: str
    entry_confirmation: str
    candidate_status: str
    selected_side: str | None
    technical_signal_score: int | None
    setup_score: int | None
    score_gap: int | None
    risk_reward_ratio: Fraction | None
    proximity: float | None
    evidence_score: int | None
    execution_quality_score: int | None
    decision_cap: str | None
    gate_codes: tuple[str, ...]
    reason_codes: tuple[str, ...]
    block_codes: tuple[str, ...]
    execution: ExecutionReadiness
    order_payload: ScannerV4OrderPayload | None

    def __post_init__(self) -> None:
        # --- identity / versions -------------------------------------------
        for field, expected in _V4_ONLY_VERSIONS.items():
            actual = _require_text(getattr(self, field), f"candidate.{field}")
            if actual != expected:
                _error(
                    f"candidate.{field}",
                    f"expected the locked V4 {expected!r}, got {actual!r}",
                    code=SCANNER_V4_VERSION_MISMATCH,
                )
        threshold_version = _require_text(
            self.threshold_policy_version, "candidate.threshold_policy_version"
        )
        if threshold_version == "":
            _error("candidate.threshold_policy_version", "must be non-empty")

        # --- scalar validations ---------------------------------------------
        captured_at = _require_datetime(self.captured_at, "candidate.captured_at")
        side = (
            None
            if self.selected_side is None
            else _require_choice(self.selected_side, {BUY, SELL}, "candidate.selected_side")
        )
        status = _require_choice(
            self.candidate_status, VALID_CANDIDATE_STATUSES, "candidate.candidate_status"
        )
        entry_confirmation = _require_choice(
            self.entry_confirmation,
            VALID_ENTRY_CONFIRMATIONS,
            "candidate.entry_confirmation",
        )
        technical = _optional_int(
            self.technical_signal_score,
            "candidate.technical_signal_score",
            minimum=0,
            maximum=100,
        )
        setup = _optional_int(
            self.setup_score, "candidate.setup_score", minimum=0, maximum=100
        )
        gap = _optional_int(
            self.score_gap, "candidate.score_gap", minimum=0, maximum=100
        )
        rr = _require_positive_fraction(
            self.risk_reward_ratio, "candidate.risk_reward_ratio"
        )
        proximity = _require_proximity(self.proximity)
        evidence = _optional_int(
            self.evidence_score, "candidate.evidence_score", minimum=0, maximum=100
        )
        execution_score = _optional_int(
            self.execution_quality_score,
            "candidate.execution_quality_score",
            minimum=0,
            maximum=100,
        )
        cap = _optional_text(self.decision_cap, "candidate.decision_cap")
        gate_codes = _parse_reason_codes(self.gate_codes, "candidate.gate_codes")
        reason_codes = _parse_reason_codes(self.reason_codes, "candidate.reason_codes")
        block_codes = _parse_reason_codes(self.block_codes, "candidate.block_codes")

        if type(self.execution) is not ExecutionReadiness:
            _error("candidate.execution", "expected ExecutionReadiness")

        # --- status invariants ----------------------------------------------
        if status == READY_NOW:
            if side is None:
                _error("candidate.selected_side", "READY_NOW requires a selected side")
            if self.order_payload is None:
                _error("candidate.order_payload", "READY_NOW requires a prepared order payload")
            if self.order_payload.side != side:
                _error(
                    "candidate.order_payload.side",
                    "order payload side must match the selected side",
                )
            if entry_confirmation != "confirmed":
                _error(
                    "candidate.entry_confirmation",
                    "READY_NOW requires entry confirmed",
                )
            if cap is not None:
                _error("candidate.decision_cap", "READY_NOW cannot carry a decision cap")
            if block_codes:
                _error("candidate.block_codes", "READY_NOW cannot carry block codes")
            if technical is None or setup is None:
                _error("candidate.technical_signal_score", "READY_NOW requires both scores")
        elif status == DATA_UNAVAILABLE:
            if side is not None or technical is not None or setup is not None:
                _error(
                    "candidate.selected_side",
                    "DATA_UNAVAILABLE requires no selected side or scores",
                )
            if self.order_payload is not None:
                _error("candidate.order_payload", "DATA_UNAVAILABLE has no order payload")
        else:  # WATCH_ZONE / WAITING_CONFIRMATION / BLOCKED
            if self.order_payload is not None:
                _error(
                    "candidate.order_payload",
                    f"{status} cannot carry an order payload",
                )

        if status == BLOCKED and not block_codes:
            _error("candidate.block_codes", "BLOCKED requires block codes")

        object.__setattr__(self, "captured_at", captured_at)
        object.__setattr__(self, "selected_side", side)
        object.__setattr__(self, "candidate_status", status)
        object.__setattr__(self, "entry_confirmation", entry_confirmation)
        object.__setattr__(self, "technical_signal_score", technical)
        object.__setattr__(self, "setup_score", setup)
        object.__setattr__(self, "score_gap", gap)
        object.__setattr__(self, "risk_reward_ratio", rr)
        object.__setattr__(self, "proximity", proximity)
        object.__setattr__(self, "evidence_score", evidence)
        object.__setattr__(self, "execution_quality_score", execution_score)
        object.__setattr__(self, "decision_cap", cap)
        object.__setattr__(self, "gate_codes", gate_codes)
        object.__setattr__(self, "reason_codes", reason_codes)
        object.__setattr__(self, "block_codes", block_codes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "captured_at": self.captured_at.isoformat(),
            "snapshot_id": self.snapshot_id,
            "composition_version": self.composition_version,
            "scoring_version": self.scoring_version,
            "feature_version": self.feature_version,
            "output_schema_version": self.output_schema_version,
            "snapshot_version": self.snapshot_version,
            "safety_policy_version": self.safety_policy_version,
            "macro_policy_version": self.macro_policy_version,
            "threshold_policy_version": self.threshold_policy_version,
            "entry_confirmation": self.entry_confirmation,
            "candidate_status": self.candidate_status,
            "selected_side": self.selected_side,
            "technical_signal_score": self.technical_signal_score,
            "setup_score": self.setup_score,
            "score_gap": self.score_gap,
            "risk_reward_ratio": (
                None if self.risk_reward_ratio is None else str(self.risk_reward_ratio)
            ),
            "proximity": self.proximity,
            "evidence_score": self.evidence_score,
            "execution_quality_score": self.execution_quality_score,
            "decision_cap": self.decision_cap,
            "gate_codes": list(self.gate_codes),
            "reason_codes": list(self.reason_codes),
            "block_codes": list(self.block_codes),
            "execution": self.execution.to_dict(),
            "order_payload": (
                None if self.order_payload is None else self.order_payload.to_dict()
            ),
        }

    @classmethod
    def from_dict(
        cls, value: object, *, path: str = "candidate"
    ) -> ScannerV4CandidateDecision:
        payload = _require_exact_keys(value, _SCHEMA_KEYS, path)
        execution = ExecutionReadiness.from_dict(
            payload["execution"], path=f"{path}.execution"
        )
        order = payload["order_payload"]
        return cls(
            symbol=_require_text(payload["symbol"], f"{path}.symbol"),
            captured_at=_require_datetime(payload["captured_at"], f"{path}.captured_at"),
            snapshot_id=_require_text(payload["snapshot_id"], f"{path}.snapshot_id"),
            composition_version=_require_text(
                payload["composition_version"], f"{path}.composition_version"
            ),
            scoring_version=_require_text(
                payload["scoring_version"], f"{path}.scoring_version"
            ),
            feature_version=_require_text(
                payload["feature_version"], f"{path}.feature_version"
            ),
            output_schema_version=_require_text(
                payload["output_schema_version"], f"{path}.output_schema_version"
            ),
            snapshot_version=_require_text(
                payload["snapshot_version"], f"{path}.snapshot_version"
            ),
            safety_policy_version=_require_text(
                payload["safety_policy_version"], f"{path}.safety_policy_version"
            ),
            macro_policy_version=_require_text(
                payload["macro_policy_version"], f"{path}.macro_policy_version"
            ),
            threshold_policy_version=_require_text(
                payload["threshold_policy_version"],
                f"{path}.threshold_policy_version",
            ),
            entry_confirmation=_require_choice(
                payload["entry_confirmation"],
                VALID_ENTRY_CONFIRMATIONS,
                f"{path}.entry_confirmation",
            ),
            candidate_status=_require_choice(
                payload["candidate_status"],
                VALID_CANDIDATE_STATUSES,
                f"{path}.candidate_status",
            ),
            selected_side=_optional_text(payload["selected_side"], f"{path}.selected_side"),
            technical_signal_score=_optional_int(
                payload["technical_signal_score"],
                f"{path}.technical_signal_score",
                minimum=0,
                maximum=100,
            ),
            setup_score=_optional_int(
                payload["setup_score"], f"{path}.setup_score", minimum=0, maximum=100
            ),
            score_gap=_optional_int(
                payload["score_gap"], f"{path}.score_gap", minimum=0, maximum=100
            ),
            risk_reward_ratio=_require_positive_fraction(
                payload["risk_reward_ratio"], f"{path}.risk_reward_ratio"
            ),
            proximity=_require_proximity(payload["proximity"]),
            evidence_score=_optional_int(
                payload["evidence_score"], f"{path}.evidence_score", minimum=0, maximum=100
            ),
            execution_quality_score=_optional_int(
                payload["execution_quality_score"],
                f"{path}.execution_quality_score",
                minimum=0,
                maximum=100,
            ),
            decision_cap=_optional_text(payload["decision_cap"], f"{path}.decision_cap"),
            gate_codes=_parse_reason_codes(payload["gate_codes"], f"{path}.gate_codes"),
            reason_codes=_parse_reason_codes(payload["reason_codes"], f"{path}.reason_codes"),
            block_codes=_parse_reason_codes(payload["block_codes"], f"{path}.block_codes"),
            execution=execution,
            order_payload=(
                None
                if order is None
                else ScannerV4OrderPayload.from_dict(order, path=f"{path}.order_payload")
            ),
        )


# ---------------------------------------------------------------------------
# build_candidate — the single writer of the candidate decision
# ---------------------------------------------------------------------------


def _all_gates_pass(composition: ScannerV4CompositionResult) -> bool:
    return (
        composition.safety.status == PASS
        and composition.macro_gate.status == PASS
        and all(gate.status == PASS for gate in composition.composition_gates)
    )


def _gate_codes_of(composition: ScannerV4CompositionResult) -> tuple[str, ...]:
    codes: list[str] = []
    for source in (
        composition.safety.reason_codes,
        composition.macro_gate.reason_codes,
        *(gate.reason_codes for gate in composition.composition_gates),
    ):
        for code in source:
            if code not in codes:
                codes.append(code)
    return tuple(codes)


def build_candidate(
    *,
    composition: ScannerV4CompositionResult,
    thresholds: ThresholdPolicy,
    entry_confirmation: str,
    execution: ExecutionReadiness,
    proximity: float | None = None,
) -> ScannerV4CandidateDecision:
    """Build the single candidate decision from the canonical Step 07 output.

    Decision precedence (locked in docs Mục 9 / Bước 08):

    1. critical data UNKNOWN / missing Technical -> ``DATA_UNAVAILABLE``;
    2. any gate BLOCK -> ``BLOCKED`` (score 100 cannot change it);
    3. ``CAUTION`` / non-critical ``UNKNOWN`` -> never ``READY_NOW``;
    4. only when every gate PASSes: floors/gap/R:R from the ONE versioned
       threshold contract, then entry confirmation and R:R.
    """
    _require_choice(
        entry_confirmation, VALID_ENTRY_CONFIRMATIONS, "entry_confirmation"
    )
    proximity = _require_proximity(proximity)

    canonical = composition.canonical
    base_decision = composition.decision
    base_status = base_decision.candidate_status
    selected_side = base_decision.selected_side
    gap = base_decision.score_gap

    # --- side/scenario/gate consistency guard -------------------------------
    if selected_side is not None and base_status != DATA_UNAVAILABLE:
        if composition.scenario.side not in (None, selected_side):
            return _unavailable(composition, thresholds, entry_confirmation, execution, proximity, V4_CANDIDATE_SIDE_INCONSISTENT)
        if (
            composition.macro_gate.assessed_side not in (None, selected_side)
            and base_status != BLOCKED  # BLOCK keeps evidence; the guard is on decision
        ):
            return _unavailable(composition, thresholds, entry_confirmation, execution, proximity, V4_CANDIDATE_SIDE_INCONSISTENT)

    gate_codes = _gate_codes_of(composition)
    if selected_side is None:
        side_score = None
    else:
        side_score = canonical.side_score(selected_side)

    def _base(
        *,
        status: str,
        reason: tuple[str, ...],
        block: tuple[str, ...] = (),
        force_unavailable: bool = False,
        order_payload: ScannerV4OrderPayload | None = None,
    ) -> ScannerV4CandidateDecision:
        return _assemble(
            composition=composition,
            thresholds=thresholds,
            entry_confirmation=entry_confirmation,
            execution=execution,
            proximity=proximity,
            status=status,
            selected_side=None if force_unavailable else selected_side,
            side_score=side_score,
            technical_gap=gap,
            rr=composition.scenario.risk_reward_ratio,
            decision_cap=base_decision.decision_cap,
            gate_codes=gate_codes,
            reason_codes=reason,
            block_codes=block,
            order_payload=order_payload,
        )

    # 1. critical data UNKNOWN / missing technical: never recovered, never
    #    OUT_OF_STRATEGY (the V4 model has no such status).
    if base_status == DATA_UNAVAILABLE:
        return _base(
            status=DATA_UNAVAILABLE,
            reason=base_decision.reason_codes,
            force_unavailable=True,
        )

    # 2. BLOCK: strong score can never loosen a gate/cap.
    if base_status == BLOCKED:
        return _base(
            status=BLOCKED,
            reason=base_decision.block_codes,
            block=base_decision.block_codes,
        )

    # 3.+4. WATCH (always from gates) / WAITING (all PASS) — refine by contract.
    if not _all_gates_pass(composition):
        # CAUTION / non-critical UNKNOWN (or any non-PASS gate): can never reach
        # READY_NOW; Step 07 already capped the base at WATCH_ZONE.
        return _base(
            status=WATCH_ZONE,
            reason=base_decision.reason_codes,
        )

    reason: list[str] = []
    if not thresholds.certified():
        reason.append(V4_THRESHOLD_POLICY_OPEN)
        return _base(status=WATCH_ZONE, reason=tuple(reason))

    tech: int | None = side_score.technical_signal_score if side_score is not None else None
    setup: int | None = side_score.setup_score if side_score is not None else None
    assert thresholds.technical_floor is not None
    assert thresholds.setup_floor is not None
    floor_ok = (
        tech is not None
        and setup is not None
        and tech >= thresholds.technical_floor
        and setup >= thresholds.setup_floor
    )
    gap_ok = gap is not None and gap >= thresholds.min_score_gap
    rr = composition.scenario.risk_reward_ratio
    rr_ok = rr is not None and rr >= thresholds.min_risk_reward

    if not floor_ok:
        reason.append(V4_THRESHOLD_SCORE_FLOOR_NOT_MET)
    if not gap_ok:
        reason.append(V4_THRESHOLD_GAP_NOT_MET)
    if not rr_ok:
        reason.append(V4_THRESHOLD_RR_NOT_MET)

    if not (floor_ok and gap_ok and rr_ok):
        return _base(status=WATCH_ZONE, reason=tuple(reason))

    # Certified: entry confirmation and execution decide WAITING vs READY_NOW.
    assert selected_side is not None and tech is not None and setup is not None
    confirmed_reason = [GATES_ALL_PASS, V4_ENTRY_CONFIRMED]
    if entry_confirmation == "confirmed" and execution.can_execute:
        return _base(
            status=READY_NOW,
            reason=tuple(confirmed_reason + [V4_EXECUTION_FRESH_OK, V4_ORDER_PREPARED]),
            order_payload=_order_payload_for(
                composition=composition,
                thresholds=thresholds,
                side=selected_side,
                technical=tech,
                setup=setup,
                rr=rr,
            ),
        )
    if entry_confirmation == "confirmed":
        return _base(
            status=WAITING_CONFIRMATION,
            reason=tuple(confirmed_reason + [V4_EXECUTION_NOT_READY]),
        )
    if entry_confirmation == "unconfirmed":
        return _base(
            status=WAITING_CONFIRMATION,
            reason=(GATES_ALL_PASS, V4_ENTRY_UNCONFIRMED),
        )
    return _base(
        status=WAITING_CONFIRMATION,
        reason=(GATES_ALL_PASS, V4_ENTRY_CONFIRMATION_MISSING),
    )


def _assemble(
    *,
    composition: ScannerV4CompositionResult,
    thresholds: ThresholdPolicy,
    entry_confirmation: str,
    execution: ExecutionReadiness,
    proximity: float | None,
    status: str,
    selected_side: str | None,
    side_score: object,
    technical_gap: int | None,
    rr: Fraction | None,
    decision_cap: str | None,
    gate_codes: tuple[str, ...],
    reason_codes: tuple[str, ...],
    block_codes: tuple[str, ...],
    order_payload: ScannerV4OrderPayload | None = None,
) -> ScannerV4CandidateDecision:
    canonical = composition.canonical
    if selected_side is not None and side_score is not None:
        technical = side_score.technical_signal_score
        setup = side_score.setup_score
        evidence = side_score.evidence_score
        execution_score = side_score.execution_quality_score
    else:
        technical = setup = evidence = execution_score = None
    candidate = ScannerV4CandidateDecision(
        symbol=canonical.symbol,
        captured_at=canonical.captured_at,
        snapshot_id=canonical.snapshot_id,
        composition_version=COMPOSITION_POLICY_VERSION,
        scoring_version=canonical.scoring_version,
        feature_version=canonical.feature_version,
        output_schema_version=canonical.output_schema_version,
        snapshot_version=canonical.snapshot_version,
        safety_policy_version=canonical.safety_policy_version,
        macro_policy_version=canonical.macro_policy_version,
        threshold_policy_version=thresholds.policy_version,
        entry_confirmation=entry_confirmation,
        candidate_status=status,
        selected_side=selected_side,
        technical_signal_score=technical,
        setup_score=setup,
        score_gap=technical_gap,
        risk_reward_ratio=rr,
        proximity=proximity,
        evidence_score=evidence,
        execution_quality_score=execution_score,
        decision_cap=decision_cap,
        gate_codes=gate_codes,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        block_codes=block_codes,
        execution=execution.with_candidate(None),  # prepared weighed at assembly
        order_payload=order_payload,
    )
    if status == READY_NOW:
        # Re-weight readiness against the final READY_NOW verdict (idempotent).
        candidate = ScannerV4CandidateDecision(
            symbol=candidate.symbol,
            captured_at=candidate.captured_at,
            snapshot_id=candidate.snapshot_id,
            composition_version=candidate.composition_version,
            scoring_version=candidate.scoring_version,
            feature_version=candidate.feature_version,
            output_schema_version=candidate.output_schema_version,
            snapshot_version=candidate.snapshot_version,
            safety_policy_version=candidate.safety_policy_version,
            macro_policy_version=candidate.macro_policy_version,
            threshold_policy_version=candidate.threshold_policy_version,
            entry_confirmation=candidate.entry_confirmation,
            candidate_status=candidate.candidate_status,
            selected_side=candidate.selected_side,
            technical_signal_score=candidate.technical_signal_score,
            setup_score=candidate.setup_score,
            score_gap=candidate.score_gap,
            risk_reward_ratio=candidate.risk_reward_ratio,
            proximity=candidate.proximity,
            evidence_score=candidate.evidence_score,
            execution_quality_score=candidate.execution_quality_score,
            decision_cap=candidate.decision_cap,
            gate_codes=candidate.gate_codes,
            reason_codes=candidate.reason_codes,
            block_codes=candidate.block_codes,
            execution=candidate.execution.with_candidate(candidate),
            order_payload=candidate.order_payload,
        )
    return candidate


def _unavailable(
    composition: ScannerV4CompositionResult,
    thresholds: ThresholdPolicy,
    entry_confirmation: str,
    execution: ExecutionReadiness,
    proximity: float | None,
    reason: str,
) -> ScannerV4CandidateDecision:
    """Force DATA_UNAVAILABLE from an inconsistency guard (fail closed)."""
    return _assemble(
        composition=composition,
        thresholds=thresholds,
        entry_confirmation=entry_confirmation,
        execution=execution,
        proximity=proximity,
        status=DATA_UNAVAILABLE,
        selected_side=None,
        side_score=None,
        technical_gap=composition.decision.score_gap,
        rr=composition.scenario.risk_reward_ratio,
        decision_cap=composition.decision.decision_cap,
        gate_codes=_gate_codes_of(composition),
        reason_codes=(reason,),
        block_codes=(),
    )


def _order_payload_for(
    *,
    composition: ScannerV4CompositionResult,
    thresholds: ThresholdPolicy,
    side: str,
    technical: int,
    setup: int,
    rr: Fraction | None,
) -> ScannerV4OrderPayload:
    """Materialize the prepared order envelope (never sent at Bước 08)."""
    plan = composition.scenario.plan
    assert plan is not None and plan.direction == side
    canonical = composition.canonical
    return ScannerV4OrderPayload(
        symbol=canonical.symbol,
        side=side,
        captured_at=canonical.captured_at,
        snapshot_id=canonical.snapshot_id,
        composition_version=COMPOSITION_POLICY_VERSION,
        scoring_version=canonical.scoring_version,
        feature_version=canonical.feature_version,
        output_schema_version=canonical.output_schema_version,
        snapshot_version=canonical.snapshot_version,
        safety_policy_version=canonical.safety_policy_version,
        macro_policy_version=canonical.macro_policy_version,
        threshold_policy_version=thresholds.policy_version,
        entry=plan.entry,
        stop_loss=plan.stop_loss,
        take_profit=plan.take_profit,
        risk_reward_ratio=rr,
        technical_signal_score=technical,
        setup_score=setup,
    )