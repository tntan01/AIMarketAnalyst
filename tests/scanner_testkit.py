"""Scanner Bước 11 shared fixture helpers (target-only; NOT a pytest file).

This module is imported only by the Bước 11 verification-test files.  It builds
deterministic immutable ``ScannerSnapshot`` objects (and the underlying SMC /
safety / macro inputs) exactly the way Bước 07's canonical composition test
constructs them, so the integration / invariant / scenario / parity tests all
share one proven fixture builder.

Value discipline: everything here uses the *default* policies already stamped by
the Bước 04–08 modules (``SafetyPolicy`` with the locked version, the composition
default options, ``make_default_threshold_policy``).  The default numbers are the
single-owner defaults (40/35/5/2-1) — honest, not a PIT calibration; the tests
that need a certified decision policy use the module-supplied default policy
explicitly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from fractions import Fraction
from typing import Any

from core.final_score import FINAL_SCORE_NEUTRAL_FALLBACK_SOURCE
from core.macro_gate import MacroPolicy
from core.market_safety_gate import (
    AVAILABILITY_VALID,
    ConnectivitySource,
    DataFreshnessSource,
    MarketSafetyContext,
    NewsSource,
    SafetyPolicy,
    SpreadSource,
    VolatilitySource,
)
from core.scanner_composition import (
    ComposeOptions,
    ScannerSnapshot,
    SideSnapshot,
    ScenarioPlan,
    build_backtest_snapshot,
    build_live_snapshot,
    compose_scanner,
)
from core.scanner_v4_models import (
    BUY,
    SCANNER_MACRO_POLICY_VERSION,
    SCANNER_SAFETY_POLICY_VERSION,
    SELL,
)
from core.scanner_threshold_policy import make_default_threshold_policy
from core.smc_models import SMC_DOMAIN_VERSION
from core.smc_scoring_result import (
    SMC_SCORING_CONTRACT_VERSION,
    SmcScoringResult,
    SmcSideScoringResult,
)
from core.smc_versions import SMC_SCORER_VERSION

UTC = timezone.utc
NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)
CAPTURED = NOW
PROV = {"captured_by": "scanner-v4-b11-testkit", "feed": "mt5", "session": "b11"}


# ---------------------------------------------------------------------------
# SMC construction (mirrors the canonical SMC of the scoring projection)
# ---------------------------------------------------------------------------


def smc_components(subtotal: int) -> tuple[int, int, int, int]:
    remaining = subtotal
    structure = min(5, remaining)
    remaining -= structure
    zone = min(5, remaining)
    remaining -= zone
    ltf = min(3, remaining)
    remaining -= ltf
    technical = min(2, remaining)
    return structure, zone, ltf, technical


def smc_side(
    side: str,
    *,
    subtotal: int,
    penalty_points: int = 0,
    applied_cap: int | None = None,
    evidence_code: str = "CANONICAL_STRUCTURE_EVIDENCE",
) -> SmcSideScoringResult:
    structure, zone, ltf, technical = smc_components(subtotal)
    has_selected_zone = zone > 0
    setup_score = {1: 25, 2: 40, 3: 55, 4: 70, 5: 85}.get(zone)
    source_score = max(0, subtotal - penalty_points)
    if applied_cap is not None:
        source_score = min(source_score, applied_cap)
    zone_id = f"zone-{side}" if has_selected_zone else None
    zone_type = "demand_zone" if side == "buy" else "supply_zone"
    breakdown = {
        "side": side,
        "total": source_score,
        "structure_score": structure,
        "zone_score": zone,
        "ltf_confirmation_score": ltf,
        "technical_validation_score": technical,
        "subtotal": subtotal,
        "penalty_points": penalty_points,
        "applied_cap": applied_cap,
        "penalties": [evidence_code] if penalty_points else [],
        "caps": [evidence_code] if applied_cap is not None else [],
        "selected_zone_id": zone_id,
        "selected_zone_quality_score": 80 if has_selected_zone else None,
        "selected_zone_relevance_score": 70 if has_selected_zone else None,
        "selected_zone_setup_score": setup_score if has_selected_zone else None,
        "reason_codes": [evidence_code],
        "scoring_version": SMC_SCORER_VERSION,
        "domain_version": SMC_DOMAIN_VERSION,
    }
    zone_payload = (
        {
            "zone_id": zone_id,
            "direction": side,
            "timeframe": "H4",
            "family": "demand" if side == "buy" else "supply",
            "zone_type": zone_type,
            "low": 90.0 if side == "buy" else 105.0,
            "high": 95.0 if side == "buy" else 110.0,
            "level": 92.5 if side == "buy" else 107.5,
            "zone_quality_score": 80,
            "zone_relevance_score": 70,
            "zone_setup_score": setup_score,
            "liquidity_sweep_linked": False,
            "linked_sweep_id": None,
            "linked_sweep_distance_atr": None,
            "linked_sweep_time_delta": None,
            "source": "smc_selected",
            "scoring_version": SMC_SCORER_VERSION,
            "domain_version": SMC_DOMAIN_VERSION,
            "selection_reason_codes": ("H4_TIMEFRAME_PREFERRED",),
            "type": zone_type,
        }
        if has_selected_zone
        else None
    )
    return SmcSideScoringResult(
        score=source_score,
        breakdown=breakdown,
        selected_zone=zone_payload,
        selected_zone_id=zone_id,
        selected_zone_type=zone_type if has_selected_zone else None,
        selected_zone_timeframe="H4" if has_selected_zone else None,
        reason_codes=(evidence_code,),
        smc_reason=evidence_code,
        selected_zone_score=setup_score if has_selected_zone else None,
        selected_zone_quality_score=80 if has_selected_zone else None,
        selected_zone_relevance_score=70 if has_selected_zone else None,
        selected_zone_setup_score=setup_score if has_selected_zone else None,
    )


def canonical_smc(*, buy_subtotal: int = 12, sell_subtotal: int = 7) -> SmcScoringResult:
    return SmcScoringResult(
        scoring_version=SMC_SCORER_VERSION,
        contract_version=SMC_SCORING_CONTRACT_VERSION,
        sides={
            "buy": smc_side("buy", subtotal=buy_subtotal),
            "sell": smc_side("sell", subtotal=sell_subtotal),
        },
    )


# ---------------------------------------------------------------------------
# Safety context / policy / macro policy / options
# ---------------------------------------------------------------------------


def safety_context(
    *,
    captured_at: datetime = CAPTURED,
    spread_points: float = 20.0,
) -> MarketSafetyContext:
    return MarketSafetyContext(
        symbol="XAUUSD",
        captured_at=captured_at,
        connectivity=ConnectivitySource(
            availability=AVAILABILITY_VALID,
            source="mt5_connection_status",
            checked_at=captured_at,
            provenance=PROV,
            terminal_connected=True,
            broker_logged_in=True,
        ),
        data=DataFreshnessSource(
            availability=AVAILABILITY_VALID,
            source="mt5_candles",
            checked_at=captured_at,
            provenance=PROV,
            last_candle_time_utc=captured_at - timedelta(seconds=60),
            intended_timeframe="M15",
        ),
        spread=SpreadSource(
            availability=AVAILABILITY_VALID,
            source="mt5_tick",
            checked_at=captured_at,
            provenance=PROV,
            spread_points=spread_points,
            symbol="XAUUSD",
        ),
        news=NewsSource(
            availability=AVAILABILITY_VALID,
            source="news_service",
            checked_at=captured_at,
            provenance=PROV,
            source_verified=True,
            events=(),
        ),
        volatility=VolatilitySource(
            availability=AVAILABILITY_VALID,
            source="technical_context",
            checked_at=captured_at,
            provenance=PROV,
            volatility_ratio=1.0,
            metric="atr14_h1",
        ),
    )


def safety_policy(**overrides: Any) -> SafetyPolicy:
    base = {
        "policy_version": SCANNER_SAFETY_POLICY_VERSION,
        "max_candle_age_minutes": 5,
        "spread_threshold_by_symbol": {"XAUUSD": 50},
        "connectivity_max_age_minutes": 10,
        "volatility_calibrated": True,
        "volatility_upper_ratio": 1.5,
    }
    base.update(overrides)
    return SafetyPolicy(**base)


def macro_policy(**overrides: Any) -> MacroPolicy:
    base = {
        "policy_version": SCANNER_MACRO_POLICY_VERSION,
        "deadband_points": 3,
        "confidence_threshold": 0.0,
    }
    base.update(overrides)
    return MacroPolicy(**base)


def options(**overrides: Any) -> ComposeOptions:
    base = {
        "min_risk_reward": Fraction(2, 1),
        "technical_floor": 40,
        "setup_floor": 35,
        "portfolio_position_limit": 5,
        "portfolio_exposure_limit": 2.0,
        "journal_max_consecutive_losses": 3,
        "journal_drawdown_caution_ratio": 0.5,
    }
    base.update(overrides)
    return ComposeOptions(**base)


def side_snapshot(
    side: str,
    *,
    trend: int,
    momentum: int,
    location: int,
    evidence: int | None = 60,
    execution: int | None = 70,
    plan: bool = True,
) -> SideSnapshot:
    if side == "buy":
        plan_obj: ScenarioPlan | None = (
            ScenarioPlan("buy", 91.0, 90.0, 94.0, source="plan") if plan else None
        )
    else:
        plan_obj = (
            ScenarioPlan("sell", 108.0, 109.0, 105.0, source="plan") if plan else None
        )
    return SideSnapshot(
        technical_raws={"trend": trend, "momentum": momentum, "location": location},
        evidence_score=evidence,
        evidence_source=("evidence_feed" if evidence is not None else ""),
        execution_quality_score=execution,
        execution_quality_source=("exec_feed" if execution is not None else ""),
        scenario_plan=plan_obj,
    )


DEFAULT_STRONG = {"trend": 20, "momentum": 14, "location": 18}
DEFAULT_WEAK = {"trend": 8, "momentum": 5, "location": 6}


def build_snapshot(
    *,
    captured_at: datetime = CAPTURED,
    buy_side: SideSnapshot | None = None,
    sell_side: SideSnapshot | None = None,
    smc: SmcScoringResult | None = None,
    safety: MarketSafetyContext | None = None,
    macro_raw_buy: int | None = 20,
    macro_raw_sell: int | None = 14,
    macro_confidence: float | None = 0.8,
    account: Any = None,
    portfolio: Any = None,
    journal: Any = None,
    source: str = "live",
    symbol: str = "XAUUSD",
    regime: str = "trending_up",
) -> ScannerSnapshot:
    """Build a deterministic immutable snapshot (live or backtest adapter).

    Defaults mirror the strong-buy / weak-sell profile of the Bước 07 test
    (technical 76 vs 32) so downstream status expectations are stable.
    """
    from core.scanner_composition import AccountState, JournalState, PortfolioState

    buy = buy_side if buy_side is not None else side_snapshot(BUY, **DEFAULT_STRONG)
    sell = sell_side if sell_side is not None else side_snapshot(SELL, **DEFAULT_WEAK)
    builder = build_live_snapshot if source == "live" else build_backtest_snapshot
    if account is None:
        account = AccountState(free_margin=10000.0, required_margin=500.0)
    if portfolio is None:
        portfolio = PortfolioState(open_positions=2, exposure_ratio=0.8)
    if journal is None:
        journal = JournalState(consecutive_losses=1, recent_drawdown_ratio=0.2)
    return builder(
        symbol=symbol,
        captured_at=captured_at,
        regime=regime,
        canonical_smc=smc if smc is not None else canonical_smc(),
        buy=buy,
        sell=sell,
        safety_context=safety if safety is not None else safety_context(captured_at=captured_at),
        macro_raw_buy=macro_raw_buy,
        macro_raw_sell=macro_raw_sell,
        macro_confidence=macro_confidence,
        account=account,
        portfolio=portfolio,
        journal=journal,
    )


def compose(
    snapshot: ScannerSnapshot,
    *,
    now: datetime = NOW,
    safety: SafetyPolicy | None = None,
    macro: MacroPolicy | None = None,
    opts: ComposeOptions | None = None,
):
    from core.scanner_composition import compose_scanner

    if safety is None:
        safety = safety_policy()
    if macro is None:
        macro = macro_policy()
    if opts is None:
        opts = options()
    return compose_scanner(
        snapshot,
        now=now,
        safety_policy=safety,
        macro_policy=macro,
        options=opts,
    )


def run(source: str = "live", **snapshot_kwargs: Any):
    """Compose a default snapshot (live or backtest) using the default policies."""
    return compose(build_snapshot(source=source, **snapshot_kwargs))


DEFAULT_THRESHOLD_POLICY = make_default_threshold_policy()