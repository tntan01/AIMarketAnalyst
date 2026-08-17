"""Scanner V4 live producers (Bước 3 — build V4 input from live app data).

Production adapters that build the immutable V4 composition inputs
``SideSnapshot`` and ``MarketSafetyContext`` (plus the deterministic regime
resolver) directly from live app/MT5 state.  They sit on top of the retained
low-level producers:

* ``technical_context.build_technical_snapshot`` + ``indicators`` (retained);
* ``scanner_v4_features.derive_technical_raws`` (Bước 2 port of V3 raw
  formulas) and the retained canonical-SMC producer ``score_smc`` (owner
  decision §4-a);
* ``technical_context.detect_market_regime`` with the V3 regime-key mapping
  ported to the V4 vocabulary.

Governance: nothing here fabricates a value or a threshold.  Availability is
stamped from the ACTUAL live state (``None``/disconnected ⇒
``AVAILABILITY_MISSING``, never VALID); age limits are only enforced when an
explicit threshold is passed (the default ``SafetyPolicy`` has ``None`` limits,
so this producer does not invent one).  The ``MarketSafetyGate`` then maps any
non-VALID availability to a fail-closed UNKNOWN.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Mapping

from core.market_safety_gate import (
    AVAILABILITY_ERROR,
    AVAILABILITY_MISSING,
    AVAILABILITY_STALE,
    AVAILABILITY_VALID,
    VOLATILITY_METRIC_ATR14,
    ConnectivitySource,
    DataFreshnessSource,
    MarketSafetyContext,
    NewsSource,
    SpreadSource,
    VolatilitySource,
)
from core.scanner_v4_composition import ScenarioPlan, SideSnapshot
from core.smc_scoring_result import SmcScoringResult
from core.technical_context import atr_volatility_readings, detect_market_regime
from core.technical_signal_scorer import VALID_TECHNICAL_REGIMES

PRODUCER_VERSION = "scanner-v4-live-producer-v1"
PROVENANCE = {"captured_by": "scanner-v4-live-producer", "source": "mt5"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def compute_live_volatility_ratio(
    d1_candles: list[Any] | None, h4_candles: list[Any] | None
) -> float | None:
    """Live volatility ratio for the ``MarketSafetyGate`` (locked atr14 semantics).

    ``ratio = ATR(14) mới nhất trên H4 ÷ trung bình 14 ngày của ATR(14) trên D1``
    — the exact reference pair locked by ``market_safety_gate.VOLATILITY_*``
    (metric ``atr14``, intraday H4, structural D1, 14-day window).  Computed
    only from REAL candles via ``technical_context.atr_volatility_readings``;
    insufficient history or non-positive/non-finite readings return ``None``
    (fail-closed: the gate then reports UNKNOWN, never an invented ratio).
    """
    if not d1_candles or not h4_candles:
        return None
    readings = atr_volatility_readings(list(d1_candles), list(h4_candles))
    atr_h4 = readings.get("atr_h4")
    atr_avg_14d = readings.get("atr_avg_14d")
    if atr_h4 is None or atr_avg_14d is None:
        return None
    if atr_h4 <= 0 or atr_avg_14d <= 0:
        return None
    ratio = float(atr_h4) / float(atr_avg_14d)
    if not math.isfinite(ratio):
        return None
    return ratio


def resolve_technical_regime(
    technical: Mapping[str, Any], news_in_3h: bool
) -> str:
    """Map ``detect_market_regime``'s primary onto the V4 regime vocabulary.

    Ported verbatim from V3 ``signal_engine._resolve_regime_key`` (which is on
    the deletion list): primary 'volatile'→volatile, 'trend_up'→trending_up,
    'trend_down'→trending_down, 'range'→ranging, else unknown.
    """
    regime = detect_market_regime(dict(technical), news_in_3h)
    primary = str(regime.get("primary", "unknown"))
    secondary = regime.get("secondary", [])
    if isinstance(secondary, list) and "volatile" in secondary:
        return "volatile"
    if primary == "volatile":
        return "volatile"
    if primary == "trend_up":
        return "trending_up"
    if primary == "trend_down":
        return "trending_down"
    if primary == "range":
        return "ranging"
    return "unknown"


def build_side_snapshot(
    side: str,
    *,
    trend: int,
    momentum: int,
    location: int,
    evidence_score: int | None = None,
    evidence_source: str = "",
    execution_quality_score: int | None = None,
    execution_quality_source: str = "",
    scenario_plan: ScenarioPlan | None = None,
) -> SideSnapshot:
    """Build a V4 ``SideSnapshot`` from the derived raw values.

    Evidence/Execution are optional: ``None`` scores trigger the composition's
    documented neutral-50 fallback (never fabricated here).  A score without a
    source is rejected by ``SideSnapshot`` itself (source contract).
    """
    if side not in ("buy", "sell"):
        raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
    return SideSnapshot(
        technical_raws={
            "trend": int(trend),
            "momentum": int(momentum),
            "location": int(location),
        },
        evidence_score=evidence_score,
        evidence_source=evidence_source,
        execution_quality_score=execution_quality_score,
        execution_quality_source=execution_quality_source,
        scenario_plan=scenario_plan,
    )


def _mark_availability(
    present: bool,
    checked_at: datetime | None,
    now: datetime | None,
    max_age_minutes: int | None,
) -> str:
    """Stamp a source's availability from the live state.

    ``present is False`` ⇒ MISSING (fail-closed, never VALID).  An explicit
    ``max_age_minutes`` (>0) marks a too-old probe STALE; ``None`` (the default
    policy's own value) means the producer does NOT invent an age limit.
    """
    if not present or checked_at is None:
        return AVAILABILITY_MISSING
    if max_age_minutes is not None and max_age_minutes > 0 and now is not None:
        if (now - checked_at).total_seconds() > max_age_minutes * 60:
            return AVAILABILITY_STALE
    return AVAILABILITY_VALID


def build_live_market_safety_context(
    symbol: str,
    captured_at: datetime,
    *,
    terminal_connected: bool | None,
    broker_logged_in: bool | None,
    connectivity_checked_at: datetime | None,
    last_candle_time_utc: datetime | None,
    data_intended_timeframe: str = "M15",
    data_checked_at: datetime | None = None,
    last_tick_time_utc: datetime | None = None,
    spread_points: float | None,
    spread_checked_at: datetime | None = None,
    news_source_verified: bool,
    news_checked_at: datetime | None = None,
    news_events: tuple[Mapping[str, Any], ...] = (),
    volatility_ratio: float | None,
    volatility_checked_at: datetime | None = None,
    volatility_metric: str = VOLATILITY_METRIC_ATR14,
    connectivity_max_age_minutes: int | None = None,
    max_candle_age_minutes: int | None = None,
) -> MarketSafetyContext:
    """Build the V4 ``MarketSafetyContext`` from live MT5/app state.

    Availability is stamped from the ACTUAL live state, so the ``MarketSafetyGate``
    fails closed (UNKNOWN) on any missing/stale/unreliable source.  Age limits are
    only enforced when explicitly passed (the default ``SafetyPolicy`` has
    ``None`` limits — the producer never invents one).  ``last_tick_time_utc`` is
    the optional broker-tick reference the freshness gate prefers over the candle
    open time; ``None`` (tick unavailable) falls back to the candle (fail-closed).
    """
    now = captured_at if captured_at.tzinfo is not None else _utcnow()

    connect_ok = bool(terminal_connected) and bool(broker_logged_in)
    data_checked = data_checked_at if data_checked_at is not None else last_candle_time_utc

    connectivity = ConnectivitySource(
        availability=_mark_availability(
            connect_ok, connectivity_checked_at, now, connectivity_max_age_minutes
        ),
        source="mt5_connection_status",
        checked_at=connectivity_checked_at,
        provenance=PROVENANCE,
        terminal_connected=terminal_connected,
        broker_logged_in=broker_logged_in,
    )
    data = DataFreshnessSource(
        availability=_mark_availability(
            last_candle_time_utc is not None, data_checked, now, max_candle_age_minutes
        ),
        source="mt5_candles",
        checked_at=data_checked,
        provenance=PROVENANCE,
        last_candle_time_utc=last_candle_time_utc,
        intended_timeframe=data_intended_timeframe,
        last_tick_time_utc=last_tick_time_utc,
    )
    spread = SpreadSource(
        availability=_mark_availability(
            spread_points is not None, spread_checked_at, now, None
        ),
        source="mt5_tick",
        checked_at=spread_checked_at,
        provenance=PROVENANCE,
        spread_points=spread_points,
        symbol=symbol,
    )
    news = NewsSource(
        availability=_mark_availability(
            news_source_verified, news_checked_at, now, None
        ),
        source="news_service",
        checked_at=news_checked_at,
        provenance=PROVENANCE,
        source_verified=news_source_verified,
        events=tuple(news_events),
    )
    volatility = VolatilitySource(
        availability=_mark_availability(
            volatility_ratio is not None, volatility_checked_at, now, None
        ),
        source="technical_context",
        checked_at=volatility_checked_at,
        provenance=PROVENANCE,
        volatility_ratio=volatility_ratio,
        metric=volatility_metric,
    )
    return MarketSafetyContext(
        symbol=symbol,
        captured_at=captured_at,
        connectivity=connectivity,
        data=data,
        spread=spread,
        news=news,
        volatility=volatility,
    )


def derive_live_analysis(
    d1: list[Any],
    h4: list[Any],
    h1: list[Any],
    *,
    symbol: str,
    captured_at: datetime | None = None,
    news_in_3h: bool = False,
) -> dict[str, Any]:
    """Derive the full technical analysis layer + canonical SMC + regime.

    This is the production candle→analysis path: it builds the retained
    technical context, derives the V4 raws (Bước 2), produces the canonical SMC
    via the retained ``score_smc`` producer, and resolves the regime — ready for
    the caller to assemble a ``ScannerV4Snapshot`` in Bước 5.
    """
    from core.scanner_v4_features import (
        MIN_D1,
        MIN_H4,
        MIN_H1,
        TechnicalRawDerivationError,
        derive_technical_raws,
    )
    from core.smc_context import build_smc_context
    from core.smc_scorer import score_smc

    cap = captured_at if captured_at is not None else _utcnow()
    # Fail-closed FIRST (single source of truth, identical to the raws gate),
    # so insufficient history never reaches build_technical_snapshot's plain
    # ValueError and always raises the typed derivation error.
    if len(d1) < MIN_D1 or len(h4) < MIN_H4 or len(h1) < MIN_H1:
        raise TechnicalRawDerivationError(
            f"features_insufficient_data: need D1>={MIN_D1} H4>={MIN_H4} H1>={MIN_H1} "
            f"(got D1={len(d1)} H4={len(h4)} H1={len(h1)})"
        )
    technical = _build_technical(d1, h4, h1)
    canonical_smc: SmcScoringResult = score_smc(
        build_smc_context(d1, h4, h1, scan_interval_min=15, symbol=symbol),
        technical,
    )
    raws = derive_technical_raws(
        d1, h4, h1, symbol=symbol, captured_at=cap, canonical_smc=canonical_smc
    )
    regime = resolve_technical_regime(technical, news_in_3h)
    return {
        "symbol": symbol,
        "captured_at": cap,
        "technical": technical,
        "raws": raws,
        "canonical_smc": canonical_smc,
        "regime": regime,
    }


def _build_technical(d1: list[Any], h4: list[Any], h1: list[Any]):
    from core.technical_context import build_technical_snapshot

    return build_technical_snapshot(d1, h4, h1)


__all__ = [
    "PRODUCER_VERSION",
    "PROVENANCE",
    "resolve_technical_regime",
    "build_side_snapshot",
    "build_live_market_safety_context",
    "derive_live_analysis",
]