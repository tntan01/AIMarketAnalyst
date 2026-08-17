"""Pure, target-only Scanner V4 MarketSafetyGate and volatility semantics.

This module is intentionally NOT wired into the executable scanner (Step 04 of
the Scanner V4 migration is target construction).  It is the single canonical
owner of five safety sub-gates: connectivity, data/candle freshness, spread,
news/event window, and volatility.  It evaluates a strict ``MarketSafetyContext``
against a versioned ``SafetyPolicy`` and returns a fail-closed
``MarketSafetyResult`` with exactly five ``GateCheck`` entries.

Fail-closed rules (do NOT infer optimistic defaults):
  * policy_version must equal ``scanner-safety-policy-v4``
  * a sub-gate whose policy is still OPEN (per-symbol spread threshold, candle
    freshness SLA, calibrated volatility band) returns ``UNKNOWN`` and does NOT
    PASS, because there is no evidence from which to PASS.
  * a sub-gate with missing, stale, or erroneous source data returns ``UNKNOWN``.
  * aggregate precedence is ``BLOCK > UNKNOWN > CAUTION > PASS``: UNKNOWN in any
    mandatory safety source blocks auto-entry (decision mapping lives downstream,
    Step 08; this step only produces the fail-closed status).
  * Safety never mutates TechnicalScore; a BLOCK here may coexist with a score of
    100, but auto-entry must not proceed.

Per-source timestamps and provenance are mandatory: a source marked ``valid``
must carry ``checked_at`` plus non-empty provenance before the gate may PASS on
it.  ``UNKNOWN`` uniformly covers missing / stale / fetch-error so each is
distinguishable from "valid source, no qualifying event" (the news no-event case
is a genuine PASS).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Any

from core.reason_codes import (
    SAFETY_DATA_FRESHNESS_UNKNOWN,
    SAFETY_DATA_STALE,
    SAFETY_MT5_NOT_READY,
    SAFETY_MT5_STATE_UNKNOWN,
    SAFETY_NEWS_HIGH_IMPACT_BLOCK,
    SAFETY_NEWS_HIGH_IMPACT_CAUTION,
    SAFETY_NEWS_SOURCE_UNAVAILABLE,
    SAFETY_SPREAD_ABNORMAL,
    SAFETY_SPREAD_THRESHOLD_UNSET,
    SAFETY_SPREAD_UNKNOWN,
    SAFETY_VOLATILITY_BAND_UNSET,
    SAFETY_VOLATILITY_EXTREME,
    SAFETY_VOLATILITY_UNKNOWN,
)
from core.scanner_v4_models import (
    BLOCK,
    CAUTION,
    PASS,
    UNKNOWN,
    SCANNER_V4_SAFETY_POLICY_VERSION,
    GateCheck,
    MarketSafetyResult,
    SAFETY_CHECK_NAMES,
)

__all__ = [
    "AVAILABILITY_ERROR",
    "AVAILABILITY_MISSING",
    "AVAILABILITY_STALE",
    "AVAILABILITY_VALID",
    "DEFAULT_MARKET_SAFETY_POLICY",
    "MANUAL_ORDER_POLICY_VERSION",
    "MarketSafetyContext",
    "MarketSafetyGate",
    "MarketSafetyGateError",
    "SPREAD_POLICY_VERSION",
    "SafetyPolicy",
    "VALID_AVAILABILITIES",
    "VOLATILITY_METRIC_ATR14",
    "VOLATILITY_REFERENCE_WINDOW_DAYS",
    "VOLATILITY_SEMANTICS_VERSION",
    "VOLATILITY_INTRADAY_REFERENCE",
    "VOLATILITY_STRUCTURAL_REFERENCE",
]


class MarketSafetyGateError(ValueError):
    """Fail-closed error raised on malformed safety context/policy input."""


AVAILABILITY_VALID = "valid"
AVAILABILITY_MISSING = "missing"
AVAILABILITY_STALE = "stale"
AVAILABILITY_ERROR = "error"
VALID_AVAILABILITIES = frozenset({
    AVAILABILITY_VALID,
    AVAILABILITY_MISSING,
    AVAILABILITY_STALE,
    AVAILABILITY_ERROR,
})

# High-impact event labels accepted by the calendar/event provider.  Mirrors the
# normalized values used by the news service (calendar_helpers.HIGH_IMPACT_VALUES).
HIGH_IMPACT_VALUES = frozenset({"high", "red", "cao"})

# Default news window (LOCKED in the architecture doc): 0-30m BLOCK,
# 30m-3h CAUTION; a valid source with no qualifying event is a genuine PASS.
DEFAULT_NEWS_BLOCK_MINUTES = 30
DEFAULT_NEWS_CAUTION_MINUTES = 180

# ---------------------------------------------------------------------------
# Locked policies (Step 04, evidence-based; see docs Mục 6.2)
# ---------------------------------------------------------------------------
# Volatility semantics: metric ATR(14); intraday reference H4; structural
# reference D1; reference window = 14-day average of daily ATR.  Evidence:
# core/technical_context.py builds atr_h4/atr_d1/atr_avg_14d exactly this way.
VOLATILITY_METRIC_ATR14 = "atr14"
VOLATILITY_INTRADAY_REFERENCE = "H4"
VOLATILITY_STRUCTURAL_REFERENCE = "D1"
VOLATILITY_REFERENCE_WINDOW_DAYS = 14
VOLATILITY_SEMANTICS_VERSION = "scanner-safety-volatility-atr14-v1"

# Spread policy shape (LOCKED): per-symbol threshold map, no global default.
# A symbol not present in the map -> UNKNOWN (never a fabricated global value).
SPREAD_POLICY_VERSION = "scanner-safety-spread-per-symbol-v1"

# Manual-order policy (LOCKED default): aggregate safety UNKNOWN blocks
# auto-entry; a manual order does NOT auto-bypass the fail-closed gate.
# Any human override is an explicit, logged decision owned by Release at
# cutover (Bước 12); the gate itself is deliberately override-free.
MANUAL_ORDER_POLICY_VERSION = "scanner-safety-manual-order-v1"


def _require_gate_status(value: str, path: str) -> None:
    if value not in {"PASS", "CAUTION", "BLOCK", "UNKNOWN"}:
        raise MarketSafetyGateError(
            f"{path}: unexpected gate status {value!r}; expected PASS|CAUTION|BLOCK|UNKNOWN"
        )


def _require_availability(value: str, path: str) -> None:
    if value not in VALID_AVAILABILITIES:
        raise MarketSafetyGateError(
            f"{path}: unexpected availability {value!r}; "
            f"expected one of {sorted(VALID_AVAILABILITIES)}"
        )


def _require_positive_float(value: float | int, path: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise MarketSafetyGateError(f"{path}: expected a numeric value")
    if not math.isfinite(float(value)):
        raise MarketSafetyGateError(f"{path}: expected a finite number")
    if float(value) <= 0:
        raise MarketSafetyGateError(f"{path}: expected a positive number")


def _require_positive_int(value: int, path: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise MarketSafetyGateError(f"{path}: expected an integer")
    if value <= 0:
        raise MarketSafetyGateError(f"{path}: expected a positive integer")


def _past_or_none(checked_at: datetime | None, now: datetime) -> bool:
    return checked_at is None or checked_at <= now


def _is_stale(checked_at: datetime | None, now: datetime, max_age_minutes: int | None) -> bool:
    if max_age_minutes is None:
        return False
    if checked_at is None:
        return False
    age = now - checked_at
    return age.total_seconds() > max_age_minutes * 60.0


def _source_usable(source: "BaseSafetySource", now: datetime, max_age_minutes: int | None) -> bool:
    """A sub-source is usable only when valid, timestamped, and fresh enough.

    Missing / stale / fetch-error are all unusable (fail-closed -> UNKNOWN).
    A source without a checked_at timestamp can never validate a PASS because the
    policy requires per-source timestamps.
    """
    if source.availability != AVAILABILITY_VALID:
        return False
    if source.checked_at is None:
        return False
    if _past_or_none(source.checked_at, now) is False:
        return False
    if _is_stale(source.checked_at, now, max_age_minutes):
        return False
    return True


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_event_time(event: Mapping[str, Any], path: str) -> datetime:
    try:
        value = event["time_utc"]
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        text = str(value)
        handle = datetime.fromisoformat(text)
        return handle if handle.tzinfo is not None else handle.replace(tzinfo=timezone.utc)
    except (KeyError, TypeError, ValueError) as exc:  # pragma: no cover - exercised indirectly
        raise MarketSafetyGateError(
            f"{path}.time_utc: unparsable event time {event.get('time_utc')!r}: {exc}"
        ) from exc


def _is_high_impact(event: Mapping[str, Any]) -> bool:
    return str(event.get("impact", "")).strip().lower() in HIGH_IMPACT_VALUES


def _spread_threshold_for(thresholds: Mapping[str, Any], symbol: str | None) -> Any | None:
    """Look up the per-symbol spread threshold, tolerant of symbol spelling variants.

    The policy map is keyed by owner-configured broker-style keys (e.g.
    ``"EURUSD"``, ``"XAUUSD"``).  Live sources can carry different spellings of
    the same instrument: the app display form (``"EUR/USD"``) or the
    cent-account broker form (``"EURUSDc"``).  Candidate keys are tried in
    order and the first hit wins:

    1. the symbol verbatim;
    2. alphanumeric-only + uppercase (``"EUR/USD"`` -> ``"EURUSD"``);
    3. (2) with a single trailing ``"C"`` removed (cent-account suffix:
       ``"EURUSDc"`` -> ``"EURUSDC"`` -> ``"EURUSD"``).

    No candidate matches -> ``None`` -> the gate fails closed with
    ``SAFETY_SPREAD_THRESHOLD_UNSET``.  Never invents a global default.
    """
    if not symbol:
        return None
    candidates = [symbol]
    normalized = "".join(char for char in symbol if char.isalnum()).upper()
    if normalized and normalized not in candidates:
        candidates.append(normalized)
    if normalized.endswith("C"):
        stripped = normalized[:-1]
        if stripped and stripped not in candidates:
            candidates.append(stripped)
    for key in candidates:
        if key in thresholds:
            return thresholds[key]
    return None


# ---------------------------------------------------------------------------
# Safety sub-source context carriers (strict, timestamped, provenance-tagged)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BaseSafetySource:
    availability: str
    source: str
    checked_at: datetime | None
    provenance: Mapping[str, Any]

    def _validate_base(self) -> None:
        _require_availability(self.availability, "safety_source.availability")
        if self.availability == AVAILABILITY_VALID:
            if self.checked_at is None:
                raise MarketSafetyGateError(
                    "safety_source.checked_at: valid source data requires a timestamp"
                )
            if not self.provenance:
                raise MarketSafetyGateError(
                    "safety_source.provenance: valid source data requires evidence provenance"
                )

    def __post_init__(self) -> None:
        self._validate_base()


@dataclass(frozen=True, slots=True)
class ConnectivitySource(BaseSafetySource):
    terminal_connected: bool | None
    broker_logged_in: bool | None

    def __post_init__(self) -> None:
        self._validate_base()
        if self.availability == AVAILABILITY_VALID and (
            self.terminal_connected is None or self.broker_logged_in is None
        ):
            raise MarketSafetyGateError(
                "connectivity: valid state requires terminal_connected and broker_logged_in"
            )


@dataclass(frozen=True, slots=True)
class DataFreshnessSource(BaseSafetySource):
    last_candle_time_utc: datetime | None
    intended_timeframe: str = "M15"
    # Optional feed-liveness reference: the last broker tick (tz-aware UTC).
    # Candle open times lag wall-clock by up to a full timeframe period, so a
    # present tick is the preferred age reference; the candle stays the VALID
    # baseline and the fallback when no tick exists (fail-closed).
    last_tick_time_utc: datetime | None = None

    def __post_init__(self) -> None:
        self._validate_base()
        if self.availability == AVAILABILITY_VALID and self.last_candle_time_utc is None:
            raise MarketSafetyGateError(
                "data_freshness: valid state requires last_candle_time_utc"
            )


@dataclass(frozen=True, slots=True)
class SpreadSource(BaseSafetySource):
    spread_points: float | None
    symbol: str

    def __post_init__(self) -> None:
        self._validate_base()
        if self.availability == AVAILABILITY_VALID and self.spread_points is None:
            raise MarketSafetyGateError("spread: valid state requires spread_points")


@dataclass(frozen=True, slots=True)
class NewsSource(BaseSafetySource):
    source_verified: bool
    events: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        self._validate_base()


@dataclass(frozen=True, slots=True)
class VolatilitySource(BaseSafetySource):
    volatility_ratio: float | None
    metric: str | None = None

    def __post_init__(self) -> None:
        self._validate_base()
        if self.availability == AVAILABILITY_VALID and self.volatility_ratio is None:
            raise MarketSafetyGateError(
                "volatility: valid state requires volatility_ratio"
            )


@dataclass(frozen=True, slots=True)
class MarketSafetyContext:
    symbol: str
    captured_at: datetime
    connectivity: ConnectivitySource
    data: DataFreshnessSource
    spread: SpreadSource
    news: NewsSource
    volatility: VolatilitySource


@dataclass(frozen=True, slots=True)
class SafetyPolicy:
    """Versioned thresholds.  OPEN sub-policies default to None/empty -> fail closed.

    - spread_threshold_by_symbol: per-symbol threshold (OPEN).  A symbol missing
      from the mapping returns UNKNOWN; there is no optimistic global default.
    - max_candle_age_minutes: candle freshness SLA (OPEN).  None -> data gate
      returns UNKNOWN because freshness cannot be judged.
    - volatility_calibrated / volatility_upper_ratio: band (OPEN until calibrated).
      volatility_calibrated False -> volatility gate returns UNKNOWN.
    - connectivity_max_age_minutes: how fresh a connectivity probe must be.  None
      means "no age bound", but connectivity still requires a timestamp.
    - volatility semantics are LOCKED (metric/timeframe/reference window) and
      carried here so the target contract is fully versioned.  Only the *band*
      (volatility_upper_ratio) needs calibration (Bước 09 Backtest/Calibration);
      until then volatility fails closed to UNKNOWN.
    - manual_order_bypass_fail_closed defaults False: no origin — including a
      manual order — bypasses the fail-closed gate by default.  The gate itself
      never reads this field; the decision layer may consult it only at cutover.
    """

    policy_version: str
    news_block_window_minutes: int = DEFAULT_NEWS_BLOCK_MINUTES
    news_caution_window_minutes: int = DEFAULT_NEWS_CAUTION_MINUTES
    connectivity_max_age_minutes: int | None = None
    max_candle_age_minutes: int | None = None
    spread_threshold_by_symbol: Mapping[str, int] = field(default_factory=dict)
    volatility_calibrated: bool = False
    volatility_upper_ratio: float | None = None
    volatility_metric: str = VOLATILITY_METRIC_ATR14
    volatility_intraday_reference: str = VOLATILITY_INTRADAY_REFERENCE
    volatility_structural_reference: str = VOLATILITY_STRUCTURAL_REFERENCE
    volatility_reference_window_days: int = VOLATILITY_REFERENCE_WINDOW_DAYS
    manual_order_bypass_fail_closed: bool = False

    def __post_init__(self) -> None:
        if self.policy_version != SCANNER_V4_SAFETY_POLICY_VERSION:
            raise MarketSafetyGateError(
                f"SafetyPolicy.policy_version expected "
                f"{SCANNER_V4_SAFETY_POLICY_VERSION!r}, got {self.policy_version!r}"
            )
        _require_positive_int(self.news_block_window_minutes, "news_block_window_minutes")
        _require_positive_int(self.news_caution_window_minutes, "news_caution_window_minutes")
        if self.news_caution_window_minutes <= self.news_block_window_minutes:
            raise MarketSafetyGateError(
                "news_caution_window_minutes must be greater than news_block_window_minutes"
            )
        if self.connectivity_max_age_minutes is not None:
            _require_positive_int(self.connectivity_max_age_minutes, "connectivity_max_age_minutes")
        if self.max_candle_age_minutes is not None:
            _require_positive_int(self.max_candle_age_minutes, "max_candle_age_minutes")
        if not isinstance(self.spread_threshold_by_symbol, Mapping):
            raise MarketSafetyGateError("spread_threshold_by_symbol: expected a mapping")
        for symbol, threshold in self.spread_threshold_by_symbol.items():
            try:
                _require_positive_int(threshold, f"spread_threshold_by_symbol[{symbol!r}]")
            except MarketSafetyGateError:
                raise
        if self.volatility_upper_ratio is not None:
            _require_positive_float(self.volatility_upper_ratio, "volatility_upper_ratio")
        if self.volatility_calibrated and self.volatility_upper_ratio is None:
            raise MarketSafetyGateError(
                "volatility calibrated requires volatility_upper_ratio"
            )
        if self.volatility_metric != VOLATILITY_METRIC_ATR14:
            raise MarketSafetyGateError(
                f"volatility_metric must be {VOLATILITY_METRIC_ATR14!r}"
            )
        if self.volatility_intraday_reference != VOLATILITY_INTRADAY_REFERENCE:
            raise MarketSafetyGateError(
                f"volatility_intraday_reference must be {VOLATILITY_INTRADAY_REFERENCE!r}"
            )
        if self.volatility_structural_reference != VOLATILITY_STRUCTURAL_REFERENCE:
            raise MarketSafetyGateError(
                f"volatility_structural_reference must be {VOLATILITY_STRUCTURAL_REFERENCE!r}"
            )
        _require_positive_int(
            self.volatility_reference_window_days,
            "volatility_reference_window_days",
        )
        if self.volatility_reference_window_days != VOLATILITY_REFERENCE_WINDOW_DAYS:
            raise MarketSafetyGateError(
                f"volatility_reference_window_days must be "
                f"{VOLATILITY_REFERENCE_WINDOW_DAYS} (14-day average evidence)"
            )


DEFAULT_MARKET_SAFETY_POLICY = SafetyPolicy(
    policy_version=SCANNER_V4_SAFETY_POLICY_VERSION,
)


class MarketSafetyGate:
    """Canonical owner of the five safety sub-gates (target-only, not wired)."""

    def evaluate(
        self,
        context: MarketSafetyContext,
        policy: SafetyPolicy | None = None,
        *,
        now: datetime | None = None,
    ) -> MarketSafetyResult:
        policy = policy if policy is not None else DEFAULT_MARKET_SAFETY_POLICY
        now = now if now is not None else _utc_now()
        if not isinstance(context, MarketSafetyContext):
            raise MarketSafetyGateError("evaluate requires a MarketSafetyContext")

        checks = (
            self._check_connectivity(context, policy, now),
            self._check_data_freshness(context, policy, now),
            self._check_spread(context, policy, now),
            self._check_news(context, policy, now),
            self._check_volatility(context, policy, now),
        )
        statuses = tuple(check.status for check in checks)
        block = BLOCK in statuses
        unknown = UNKNOWN in statuses
        caution = CAUTION in statuses
        if block:
            status: str = BLOCK
        elif unknown:
            status = UNKNOWN  # fail-closed: any missing/stale/error safety source blocks auto-entry
        elif caution:
            status = CAUTION
        else:
            status = PASS
        reasons: list[str] = []
        for check in checks:
            for reason in check.reason_codes:
                if reason not in reasons:
                    reasons.append(reason)
        return MarketSafetyResult(
            status=status,
            checks=checks,
            reason_codes=tuple(reasons),
            policy_version=policy.policy_version,
        )

    # --- sub-gates ---------------------------------------------------------

    def _check_connectivity(
        self, context: MarketSafetyContext, policy: SafetyPolicy, now: datetime
    ) -> GateCheck:
        source = context.connectivity
        if not _source_usable(source, now, policy.connectivity_max_age_minutes):
            return self._check(
                "connectivity",
                UNKNOWN,
                (SAFETY_MT5_STATE_UNKNOWN,),
                observed=None,
                threshold={"require_terminal_connected": True, "require_broker_logged_in": True},
                source=source.source,
                provenance=source.provenance,
                now=now,
            )
        if not source.terminal_connected or not source.broker_logged_in:
            return self._check(
                "connectivity",
                BLOCK,
                (SAFETY_MT5_NOT_READY,),
                observed={
                    "terminal_connected": bool(source.terminal_connected),
                    "broker_logged_in": bool(source.broker_logged_in),
                },
                threshold={"require_terminal_connected": True, "require_broker_logged_in": True},
                source=source.source,
                provenance=source.provenance,
                now=now,
            )
        return self._check(
            "connectivity",
            PASS,
            (),
            observed={
                "terminal_connected": True,
                "broker_logged_in": True,
            },
            threshold={"require_terminal_connected": True, "require_broker_logged_in": True},
            source=source.source,
            provenance=source.provenance,
            now=now,
        )

    def _check_data_freshness(
        self, context: MarketSafetyContext, policy: SafetyPolicy, now: datetime
    ) -> GateCheck:
        source = context.data
        sla = policy.max_candle_age_minutes
        # Freshness SLA is OPEN: with no SLA there is no basis to declare data fresh.
        if sla is None:
            return self._check(
                "data",
                UNKNOWN,
                (SAFETY_DATA_FRESHNESS_UNKNOWN,),
                observed={
                    "max_candle_age_minutes": None,
                    "last_candle_age_seconds": None,
                    "freshness_reference": None,
                },
                threshold={"max_candle_age_minutes": None},
                source=source.source,
                provenance=source.provenance,
                now=now,
            )
        if not _source_usable(source, now, policy.max_candle_age_minutes):
            return self._check(
                "data",
                UNKNOWN,
                (SAFETY_DATA_FRESHNESS_UNKNOWN,),
                observed={
                    "max_candle_age_minutes": sla,
                    "last_candle_age_seconds": None,
                    "freshness_reference": None,
                },
                threshold={"max_candle_age_minutes": sla},
                source=source.source,
                provenance=source.provenance,
                now=now,
            )
        last = source.last_candle_time_utc
        assert last is not None  # guaranteed by _source_usable for valid data
        # Age reference: the last broker tick when present (feed liveness), else
        # the newest candle.  Candle open times lag wall-clock by up to a full
        # timeframe period, so a candle-only reference cannot resolve a short SLA.
        tick = source.last_tick_time_utc
        if tick is not None and tick.tzinfo is not None:
            reference = tick
            freshness_reference = "tick"
        else:
            reference = last
            freshness_reference = "candle"
        age_seconds = (now - reference).total_seconds()
        if age_seconds > sla * 60.0:
            return self._check(
                "data",
                BLOCK,
                (SAFETY_DATA_STALE,),
                observed={
                    "max_candle_age_minutes": sla,
                    "last_candle_age_seconds": max(0.0, age_seconds),
                    "freshness_reference": freshness_reference,
                },
                threshold={"max_candle_age_minutes": sla},
                source=source.source,
                provenance=source.provenance,
                now=now,
            )
        return self._check(
            "data",
            PASS,
            (),
            observed={
                "max_candle_age_minutes": sla,
                "last_candle_age_seconds": max(0.0, age_seconds),
                "freshness_reference": freshness_reference,
            },
            threshold={"max_candle_age_minutes": sla},
            source=source.source,
            provenance=source.provenance,
            now=now,
        )

    def _check_spread(
        self, context: MarketSafetyContext, policy: SafetyPolicy, now: datetime
    ) -> GateCheck:
        source = context.spread
        symbol = source.symbol or context.symbol
        threshold = _spread_threshold_for(policy.spread_threshold_by_symbol, symbol)
        # Per-symbol spread policy is OPEN: a symbol with no threshold fails closed.
        if threshold is None:
            return self._check(
                "spread",
                UNKNOWN,
                (SAFETY_SPREAD_THRESHOLD_UNSET,),
                observed={"symbol": symbol, "spread_points": source.spread_points},
                threshold={"max_spread_points": None},
                source=source.source,
                provenance=source.provenance,
                now=now,
            )
        if not _source_usable(source, now, None):
            return self._check(
                "spread",
                UNKNOWN,
                (SAFETY_SPREAD_UNKNOWN,),
                observed={"symbol": symbol, "spread_points": None},
                threshold={"max_spread_points": threshold},
                source=source.source,
                provenance=source.provenance,
                now=now,
            )
        spread = source.spread_points
        assert spread is not None
        if spread > threshold:
            return self._check(
                "spread",
                BLOCK,
                (SAFETY_SPREAD_ABNORMAL,),
                observed={"symbol": symbol, "spread_points": spread},
                threshold={"max_spread_points": threshold},
                source=source.source,
                provenance=source.provenance,
                now=now,
            )
        return self._check(
            "spread",
            PASS,
            (),
            observed={"symbol": symbol, "spread_points": spread},
            threshold={"max_spread_points": threshold},
            source=source.source,
            provenance=source.provenance,
            now=now,
        )

    def _check_news(
        self, context: MarketSafetyContext, policy: SafetyPolicy, now: datetime
    ) -> GateCheck:
        source = context.news
        # A valid folder with no event is a genuine PASS, but an unavailable or
        # unverified source must NOT silently pass.
        if (
            source.availability != AVAILABILITY_VALID
            or not source.source_verified
            or not _source_usable(source, now, None)
        ):
            return self._check(
                "news",
                UNKNOWN,
                (SAFETY_NEWS_SOURCE_UNAVAILABLE,),
                observed={
                    "source_verified": bool(source.source_verified),
                    "nearest_high_impact_minutes": None,
                },
                threshold={
                    "block_window_minutes": policy.news_block_window_minutes,
                    "caution_window_minutes": policy.news_caution_window_minutes,
                },
                source=source.source,
                provenance=source.provenance,
                now=now,
            )
        within_caution = policy.news_caution_window_minutes
        nearest: float | None = None
        qualifying = 0
        for index, event in enumerate(source.events):
            if not _is_high_impact(event):
                continue
            event_time = _parse_event_time(
                event, f"safety_source.news.events[{index}]"
            )
            minutes = (event_time - now).total_seconds() / 60.0
            # Only events at or after "now" within the caution window matter.
            if 0.0 <= minutes <= within_caution:
                qualifying += 1
                if nearest is None or minutes < nearest:
                    nearest = minutes
        if nearest is not None and nearest <= policy.news_block_window_minutes:
            return self._check(
                "news",
                BLOCK,
                (SAFETY_NEWS_HIGH_IMPACT_BLOCK,),
                observed={"nearest_high_impact_minutes": nearest, "events_in_window": qualifying},
                threshold={
                    "block_window_minutes": policy.news_block_window_minutes,
                    "caution_window_minutes": policy.news_caution_window_minutes,
                },
                source=source.source,
                provenance=source.provenance,
                now=now,
            )
        if nearest is not None:
            return self._check(
                "news",
                CAUTION,
                (SAFETY_NEWS_HIGH_IMPACT_CAUTION,),
                observed={"nearest_high_impact_minutes": nearest, "events_in_window": qualifying},
                threshold={
                    "block_window_minutes": policy.news_block_window_minutes,
                    "caution_window_minutes": policy.news_caution_window_minutes,
                },
                source=source.source,
                provenance=source.provenance,
                now=now,
            )
        # Valid source, no high-impact event within the caution window.
        return self._check(
            "news",
            PASS,
            (),
            observed={"nearest_high_impact_minutes": None, "events_in_window": 0},
            threshold={
                "block_window_minutes": policy.news_block_window_minutes,
                "caution_window_minutes": policy.news_caution_window_minutes,
            },
            source=source.source,
            provenance=source.provenance,
            now=now,
        )

    def _check_volatility(
        self, context: MarketSafetyContext, policy: SafetyPolicy, now: datetime
    ) -> GateCheck:
        source = context.volatility
        # Volatility band is OPEN until calibrated: never self-assign CAUTION/PASS.
        if not policy.volatility_calibrated:
            return self._check(
                "volatility",
                UNKNOWN,
                (SAFETY_VOLATILITY_BAND_UNSET,),
                observed={"volatility_ratio": source.volatility_ratio, "upper_ratio": None},
                threshold={"upper_ratio": None, **self._volatility_threshold(policy)},
                source=source.source,
                provenance=source.provenance,
                now=now,
            )
        upper = policy.volatility_upper_ratio
        assert upper is not None
        if not _source_usable(source, now, None):
            return self._check(
                "volatility",
                UNKNOWN,
                (SAFETY_VOLATILITY_UNKNOWN,),
                observed={"volatility_ratio": None, "upper_ratio": upper},
                threshold={"upper_ratio": upper, **self._volatility_threshold(policy)},
                source=source.source,
                provenance=source.provenance,
                now=now,
            )
        ratio = source.volatility_ratio
        assert ratio is not None
        if ratio > upper:
            return self._check(
                "volatility",
                CAUTION,
                (SAFETY_VOLATILITY_EXTREME,),
                observed={"volatility_ratio": ratio, "upper_ratio": upper},
                threshold={"upper_ratio": upper, **self._volatility_threshold(policy)},
                source=source.source,
                provenance=source.provenance,
                now=now,
            )
        return self._check(
            "volatility",
            PASS,
            (),
            observed={"volatility_ratio": ratio, "upper_ratio": upper},
            threshold={"upper_ratio": upper, **self._volatility_threshold(policy)},
            source=source.source,
            provenance=source.provenance,
            now=now,
        )

    def _volatility_threshold(self, policy: SafetyPolicy) -> Mapping[str, Any]:
        """Locked ATR(14) semantics carried on every volatility threshold."""
        return {
            "metric": policy.volatility_metric,
            "intraday_reference": policy.volatility_intraday_reference,
            "structural_reference": policy.volatility_structural_reference,
            "reference_window_days": policy.volatility_reference_window_days,
            "semantics_version": VOLATILITY_SEMANTICS_VERSION,
        }

    # --- GateCheck factory -------------------------------------------------

    def _check(
        self,
        name: str,
        status: str,
        reason_codes: tuple[str, ...],
        *,
        observed: Mapping[str, Any] | None,
        threshold: Mapping[str, Any],
        source: str,
        provenance: Mapping[str, Any],
        now: datetime,
    ) -> GateCheck:
        _require_gate_status(status, f"gate_check.{name}.status")
        return GateCheck(
            name=name,
            status=status,  # type: ignore[arg-type]
            reason_codes=reason_codes,
            observed_value=observed,
            threshold=threshold,
            policy_version=SCANNER_V4_SAFETY_POLICY_VERSION,
            checked_at=now,
            source=source,
            provenance=provenance,
        )