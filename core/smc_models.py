"""Canonical immutable domain models for SMC scoring.

Phase 1 introduces typed identities without changing legacy score semantics.
Dictionaries remain at the public pipeline boundary for now, but every
enriched SMC zone can be losslessly adapted to these models.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from math import isfinite
from typing import Any, Sequence

from core.smc_sweep_linking import SMC_SWEEP_LINK_VERSION
from core.smc_versions import SMC_CONFLUENCE_VERSION, SMC_SCORER_VERSION


SMC_DOMAIN_VERSION = "smc-domain-v1"
SMC_SNAPSHOT_CONTRACT_VERSION = "smc-snapshot-v1"
VALID_SMC_TIMEFRAMES = frozenset({"D1", "H4", "H1", "M15"})
SMC_TIMEFRAME_INTERVAL_SECONDS = {
    "D1": 86_400,
    "H4": 14_400,
    "H1": 3_600,
    "M15": 900,
}
VALID_SMC_DATA_STATUSES = frozenset({"complete", "partial", "insufficient"})
VALID_TICK_SIZE_SOURCES = frozenset({
    "trade_tick_size",
    "broker_trade_tick_size",
    "point_fallback",
})
VALID_ZONE_DIRECTIONS = frozenset({"buy", "sell"})
VALID_ZONE_FAMILIES = frozenset({"ob", "fvg", "supply_demand"})
VALID_ZONE_LIFECYCLE_STATUSES = frozenset({
    "candidate",
    "confirmed",
    "usable",
    "watch",
    "invalid",
    "expired",
})
VALID_ZONE_VISIT_STATES = frozenset({
    "open",
    "completed_unreacted",
    "completed_reacted",
    "closed_by_invalidation",
})


def _zone_evidence_payload(zone: object) -> dict[str, Any] | None:
    """Normalize detector top-level measurements into canonical evidence."""

    if not isinstance(zone, dict):
        return None
    raw = zone.get("evidence")
    evidence = dict(raw) if isinstance(raw, dict) else {}
    for key in (
        "departure_measurement",
        "base_measurement",
        "gap_measurement",
        "middle_measurement",
        "session_continuity",
        "session_origin",
    ):
        if key in zone and key not in evidence:
            evidence[key] = zone[key]
    return evidence or None
VALID_SWING_KINDS = frozenset({"high", "low"})
VALID_STRUCTURE_EVENT_TYPES = frozenset({
    "BOS",
    "CHOCH_CANDIDATE",
    "CHOCH_CONFIRMED",
})
VALID_STRUCTURE_DIRECTIONS = frozenset({"bullish", "bearish"})
VALID_CONFLUENCE_DIRECTIONS = frozenset({
    "bullish",
    "bearish",
    "mixed",
    "unknown",
})


@dataclass(frozen=True, slots=True)
class SmcTimeframeSnapshot:
    """Validated provenance for one timeframe in an SMC snapshot.

    ``None`` ATR/timestamp values are intentional: they represent unavailable
    metadata and are never replaced by a current or cross-timeframe value.
    ``from_dict`` is strict about schema keys so malformed payloads fail closed
    instead of receiving fabricated defaults.
    """

    timeframe: str
    interval_seconds: int
    first_eligible_close_at: str | None
    last_eligible_close_at: str | None
    raw_count: int
    eligible_count: int
    cutoff_filtered: int
    session_coverage_status: str
    atr_period: int
    atr_reference: float | None = None
    atr_reference_time: str | None = None
    atr_reference_source: str | None = None
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        timeframe = str(self.timeframe or "").strip().upper()
        if timeframe not in VALID_SMC_TIMEFRAMES:
            raise ValueError(f"Invalid SMC timeframe: {self.timeframe}")
        object.__setattr__(self, "timeframe", timeframe)

        if self.interval_seconds <= 0:
            raise ValueError("SMC timeframe interval must be positive")
        if self.raw_count < 0 or self.eligible_count < 0:
            raise ValueError("SMC candle counts cannot be negative")
        if self.eligible_count > self.raw_count:
            raise ValueError("Eligible candle count cannot exceed raw count")
        if self.cutoff_filtered < 0 or self.cutoff_filtered > self.raw_count:
            raise ValueError("Invalid cutoff-filtered candle count")
        if self.atr_period <= 0:
            raise ValueError("SMC ATR period must be positive")
        if not str(self.session_coverage_status or "").strip():
            raise ValueError("SMC session coverage status is required")

        first = _validate_optional_utc_timestamp(
            self.first_eligible_close_at,
            field_name="first_eligible_close_at",
        )
        last = _validate_optional_utc_timestamp(
            self.last_eligible_close_at,
            field_name="last_eligible_close_at",
        )
        if self.eligible_count > 0 and (first is None or last is None):
            raise ValueError(
                "Eligible candles require first and last close timestamps"
            )
        if first is not None and last is not None and first > last:
            raise ValueError(
                "First eligible close cannot be later than last eligible close"
            )

        atr_reference = self.atr_reference
        if atr_reference is not None:
            if not isfinite(float(atr_reference)) or float(atr_reference) <= 0:
                raise ValueError("SMC ATR reference must be finite and positive")
            if self.atr_reference_time is None or self.atr_reference_source is None:
                raise ValueError(
                    "ATR reference requires time and source provenance"
                )
        elif self.atr_reference_time is not None or self.atr_reference_source is not None:
            raise ValueError(
                "ATR time/source cannot be supplied without an ATR reference"
            )
        _validate_optional_utc_timestamp(
            self.atr_reference_time,
            field_name="atr_reference_time",
        )
        object.__setattr__(self, "session_coverage_status", str(self.session_coverage_status).strip())
        object.__setattr__(
            self,
            "reason_codes",
            _tuple_of_text(self.reason_codes),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reason_codes"] = list(self.reason_codes)
        return payload

    @classmethod
    def from_dict(cls, value: object) -> "SmcTimeframeSnapshot":
        payload = _require_mapping(value, "timeframe snapshot")
        required = (
            "timeframe",
            "interval_seconds",
            "first_eligible_close_at",
            "last_eligible_close_at",
            "raw_count",
            "eligible_count",
            "cutoff_filtered",
            "session_coverage_status",
            "atr_period",
            "atr_reference",
            "atr_reference_time",
            "atr_reference_source",
            "reason_codes",
        )
        for key in required:
            _require_payload_field(payload, key, "timeframe snapshot")
        return cls(
            timeframe=payload["timeframe"],
            interval_seconds=_required_int(payload["interval_seconds"], "interval_seconds"),
            first_eligible_close_at=payload["first_eligible_close_at"],
            last_eligible_close_at=payload["last_eligible_close_at"],
            raw_count=_required_int(payload["raw_count"], "raw_count"),
            eligible_count=_required_int(payload["eligible_count"], "eligible_count"),
            cutoff_filtered=_required_int(payload["cutoff_filtered"], "cutoff_filtered"),
            session_coverage_status=payload["session_coverage_status"],
            atr_period=_required_int(payload["atr_period"], "atr_period"),
            atr_reference=_optional_float(payload["atr_reference"]),
            atr_reference_time=_optional_text(payload["atr_reference_time"]),
            atr_reference_source=_optional_text(payload["atr_reference_source"]),
            reason_codes=_required_text_sequence(
                payload["reason_codes"],
                "timeframe snapshot reason_codes",
            ),
        )


@dataclass(frozen=True, slots=True)
class SmcDataQualityState:
    """Overall SMC data-quality state with explicit missing coverage."""

    status: str
    reason_codes: tuple[str, ...] = ()
    missing_timeframes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        status = str(self.status or "").strip().lower()
        if status not in VALID_SMC_DATA_STATUSES:
            raise ValueError(f"Invalid SMC data status: {self.status}")
        missing = tuple(
            str(timeframe).strip().upper()
            for timeframe in self.missing_timeframes
            if str(timeframe).strip()
        )
        if any(timeframe not in VALID_SMC_TIMEFRAMES for timeframe in missing):
            raise ValueError("Invalid missing SMC timeframe")
        if len(set(missing)) != len(missing):
            raise ValueError("Duplicate missing SMC timeframe")
        if status == "insufficient" and not (missing or self.reason_codes):
            raise ValueError(
                "Insufficient SMC data requires a missing timeframe or reason"
            )
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "missing_timeframes", missing)
        object.__setattr__(self, "reason_codes", _tuple_of_text(self.reason_codes))

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "missing_timeframes": list(self.missing_timeframes),
        }

    @classmethod
    def from_dict(cls, value: object) -> "SmcDataQualityState":
        payload = _require_mapping(value, "SMC data quality")
        for key in ("status", "reason_codes", "missing_timeframes"):
            _require_payload_field(payload, key, "SMC data quality")
        return cls(
            status=payload["status"],
            reason_codes=_required_text_sequence(
                payload["reason_codes"],
                "SMC data quality reason_codes",
            ),
            missing_timeframes=_required_text_sequence(
                payload["missing_timeframes"],
                "SMC data quality missing_timeframes",
            ),
        )


@dataclass(frozen=True, slots=True)
class SmcSnapshot:
    """Immutable, validated SMC input snapshot.

    The model carries only captured metadata. Missing broker/tick/ATR data is
    represented by ``None`` plus explicit quality reasons; no default source,
    timestamp, timeframe record, or cross-timeframe ATR is synthesized.
    """

    symbol: str
    as_of: str
    timeframes: tuple[SmcTimeframeSnapshot, ...]
    data_quality: SmcDataQualityState
    observed_at: str | None = None
    broker_symbol: str | None = None
    tick_size: float | None = None
    point: float | None = None
    digits: int | None = None
    tick_size_source: str | None = None
    contract_version: str = SMC_SNAPSHOT_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not str(self.symbol or "").strip():
            raise ValueError("SMC snapshot symbol is required")
        as_of = _validate_utc_timestamp(self.as_of, "as_of")
        observed = _validate_optional_utc_timestamp(self.observed_at, "observed_at")
        if not isinstance(self.data_quality, SmcDataQualityState):
            raise ValueError("SMC snapshot data_quality must be typed")

        frames = tuple(self.timeframes)
        if any(not isinstance(frame, SmcTimeframeSnapshot) for frame in frames):
            raise ValueError("SMC snapshot timeframes must be typed")
        frame_names = tuple(frame.timeframe for frame in frames)
        if len(set(frame_names)) != len(frame_names):
            raise ValueError("Duplicate SMC timeframe snapshot")
        missing = set(self.data_quality.missing_timeframes)
        if missing.intersection(frame_names):
            raise ValueError("A timeframe cannot be both present and missing")
        if self.data_quality.status == "complete" and (
            set(frame_names) != set(VALID_SMC_TIMEFRAMES)
            or missing
        ):
            raise ValueError(
                "Complete SMC data requires all canonical timeframes"
            )
        if self.data_quality.status == "partial" and not (
            set(frame_names) or missing
        ):
            raise ValueError("Partial SMC data requires coverage evidence")

        for frame in frames:
            expected_interval = SMC_TIMEFRAME_INTERVAL_SECONDS[frame.timeframe]
            if frame.interval_seconds != expected_interval:
                raise ValueError(
                    f"{frame.timeframe} interval_seconds must be {expected_interval}"
                )
            last = _validate_optional_utc_timestamp(
                frame.last_eligible_close_at,
                field_name=f"{frame.timeframe}.last_eligible_close_at",
            )
            if last is not None and last > as_of:
                raise ValueError(
                    f"{frame.timeframe} eligible close is after snapshot as_of"
                )
            atr_time = _validate_optional_utc_timestamp(
                frame.atr_reference_time,
                field_name=f"{frame.timeframe}.atr_reference_time",
            )
            if atr_time is not None and atr_time > as_of:
                raise ValueError(
                    f"{frame.timeframe} ATR reference is after snapshot as_of"
                )
            if atr_time is not None and last is not None and atr_time > last:
                raise ValueError(
                    f"{frame.timeframe} ATR reference is after eligible close"
                )

        if self.tick_size is not None:
            if not isfinite(float(self.tick_size)) or float(self.tick_size) <= 0:
                raise ValueError("SMC tick_size must be finite and positive")
            if self.tick_size_source not in VALID_TICK_SIZE_SOURCES:
                raise ValueError("SMC tick_size requires valid provenance source")
        elif self.tick_size_source is not None:
            raise ValueError("tick_size_source requires a resolved tick_size")
        if self.point is not None and (
            not isfinite(float(self.point)) or float(self.point) <= 0
        ):
            raise ValueError("SMC point must be finite and positive")
        if self.digits is not None and self.digits < 0:
            raise ValueError("SMC digits cannot be negative")
        if self.tick_size_source == "point_fallback" and (
            self.point is None or self.tick_size is None
            or float(self.tick_size) != float(self.point)
        ):
            raise ValueError(
                "point_fallback requires tick_size equal to positive point"
            )

        object.__setattr__(self, "symbol", str(self.symbol).strip())
        object.__setattr__(self, "as_of", str(self.as_of).strip())
        if observed is not None:
            object.__setattr__(self, "observed_at", str(self.observed_at).strip())
        if self.broker_symbol is not None:
            broker_symbol = str(self.broker_symbol).strip()
            object.__setattr__(self, "broker_symbol", broker_symbol or None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "symbol": self.symbol,
            "as_of": self.as_of,
            "observed_at": self.observed_at,
            "broker_symbol": self.broker_symbol,
            "tick_size": self.tick_size,
            "point": self.point,
            "digits": self.digits,
            "tick_size_source": self.tick_size_source,
            "timeframes": [frame.to_dict() for frame in self.timeframes],
            "data_quality": self.data_quality.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: object) -> "SmcSnapshot":
        payload = _require_mapping(value, "SMC snapshot")
        for key in ("symbol", "as_of", "timeframes", "data_quality"):
            _require_payload_field(payload, key, "SMC snapshot")
        raw_timeframes = payload["timeframes"]
        if not isinstance(raw_timeframes, (list, tuple)):
            raise ValueError("SMC snapshot timeframes must be a list")
        return cls(
            contract_version=str(
                payload.get("contract_version", SMC_SNAPSHOT_CONTRACT_VERSION)
                or SMC_SNAPSHOT_CONTRACT_VERSION
            ),
            symbol=payload["symbol"],
            as_of=payload["as_of"],
            observed_at=payload.get("observed_at"),
            broker_symbol=payload.get("broker_symbol"),
            tick_size=_optional_float(payload.get("tick_size")),
            point=_optional_float(payload.get("point")),
            digits=_optional_int(payload.get("digits")),
            tick_size_source=_optional_text(payload.get("tick_size_source")),
            timeframes=tuple(
                SmcTimeframeSnapshot.from_dict(item)
                for item in raw_timeframes
            ),
            data_quality=SmcDataQualityState.from_dict(payload["data_quality"]),
        )


def validate_smc_snapshot(value: object) -> bool:
    """Return whether ``value`` is a typed, validated SMC snapshot."""

    return isinstance(value, SmcSnapshot)


def build_swing_id(
    *,
    symbol: object,
    timeframe: object,
    kind: object,
    pivot_time: object,
) -> str:
    """Build a stable swing identity from source coordinates, never an index."""

    normalized_timeframe = str(timeframe or "").strip().upper()
    if normalized_timeframe not in VALID_SMC_TIMEFRAMES:
        raise ValueError(f"Invalid SMC timeframe: {timeframe}")
    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind not in VALID_SWING_KINDS:
        raise ValueError(f"Invalid SMC swing kind: {kind}")
    pivot = _validate_utc_timestamp(pivot_time, "pivot_time")
    parts = (
        _normalize_symbol(symbol),
        normalized_timeframe,
        normalized_kind,
        pivot.isoformat(),
    )
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"smcs-{digest[:20]}"


@dataclass(frozen=True, slots=True)
class SmcSwing:
    """One causal swing; only confirmed swings are usable for structure."""

    swing_id: str
    symbol: str
    timeframe: str
    kind: str
    level: float
    pivot_time: str
    confirmed_at: str | None = None
    pivot_index: int | None = None
    provisional: bool = False
    pivot_width: int | None = None
    scope: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.swing_id, str) or not self.swing_id.strip():
            raise ValueError("SMC swing_id must be a non-empty string")
        symbol = str(self.symbol or "").strip()
        if not symbol:
            raise ValueError("SMC swing symbol is required")
        timeframe = str(self.timeframe or "").strip().upper()
        if timeframe not in VALID_SMC_TIMEFRAMES:
            raise ValueError(f"Invalid SMC timeframe: {self.timeframe}")
        kind = str(self.kind or "").strip().lower()
        if kind not in VALID_SWING_KINDS:
            raise ValueError(f"Invalid SMC swing kind: {self.kind}")
        try:
            level = float(self.level)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("SMC swing level must be finite and positive") from None
        if not isfinite(level) or level <= 0:
            raise ValueError("SMC swing level must be finite and positive")
        pivot = _validate_utc_timestamp(self.pivot_time, "pivot_time")
        confirmed = _validate_optional_utc_timestamp(
            self.confirmed_at,
            "confirmed_at",
        )
        if confirmed is not None and confirmed < pivot:
            raise ValueError("SMC swing confirmed_at cannot precede pivot_time")
        if not isinstance(self.provisional, bool):
            raise ValueError("SMC swing provisional must be a boolean")
        if self.pivot_width is not None:
            if isinstance(self.pivot_width, bool) or not isinstance(self.pivot_width, int):
                raise ValueError("SMC swing pivot_width must be an integer")
            if self.pivot_width <= 0:
                raise ValueError("SMC swing pivot_width must be positive")
        scope = None if self.scope is None else str(self.scope).strip().lower()
        if scope is not None and not scope:
            scope = None
        if self.pivot_index is not None:
            if isinstance(self.pivot_index, bool) or not isinstance(self.pivot_index, int):
                raise ValueError("SMC swing pivot_index must be an integer")
            if self.pivot_index < 0:
                raise ValueError("SMC swing pivot_index cannot be negative")

        object.__setattr__(self, "swing_id", self.swing_id.strip())
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "timeframe", timeframe)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "pivot_time", pivot.isoformat())
        object.__setattr__(
            self,
            "confirmed_at",
            confirmed.isoformat() if confirmed is not None else None,
        )
        object.__setattr__(self, "scope", scope)

    @property
    def usable(self) -> bool:
        """A pivot is not a structure level until right-side confirmation exists."""

        return self.confirmed_at is not None and not self.provisional

    @property
    def id(self) -> str:
        """Compatibility alias for consumers that call the identity ``id``."""

        return self.swing_id

    @property
    def stable_id(self) -> str:
        return build_swing_id(
            symbol=self.symbol,
            timeframe=self.timeframe,
            kind=self.kind,
            pivot_time=self.pivot_time,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        # Keep the detector's canonical usability gate explicit.  Consumers
        # must not need to infer `confirmed=True` from a non-null timestamp.
        payload["confirmed"] = self.confirmed_at is not None
        payload["usable"] = self.usable
        return payload

    @classmethod
    def from_dict(cls, value: object) -> "SmcSwing":
        payload = _require_mapping(value, "SMC swing")
        for key in (
            "swing_id",
            "symbol",
            "timeframe",
            "kind",
            "level",
            "pivot_time",
            "confirmed_at",
        ):
            _require_payload_field(payload, key, "SMC swing")
        return cls(
            swing_id=payload["swing_id"],
            symbol=payload["symbol"],
            timeframe=payload["timeframe"],
            kind=payload["kind"],
            level=float(payload["level"]),
            pivot_time=payload["pivot_time"],
            confirmed_at=payload["confirmed_at"],
            pivot_index=_optional_int(payload.get("pivot_index")),
            provisional=payload.get("provisional", False),
            pivot_width=_optional_int(payload.get("pivot_width")),
            scope=payload.get("scope"),
        )


@dataclass(frozen=True, slots=True)
class SmcStructureEvent:
    """Validated BOS/CHoCH event with causal source and lifecycle timestamps."""

    event_id: str
    event_type: str
    direction: str
    source_level: float
    occurred_at: str
    broken_level_id: str
    source_swing_id: str | None = None
    protected_swing_id: str | None = None
    confirmed_at: str | None = None
    expires_at: str | None = None
    invalidated_at: str | None = None
    snapshot_id: str = ""
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise ValueError("SMC structure event_id must be a non-empty string")
        event_type = str(self.event_type or "").strip().upper()
        if event_type not in VALID_STRUCTURE_EVENT_TYPES:
            raise ValueError(f"Invalid SMC structure event type: {self.event_type}")
        direction = str(self.direction or "").strip().lower()
        if direction not in VALID_STRUCTURE_DIRECTIONS:
            raise ValueError(f"Invalid SMC structure direction: {self.direction}")
        try:
            source_level = float(self.source_level)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("SMC structure source_level must be finite and positive") from None
        if not isfinite(source_level) or source_level <= 0:
            raise ValueError("SMC structure source_level must be finite and positive")

        occurred = _validate_utc_timestamp(self.occurred_at, "occurred_at")
        confirmed = _validate_optional_utc_timestamp(
            self.confirmed_at,
            "confirmed_at",
        )
        expires = _validate_optional_utc_timestamp(self.expires_at, "expires_at")
        invalidated = _validate_optional_utc_timestamp(
            self.invalidated_at,
            "invalidated_at",
        )
        if confirmed is not None and confirmed < occurred:
            raise ValueError("SMC structure confirmed_at cannot precede occurred_at")
        if expires is not None and expires < occurred:
            raise ValueError("SMC structure expires_at cannot precede occurred_at")
        if invalidated is not None and invalidated < occurred:
            raise ValueError("SMC structure invalidated_at cannot precede occurred_at")
        if event_type == "BOS" and confirmed is None:
            raise ValueError("BOS requires confirmed_at")
        if event_type == "CHOCH_CANDIDATE" and confirmed is not None:
            raise ValueError("CHOCH_CANDIDATE cannot have confirmed_at")
        if event_type == "CHOCH_CONFIRMED" and confirmed is None:
            raise ValueError("CHOCH_CONFIRMED requires confirmed_at")

        broken_level_id = _required_reference(self.broken_level_id, "broken_level_id")
        source_swing_id = _optional_reference(self.source_swing_id)
        protected_swing_id = _optional_reference(self.protected_swing_id)
        if source_swing_id is None and protected_swing_id is None:
            raise ValueError(
                "SMC structure event requires source_swing_id or protected_swing_id"
            )
        snapshot_id = _required_reference(self.snapshot_id, "snapshot_id")

        object.__setattr__(self, "event_id", self.event_id.strip())
        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "source_level", source_level)
        object.__setattr__(self, "occurred_at", occurred.isoformat())
        object.__setattr__(self, "broken_level_id", broken_level_id)
        object.__setattr__(self, "source_swing_id", source_swing_id)
        object.__setattr__(self, "protected_swing_id", protected_swing_id)
        object.__setattr__(
            self,
            "confirmed_at",
            confirmed.isoformat() if confirmed is not None else None,
        )
        object.__setattr__(
            self,
            "expires_at",
            expires.isoformat() if expires is not None else None,
        )
        object.__setattr__(
            self,
            "invalidated_at",
            invalidated.isoformat() if invalidated is not None else None,
        )
        object.__setattr__(self, "snapshot_id", snapshot_id)
        object.__setattr__(self, "reason_codes", _tuple_of_text(self.reason_codes))

    @property
    def level(self) -> float:
        return self.source_level

    @property
    def status(self) -> str:
        if self.invalidated_at is not None:
            return "invalidated"
        if self.event_type == "CHOCH_CANDIDATE":
            return "candidate"
        return "confirmed"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reason_codes"] = list(self.reason_codes)
        payload["level"] = self.source_level
        payload["status"] = self.status
        return payload

    @classmethod
    def from_dict(cls, value: object) -> "SmcStructureEvent":
        payload = _require_mapping(value, "SMC structure event")
        required = (
            "event_id",
            "event_type",
            "direction",
            "source_level",
            "occurred_at",
            "broken_level_id",
            "source_swing_id",
            "protected_swing_id",
            "confirmed_at",
            "expires_at",
            "invalidated_at",
            "snapshot_id",
            "reason_codes",
        )
        for key in required:
            _require_payload_field(payload, key, "SMC structure event")
        return cls(
            event_id=payload["event_id"],
            event_type=payload["event_type"],
            direction=payload["direction"],
            source_level=float(payload["source_level"]),
            occurred_at=payload["occurred_at"],
            broken_level_id=payload["broken_level_id"],
            source_swing_id=payload["source_swing_id"],
            protected_swing_id=payload["protected_swing_id"],
            confirmed_at=payload["confirmed_at"],
            expires_at=payload["expires_at"],
            invalidated_at=payload["invalidated_at"],
            snapshot_id=payload["snapshot_id"],
            reason_codes=_required_text_sequence(
                payload["reason_codes"],
                "SMC structure event reason_codes",
            ),
        )


def build_zone_id(
    *,
    symbol: object,
    timeframe: object,
    family: object,
    direction: object,
    origin_time: object,
    low: object,
    high: object,
) -> str:
    """Build a stable content identity for one detected SMC zone."""

    parts = (
        _normalize_symbol(symbol),
        str(timeframe or "UNKNOWN").strip().upper() or "UNKNOWN",
        str(family or "unknown").strip().lower() or "unknown",
        _normalize_direction(direction),
        str(origin_time or "").strip(),
        _canonical_number(low),
        _canonical_number(high),
    )
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"smcz-{digest[:20]}"


def build_setup_id(
    *,
    symbol: object,
    timeframe: object,
    direction: object,
    departure_source: object,
    anchor_timeframe: object = "",
) -> str:
    """Build a stable identity for child zones from one departure lineage."""

    parts = (
        _normalize_symbol(symbol),
        str(timeframe or "UNKNOWN").strip().upper() or "UNKNOWN",
        _normalize_direction(direction),
        str(anchor_timeframe or timeframe or "UNKNOWN").strip().upper()
        or "UNKNOWN",
        str(departure_source or "").strip(),
    )
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"smcs-{digest[:20]}"


@dataclass(frozen=True, slots=True)
class ZoneVisit:
    visit_id: str
    entered_at: str | None
    exited_at: str | None
    start_index: int | None
    end_index: int | None
    max_penetration_ratio: float | None = None
    zone_id: str = ""
    reacted_at: str | None = None
    visit_state: str = ""
    bars_spent_inside: int = 0

    def __post_init__(self) -> None:
        visit_id = str(self.visit_id or "").strip()
        if not visit_id:
            raise ValueError("SMC visit_id is required")
        zone_id = str(self.zone_id or "").strip()
        if not zone_id and ":visit-" in visit_id:
            zone_id = visit_id.split(":visit-", 1)[0]
        entered_at = _validate_optional_utc_timestamp(
            self.entered_at,
            field_name="entered_at",
        )
        exited_at = _validate_optional_utc_timestamp(
            self.exited_at,
            field_name="exited_at",
        )
        reacted_at = _validate_optional_utc_timestamp(
            self.reacted_at,
            field_name="reacted_at",
        )
        if exited_at is not None and entered_at is not None and exited_at < entered_at:
            raise ValueError("SMC visit exited_at cannot precede entered_at")
        if reacted_at is not None and exited_at is None:
            raise ValueError("SMC visit reacted_at requires exited_at")
        if reacted_at is not None and exited_at is not None and reacted_at < exited_at:
            raise ValueError("SMC visit reacted_at cannot precede exited_at")
        state = str(self.visit_state or "").strip().lower()
        if not state:
            state = (
                "open" if exited_at is None
                else "completed_reacted" if reacted_at is not None
                else "completed_unreacted"
            )
        if state not in VALID_ZONE_VISIT_STATES:
            raise ValueError(f"Invalid SMC visit state: {self.visit_state}")
        if state == "open" and (exited_at is not None or reacted_at is not None):
            raise ValueError("Open SMC visit cannot have exited_at/reacted_at")
        if state in {"completed_unreacted", "closed_by_invalidation"} and exited_at is None:
            raise ValueError("Completed SMC visit requires exited_at")
        if state == "completed_unreacted" and reacted_at is not None:
            raise ValueError("Unreacted SMC visit cannot have reacted_at")
        if state == "completed_reacted" and reacted_at is None:
            raise ValueError("Reacted SMC visit requires reacted_at")
        if isinstance(self.bars_spent_inside, bool) or not isinstance(
            self.bars_spent_inside,
            int,
        ):
            raise ValueError("SMC visit bars_spent_inside must be an integer")
        bars_spent_inside = self.bars_spent_inside
        if bars_spent_inside < 0:
            raise ValueError("SMC visit bars_spent_inside must be non-negative")
        if self.max_penetration_ratio is not None:
            penetration = float(self.max_penetration_ratio)
            if not isfinite(penetration) or not 0 <= penetration <= 1:
                raise ValueError("SMC visit penetration must be within [0, 1]")
            object.__setattr__(self, "max_penetration_ratio", penetration)
        object.__setattr__(self, "visit_id", visit_id)
        object.__setattr__(self, "zone_id", zone_id)
        object.__setattr__(self, "entered_at", entered_at.isoformat() if entered_at else None)
        object.__setattr__(self, "exited_at", exited_at.isoformat() if exited_at else None)
        object.__setattr__(self, "reacted_at", reacted_at.isoformat() if reacted_at else None)
        object.__setattr__(self, "visit_state", state)
        object.__setattr__(self, "bars_spent_inside", bars_spent_inside)

    @property
    def state(self) -> str:
        """Compatibility alias for callers using the shorter state name."""

        return self.visit_state

    @property
    def status(self) -> str:
        """Compatibility alias for status-oriented lifecycle consumers."""

        return self.visit_state

    @property
    def dwell_bars(self) -> int:
        """Number of closed overlapping candles in this continuous visit."""

        return self.bars_spent_inside

    @classmethod
    def build_id(cls, zone_id: object, ordinal: object) -> str:
        zone = str(zone_id or "").strip()
        if not zone:
            raise ValueError("SMC visit zone_id is required")
        if isinstance(ordinal, bool):
            raise ValueError("SMC visit ordinal must be positive")
        try:
            number = int(ordinal)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("SMC visit ordinal must be positive") from None
        if number < 1:
            raise ValueError("SMC visit ordinal must be positive")
        return f"{zone}:visit-{number}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ZoneVisit":
        payload = value if isinstance(value, dict) else {}
        return cls(
            visit_id=str(payload.get("visit_id", "") or ""),
            entered_at=_optional_text(payload.get("entered_at")),
            exited_at=_optional_text(payload.get("exited_at")),
            start_index=_optional_int(payload.get("start_index")),
            end_index=_optional_int(payload.get("end_index")),
            max_penetration_ratio=_optional_float(
                payload.get("max_penetration_ratio")
            ),
            zone_id=str(payload.get("zone_id", "") or ""),
            reacted_at=_optional_text(payload.get("reacted_at")),
            visit_state=str(
                payload.get(
                    "visit_state",
                    payload.get("state", payload.get("status", "")),
                ) or ""
            ),
            bars_spent_inside=_int(payload.get("bars_spent_inside", 0), 0),
        )


@dataclass(frozen=True, slots=True)
class SmcZone:
    zone_id: str
    symbol: str
    timeframe: str
    family: str
    direction: str
    zone_type: str
    low: float
    high: float
    origin_index: int
    origin_time: str
    departure_end_index: int | None
    created_at: str
    invalidated_at: str | None
    invalidation_index: int | None
    first_retest_index: int | None
    first_retest_time: str | None
    independent_retest_count: int
    bars_spent_inside: int
    mitigation_ratio: float | None
    freshness_bars: int
    age_bars: int
    age_minutes: int | None
    lifecycle_mitigated: bool
    stale: bool
    broken: bool
    liquidity_sweep_linked: bool
    linked_sweep_id: str | None
    linked_sweep_kind: str | None
    linked_sweep_level: float | None
    linked_sweep_time: str | None
    linked_sweep_index: int | None
    linked_sweep_distance_atr: float | None
    linked_sweep_time_delta: int | None
    sweep_link_version: str
    zone_quality_score: int
    zone_relevance_score: int | None
    zone_setup_score: int
    scoring_version: str = ""
    domain_version: str = SMC_DOMAIN_VERSION
    visits: tuple[ZoneVisit, ...] = ()
    # Task 41 canonical zone contract.  The legacy fields above remain in
    # place so existing readers can continue to consume the model.
    setup_id: str | None = None
    original_low: float | None = None
    original_high: float | None = None
    refined_low: float | None = None
    refined_high: float | None = None
    remaining_low: float | None = None
    remaining_high: float | None = None
    formation_start: str | None = None
    formation_end: str | None = None
    departure_end: str | None = None
    departure_source_id: str | None = None
    departure_source_time: str | None = None
    confirmation_event_id: str | None = None
    confirmed_at: str | None = None
    available_at: str | None = None
    expired_at: str | None = None
    lifecycle_status: str = "candidate"
    # A3-007 data-quality gate: why a metadata-dependent rule could not be computed. This is
    # never a lifecycle status, so it travels beside `lifecycle_status`, not inside it.
    metadata_state: str = "available"
    metadata_reason: str | None = None
    tick_size_source: str | None = None
    atr_source: str | None = None
    evidence: dict[str, Any] | None = None
    reason_codes: tuple[str, ...] = ()
    fill_status: str = ""
    fill_ratio: float | None = None
    # A3-007/A-D04 projection: whether the zone may still be used as active evidence. Canonical
    # terminal state forces it False; it is never True while `broken`.
    usable: bool = True

    def __post_init__(self) -> None:
        if self.direction not in VALID_ZONE_DIRECTIONS:
            raise ValueError(f"Invalid SMC zone direction: {self.direction}")
        if self.high < self.low:
            raise ValueError("SMC zone high must be greater than or equal to low")
        inferred_direction = _explicit_direction_from_type(
            self.zone_type,
            self.family,
        )
        if inferred_direction and inferred_direction != self.direction:
            raise ValueError(
                "SMC zone direction conflicts with zone type/family"
            )
        original_low = self.low if self.original_low is None else self.original_low
        original_high = self.high if self.original_high is None else self.original_high
        if not isfinite(float(original_low)) or not isfinite(float(original_high)):
            raise ValueError("SMC zone original bounds must be finite")
        if original_high <= original_low:
            raise ValueError("SMC zone original bounds must have positive width")
        if self.refined_low is not None or self.refined_high is not None:
            if self.refined_low is None or self.refined_high is None:
                raise ValueError("Refined bounds require both low and high")
            if not original_low <= self.refined_low < self.refined_high <= original_high:
                raise ValueError("Refined bounds must be inside original bounds")
        if self.remaining_low is not None or self.remaining_high is not None:
            if self.remaining_low is None or self.remaining_high is None:
                raise ValueError("Remaining bounds require both low and high")
            allow_filled_zero_width = (
                str(self.family or "").strip().lower() == "fvg"
                and str(self.fill_status or "").strip().lower() == "filled"
            )
            if not original_low <= self.remaining_low <= self.remaining_high <= original_high:
                raise ValueError("Remaining bounds must be inside original bounds")
            if self.remaining_low == self.remaining_high and not allow_filled_zero_width:
                raise ValueError("Remaining bounds must have positive width")
        status = str(self.lifecycle_status or "candidate").strip().lower()
        if status not in VALID_ZONE_LIFECYCLE_STATUSES:
            raise ValueError(f"Invalid SMC zone lifecycle status: {self.lifecycle_status}")
        fill_status = str(self.fill_status or "").strip().lower()
        if fill_status not in {"", "unfilled", "partially_filled", "filled"}:
            raise ValueError(f"Invalid SMC FVG fill status: {self.fill_status}")
        if fill_status and str(self.family or "").strip().lower() != "fvg":
            raise ValueError("FVG fill status requires an FVG family")
        if self.fill_ratio is not None:
            fill_ratio = float(self.fill_ratio)
            if not isfinite(fill_ratio) or not 0 <= fill_ratio <= 1:
                raise ValueError("SMC FVG fill ratio must be within [0, 1]")
            object.__setattr__(self, "fill_ratio", fill_ratio)
        if self.available_at is not None and self.confirmed_at is not None:
            confirmed = _validate_optional_utc_timestamp(
                self.confirmed_at,
                field_name="confirmed_at",
            )
            available = _validate_optional_utc_timestamp(
                self.available_at,
                field_name="available_at",
            )
            if confirmed is not None and available is not None and available < confirmed:
                raise ValueError("SMC zone available_at cannot precede confirmed_at")
        object.__setattr__(self, "original_low", float(original_low))
        object.__setattr__(self, "original_high", float(original_high))
        object.__setattr__(self, "lifecycle_status", status)
        object.__setattr__(self, "reason_codes", _tuple_of_text(self.reason_codes))
        object.__setattr__(self, "fill_status", fill_status)
        # Canonical terminal is authoritative over the legacy flags (A-D04). An invalid zone is
        # broken and unusable whatever the incoming booleans said, and a broken zone can never
        # be usable — no payload may end up both broken and usable.
        if status == "invalid":
            object.__setattr__(self, "broken", True)
            object.__setattr__(self, "usable", False)
        elif self.broken:
            object.__setattr__(self, "usable", False)

    @property
    def original_bounds(self) -> dict[str, float]:
        """Protective/invalidation bounds that never change on retest."""

        return {"low": self.original_low, "high": self.original_high}

    @property
    def refined_bounds(self) -> dict[str, float] | None:
        if self.refined_low is None or self.refined_high is None:
            return None
        return {"low": self.refined_low, "high": self.refined_high}

    @property
    def remaining_bounds(self) -> dict[str, float] | None:
        if self.remaining_low is None or self.remaining_high is None:
            return None
        return {"low": self.remaining_low, "high": self.remaining_high}

    def to_dict(self, *, include_compatibility: bool = True) -> dict[str, Any]:
        payload = asdict(self)
        payload["visits"] = [visit.to_dict() for visit in self.visits]
        payload["type"] = self.zone_type
        payload["index"] = self.origin_index
        payload["time"] = self.origin_time
        payload["lifecycle_stale"] = self.stale
        payload["lifecycle_broken"] = self.broken
        payload["original_bounds"] = self.original_bounds
        payload["refined_bounds"] = self.refined_bounds
        payload["remaining_bounds"] = self.remaining_bounds
        payload["reason_codes"] = list(self.reason_codes)
        if include_compatibility:
            payload["zone_score"] = self.zone_setup_score
            payload["test_count"] = self.independent_retest_count
            payload["mitigated"] = self.lifecycle_mitigated
            payload["stale"] = self.stale
            payload["broken"] = self.broken
            payload["liquidity_sweep"] = self.liquidity_sweep_linked
        return payload

    @classmethod
    def from_dict(
        cls,
        value: dict[str, Any],
        *,
        symbol: object = "",
        timeframe: object = "",
        family: object = "",
        direction: object = "",
    ) -> "SmcZone":
        payload = value if isinstance(value, dict) else {}
        zone_type = str(
            payload.get("zone_type", payload.get("type", "smc_zone"))
            or "smc_zone"
        )
        resolved_family = (
            str(payload.get("family", family) or "").strip().lower()
            or _family_from_type(zone_type)
        )
        resolved_direction = _normalize_direction(
            payload.get("direction", direction)
            or _direction_from_type(zone_type, resolved_family)
        )
        low = _float(payload.get("low"), 0.0)
        high = _float(payload.get("high"), low)
        if high < low:
            low, high = high, low
        origin_index = _int(
            payload.get("origin_index", payload.get("index", -1)),
            -1,
        )
        origin_time = str(
            payload.get("origin_time", payload.get("time", "")) or ""
        )
        original_payload = payload.get("original_bounds")
        original_low = _float(
            payload.get(
                "original_low",
                original_payload.get("low") if isinstance(original_payload, dict) else low,
            ),
            low,
        )
        original_high = _float(
            payload.get(
                "original_high",
                original_payload.get("high") if isinstance(original_payload, dict) else high,
            ),
            high,
        )
        if original_high < original_low:
            original_low, original_high = original_high, original_low
        resolved_symbol = _normalize_symbol(
            payload.get("symbol", symbol)
        )
        resolved_timeframe = str(
            payload.get("timeframe", timeframe) or "UNKNOWN"
        ).strip().upper()
        quality = _score(
            payload.get(
                "zone_quality_score",
                payload.get("zone_score", 0),
            )
        )
        setup = _score(
            payload.get(
                "zone_setup_score",
                payload.get("zone_score", quality),
            )
        )
        relevance = _optional_score(payload.get("zone_relevance_score"))
        raw_visits = payload.get("visits", [])
        visits = tuple(
            ZoneVisit.from_dict(item)
            for item in raw_visits
            if isinstance(item, dict)
        ) if isinstance(raw_visits, list) else ()
        zone_id = str(payload.get("zone_id", "") or "").strip()
        if not zone_id:
            zone_id = build_zone_id(
                symbol=resolved_symbol,
                timeframe=resolved_timeframe,
                family=resolved_family,
                direction=resolved_direction,
                origin_time=origin_time,
                low=original_low,
                high=original_high,
            )
        refined_payload = payload.get("refined_bounds")
        remaining_payload = payload.get("remaining_bounds")
        raw_reasons = payload.get("reason_codes", [])
        raw_evidence = payload.get("evidence")
        # Detector seams emit typed measurements at the top level, while the
        # model contract stores child-specific audit data under ``evidence``.
        # Adapt once at the boundary so no ATR/formation provenance is lost.
        evidence = dict(raw_evidence) if isinstance(raw_evidence, dict) else {}
        for evidence_key in (
            "departure_measurement",
            "base_measurement",
            "gap_measurement",
            "middle_measurement",
            "session_continuity",
            "session_origin",
        ):
            if evidence_key in payload and evidence_key not in evidence:
                evidence[evidence_key] = payload[evidence_key]
        departure_end = _optional_text(payload.get("departure_end"))
        confirmation_event_id = _optional_text(payload.get("confirmation_event_id"))
        setup_id = _optional_text(payload.get("setup_id"))
        if setup_id is None:
            setup_id = build_setup_id(
                symbol=resolved_symbol,
                timeframe=resolved_timeframe,
                direction=resolved_direction,
                departure_source=(
                    confirmation_event_id
                    or departure_end
                    or origin_time
                ),
            )
        return cls(
            zone_id=zone_id,
            symbol=resolved_symbol,
            timeframe=resolved_timeframe,
            family=resolved_family,
            direction=resolved_direction,
            zone_type=zone_type,
            low=low,
            high=high,
            origin_index=origin_index,
            origin_time=origin_time,
            departure_end_index=_optional_int(
                payload.get("departure_end_index")
            ),
            created_at=str(payload.get("created_at", origin_time) or ""),
            invalidated_at=_optional_text(payload.get("invalidated_at")),
            invalidation_index=_optional_int(
                payload.get("invalidation_index")
            ),
            first_retest_index=_optional_int(
                payload.get("first_retest_index")
            ),
            first_retest_time=_optional_text(
                payload.get("first_retest_time")
            ),
            independent_retest_count=max(
                0,
                _int(
                    payload.get(
                        "independent_retest_count",
                        payload.get("test_count", 0),
                    ),
                    0,
                ),
            ),
            bars_spent_inside=max(
                0,
                _int(payload.get("bars_spent_inside", 0), 0),
            ),
            mitigation_ratio=_optional_float(
                payload.get("mitigation_ratio")
            ),
            freshness_bars=max(
                0,
                _int(payload.get("freshness_bars", 0), 0),
            ),
            age_bars=max(
                0,
                _int(
                    payload.get(
                        "age_bars",
                        payload.get("freshness_bars", 0),
                    ),
                    0,
                ),
            ),
            age_minutes=_optional_int(payload.get("age_minutes")),
            lifecycle_mitigated=bool(
                payload.get(
                    "lifecycle_mitigated",
                    payload.get(
                        "mitigated",
                        payload.get("test_count", 0),
                    ),
                )
            ),
            stale=bool(
                payload.get(
                    "lifecycle_stale",
                    payload.get("stale", False),
                )
            ),
            broken=bool(
                payload.get(
                    "lifecycle_broken",
                    payload.get("broken", False),
                )
            ),
            liquidity_sweep_linked=bool(
                payload.get(
                    "liquidity_sweep_linked",
                    payload.get("linked_sweep_id"),
                )
            ),
            linked_sweep_id=_optional_text(
                payload.get("linked_sweep_id")
            ),
            linked_sweep_kind=_optional_text(
                payload.get("linked_sweep_kind")
            ),
            linked_sweep_level=_optional_float(
                payload.get("linked_sweep_level")
            ),
            linked_sweep_time=_optional_text(
                payload.get("linked_sweep_time")
            ),
            linked_sweep_index=_optional_int(
                payload.get("linked_sweep_index")
            ),
            linked_sweep_distance_atr=_optional_float(
                payload.get("linked_sweep_distance_atr")
            ),
            linked_sweep_time_delta=_optional_int(
                payload.get("linked_sweep_time_delta")
            ),
            sweep_link_version=str(
                payload.get(
                    "sweep_link_version",
                    SMC_SWEEP_LINK_VERSION,
                )
                or SMC_SWEEP_LINK_VERSION
            ),
            zone_quality_score=quality,
            zone_relevance_score=relevance,
            zone_setup_score=setup,
            scoring_version=str(
                payload.get("scoring_version", "") or ""
            ),
            domain_version=str(
                payload.get("domain_version", SMC_DOMAIN_VERSION)
                or SMC_DOMAIN_VERSION
            ),
            visits=visits,
            setup_id=setup_id,
            original_low=original_low,
            original_high=original_high,
            refined_low=(
                _optional_float(
                    payload.get(
                        "refined_low",
                        refined_payload.get("low")
                        if isinstance(refined_payload, dict) else None,
                    )
                )
            ),
            refined_high=(
                _optional_float(
                    payload.get(
                        "refined_high",
                        refined_payload.get("high")
                        if isinstance(refined_payload, dict) else None,
                    )
                )
            ),
            remaining_low=(
                _optional_float(
                    payload.get(
                        "remaining_low",
                        remaining_payload.get("low")
                        if isinstance(remaining_payload, dict) else None,
                    )
                )
            ),
            remaining_high=(
                _optional_float(
                    payload.get(
                        "remaining_high",
                        remaining_payload.get("high")
                        if isinstance(remaining_payload, dict) else None,
                    )
                )
            ),
            formation_start=_optional_text(payload.get("formation_start")),
            formation_end=_optional_text(payload.get("formation_end")),
            departure_end=departure_end,
            departure_source_id=_optional_text(payload.get("departure_source_id")),
            departure_source_time=_optional_text(payload.get("departure_source_time")),
            confirmation_event_id=confirmation_event_id,
            confirmed_at=_optional_text(payload.get("confirmed_at")),
            available_at=_optional_text(payload.get("available_at")),
            expired_at=_optional_text(payload.get("expired_at")),
            lifecycle_status=str(
                payload.get("lifecycle_status", "candidate") or "candidate"
            ),
            metadata_state=str(payload.get("metadata_state", "available") or "available"),
            metadata_reason=_optional_text(payload.get("metadata_reason")),
            tick_size_source=_optional_text(payload.get("tick_size_source")),
            atr_source=_optional_text(payload.get("atr_source")),
            evidence=evidence or None,
            reason_codes=(
                _required_text_sequence(raw_reasons, "SMC zone reason_codes")
                if isinstance(raw_reasons, list) else ()
            ),
            fill_status=str(payload.get("fill_status", "") or ""),
            fill_ratio=_optional_float(payload.get("fill_ratio")),
            usable=bool(payload.get("usable", True)),
        )


@dataclass(frozen=True, slots=True)
class SmcSetupChild:
    """A setup child retaining its own family, bounds and evidence."""

    zone_id: str
    family: str
    direction: str
    original_low: float
    original_high: float
    evidence: dict[str, Any] | None = None
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        zone_id = str(self.zone_id or "").strip()
        if not zone_id:
            raise ValueError("SMC setup child zone_id is required")
        direction = _normalize_direction(self.direction)
        if not isfinite(float(self.original_low)) or not isfinite(float(self.original_high)):
            raise ValueError("SMC setup child original bounds must be finite")
        if self.original_high <= self.original_low:
            raise ValueError("SMC setup child original bounds must have positive width")
        object.__setattr__(self, "zone_id", zone_id)
        object.__setattr__(self, "family", str(self.family or "unknown").strip().lower())
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "original_low", float(self.original_low))
        object.__setattr__(self, "original_high", float(self.original_high))
        object.__setattr__(self, "reason_codes", _tuple_of_text(self.reason_codes))

    @property
    def original_bounds(self) -> dict[str, float]:
        return {"low": self.original_low, "high": self.original_high}

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["original_bounds"] = self.original_bounds
        payload["reason_codes"] = list(self.reason_codes)
        return payload

    @classmethod
    def from_dict(cls, value: object) -> "SmcSetupChild":
        payload = _require_mapping(value, "SMC setup child")
        bounds = payload.get("original_bounds")
        return cls(
            zone_id=payload.get("zone_id", ""),
            family=payload.get("family", "unknown"),
            direction=payload.get("direction", "unknown"),
            original_low=payload.get(
                "original_low",
                bounds.get("low") if isinstance(bounds, dict) else 0,
            ),
            original_high=payload.get(
                "original_high",
                bounds.get("high") if isinstance(bounds, dict) else 0,
            ),
            evidence=payload.get("evidence") if isinstance(payload.get("evidence"), dict) else None,
            reason_codes=_required_text_sequence(
                payload.get("reason_codes", []),
                "SMC setup child reason_codes",
            ),
        )


@dataclass(frozen=True, slots=True)
class SmcSetup:
    """Immutable grouping of child zones sharing one departure lineage."""

    setup_id: str
    symbol: str
    timeframe: str
    direction: str
    departure_source: str
    child_zone_ids: tuple[str, ...] = ()
    status: str = "candidate"
    available_at: str | None = None
    reason_codes: tuple[str, ...] = ()
    children: tuple[SmcSetupChild, ...] = ()

    def __post_init__(self) -> None:
        setup_id = str(self.setup_id or "").strip()
        if not setup_id:
            raise ValueError("SMC setup_id is required")
        direction = _normalize_direction(self.direction)
        if direction not in VALID_ZONE_DIRECTIONS:
            raise ValueError(f"Invalid SMC setup direction: {self.direction}")
        status = str(self.status or "candidate").strip().lower()
        if status not in VALID_ZONE_LIFECYCLE_STATUSES:
            raise ValueError(f"Invalid SMC setup status: {self.status}")
        child_ids = tuple(
            str(zone_id).strip()
            for zone_id in self.child_zone_ids
            if str(zone_id).strip()
        )
        if len(set(child_ids)) != len(child_ids):
            raise ValueError("SMC setup child_zone_ids must be unique")
        children = tuple(
            child if isinstance(child, SmcSetupChild)
            else SmcSetupChild.from_dict(child)
            for child in self.children
        )
        child_ids_from_children = tuple(child.zone_id for child in children)
        if child_ids and child_ids_from_children and child_ids != child_ids_from_children:
            raise ValueError("SMC setup child IDs do not match children")
        if not child_ids and child_ids_from_children:
            child_ids = child_ids_from_children
        if len(set(child_ids_from_children)) != len(child_ids_from_children):
            raise ValueError("SMC setup children must have unique zone IDs")
        object.__setattr__(self, "setup_id", setup_id)
        object.__setattr__(self, "symbol", _normalize_symbol(self.symbol))
        object.__setattr__(self, "timeframe", str(self.timeframe or "UNKNOWN").strip().upper())
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "departure_source", str(self.departure_source or "").strip())
        object.__setattr__(self, "child_zone_ids", child_ids)
        object.__setattr__(self, "children", children)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reason_codes", _tuple_of_text(self.reason_codes))
        _validate_optional_utc_timestamp(self.available_at, field_name="available_at")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["child_zone_ids"] = list(self.child_zone_ids)
        payload["children"] = [child.to_dict() for child in self.children]
        payload["reason_codes"] = list(self.reason_codes)
        return payload

    @classmethod
    def from_dict(cls, value: object) -> "SmcSetup":
        payload = _require_mapping(value, "SMC setup")
        raw_children = payload.get("child_zone_ids", [])
        raw_child_models = payload.get("children", payload.get("child_zones", []))
        raw_reasons = payload.get("reason_codes", [])
        return cls(
            setup_id=payload.get("setup_id", ""),
            symbol=payload.get("symbol", ""),
            timeframe=payload.get("timeframe", "UNKNOWN"),
            direction=payload.get("direction", "unknown"),
            departure_source=payload.get("departure_source", ""),
            child_zone_ids=_required_text_sequence(raw_children, "SMC setup child_zone_ids"),
            status=payload.get("status", "candidate"),
            available_at=_optional_text(payload.get("available_at")),
            reason_codes=_required_text_sequence(raw_reasons, "SMC setup reason_codes"),
            children=tuple(
                SmcSetupChild.from_dict(item)
                for item in raw_child_models
                if isinstance(item, dict)
            ) if isinstance(raw_child_models, list) else (),
        )

    @classmethod
    def from_zones(
        cls,
        zones: Sequence[dict[str, Any]],
        *,
        setup_id: str | None = None,
        symbol: object = "",
        timeframe: object = "",
        direction: object | None = None,
        departure_source: object = "",
        status: str = "candidate",
    ) -> "SmcSetup":
        """Build a setup while preserving each child's own evidence/bounds."""

        if not zones:
            raise ValueError("SMC setup requires at least one child zone")
        children = tuple(
            SmcSetupChild(
                zone_id=zone.get("zone_id", ""),
                family=zone.get("family", "unknown"),
                direction=zone.get("direction", direction or "unknown"),
                original_low=(
                    zone.get("original_low")
                    if zone.get("original_low") is not None
                    else (zone.get("original_bounds", {}).get("low") if isinstance(zone.get("original_bounds"), dict) else zone.get("low", 0))
                ),
                original_high=(
                    zone.get("original_high")
                    if zone.get("original_high") is not None
                    else (zone.get("original_bounds", {}).get("high") if isinstance(zone.get("original_bounds"), dict) else zone.get("high", 0))
                ),
                evidence=_zone_evidence_payload(zone),
                reason_codes=_required_text_sequence(zone.get("reason_codes", []), "SMC setup child reason_codes"),
            )
            for zone in zones
            if isinstance(zone, dict)
        )
        if not children:
            raise ValueError("SMC setup requires mapping child zones")
        first = zones[0]
        resolved_direction = direction or first.get("direction", "unknown")
        resolved_source = departure_source or first.get("departure_source_id") or first.get("departure_end", "")
        resolved_setup_id = setup_id or first.get("setup_id")
        if not resolved_setup_id:
            resolved_setup_id = build_setup_id(
                symbol=symbol or first.get("symbol", ""),
                timeframe=timeframe or first.get("timeframe", "UNKNOWN"),
                direction=resolved_direction,
                departure_source=resolved_source,
            )
        return cls(
            setup_id=resolved_setup_id,
            symbol=symbol or first.get("symbol", ""),
            timeframe=timeframe or first.get("timeframe", "UNKNOWN"),
            direction=resolved_direction,
            departure_source=resolved_source,
            child_zone_ids=tuple(child.zone_id for child in children),
            status=status,
            children=children,
        )


@dataclass(frozen=True, slots=True)
class TimeframeConfluenceEvidence:
    timeframe: str
    structure: str
    direction: str
    bos: bool
    choch: bool
    choch_confirmed: bool
    displacement: str
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reason_codes"] = list(self.reason_codes)
        return payload

    @classmethod
    def from_dict(
        cls,
        timeframe: object,
        value: dict[str, Any],
    ) -> "TimeframeConfluenceEvidence":
        payload = value if isinstance(value, dict) else {}
        raw_reasons = payload.get("reason_codes", [])
        return cls(
            timeframe=str(
                payload.get("timeframe", timeframe) or "UNKNOWN"
            ).upper(),
            structure=str(payload.get("structure", "unknown") or "unknown"),
            direction=str(
                payload.get("direction", "unknown") or "unknown"
            ).lower(),
            bos=bool(payload.get("bos", False)),
            choch=bool(payload.get("choch", False)),
            choch_confirmed=bool(
                payload.get("choch_confirmed", False)
            ),
            displacement=str(
                payload.get("displacement", "neutral") or "neutral"
            ).lower(),
            reason_codes=tuple(
                str(code)
                for code in raw_reasons
                if str(code).strip()
            ) if isinstance(raw_reasons, list) else (),
        )


@dataclass(frozen=True, slots=True)
class DirectionalConfluence:
    direction: str
    buy_score: int | None
    sell_score: int | None
    d1_h4_aligned: bool
    h4_h1_aligned: bool
    h1_against_h4: bool
    all_aligned: bool
    h1_relationship: str = "unknown"
    data_status: str = "insufficient"
    buy_reason_codes: tuple[str, ...] = ()
    sell_reason_codes: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    timeframe_evidence: tuple[TimeframeConfluenceEvidence, ...] = ()
    confluence_version: str = SMC_CONFLUENCE_VERSION
    domain_version: str = SMC_DOMAIN_VERSION

    def __post_init__(self) -> None:
        if self.direction not in VALID_CONFLUENCE_DIRECTIONS:
            raise ValueError(
                f"Invalid SMC confluence direction: {self.direction}"
            )
        for score in (self.buy_score, self.sell_score):
            if score is not None and not 0 <= score <= 5:
                raise ValueError(
                    "Directional confluence score must be between 0 and 5"
                )

    def to_dict(self, *, include_compatibility: bool = True) -> dict[str, Any]:
        payload = asdict(self)
        payload["buy_reason_codes"] = list(self.buy_reason_codes)
        payload["sell_reason_codes"] = list(self.sell_reason_codes)
        payload["reason_codes"] = list(self.reason_codes)
        payload["timeframe_evidence"] = {
            evidence.timeframe: evidence.to_dict()
            for evidence in self.timeframe_evidence
        }
        payload["h4_aligns_d1"] = self.d1_h4_aligned
        payload["h1_aligns_h4"] = self.h4_h1_aligned
        return payload

    @classmethod
    def from_dict(
        cls,
        value: dict[str, Any],
    ) -> "DirectionalConfluence":
        payload = value if isinstance(value, dict) else {}
        raw_reasons = payload.get("reason_codes", [])
        raw_buy_reasons = payload.get("buy_reason_codes", [])
        raw_sell_reasons = payload.get("sell_reason_codes", [])
        raw_evidence = payload.get("timeframe_evidence", {})
        evidence: tuple[TimeframeConfluenceEvidence, ...]
        if isinstance(raw_evidence, dict):
            evidence = tuple(
                TimeframeConfluenceEvidence.from_dict(timeframe, item)
                for timeframe, item in raw_evidence.items()
                if isinstance(item, dict)
            )
        elif isinstance(raw_evidence, list):
            evidence = tuple(
                TimeframeConfluenceEvidence.from_dict(
                    item.get("timeframe", "UNKNOWN"),
                    item,
                )
                for item in raw_evidence
                if isinstance(item, dict)
            )
        else:
            evidence = ()
        return cls(
            direction=str(
                payload.get("direction", "unknown") or "unknown"
            ).lower(),
            buy_score=_optional_score(payload.get("buy_score")),
            sell_score=_optional_score(payload.get("sell_score")),
            d1_h4_aligned=bool(
                payload.get(
                    "d1_h4_aligned",
                    payload.get("h4_aligns_d1", False),
                )
            ),
            h4_h1_aligned=bool(
                payload.get(
                    "h4_h1_aligned",
                    payload.get("h1_aligns_h4", False),
                )
            ),
            h1_against_h4=bool(payload.get("h1_against_h4", False)),
            all_aligned=bool(payload.get("all_aligned", False)),
            h1_relationship=str(
                payload.get("h1_relationship", "unknown") or "unknown"
            ),
            data_status=str(
                payload.get("data_status", "insufficient") or "insufficient"
            ),
            buy_reason_codes=tuple(
                str(code)
                for code in raw_buy_reasons
                if str(code).strip()
            ) if isinstance(raw_buy_reasons, list) else (),
            sell_reason_codes=tuple(
                str(code)
                for code in raw_sell_reasons
                if str(code).strip()
            ) if isinstance(raw_sell_reasons, list) else (),
            reason_codes=tuple(
                str(code)
                for code in raw_reasons
                if str(code).strip()
            ) if isinstance(raw_reasons, list) else (),
            timeframe_evidence=evidence,
            confluence_version=str(
                payload.get(
                    "confluence_version",
                    SMC_CONFLUENCE_VERSION,
                )
                or SMC_CONFLUENCE_VERSION
            ),
        )


@dataclass(frozen=True, slots=True)
class SelectedSmcZone:
    zone_id: str
    direction: str
    timeframe: str
    family: str
    zone_type: str
    low: float
    high: float
    level: float
    zone_quality_score: int
    zone_relevance_score: int | None
    zone_setup_score: int
    liquidity_sweep_linked: bool
    linked_sweep_id: str | None
    linked_sweep_distance_atr: float | None
    linked_sweep_time_delta: int | None
    source: str = "smc_selected"
    scoring_version: str = SMC_SCORER_VERSION
    domain_version: str = SMC_DOMAIN_VERSION
    selection_reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.direction not in VALID_ZONE_DIRECTIONS:
            raise ValueError(
                f"Invalid selected SMC zone direction: {self.direction}"
            )
        object.__setattr__(
            self,
            "selection_reason_codes",
            tuple(
                str(code)
                for code in self.selection_reason_codes
                if str(code).strip()
            ),
        )

    @property
    def selected_zone_score(self) -> int:
        return self.zone_setup_score

    def to_dict(self, *, include_compatibility: bool = True) -> dict[str, Any]:
        payload = asdict(self)
        payload["type"] = self.zone_type
        if include_compatibility:
            payload["zone_score"] = self.zone_setup_score
            payload["selected_zone_score"] = self.selected_zone_score
        return payload

    @classmethod
    def from_zone(
        cls,
        zone: SmcZone,
        *,
        source: str = "smc_selected",
        selection_reason_codes: tuple[str, ...] = (),
    ) -> "SelectedSmcZone":
        return cls(
            zone_id=zone.zone_id,
            direction=zone.direction,
            timeframe=zone.timeframe,
            family=zone.family,
            zone_type=zone.zone_type,
            low=zone.low,
            high=zone.high,
            level=(zone.low + zone.high) / 2,
            zone_quality_score=zone.zone_quality_score,
            zone_relevance_score=zone.zone_relevance_score,
            zone_setup_score=zone.zone_setup_score,
            liquidity_sweep_linked=zone.liquidity_sweep_linked,
            linked_sweep_id=zone.linked_sweep_id,
            linked_sweep_distance_atr=zone.linked_sweep_distance_atr,
            linked_sweep_time_delta=zone.linked_sweep_time_delta,
            source=source,
            scoring_version=zone.scoring_version,
            domain_version=zone.domain_version,
            selection_reason_codes=tuple(selection_reason_codes),
        )


@dataclass(frozen=True, slots=True)
class SmcScoreBreakdown:
    side: str
    total: int
    structure_score: int | None = None
    zone_score: int | None = None
    ltf_confirmation_score: int | None = None
    technical_validation_score: int | None = None
    subtotal: int | None = None
    penalty_points: int = 0
    applied_cap: int | None = None
    penalties: tuple[str, ...] = ()
    caps: tuple[str, ...] = ()
    selected_zone_id: str | None = None
    selected_zone_quality_score: int | None = None
    selected_zone_relevance_score: int | None = None
    selected_zone_setup_score: int | None = None
    reason_codes: tuple[str, ...] = ()
    scoring_version: str = SMC_SCORER_VERSION
    domain_version: str = SMC_DOMAIN_VERSION

    def __post_init__(self) -> None:
        if self.side not in VALID_ZONE_DIRECTIONS:
            raise ValueError(f"Invalid SMC score side: {self.side}")
        if not 0 <= self.total <= 15:
            raise ValueError("SMC score total must be between 0 and 15")
        components = (
            (self.structure_score, 5),
            (self.zone_score, 5),
            (self.ltf_confirmation_score, 3),
            (self.technical_validation_score, 2),
        )
        for component, maximum in components:
            if component is not None and not 0 <= component <= maximum:
                raise ValueError("SMC score component is out of bounds")
        if self.penalty_points < 0:
            raise ValueError("SMC penalty points cannot be negative")
        if self.applied_cap is not None and not 0 <= self.applied_cap <= 15:
            raise ValueError("SMC applied cap must be between 0 and 15")
        if self.subtotal is not None:
            if not 0 <= self.subtotal <= 15:
                raise ValueError("SMC subtotal must be between 0 and 15")
            if all(component is not None for component, _ in components):
                component_total = sum(
                    int(component)
                    for component, _ in components
                    if component is not None
                )
                if self.subtotal != min(15, component_total):
                    raise ValueError(
                        "SMC subtotal does not match component scores"
                    )
            expected_total = max(0, self.subtotal - self.penalty_points)
            if self.applied_cap is not None:
                expected_total = min(expected_total, self.applied_cap)
            if self.total != expected_total:
                raise ValueError(
                    "SMC total does not match subtotal, penalties, and cap"
                )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["penalties"] = list(self.penalties)
        payload["caps"] = list(self.caps)
        payload["reason_codes"] = list(self.reason_codes)
        return payload

    @classmethod
    def from_score(
        cls,
        side: str,
        score: object,
        *,
        selected_zone_id: object = None,
        reason: object = "",
    ) -> "SmcScoreBreakdown":
        reason_text = str(reason or "").strip()
        return cls(
            side=_normalize_direction(side),
            total=min(15, _score(score)),
            selected_zone_id=_optional_text(selected_zone_id),
            reason_codes=(reason_text,) if reason_text else (),
        )


def _normalize_symbol(value: object) -> str:
    normalized = "".join(
        character
        for character in str(value or "").upper()
        if character.isalnum()
    )
    return normalized or "UNKNOWN"


def _normalize_direction(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in VALID_ZONE_DIRECTIONS:
        return normalized
    raise ValueError(f"Invalid SMC zone direction: {value}")


def _direction_from_type(zone_type: str, family: str) -> str:
    explicit = _explicit_direction_from_type(zone_type, family)
    if explicit:
        return explicit
    return "buy" if family == "demand" else "sell"


def _explicit_direction_from_type(
    zone_type: str,
    family: str,
) -> str | None:
    lowered = zone_type.lower()
    if "demand" in lowered or "bullish" in lowered:
        return "buy"
    if "supply" in lowered or "bearish" in lowered:
        return "sell"
    if family == "demand":
        return "buy"
    if family == "supply":
        return "sell"
    return None


def _family_from_type(zone_type: str) -> str:
    lowered = zone_type.lower()
    if "order_block" in lowered:
        return "order_block"
    if "fvg" in lowered:
        return "fvg"
    if "demand" in lowered:
        return "demand"
    if "supply" in lowered:
        return "supply"
    return "unknown"


def _canonical_number(value: object) -> str:
    try:
        decimal = Decimal(str(value))
        if not decimal.is_finite():
            return "0"
        normalized = format(decimal.normalize(), "f")
        return "0" if normalized in {"-0", ""} else normalized
    except (InvalidOperation, TypeError, ValueError):
        return "0"


def _float(value: object, default: float) -> float:
    try:
        result = float(value)
        return result if isfinite(result) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _score(value: object) -> int:
    return max(0, min(100, _int(value, 0)))


def _optional_score(value: object) -> int | None:
    if value is None:
        return None
    return _score(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_reference(value: object, field_name: str) -> str:
    text = _optional_reference(value)
    if text is None:
        raise ValueError(f"SMC structure {field_name} is required")
    return text


def _optional_reference(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _require_payload_field(
    payload: dict[str, Any],
    field_name: str,
    label: str,
) -> None:
    if field_name not in payload:
        raise ValueError(f"{label} missing required field: {field_name}")


def _required_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{field_name} must be an integer") from None
    if str(value).strip() != str(result) and not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    return result


def _tuple_of_text(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(
        text
        for text in (str(item).strip() for item in value)
        if text
    )


def _required_text_sequence(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list")
    return _tuple_of_text(value)


def _validate_utc_timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a timezone-aware UTC timestamp")
    text = value.strip()
    parse_text = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(parse_text)
    except ValueError:
        raise ValueError(f"{field_name} must be an ISO timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    return parsed.astimezone(timezone.utc)


def _validate_optional_utc_timestamp(
    value: object,
    field_name: str,
) -> datetime | None:
    if value is None:
        return None
    return _validate_utc_timestamp(value, field_name)
