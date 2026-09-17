"""Scanner live producers (Bước 3 — build input from live app data).

Production adapters that build the immutable composition inputs
``SideSnapshot`` and ``MarketSafetyContext`` (plus the deterministic regime
resolver) directly from live app/MT5 state.  They sit on top of the retained
low-level producers:

* ``technical_context.build_technical_snapshot`` + ``indicators`` (retained);
* ``scanner_features.derive_technical_raws_with_location`` (Trend/Momentum
  feature producers plus the canonical Location engine) and the retained
  canonical-SMC producer ``score_smc`` (owner decision §4-a);
* ``technical_context.detect_market_regime`` with the legacy regime-key mapping
  ported to the Scanner vocabulary.

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
from pathlib import Path
from typing import Any, Mapping, Sequence

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
from core.location_engine import LocationResult
from core.scanner_composition import ScenarioPlan, SideSnapshot
from core.technical_context import atr_volatility_readings, detect_market_regime
from core.technical_signal_scorer import VALID_TECHNICAL_REGIMES

PRODUCER_VERSION = "scanner-live-producer"
PRODUCER_LEGACY_VERSION = "scanner-v4-live-producer-v1"
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
    """Map ``detect_market_regime``'s primary onto the Scanner regime vocabulary.

    Ported verbatim from legacy ``signal_engine._resolve_regime_key`` (which is on
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
    location_detail: LocationResult | None = None,
) -> SideSnapshot:
    """Build a ``SideSnapshot`` from the derived raw values.

    Evidence/Execution are optional: ``None`` scores trigger the composition's
    documented neutral-50 fallback (never fabricated here).  A score without a
    source is rejected by ``SideSnapshot`` itself (source contract).
    """
    if side not in ("buy", "sell"):
        raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
    if location_detail is not None:
        if type(location_detail) is not LocationResult:
            raise TypeError("location_detail must be a LocationResult or None")
        if location_detail.side != side:
            raise ValueError("location_detail.side must match side")
        if location_detail.raw != int(location):
            raise ValueError("location_detail.raw must match location")
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
        location_detail=location_detail,
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

    F-C-02: a timestamp that is not a timezone-aware instant cannot be aged, so
    it is treated as MISSING — a fail-closed verdict with a reason — instead of
    raising ``TypeError`` and taking the whole row down with it.  An aware
    timestamp carrying a non-UTC offset is a real instant and is aged normally.
    """

    if not present or checked_at is None:
        return AVAILABILITY_MISSING
    if not isinstance(checked_at, datetime):
        return AVAILABILITY_MISSING
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        return AVAILABILITY_MISSING
    if max_age_minutes is not None and max_age_minutes > 0 and now is not None:
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            return AVAILABILITY_MISSING
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
    """Build the ``MarketSafetyContext`` from live MT5/app state.

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
    m15_candles: list[Any] | None = None,
    m15_as_of: datetime | None = None,
    tick_size: float | None = None,
    tick_size_source: str | None = None,
    core_reason_codes: tuple[str, ...] = (),
    min_rr: float | None = None,
    external_status: str | None = None,
    external_reason_codes: Sequence[str] = (),
    context_cache_root: Path | None = None,
) -> dict[str, Any]:
    """Derive the full technical analysis layer + canonical SMC + regime.

    This is the production candle→analysis path.  It freezes ONE snapshot
    through the shared seam (task 101): the cutoff and the M15 window travel
    together with the symbol metadata, every timeframe is filtered to its
    closed candles before the context is built, and the canonical chain
    (evaluator → candidate order → coordinator/planner → final result) runs
    exactly once for that snapshot.  The returned ``canonical_smc`` is the
    final result carrying one selected setup per side, so Scanner, Analyze and
    replay read the same verdict for the same input.

    M15 is a REAL input, not an optional extra: a caller that omits the window
    gets a snapshot whose readiness stays ``WAITING_CONFIRMATION`` with
    ``M15_DATA_UNAVAILABLE`` instead of a side that silently never saw it.

    A missing/naive cutoff is never replaced by ``datetime.now()``: the seam
    reports the canonical cutoff reason and the side is ``data_unavailable``.
    """
    from core.scanner_features import (
        MIN_D1,
        MIN_H4,
        MIN_H1,
        TechnicalRawDerivationError,
        derive_technical_raws_with_location,
    )
    from core.smc_snapshot import build_smc_snapshot, evaluate_smc_snapshot

    # Fail-closed FIRST (single source of truth, identical to the raws gate),
    # so insufficient history never reaches build_technical_snapshot's plain
    # ValueError and always raises the typed derivation error.
    if len(d1) < MIN_D1 or len(h4) < MIN_H4 or len(h1) < MIN_H1:
        raise TechnicalRawDerivationError(
            f"features_insufficient_data: need D1>={MIN_D1} H4>={MIN_H4} H1>={MIN_H1} "
            f"(got D1={len(d1)} H4={len(h4)} H1={len(h1)})"
        )
    # Canonical CONTEXT cache (Lô B-Ctx / D-LB-01).  This is an EXPLICIT opt-in:
    # with no root the seam is not consulted at all.  F-BCTX-01 removed the only
    # production caller that passed one, because the live scan freezes a new
    # cutoff every scan and analyses each symbol once — no two real callers ever
    # share a key, so every miss would write a record nobody reads.  The seam
    # stays here for a caller that really repeats a frozen input (see
    # ``core.smc_context_cache``); production wiring is DEFERRED.
    #
    # Only the context is cached: ``evaluate_smc_snapshot`` below still runs
    # fresh, exactly once, and still produces the typed evaluation.
    context_builder = None
    if context_cache_root is not None:
        from core.smc_context_cache import caching_context_builder

        context_builder = caching_context_builder(
            root=Path(context_cache_root),
            extra_metadata={"tick_size_source": tick_size_source},
        )
    snapshot = build_smc_snapshot(
        {"D1": d1, "H4": h4, "H1": h1, "M15": m15_candles or ()},
        symbol=symbol,
        as_of=captured_at,
        m15_as_of=m15_as_of if m15_as_of is not None else captured_at,
        tick_size=tick_size,
        tick_size_source=tick_size_source,
        core_reason_codes=core_reason_codes,
        context_builder=context_builder,
    )
    evaluation = evaluate_smc_snapshot(
        snapshot,
        min_rr=min_rr,
        external_status=({"buy": external_status, "sell": external_status}
                         if external_status else None),
        external_reason_codes=(
            {"buy": external_reason_codes, "sell": external_reason_codes}
            if external_reason_codes
            else None
        ),
    )
    technical = snapshot.technical if isinstance(snapshot.technical, Mapping) else {}
    raws = derive_technical_raws_with_location(
        snapshot.candles.get("D1", ()),
        snapshot.candles.get("H4", ()),
        snapshot.candles.get("H1", ()),
        cutoff=snapshot.as_of,
        symbol=symbol,
        captured_at=snapshot.as_of,
        canonical_smc=evaluation.result,
        tick_size=snapshot.tick_size,
    )
    regime = resolve_technical_regime(dict(technical), news_in_3h)
    return {
        "symbol": symbol,
        "captured_at": snapshot.as_of,
        "technical": technical,
        "raws": raws,
        "canonical_smc": evaluation.result,
        "regime": regime,
        "smc_snapshot": snapshot,
        "smc_evaluation": evaluation,
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
