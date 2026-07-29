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
MIN_OPTIMIZER_EXPECTANCY_R = 0.10
MIN_OPTIMIZER_PROFIT_FACTOR = 1.20
RELEASE_ENTRY_ZONE_SOURCES = frozenset({
    "smc",
    "smc_selected",
    "smc_v2_selected",
})
RELEASE_ENTRY_STATUS = "confirmed_entry"
RELEASE_DECISION = "READY_TO_TRADE"
RELEASE_M15_QUALITY = "strict"
RELEASE_SCAN_READY_REJECTIONS = frozenset({
    "blocked_by_trade_gate",
    "blocked_by_permission",
    "blocked_by_decision",
    "blocked_by_entry_status",
})


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
    simulation_rejection_reason: str | None = None
    simulation_rejection_detail: dict[str, Any] | None = None
    entry_zone_source: str | None = None
    m15_quality: str | None = None
    entry_status: str | None = None
    decision: str | None = None
    tp1_source: str | None = None
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
    decision_engine = (
        analysis.get("decision_engine")
        if isinstance(analysis.get("decision_engine"), dict)
        else {}
    )
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
        entry_zone_source=_optional_str(scenario_value.get("entry_zone_source")),
        m15_quality=_optional_str(scenario_value.get("m15_quality")),
        entry_status=_optional_str(scenario_value.get("entry_status")),
        decision=_optional_str(decision_engine.get("decision")),
        tp1_source=_optional_str(scenario_value.get("tp1_source")),
        scenario_source=scenario_source,
        research_only=research_only,
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


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
    reasons.extend(release_candidate_rejection_reasons(entry))
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
    if (
        entry.expected_effective_rr is not None
        and entry.expected_effective_rr < config.min_expected_rr
    ):
        reasons.append("FROZEN_EXPECTED_RR_BELOW_MIN")
    return not reasons, _unique(reasons)


def release_candidate_rejection_reasons(
    entry: CandidateLedgerEntry | dict[str, Any],
) -> list[str]:
    """Return reasons a ledger row cannot seed a frozen strategy config.

    A release candidate can be clean in either of two ways:

    * scan-ready: the live decision path already said READY_TO_TRADE and the
      selected scenario was a confirmed entry; or
    * simulated-fill-ready: the historical fill model produced a simulated
      trade from a clean, non-fallback scenario.

    The second path matters for validation replay.  A scan can legitimately
    see a clean SMC setup as ``watch_zone`` / ``WAITING_CONFIRMATION`` while
    the backtest execution model later confirms a fill inside the entry zone.
    In that case ``simulated_trade`` is the execution confirmation evidence,
    and scan-time caps such as M15/journal WATCH are diagnostics rather than
    hard optimizer exclusions.  M15 quality is still a release gate: loose or
    missing lower-timeframe confirmation is not allowed to seed a frozen config.
    """
    row = _ledger_dict(entry)
    reasons: list[str] = []
    has_simulated_trade = isinstance(row.get("simulated_trade"), dict)
    base_rejection_reason = str(row.get("base_rejection_reason") or "")
    scan_ready = (
        row.get("base_eligible") is True
        and str(row.get("entry_status") or "") == RELEASE_ENTRY_STATUS
        and str(row.get("decision") or "") == RELEASE_DECISION
    )
    simulated_fill_ready = (
        has_simulated_trade
        and (
            row.get("base_eligible") is True
            or base_rejection_reason in RELEASE_SCAN_READY_REJECTIONS
        )
    )

    if not scan_ready and not simulated_fill_ready:
        reasons.append(
            base_rejection_reason or "RELEASE_BASE_PIPELINE_REJECTED"
        )
    if row.get("research_only") is True:
        reasons.append("RELEASE_RESEARCH_ONLY_CANDIDATE")
    if row.get("setup_score") is None:
        reasons.append("RELEASE_SETUP_SCORE_MISSING")
    if not has_simulated_trade:
        reasons.append("RELEASE_SIMULATED_TRADE_MISSING")
    if optional_float(row.get("expected_effective_rr")) is None:
        reasons.append("RELEASE_EXPECTED_RR_MISSING")

    scenario_source = str(row.get("scenario_source") or "")
    if scenario_source in {"fallback", "synthetic_fallback"}:
        reasons.append("RELEASE_SCENARIO_SOURCE_NOT_CLEAN")

    entry_zone_source = str(row.get("entry_zone_source") or "")
    if entry_zone_source not in RELEASE_ENTRY_ZONE_SOURCES:
        reasons.append("RELEASE_ENTRY_ZONE_SOURCE_NOT_CLEAN")
    simulated_trade = (
        row.get("simulated_trade")
        if isinstance(row.get("simulated_trade"), dict)
        else {}
    )
    m15_quality = str(
        row.get("m15_quality")
        or simulated_trade.get("m15_quality")
        or ""
    )
    if m15_quality != RELEASE_M15_QUALITY:
        reasons.append("RELEASE_M15_QUALITY_NOT_STRICT")
    if (
        not simulated_fill_ready
        and str(row.get("entry_status") or "") != RELEASE_ENTRY_STATUS
    ):
        reasons.append("RELEASE_ENTRY_STATUS_NOT_CONFIRMED")
    if (
        not simulated_fill_ready
        and str(row.get("decision") or "") != RELEASE_DECISION
    ):
        reasons.append("RELEASE_DECISION_NOT_READY")
    tp1_source = str(row.get("tp1_source") or "")
    if not tp1_source or tp1_source == "none":
        reasons.append("RELEASE_TP1_MISSING")
    return _unique(reasons)


def optimize_frozen_strategy(
    entries: Iterable[CandidateLedgerEntry | dict[str, Any]],
    *,
    symbol: str,
    min_candidates: int = MIN_LEDGER_CANDIDATES,
) -> FrozenStrategyConfig | None:
    """Select one config using only simulated, explicit-score IS candidates."""

    eligible = release_optimizer_candidate_rows(entries, symbol=symbol)
    if len(eligible) < min_candidates:
        return None

    best: tuple[float, str, str, int, float] | None = None
    for bucket in _optimizer_threshold_buckets(
        eligible,
        min_candidates=min_candidates,
    ):
        if not bucket["passes_optimizer_thresholds"]:
            continue
        candidate = (
            float(bucket["composite_score"]),
            str(bucket["market_regime"]),
            str(bucket["side"]),
            int(bucket["min_setup_score"]),
            float(bucket["min_expected_rr"]),
        )
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


def release_optimizer_candidate_rows(
    entries: Iterable[CandidateLedgerEntry | dict[str, Any]],
    *,
    symbol: str,
) -> list[dict[str, Any]]:
    """Return the exact release-clean rows allowed to seed optimizer search."""

    rows = [_ledger_dict(entry) for entry in entries]
    return [
        row for row in rows
        if row.get("symbol") == symbol
        and not release_candidate_rejection_reasons(row)
    ]


def release_optimizer_diagnostics(
    entries: Iterable[CandidateLedgerEntry | dict[str, Any]],
    *,
    symbol: str,
    min_candidates: int = MIN_LEDGER_CANDIDATES,
) -> dict[str, Any]:
    """Explain which IS candidates reached the optimizer and why search failed."""

    rows = [_ledger_dict(entry) for entry in entries]
    symbol_rows = [row for row in rows if row.get("symbol") == symbol]
    eligible = [
        row for row in symbol_rows
        if not release_candidate_rejection_reasons(row)
    ]
    reason_counts: dict[str, int] = {}
    for row in symbol_rows:
        reasons = release_candidate_rejection_reasons(row) or ["<accepted>"]
        for reason in reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    buckets = list(
        _optimizer_threshold_buckets(
            eligible,
            min_candidates=min_candidates,
        )
    )
    passing_buckets = [
        bucket for bucket in buckets
        if bucket["passes_optimizer_thresholds"]
    ]
    best_bucket = (
        max(
            buckets,
            key=lambda bucket: (
                float(bucket["composite_score"]),
                str(bucket["market_regime"]),
                str(bucket["side"]),
                int(bucket["min_setup_score"]),
                float(bucket["min_expected_rr"]),
            ),
        )
        if buckets
        else None
    )
    return {
        "symbol": symbol,
        "input_count": len(rows),
        "symbol_candidate_count": len(symbol_rows),
        "release_candidate_count": len(eligible),
        "release_candidate_ids": [
            str(row.get("candidate_id") or "") for row in eligible
        ],
        "min_candidates": min_candidates,
        "score_thresholds": list(SCORE_THRESHOLDS),
        "rr_thresholds": list(RR_THRESHOLDS),
        "optimizer_thresholds": {
            "min_expectancy_r": MIN_OPTIMIZER_EXPECTANCY_R,
            "min_profit_factor": MIN_OPTIMIZER_PROFIT_FACTOR,
        },
        "rejection_reasons": dict(sorted(reason_counts.items())),
        "threshold_bucket_count": len(buckets),
        "passing_threshold_bucket_count": len(passing_buckets),
        "best_threshold_bucket": best_bucket,
    }


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


def _optimizer_threshold_buckets(
    eligible: list[dict[str, Any]],
    *,
    min_candidates: int,
) -> Iterable[dict[str, Any]]:
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
                    and optional_float(
                        row.get("expected_effective_rr")
                    ) is not None
                    and float(row.get("expected_effective_rr") or 0) >= min_rr
                ]
                if len(selected) < min_candidates:
                    continue
                results = [
                    float(
                        (row.get("simulated_trade") or {}).get(
                            "result_r",
                            0,
                        ) or 0
                    )
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
                yield {
                    "market_regime": regime,
                    "side": side,
                    "min_setup_score": min_score,
                    "min_expected_rr": min_rr,
                    "selected_count": len(selected),
                    "candidate_ids": [
                        str(row.get("candidate_id") or "")
                        for row in selected
                    ],
                    "total_r": round(sum(results), 6),
                    "expectancy_r": round(expectancy, 6),
                    "profit_factor": round(profit_factor, 6),
                    "gross_profit_r": round(gross_profit, 6),
                    "gross_loss_r": round(gross_loss, 6),
                    "composite_score": (
                        expectancy * 10
                        + profit_factor
                        + len(selected) * 0.01
                    ),
                    "passes_optimizer_thresholds": (
                        expectancy >= MIN_OPTIMIZER_EXPECTANCY_R
                        and profit_factor >= MIN_OPTIMIZER_PROFIT_FACTOR
                    ),
                }


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))
