"""Candidate ledger and immutable strategy configuration for OOS replay."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import hashlib
import json
from typing import Any, Iterable

from core.safe_types import optional_float


CANDIDATE_LEDGER_VERSION = "backtest-candidate-ledger-v1"
FROZEN_STRATEGY_VERSION = "frozen-strategy-config-v1"
CANDIDATE_REPLAY_VERSION = "candidate-replay-v1"

SCORE_THRESHOLDS = (50, 55, 60, 65, 70, 75, 80)
RR_THRESHOLDS = (1.0, 1.3, 1.5, 2.0)
MIN_LEDGER_CANDIDATES = 8


@dataclass(frozen=True, slots=True)
class FrozenStrategyConfig:
    config_id: str
    symbol: str
    side: str
    allowed_regimes: tuple[str, ...]
    min_setup_score: int
    min_expected_rr: float
    score_metric: str = "setup_score"
    version: str = FROZEN_STRATEGY_VERSION
    selected_from: str = "IN_SAMPLE_CANDIDATE_LEDGER"

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["allowed_regimes"] = list(self.allowed_regimes)
        return value


@dataclass(slots=True)
class CandidateLedgerEntry:
    candidate_id: str
    symbol: str
    decision_time: str
    side: str
    setup_score: int | None
    setup_score_source: str
    signal_score: int | None
    market_regime: str
    expected_effective_rr: float | None
    scenario_available: bool
    base_eligible: bool
    base_rejection_reason: str | None
    scenario_source: str = "pipeline"
    research_only: bool = False
    frozen_config_id: str = ""
    strategy_eligible: bool | None = None
    strategy_rejection_reasons: list[str] = field(default_factory=list)
    simulated_trade: dict[str, Any] | None = None
    executed: bool = False
    version: str = CANDIDATE_LEDGER_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_candidate_ledger_entry(
    *,
    symbol: str,
    decision_time: datetime,
    analysis: dict[str, Any],
    scenario: dict[str, Any] | None,
    base_rejection_reason: str | None,
) -> CandidateLedgerEntry:
    side = _selected_side(analysis, scenario)
    setup_score, score_source = side_setup_score(analysis, side)
    signal_score = _side_signal_score(analysis, side)
    market_regime = analysis.get("market_regime")
    regime = (
        str(market_regime.get("primary", "unknown") or "unknown").lower()
        if isinstance(market_regime, dict)
        else "unknown"
    )
    scenario_value = scenario if isinstance(scenario, dict) else {}
    scenario_source = str(
        scenario_value.get("scenario_source")
        or (
            "synthetic_fallback"
            if scenario_value.get("_fallback") is True
            else "pipeline"
        )
    )
    research_only = bool(
        scenario_value.get("research_only") is True
        or scenario_value.get("synthetic") is True
        or scenario_value.get("_fallback") is True
    )
    identity = {
        "symbol": symbol,
        "decision_time": decision_time.isoformat(),
        "side": side,
        "entry_zone": scenario_value.get("entry_zone"),
        "stop_loss": scenario_value.get("stop_loss"),
        "take_profit": scenario_value.get("take_profit"),
    }
    candidate_id = hashlib.sha256(
        json.dumps(
            identity,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:20]
    scenario_available = bool(scenario_value and side in {"buy", "sell"})
    rejection = base_rejection_reason
    if not scenario_available:
        rejection = rejection or "NO_SIDE_SCENARIO"
    return CandidateLedgerEntry(
        candidate_id=candidate_id,
        symbol=symbol,
        decision_time=decision_time.isoformat(),
        side=side,
        setup_score=setup_score,
        setup_score_source=score_source,
        signal_score=signal_score,
        market_regime=regime,
        expected_effective_rr=optional_float(
            scenario_value.get("expected_effective_rr")
        ),
        scenario_available=scenario_available,
        base_eligible=scenario_available and rejection is None,
        base_rejection_reason=rejection,
        scenario_source=scenario_source,
        research_only=research_only,
    )


def side_setup_score(
    analysis: dict[str, Any],
    side: str,
) -> tuple[int | None, str]:
    """Read only an explicit side-owned setup_score; never use final_score."""

    if side not in {"buy", "sell"}:
        return None, "missing_side"
    for container_name in ("side_scores", "scenario_scores"):
        container = analysis.get(container_name)
        side_value = (
            container.get(side)
            if isinstance(container, dict)
            else None
        )
        if not isinstance(side_value, dict) or side_value.get("setup_score") is None:
            continue
        try:
            return int(side_value["setup_score"]), f"{container_name}.{side}.setup_score"
        except (TypeError, ValueError):
            return None, f"invalid_{container_name}.{side}.setup_score"
    return None, f"missing_{side}_setup_score"


def evaluate_frozen_strategy(
    entry: CandidateLedgerEntry,
    config: FrozenStrategyConfig | None,
) -> tuple[bool, list[str]]:
    if config is None:
        return True, []
    reasons: list[str] = []
    if entry.symbol != config.symbol:
        reasons.append("FROZEN_SYMBOL_MISMATCH")
    if entry.side != config.side:
        reasons.append("FROZEN_SIDE_MISMATCH")
    if entry.market_regime not in config.allowed_regimes:
        reasons.append("FROZEN_REGIME_MISMATCH")
    if entry.setup_score is None:
        reasons.append("FROZEN_SETUP_SCORE_MISSING")
    elif entry.setup_score < config.min_setup_score:
        reasons.append("FROZEN_SETUP_SCORE_BELOW_MIN")
    if entry.expected_effective_rr is None:
        reasons.append("FROZEN_EXPECTED_RR_MISSING")
    elif entry.expected_effective_rr < config.min_expected_rr:
        reasons.append("FROZEN_EXPECTED_RR_BELOW_MIN")
    if entry.research_only:
        reasons.append("FROZEN_RESEARCH_ONLY_CANDIDATE")
    if not entry.base_eligible:
        reasons.append(
            entry.base_rejection_reason or "FROZEN_BASE_PIPELINE_REJECTED"
        )
    return not reasons, _unique(reasons)


def optimize_frozen_strategy(
    entries: Iterable[CandidateLedgerEntry | dict[str, Any]],
    *,
    symbol: str,
    min_candidates: int = MIN_LEDGER_CANDIDATES,
) -> FrozenStrategyConfig | None:
    """Select one config using only simulated, explicit-score IS candidates."""

    rows = [_ledger_dict(entry) for entry in entries]
    eligible = [
        row for row in rows
        if row.get("symbol") == symbol
        and row.get("base_eligible") is True
        and row.get("research_only") is not True
        and row.get("setup_score") is not None
        and isinstance(row.get("simulated_trade"), dict)
    ]
    if len(eligible) < min_candidates:
        return None

    best: tuple[float, str, str, int, float] | None = None
    for regime, side in sorted({
        (str(row.get("market_regime") or "unknown"), str(row.get("side") or ""))
        for row in eligible
        if str(row.get("side") or "") in {"buy", "sell"}
    }):
        for min_score in SCORE_THRESHOLDS:
            for min_rr in RR_THRESHOLDS:
                selected = [
                    row for row in eligible
                    if row.get("market_regime") == regime
                    and row.get("side") == side
                    and int(row.get("setup_score") or 0) >= min_score
                    and optional_float(row.get("expected_effective_rr")) is not None
                    and float(row.get("expected_effective_rr") or 0) >= min_rr
                ]
                if len(selected) < min_candidates:
                    continue
                results = [
                    float((row.get("simulated_trade") or {}).get("result_r", 0) or 0)
                    for row in selected
                ]
                expectancy = sum(results) / len(results)
                gross_profit = sum(value for value in results if value > 0)
                gross_loss = abs(sum(value for value in results if value < 0))
                profit_factor = (
                    gross_profit / gross_loss
                    if gross_loss > 0
                    else gross_profit
                )
                if expectancy < 0.10 or profit_factor < 1.20:
                    continue
                composite = expectancy * 10 + profit_factor + len(selected) * 0.01
                candidate = (composite, regime, side, min_score, min_rr)
                if best is None or candidate > best:
                    best = candidate
    if best is None:
        return None
    _score, regime, side, min_score, min_rr = best
    identity = {
        "version": FROZEN_STRATEGY_VERSION,
        "symbol": symbol,
        "regime": regime,
        "side": side,
        "min_setup_score": min_score,
        "min_expected_rr": min_rr,
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:12]
    return FrozenStrategyConfig(
        config_id=f"{symbol.replace('/', '')}-frozen-{digest}",
        symbol=symbol,
        side=side,
        allowed_regimes=(regime,),
        min_setup_score=min_score,
        min_expected_rr=min_rr,
    )


def candidate_ledger_fingerprint(
    entries: Iterable[CandidateLedgerEntry | dict[str, Any]],
) -> str:
    payload = [_ledger_dict(entry) for entry in entries]
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _selected_side(
    analysis: dict[str, Any],
    scenario: dict[str, Any] | None,
) -> str:
    if isinstance(scenario, dict):
        side = str(scenario.get("type") or "").lower()
        if side in {"buy", "sell"}:
            return side
    summary = analysis.get("decision_summary")
    if isinstance(summary, dict):
        side = str(
            summary.get("best_side") or summary.get("best_scenario") or ""
        ).lower()
        if side in {"buy", "sell"}:
            return side
    return ""


def _side_signal_score(analysis: dict[str, Any], side: str) -> int | None:
    scores = analysis.get("scenario_scores")
    side_scores = scores.get(side) if isinstance(scores, dict) else None
    if not isinstance(side_scores, dict):
        return None
    try:
        return int(
            side_scores.get("signal_score", side_scores.get("total"))
        )
    except (TypeError, ValueError):
        return None


def _ledger_dict(
    entry: CandidateLedgerEntry | dict[str, Any],
) -> dict[str, Any]:
    return entry.to_dict() if isinstance(entry, CandidateLedgerEntry) else dict(entry)


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))
