"""Pure Location-engine models, configuration, and persisted detail.

Zone construction, lifecycle handling, and scoring are added in later tasks.
Importing this module must not read settings, touch the filesystem, start
threads, access a broker, or create a database connection.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import math
from numbers import Real
from typing import Any, Mapping, Sequence

from core.indicators import atr


LOCATION_MODEL_VERSION = "location-geometry-v2"
LOCATION_CONFIG_VERSION = "location-config-v1"
LOCATION_ROUNDING_MODE = "ROUND_HALF_UP"
LOCATION_DETAIL_SCHEMA_VERSION = "location-detail-v1"
LOCATION_CONTEXT_SCHEMA_VERSION = "location-context-v1"
LOCATION_ATR_PERIOD = 14
MIN_LOCATION_H4_BARS = 60
# MT5 Candle.time is the verified UTC open-time boundary for these bars.
# Close time is derived purely from the requested timeframe; no wall-clock is
# consulted by the domain seam.
LOCATION_TIMEFRAME_INTERVALS = {
    "H1": timedelta(hours=1),
    "H4": timedelta(hours=4),
}
LOCATION_ROLES = frozenset({"support", "resistance"})
LOCATION_STATUSES = frozenset({"ACTIVE", "SUSPECT", "INVALIDATED", "EXPIRED"})
LOCATION_RESULT_STATUSES = frozenset(
    {"EVALUATED", "LIMITED_CONTEXT", "NO_VALID_ANCHOR", "CONFLICT", "UNAVAILABLE"}
)


@dataclass(frozen=True, slots=True)
class LocationConfig:
    """Resolved, immutable configuration for the Location engine."""

    config_version: str = LOCATION_CONFIG_VERSION
    model_version: str = LOCATION_MODEL_VERSION
    raw_max: int = 25
    rounding_mode: str = LOCATION_ROUNDING_MODE
    swing_lookback: int = 2
    history_h4_bars: int = 240
    zone_half_width_atr: float = 0.15
    zone_max_width_atr: float = 1.0
    invalidation_close_count: int = 2
    invalidation_buffer_atr: float = 0.10
    zone_max_age_h4_bars: int = 120
    proximity_zero_at_atr: float = 1.0
    clearance_full_at_atr: float = 1.0
    unknown_clearance_factor: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {field.name: getattr(self, field.name) for field in fields(self)}

    @classmethod
    def from_dict(cls, value: object) -> "LocationConfig":
        payload = _require_payload(value, "config")
        if payload.get("config_version") != LOCATION_CONFIG_VERSION:
            _invalid(
                "UNSUPPORTED_VERSION",
                "config.config_version",
                f"unsupported config version: {payload.get('config_version')!r}",
            )
        if payload.get("model_version") != LOCATION_MODEL_VERSION:
            _invalid(
                "UNSUPPORTED_VERSION",
                "config.model_version",
                f"unsupported model version: {payload.get('model_version')!r}",
            )
        expected = {field.name for field in fields(cls)}
        _require_exact_keys(payload, expected, "config")
        try:
            config = cls(**payload)
        except TypeError as exc:
            _invalid("INVALID_CONFIG", "config", str(exc))
        return validate_location_config(config)


DEFAULT_LOCATION_CONFIG = LocationConfig()


@dataclass(frozen=True, slots=True)
class LocationZone:
    """A Location zone with stable identity and current lifecycle status."""

    id: str
    role: str
    low: float
    high: float
    formed_at: datetime
    confirmed_at: datetime
    formation_atr: float
    status: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            _invalid("INVALID_ZONE", "zone.id", "must be a non-empty string")
        if self.role not in LOCATION_ROLES:
            _invalid("INVALID_ZONE", "zone.role", "unsupported zone role")
        _require_positive_number(self.low, "zone.low")
        _require_positive_number(self.high, "zone.high")
        if self.low > self.high:
            _invalid("INVALID_ZONE", "zone", "low must be <= high")
        formed_at = _require_utc_datetime(self.formed_at, "zone.formed_at")
        confirmed_at = _require_utc_datetime(self.confirmed_at, "zone.confirmed_at")
        if confirmed_at < formed_at:
            _invalid("INVALID_TIMESTAMP", "zone.confirmed_at", "must not precede formed_at")
        _require_positive_number(self.formation_atr, "zone.formation_atr")
        if self.status not in LOCATION_STATUSES:
            _invalid("INVALID_ZONE", "zone.status", "unsupported zone status")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "low": self.low,
            "high": self.high,
            "formed_at": _datetime_to_iso(self.formed_at, "zone.formed_at"),
            "confirmed_at": _datetime_to_iso(self.confirmed_at, "zone.confirmed_at"),
            "formation_atr": self.formation_atr,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, value: object, *, path: str = "zone") -> "LocationZone":
        payload = _require_payload(value, path)
        _require_exact_keys(
            payload,
            {"id", "role", "low", "high", "formed_at", "confirmed_at", "formation_atr", "status"},
            path,
        )
        return cls(
            id=payload["id"],
            role=payload["role"],
            low=payload["low"],
            high=payload["high"],
            formed_at=_parse_datetime(payload["formed_at"], f"{path}.formed_at"),
            confirmed_at=_parse_datetime(payload["confirmed_at"], f"{path}.confirmed_at"),
            formation_atr=payload["formation_atr"],
            status=payload["status"],
        )


@dataclass(frozen=True, slots=True)
class LocationContext:
    """Immutable context shared when scoring BUY and SELL."""

    reference_price: float
    reference_closed_at: datetime | None
    cutoff: datetime
    current_atr_h4: float | None
    zones: tuple[LocationZone, ...]
    h4_bars_considered: int
    config: LocationConfig
    tick_size: float | None = None

    def __post_init__(self) -> None:
        validate_location_config(self.config)
        _require_positive_number(self.reference_price, "context.reference_price")
        if self.reference_closed_at is not None:
            _require_utc_datetime(self.reference_closed_at, "context.reference_closed_at")
        _require_utc_datetime(self.cutoff, "context.cutoff")
        if self.reference_closed_at is not None and self.reference_closed_at > self.cutoff:
            _invalid(
                "FUTURE_DATA",
                "context.reference_closed_at",
                "reference close must not be after cutoff",
            )
        if self.current_atr_h4 is not None:
            _require_positive_number(self.current_atr_h4, "context.current_atr_h4")
        _require_positive_integer(self.h4_bars_considered, "context.h4_bars_considered")
        if self.tick_size is not None:
            _require_positive_number(self.tick_size, "context.tick_size")
        if not isinstance(self.zones, tuple):
            object.__setattr__(self, "zones", tuple(self.zones))
        for index, zone in enumerate(self.zones):
            if not isinstance(zone, LocationZone):
                _invalid("INVALID_ZONE", f"context.zones[{index}]", "expected LocationZone")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": LOCATION_CONTEXT_SCHEMA_VERSION,
            "reference_price": self.reference_price,
            "reference_closed_at": (
                _datetime_to_iso(self.reference_closed_at, "context.reference_closed_at")
                if self.reference_closed_at is not None
                else None
            ),
            "cutoff": _datetime_to_iso(self.cutoff, "context.cutoff"),
            "current_atr_h4": self.current_atr_h4,
            "zones": [zone.to_dict() for zone in self.zones],
            "h4_bars_considered": self.h4_bars_considered,
            "config": self.config.to_dict(),
            "tick_size": self.tick_size,
        }

    @classmethod
    def from_dict(cls, value: object) -> "LocationContext":
        payload = _require_payload(value, "location_context")
        _require_schema_version(
            payload,
            LOCATION_CONTEXT_SCHEMA_VERSION,
            "location_context",
        )
        _require_exact_keys(
            payload,
            {
                "schema_version",
                "reference_price",
                "reference_closed_at",
                "cutoff",
                "current_atr_h4",
                "zones",
                "h4_bars_considered",
                "config",
                "tick_size",
            },
            "location_context",
        )
        zones = payload["zones"]
        if type(zones) is not list:
            _invalid("INVALID_SCHEMA", "location_context.zones", "expected a list")
        return cls(
            reference_price=payload["reference_price"],
            reference_closed_at=_parse_optional_datetime(
                payload["reference_closed_at"], "location_context.reference_closed_at"
            ),
            cutoff=_parse_datetime(payload["cutoff"], "location_context.cutoff"),
            current_atr_h4=payload["current_atr_h4"],
            zones=tuple(
                LocationZone.from_dict(item, path=f"location_context.zones[{index}]")
                for index, item in enumerate(zones)
            ),
            h4_bars_considered=payload["h4_bars_considered"],
            config=LocationConfig.from_dict(payload["config"]),
            tick_size=payload["tick_size"],
        )


@dataclass(frozen=True, slots=True)
class LocationResult:
    """One side's Location score and compact explanation detail."""

    side: str
    raw: int | None
    status: str
    reason_codes: tuple[str, ...]
    reference_price: float
    reference_closed_at: datetime | None
    anchor: LocationZone | None
    obstacle: LocationZone | None
    distance_atr: float | None
    clearance_atr: float | None
    proximity_factor: float | None
    clearance_factor: float | None
    model_version: str
    config_used: LocationConfig
    raw_exact: float | None = None
    cutoff: datetime | None = None
    h4_bars_considered: int | None = None

    def __post_init__(self) -> None:
        validate_location_side(self.side)
        validate_location_config(self.config_used)
        _require_positive_number(self.reference_price, "result.reference_price")
        if self.reference_closed_at is not None:
            _require_utc_datetime(self.reference_closed_at, "result.reference_closed_at")
        if self.cutoff is not None:
            _require_utc_datetime(self.cutoff, "result.cutoff")
        if not isinstance(self.reason_codes, tuple):
            object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        if any(not isinstance(reason, str) or not reason.strip() for reason in self.reason_codes):
            _invalid("INVALID_RESULT", "result.reason_codes", "must contain non-empty strings")
        if self.status not in LOCATION_RESULT_STATUSES:
            _invalid("INVALID_RESULT", "result.status", "unsupported result status")
        if self.status == "UNAVAILABLE":
            if self.raw is not None:
                _invalid("INVALID_RESULT", "result.raw", "UNAVAILABLE requires raw=null")
            if any(
                factor is not None
                for factor in (
                    self.distance_atr,
                    self.clearance_atr,
                    self.proximity_factor,
                    self.clearance_factor,
                )
            ):
                _invalid(
                    "INVALID_RESULT",
                    "result",
                    "UNAVAILABLE requires all distance/factor fields to be null",
                )
        elif type(self.raw) is not int or not 0 <= self.raw <= self.config_used.raw_max:
            _invalid("INVALID_RESULT", "result.raw", "evaluated status requires integer raw in 0..25")
        elif self.status in {"CONFLICT", "NO_VALID_ANCHOR"} and self.raw != 0:
            _invalid(
                "INVALID_RESULT",
                "result.raw",
                f"{self.status} requires raw=0",
            )
        if self.model_version != self.config_used.model_version:
            _invalid("INVALID_RESULT", "result.model_version", "must match config_used.model_version")
        for field in ("distance_atr", "clearance_atr"):
            value = getattr(self, field)
            if value is not None:
                if not _is_finite_number(value) or float(value) < 0:
                    _invalid("INVALID_RESULT", f"result.{field}", "must be finite and non-negative")
        for field in ("proximity_factor", "clearance_factor"):
            value = getattr(self, field)
            if value is not None:
                if not _is_finite_number(value) or not 0 <= float(value) <= 1:
                    _invalid("INVALID_RESULT", f"result.{field}", "must be in [0, 1]")
        if self.raw_exact is not None and (
            not _is_finite_number(self.raw_exact) or float(self.raw_exact) < 0
        ):
            _invalid("INVALID_RESULT", "result.raw_exact", "must be finite and non-negative")
        if self.h4_bars_considered is not None:
            _require_positive_integer(self.h4_bars_considered, "result.h4_bars_considered")

    def to_dict(self) -> dict[str, Any]:
        """Return compact persisted detail; no candle history is embedded."""

        return {
            "schema_version": LOCATION_DETAIL_SCHEMA_VERSION,
            "model_version": self.model_version,
            "side": self.side,
            "raw": self.raw,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "reference_price": self.reference_price,
            "reference_closed_at": (
                _datetime_to_iso(self.reference_closed_at, "result.reference_closed_at")
                if self.reference_closed_at is not None
                else None
            ),
            "anchor": self.anchor.to_dict() if self.anchor is not None else None,
            "obstacle": self.obstacle.to_dict() if self.obstacle is not None else None,
            "distance_atr": self.distance_atr,
            "clearance_atr": self.clearance_atr,
            "proximity_factor": self.proximity_factor,
            "clearance_factor": self.clearance_factor,
            "config_used": self.config_used.to_dict(),
            "raw_exact": self.raw_exact,
            "cutoff": (
                _datetime_to_iso(self.cutoff, "result.cutoff")
                if self.cutoff is not None
                else None
            ),
            "h4_bars_considered": self.h4_bars_considered,
        }

    @classmethod
    def from_dict(cls, value: object) -> "LocationResult":
        payload = _require_payload(value, "location_result")
        _require_schema_version(payload, LOCATION_DETAIL_SCHEMA_VERSION, "location_result")
        model_version = payload.get("model_version")
        if model_version != LOCATION_MODEL_VERSION:
            _invalid(
                "UNSUPPORTED_VERSION",
                "location_result.model_version",
                f"unsupported model version: {model_version!r}",
            )
        _require_exact_keys(
            payload,
            {
                "schema_version",
                "model_version",
                "side",
                "raw",
                "status",
                "reason_codes",
                "reference_price",
                "reference_closed_at",
                "anchor",
                "obstacle",
                "distance_atr",
                "clearance_atr",
                "proximity_factor",
                "clearance_factor",
                "config_used",
                "raw_exact",
                "cutoff",
                "h4_bars_considered",
            },
            "location_result",
        )
        reason_codes = payload["reason_codes"]
        if type(reason_codes) is not list or any(
            type(code) is not str or not code for code in reason_codes
        ):
            _invalid("INVALID_SCHEMA", "location_result.reason_codes", "expected non-empty strings")
        return cls(
            side=payload["side"],
            raw=payload["raw"],
            status=payload["status"],
            reason_codes=tuple(reason_codes),
            reference_price=payload["reference_price"],
            reference_closed_at=_parse_optional_datetime(
                payload["reference_closed_at"], "location_result.reference_closed_at"
            ),
            anchor=(
                None
                if payload["anchor"] is None
                else LocationZone.from_dict(payload["anchor"], path="location_result.anchor")
            ),
            obstacle=(
                None
                if payload["obstacle"] is None
                else LocationZone.from_dict(payload["obstacle"], path="location_result.obstacle")
            ),
            distance_atr=payload["distance_atr"],
            clearance_atr=payload["clearance_atr"],
            proximity_factor=payload["proximity_factor"],
            clearance_factor=payload["clearance_factor"],
            model_version=model_version,
            config_used=LocationConfig.from_dict(payload["config_used"]),
            raw_exact=payload["raw_exact"],
            cutoff=_parse_optional_datetime(payload["cutoff"], "location_result.cutoff"),
            h4_bars_considered=payload["h4_bars_considered"],
        )


class LocationDataError(ValueError):
    """Typed domain error for invalid Location config or input data."""

    def __init__(self, code: str, field: str, detail: str):
        self.code = code
        self.field = field
        self.detail = detail
        super().__init__(f"{code} [{field}]: {detail}")


def _invalid(code: str, field: str, detail: str) -> None:
    raise LocationDataError(code, field, detail)


def _require_payload(value: object, field: str) -> dict[str, Any]:
    if type(value) is not dict:
        _invalid("INVALID_SCHEMA", field, "expected an object")
    return value


def _require_exact_keys(payload: Mapping[str, Any], expected: set[str], field: str) -> None:
    actual = set(payload)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing or unknown:
        details: list[str] = []
        if missing:
            details.append(f"missing={missing}")
        if unknown:
            details.append(f"unknown={unknown}")
        _invalid("INVALID_SCHEMA", field, "; ".join(details))


def _require_schema_version(
    payload: Mapping[str, Any], expected: str, field: str
) -> None:
    version = payload.get("schema_version")
    if version != expected:
        _invalid(
            "UNSUPPORTED_VERSION",
            f"{field}.schema_version",
            f"unsupported schema version: {version!r}",
        )


def _datetime_to_iso(value: datetime, field: str) -> str:
    parsed = _require_utc_datetime(value, field)
    return parsed.isoformat().replace("+00:00", "Z")


def _parse_datetime(value: object, field: str) -> datetime:
    if type(value) is not str:
        _invalid("INVALID_TIMESTAMP", field, "expected an ISO UTC string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError) as exc:
        _invalid("INVALID_TIMESTAMP", field, f"invalid ISO datetime: {exc}")
    return _require_utc_datetime(parsed, field)


def _parse_optional_datetime(value: object, field: str) -> datetime | None:
    return None if value is None else _parse_datetime(value, field)


def _is_finite_number(value: object) -> bool:
    return (
        isinstance(value, Real)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _require_positive_number(value: object, field: str) -> None:
    if not _is_finite_number(value):
        _invalid("INVALID_NUMBER", field, "expected a finite real number")
    if float(value) <= 0:
        _invalid("OUT_OF_RANGE", field, "must be greater than zero")


def _require_positive_integer(value: object, field: str) -> None:
    if type(value) is not int:
        _invalid("INVALID_TYPE", field, "expected a positive integer, not bool")
    if value <= 0:
        _invalid("OUT_OF_RANGE", field, "must be greater than zero")


def _require_utc_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, datetime):
        _invalid("INVALID_TIMESTAMP", field, "expected a datetime")
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        _invalid("INVALID_TIMESTAMP", field, "must be timezone-aware UTC")
    return value


def validate_location_config(config: LocationConfig) -> LocationConfig:
    """Validate a resolved LocationConfig without repairing any value."""

    if not isinstance(config, LocationConfig):
        _invalid("INVALID_CONFIG", "config", "expected LocationConfig")

    for field in (
        "raw_max",
        "swing_lookback",
        "history_h4_bars",
        "invalidation_close_count",
        "zone_max_age_h4_bars",
    ):
        _require_positive_integer(getattr(config, field), f"config.{field}")

    if config.raw_max != 25:
        _invalid("OUT_OF_RANGE", "config.raw_max", "must equal 25")
    if config.swing_lookback < 2:
        _invalid("OUT_OF_RANGE", "config.swing_lookback", "must be at least 2")
    if config.history_h4_bars < MIN_LOCATION_H4_BARS:
        _invalid(
            "OUT_OF_RANGE",
            "config.history_h4_bars",
            f"must be at least {MIN_LOCATION_H4_BARS}",
        )

    for field in (
        "zone_half_width_atr",
        "zone_max_width_atr",
        "invalidation_buffer_atr",
        "proximity_zero_at_atr",
        "clearance_full_at_atr",
    ):
        _require_positive_number(getattr(config, field), f"config.{field}")

    unknown_factor = config.unknown_clearance_factor
    if not _is_finite_number(unknown_factor):
        _invalid(
            "INVALID_NUMBER",
            "config.unknown_clearance_factor",
            "expected a finite real number",
        )
    if not 0 <= float(unknown_factor) < 1:
        _invalid(
            "OUT_OF_RANGE",
            "config.unknown_clearance_factor",
            "must be in [0, 1)",
        )

    for field in ("config_version", "model_version", "rounding_mode"):
        value = getattr(config, field)
        if not isinstance(value, str) or not value.strip():
            if field in {"config_version", "model_version"}:
                _invalid("UNSUPPORTED_VERSION", f"config.{field}", "version is missing or empty")
            _invalid("INVALID_TYPE", f"config.{field}", "must be a non-empty string")
    if config.config_version != LOCATION_CONFIG_VERSION:
        _invalid(
            "UNSUPPORTED_VERSION",
            "config.config_version",
            f"unsupported config version: {config.config_version!r}",
        )
    if config.model_version != LOCATION_MODEL_VERSION:
        _invalid(
            "UNSUPPORTED_VERSION",
            "config.model_version",
            f"unsupported model version: {config.model_version!r}",
        )
    if config.rounding_mode != LOCATION_ROUNDING_MODE:
        _invalid(
            "INVALID_CONFIG",
            "config.rounding_mode",
            f"must equal {LOCATION_ROUNDING_MODE}",
        )
    return config


def validate_location_side(side: object) -> str:
    """Validate and return a side; invalid values never fall through to SELL."""

    if side not in {"buy", "sell"}:
        _invalid("INVALID_SIDE", "side", "expected exactly 'buy' or 'sell'")
    return side


def _candle_value(candle: object, name: str, field: str) -> object:
    if isinstance(candle, Mapping):
        if name not in candle:
            _invalid("INVALID_CANDLE", field, f"missing {name}")
        return candle[name]
    if not hasattr(candle, name):
        _invalid("INVALID_CANDLE", field, f"missing {name}")
    return getattr(candle, name)


def validate_location_candle(candle: object, index: int) -> None:
    """Validate one normalized UTC candle and its OHLC geometry."""

    prefix = f"closed_h4[{index}]"
    _require_utc_datetime(_candle_value(candle, "time", f"{prefix}.time"), f"{prefix}.time")
    values = {
        name: _candle_value(candle, name, f"{prefix}.{name}")
        for name in ("open", "high", "low", "close")
    }
    for name, value in values.items():
        _require_positive_number(value, f"{prefix}.{name}")
    if values["low"] > values["high"]:
        _invalid("INVALID_OHLC", f"{prefix}.low", "must be <= high")
    if not values["low"] <= values["open"] <= values["high"]:
        _invalid("INVALID_OHLC", f"{prefix}.open", "must be within low/high")
    if not values["low"] <= values["close"] <= values["high"]:
        _invalid("INVALID_OHLC", f"{prefix}.close", "must be within low/high")
    if isinstance(candle, Mapping) and "volume" in candle and candle["volume"] is not None:
        _require_positive_number(candle["volume"], f"{prefix}.volume")


def validate_location_inputs(
    closed_h4: Sequence[object],
    reference_price: object,
    cutoff: object,
    config: LocationConfig,
    tick_size: object | None = None,
) -> None:
    """Validate essential context inputs before zone construction."""

    validate_location_config(config)
    if isinstance(closed_h4, (str, bytes)) or not isinstance(closed_h4, Sequence):
        _invalid("INVALID_INPUT", "closed_h4", "expected a sequence of candles")
    _require_positive_number(reference_price, "reference_price")
    if tick_size is not None:
        _require_positive_number(tick_size, "tick_size")

    # Keep the filtering and windowing contract in one helper.  In particular,
    # a currently forming bar is allowed in the adapter payload and is removed
    # by its derived close boundary rather than by its open time.
    closed_h4_history_at_cutoff(closed_h4, cutoff, config)


def validate_location_zone(zone: object, field: str = "zone") -> None:
    """Validate the geometry/status fields accepted from a zone mapping."""

    if not isinstance(zone, Mapping):
        _invalid("INVALID_ZONE", field, "expected a mapping")
    if "low" not in zone or "high" not in zone:
        _invalid("INVALID_ZONE", field, "requires low and high")
    _require_positive_number(zone["low"], f"{field}.low")
    _require_positive_number(zone["high"], f"{field}.high")
    if zone["low"] > zone["high"]:
        _invalid("INVALID_ZONE", field, "low must be <= high")
    if "role" in zone and zone["role"] not in LOCATION_ROLES:
        _invalid("INVALID_ZONE", f"{field}.role", "unsupported zone role")
    if "status" in zone and zone["status"] not in LOCATION_STATUSES:
        _invalid("INVALID_ZONE", f"{field}.status", "unsupported zone status")


def validate_location_zones(zones: Sequence[object], field: str = "zones") -> None:
    if isinstance(zones, (str, bytes)) or not isinstance(zones, Sequence):
        _invalid("INVALID_ZONE", field, "expected a sequence")
    for index, zone in enumerate(zones):
        validate_location_zone(zone, f"{field}[{index}]")


@dataclass(frozen=True, slots=True)
class ClosedCandle:
    """One candle paired with its derived close boundary."""

    candle: Any
    open_time: datetime
    closed_at: datetime

    def __post_init__(self) -> None:
        _require_utc_datetime(self.open_time, "closed_candle.open_time")
        _require_utc_datetime(self.closed_at, "closed_candle.closed_at")
        if self.closed_at <= self.open_time:
            _invalid(
                "INVALID_TIMESTAMP",
                "closed_candle.closed_at",
                "must be after open_time",
            )


@dataclass(frozen=True, slots=True)
class LocationReference:
    """Reference price and close boundary selected from closed H1 candles."""

    reference_price: float
    reference_closed_at: datetime

    def __post_init__(self) -> None:
        _require_positive_number(self.reference_price, "reference.reference_price")
        _require_utc_datetime(self.reference_closed_at, "reference.reference_closed_at")


@dataclass(frozen=True, slots=True)
class LocationSwing:
    """A causally confirmed H4 swing used by the Location zone builder."""

    id: str
    role: str
    level: float
    formed_at: datetime
    confirmed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            _invalid("INVALID_SWING", "swing.id", "must be a non-empty string")
        if self.role not in LOCATION_ROLES:
            _invalid("INVALID_SWING", "swing.role", "unsupported swing role")
        _require_positive_number(self.level, "swing.level")
        _require_utc_datetime(self.formed_at, "swing.formed_at")
        _require_utc_datetime(self.confirmed_at, "swing.confirmed_at")
        if self.confirmed_at < self.formed_at:
            _invalid(
                "INVALID_TIMESTAMP",
                "swing.confirmed_at",
                "must not precede formed_at",
            )


@dataclass(frozen=True, slots=True)
class LocationObstacleSelection:
    """Obstacle selection outcome, including the conflict-first decision."""

    obstacle: LocationZone | None
    conflict: bool
    clearance_distance: float | None

    def __post_init__(self) -> None:
        if not isinstance(self.conflict, bool):
            _invalid("INVALID_OBSTACLE", "obstacle_selection.conflict", "expected bool")
        if self.conflict and self.obstacle is None:
            _invalid(
                "INVALID_OBSTACLE",
                "obstacle_selection.obstacle",
                "conflict requires an obstacle",
            )
        if self.clearance_distance is not None:
            if (
                not _is_finite_number(self.clearance_distance)
                or float(self.clearance_distance) < 0
            ):
                _invalid(
                    "INVALID_OBSTACLE",
                    "obstacle_selection.clearance_distance",
                    "must be finite and non-negative",
                )


def close_time_from_open_time(open_time: object, timeframe: object) -> datetime:
    """Derive a bar close boundary from verified MT5 open-time semantics."""

    parsed_open = _require_utc_datetime(open_time, "open_time")
    key = timeframe.strip().upper() if isinstance(timeframe, str) else None
    if key not in LOCATION_TIMEFRAME_INTERVALS:
        _invalid(
            "INVALID_TIMEFRAME",
            "timeframe",
            "Location supports only H1 and H4 close boundaries",
        )
    return parsed_open + LOCATION_TIMEFRAME_INTERVALS[key]


def closed_candles_at_cutoff(
    candles: Sequence[object],
    timeframe: str,
    cutoff: datetime,
    *,
    max_bars: int | None = None,
) -> tuple[ClosedCandle, ...]:
    """Keep closed bars at a cutoff, optionally retaining only the newest bars.

    The input is validated as one ordered adapter stream before filtering.  The
    limit is deliberately applied *after* the close-boundary filter so a
    forming/future bar cannot evict a valid historical bar from the window.
    """

    cutoff_dt = _require_utc_datetime(cutoff, "cutoff")
    if isinstance(candles, (str, bytes)) or not isinstance(candles, Sequence):
        _invalid("INVALID_INPUT", "candles", "expected a sequence")
    if max_bars is not None:
        _require_positive_integer(max_bars, "max_bars")
    result: list[ClosedCandle] = []
    previous_open: datetime | None = None
    for index, candle in enumerate(candles):
        open_time = _require_utc_datetime(
            _candle_value(candle, "time", f"candles[{index}].time"),
            f"candles[{index}].time",
        )
        if previous_open is not None and open_time <= previous_open:
            _invalid(
                "INVALID_TIMESTAMP",
                f"candles[{index}].time",
                "candles must be strictly increasing with no duplicates",
            )
        closed_at = close_time_from_open_time(open_time, timeframe)
        if closed_at <= cutoff_dt:
            result.append(ClosedCandle(candle, open_time, closed_at))
        previous_open = open_time
    if max_bars is not None:
        result = result[-max_bars:]
    return tuple(result)


def closed_h4_history_at_cutoff(
    closed_h4: Sequence[object],
    cutoff: datetime,
    config: LocationConfig,
) -> tuple[ClosedCandle, ...]:
    """Return the causal H4 history used by Location.

    The adapter may provide a bar that is still forming and may provide more
    history than the engine needs.  We first derive ``closed_at`` and remove
    every bar after the explicit cutoff, then retain at most the configured
    number of newest eligible bars.  The minimum check is performed on that
    final set, so a payload with enough closed history plus a forming bar is
    valid, while a payload with fewer than the minimum eligible bars fails.

    OHLC validation is applied only to bars that can affect Location.  Future
    bars are still checked for timestamp order/duplicates by
    ``closed_candles_at_cutoff`` but cannot make a past assessment fail because
    their OHLC values are not consumed.
    """

    validate_location_config(config)
    eligible = closed_candles_at_cutoff(
        closed_h4,
        "H4",
        cutoff,
        max_bars=config.history_h4_bars,
    )
    if len(eligible) < MIN_LOCATION_H4_BARS:
        _invalid(
            "INSUFFICIENT_HISTORY",
            "closed_h4",
            f"need at least {MIN_LOCATION_H4_BARS} closed H4 candles at cutoff; "
            f"received {len(eligible)} after the {config.history_h4_bars}-bar limit",
        )
    for index, item in enumerate(eligible):
        validate_location_candle(item.candle, index)
    return eligible


def location_swing_points(
    closed_h4: Sequence[object],
    cutoff: datetime,
    config: LocationConfig,
) -> tuple[LocationSwing, ...]:
    """Find causally confirmed Location swings in an H4 adapter stream.

    This intentionally mirrors the existing ``lookback=2`` swing criterion
    without importing or changing canonical SMC detection.  A swing at index
    ``i`` is only usable after the second candle to its right has closed, so
    ``confirmed_at`` is the derived close boundary of ``i + lookback``.
    """

    validate_location_config(config)
    history = closed_candles_at_cutoff(
        closed_h4,
        "H4",
        cutoff,
        max_bars=config.history_h4_bars,
    )
    for index, item in enumerate(history):
        validate_location_candle(item.candle, index)

    return _location_swing_points_from_history(history, cutoff, config)


def _location_swing_points_from_history(
    history: Sequence[ClosedCandle],
    cutoff: datetime,
    config: LocationConfig,
) -> tuple[LocationSwing, ...]:
    """Find swings from one already filtered/validated H4 history window."""

    lookback = config.swing_lookback
    swings: list[LocationSwing] = []
    for index in range(lookback, len(history) - lookback):
        window = history[index - lookback : index + lookback + 1]
        candle = window[lookback].candle
        high = float(_candle_value(candle, "high", f"closed_h4[{index}].high"))
        low = float(_candle_value(candle, "low", f"closed_h4[{index}].low"))
        window_highs = [
            float(_candle_value(item.candle, "high", f"closed_h4[{item_index}].high"))
            for item_index, item in enumerate(history[index - lookback : index + lookback + 1], start=index - lookback)
        ]
        window_lows = [
            float(_candle_value(item.candle, "low", f"closed_h4[{item_index}].low"))
            for item_index, item in enumerate(history[index - lookback : index + lookback + 1], start=index - lookback)
        ]
        formed_at = history[index].open_time
        confirmed_at = history[index + lookback].closed_at
        if confirmed_at > cutoff:
            continue

        if high == max(window_highs) and window_highs.count(high) == 1:
            swings.append(
                LocationSwing(
                    id=f"resistance:{formed_at.isoformat()}",
                    role="resistance",
                    level=high,
                    formed_at=formed_at,
                    confirmed_at=confirmed_at,
                )
            )
        if low == min(window_lows) and window_lows.count(low) == 1:
            swings.append(
                LocationSwing(
                    id=f"support:{formed_at.isoformat()}",
                    role="support",
                    level=low,
                    formed_at=formed_at,
                    confirmed_at=confirmed_at,
                )
            )

    return tuple(swings)


def build_location_zones(
    closed_h4: Sequence[object],
    cutoff: datetime,
    config: LocationConfig,
    tick_size: float | None = None,
) -> tuple[LocationZone, ...]:
    """Build Location zones with width fixed by ATR at swing confirmation.

    ATR is calculated once for the causal H4 history.  Each swing reads the
    ATR value at its own confirmation candle; later volatility cannot resize an
    already formed zone.  This builder is intentionally separate from the
    canonical SMC zone builder.
    """

    validate_location_config(config)
    if tick_size is not None:
        _require_positive_number(tick_size, "tick_size")
    history = closed_h4_history_at_cutoff(closed_h4, cutoff, config)
    return _build_location_zones_from_history(history, cutoff, config, tick_size)


def _build_location_zones_from_history(
    history: Sequence[ClosedCandle],
    cutoff: datetime,
    config: LocationConfig,
    tick_size: float | None,
) -> tuple[LocationZone, ...]:
    """Build and lifecycle one already filtered H4 context."""

    swings = _location_swing_points_from_history(history, cutoff, config)
    atr_values = _atr_values_for_history(history)
    confirmation_index = {item.closed_at: index for index, item in enumerate(history)}
    zones: list[LocationZone] = []

    for swing in swings:
        index = confirmation_index.get(swing.confirmed_at)
        formation_atr = (
            atr_values[index]
            if index is not None and index < len(atr_values)
            else None
        )
        if formation_atr is None or not _is_finite_number(formation_atr) or float(formation_atr) <= 0:
            # There is no valid ATR prefix at confirmation.  Do not replace it
            # with the latest ATR, because that would make the zone non-causal.
            continue

        formation_atr = float(formation_atr)
        half_width = config.zone_half_width_atr * formation_atr
        low = swing.level - half_width
        high = swing.level + half_width
        raw_low = low
        raw_high = high
        if tick_size is not None:
            low = math.floor(low / tick_size) * tick_size
            high = math.ceil(high / tick_size) * tick_size
            if high <= low:
                high = low + tick_size

        if _width_exceeds_max(
            low,
            high,
            formation_atr,
            config.zone_max_width_atr,
            raw_low=raw_low,
            raw_high=raw_high,
            tick_size=tick_size,
        ):
            continue

        zones.append(
            LocationZone(
                id=swing.id,
                role=swing.role,
                low=low,
                high=high,
                formed_at=swing.formed_at,
                confirmed_at=swing.confirmed_at,
                formation_atr=formation_atr,
                status="ACTIVE",
            )
        )

    canonical_zones = deduplicate_location_zones(tuple(zones))
    return _update_location_zone_lifecycle_from_history(
        canonical_zones,
        history,
        cutoff,
        config,
    )


def _atr_values_for_history(
    history: Sequence[ClosedCandle],
) -> list[float | None]:
    """Calculate one ATR(14) series for a validated H4 history window."""

    return atr(
        [
            float(_candle_value(item.candle, "high", f"closed_h4[{index}].high"))
            for index, item in enumerate(history)
        ],
        [
            float(_candle_value(item.candle, "low", f"closed_h4[{index}].low"))
            for index, item in enumerate(history)
        ],
        [
            float(_candle_value(item.candle, "close", f"closed_h4[{index}].close"))
            for index, item in enumerate(history)
        ],
        LOCATION_ATR_PERIOD,
    )


def _width_exceeds_max(
    low: float,
    high: float,
    formation_atr: float,
    max_width_atr: float,
    *,
    raw_low: float | None = None,
    raw_high: float | None = None,
    tick_size: float | None = None,
) -> bool:
    """Compare zone width without rejecting an equal float result.

    The error budget includes the operands used to create the width: the two
    rounded price levels, the unrounded levels, the tick size, and the ATR
    threshold.  This covers both tick rounding and the subsequent
    ``high - low`` subtraction, including larger-price instruments where one
    ULP is materially larger than at price 1.
    """

    width = high - low
    max_width = formation_atr * max_width_atr
    difference = width - max_width
    if difference <= 0:
        return False
    operands = [low, high, width, max_width, formation_atr, max_width_atr]
    if raw_low is not None:
        operands.append(raw_low)
    if raw_high is not None:
        operands.append(raw_high)
    if tick_size is not None:
        operands.append(tick_size)
    error_budget = sum(math.ulp(abs(value)) for value in operands if value != 0)
    return difference > 4 * error_budget


def deduplicate_location_zones(
    zones: Sequence[LocationZone],
) -> tuple[LocationZone, ...]:
    """Deduplicate exact zone records and return a deterministic ordering.

    An identical repeated record is harmless and kept once.  Reusing an ID for
    different geometry, timestamps, formation ATR, or lifecycle state is an
    input contradiction; silently choosing the first record would make the
    result depend on adapter order.  Nearby but distinct IDs are intentionally
    not merged in this first model.
    """

    if isinstance(zones, (str, bytes)) or not isinstance(zones, Sequence):
        _invalid("INVALID_ZONE", "zones", "expected a sequence")
    by_id: dict[str, LocationZone] = {}
    for index, zone in enumerate(zones):
        if not isinstance(zone, LocationZone):
            _invalid("INVALID_ZONE", f"zones[{index}]", "expected LocationZone")
        previous = by_id.get(zone.id)
        if previous is None:
            by_id[zone.id] = zone
            continue
        if previous != zone:
            _invalid(
                "CONFLICTING_ZONE_ID",
                f"zones[{index}].id",
                f"zone id {zone.id!r} has conflicting source data",
            )

    role_order = {"support": 0, "resistance": 1}
    return tuple(
        sorted(
            by_id.values(),
            key=lambda zone: (
                role_order[zone.role],
                zone.confirmed_at,
                zone.id,
            ),
        )
    )


def update_location_zone_lifecycle(
    zones: Sequence[LocationZone],
    closed_h4: Sequence[object],
    cutoff: datetime,
    config: LocationConfig,
) -> tuple[LocationZone, ...]:
    """Apply close-based breach streaks and age expiry to Location zones.

    Lifecycle is rebuilt from the causal H4 history on every call.  A support
    breaches below ``low - buffer`` and a resistance breaches above
    ``high + buffer``; equality is deliberately not a breach.  The
    confirmation candle is included in the scan with age zero.
    """

    validate_location_config(config)
    if isinstance(zones, (str, bytes)) or not isinstance(zones, Sequence):
        _invalid("INVALID_ZONE", "zones", "expected a sequence")
    canonical_zones = deduplicate_location_zones(zones)

    history = closed_h4_history_at_cutoff(closed_h4, cutoff, config)
    return _update_location_zone_lifecycle_from_history(
        canonical_zones,
        history,
        cutoff,
        config,
    )


def _update_location_zone_lifecycle_from_history(
    zones: Sequence[LocationZone],
    history: Sequence[ClosedCandle],
    cutoff: datetime,
    config: LocationConfig,
) -> tuple[LocationZone, ...]:
    """Apply lifecycle to one already filtered/validated history window."""

    history_by_close = {item.closed_at: item for item in history}
    result: list[LocationZone] = []

    for zone in zones:
        if zone.status in {"INVALIDATED", "EXPIRED"}:
            result.append(zone)
            continue
        if zone.confirmed_at > cutoff:
            _invalid(
                "FUTURE_DATA",
                "zone.confirmed_at",
                "zone confirmation must not be after cutoff",
            )
        if zone.confirmed_at not in history_by_close:
            _invalid(
                "INSUFFICIENT_HISTORY",
                "zone.confirmed_at",
                "confirmation candle is not available in the H4 history",
            )

        buffer = config.invalidation_buffer_atr * zone.formation_atr
        break_line = (
            zone.low - buffer
            if zone.role == "support"
            else zone.high + buffer
        )
        relevant = [
            item
            for item in history
            if item.closed_at >= zone.confirmed_at
        ]
        breach_streak = 0
        status = "ACTIVE"
        for item in relevant:
            close = float(
                _candle_value(
                    item.candle,
                    "close",
                    "closed_h4.lifecycle.close",
                )
            )
            breached = (
                close < break_line
                if zone.role == "support"
                else close > break_line
            )
            if not breached:
                breach_streak = 0
                status = "ACTIVE"
                continue

            breach_streak += 1
            if breach_streak >= config.invalidation_close_count:
                status = "INVALIDATED"
                break
            status = "SUSPECT"

        if status != "INVALIDATED":
            age = max(0, len(relevant) - 1)
            if age > config.zone_max_age_h4_bars:
                status = "EXPIRED"

        result.append(replace(zone, status=status))

    return tuple(result)


def distance_to_interval(price: float, low: float, high: float) -> float:
    """Return zero inside an interval, otherwise distance to the nearest edge."""

    _require_positive_number(price, "price")
    _require_positive_number(low, "low")
    _require_positive_number(high, "high")
    if low > high:
        _invalid("INVALID_ZONE", "interval", "low must be <= high")
    if price < low:
        return low - price
    if price > high:
        return price - high
    return 0.0


def select_location_anchor(
    side: str,
    context: LocationContext,
) -> LocationZone | None:
    """Select the nearest valid directional anchor from one shared context."""

    validate_location_side(side)
    if not isinstance(context, LocationContext):
        _invalid("INVALID_INPUT", "context", "expected LocationContext")

    reference_price = context.reference_price
    expected_role = "support" if side == "buy" else "resistance"
    candidates: list[tuple[tuple[float, float, float, str], LocationZone]] = []
    for zone in context.zones:
        if zone.role != expected_role or zone.status != "ACTIVE":
            continue
        if zone.confirmed_at > context.cutoff:
            continue
        if side == "buy" and reference_price < zone.low:
            continue
        if side == "sell" and reference_price > zone.high:
            continue

        distance = distance_to_interval(reference_price, zone.low, zone.high)
        width = zone.high - zone.low
        candidates.append(
            (
                (
                    distance,
                    width,
                    -zone.confirmed_at.timestamp(),
                    zone.id,
                ),
                zone,
            )
        )

    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


def select_location_obstacle(
    side: str,
    context: LocationContext,
) -> LocationObstacleSelection:
    """Select the nearest forward obstacle, with conflict taking priority."""

    validate_location_side(side)
    if not isinstance(context, LocationContext):
        _invalid("INVALID_INPUT", "context", "expected LocationContext")

    reference_price = context.reference_price
    expected_role = "resistance" if side == "buy" else "support"
    containing: list[LocationZone] = []
    forward: list[tuple[tuple[float, float, float, str], LocationZone, float]] = []

    for zone in context.zones:
        if zone.role != expected_role:
            continue
        if zone.status not in {"ACTIVE", "SUSPECT"}:
            continue
        if zone.confirmed_at > context.cutoff:
            continue

        contains = zone.low <= reference_price <= zone.high
        if contains:
            containing.append(zone)
            continue

        if side == "buy" and zone.low > reference_price:
            clearance = zone.low - reference_price
        elif side == "sell" and zone.high < reference_price:
            clearance = reference_price - zone.high
        else:
            continue

        forward.append(
            (
                (
                    clearance,
                    zone.high - zone.low,
                    -zone.confirmed_at.timestamp(),
                    zone.id,
                ),
                zone,
                clearance,
            )
        )

    if containing:
        selected = min(
            containing,
            key=lambda zone: (
                zone.high - zone.low,
                -zone.confirmed_at.timestamp(),
                zone.id,
            ),
        )
        return LocationObstacleSelection(
            obstacle=selected,
            conflict=True,
            clearance_distance=0.0,
        )

    if not forward:
        return LocationObstacleSelection(
            obstacle=None,
            conflict=False,
            clearance_distance=None,
        )

    _, obstacle, clearance = min(forward, key=lambda item: item[0])
    return LocationObstacleSelection(
        obstacle=obstacle,
        conflict=False,
        clearance_distance=clearance,
    )


def reference_from_closed_h1(
    h1_candles: Sequence[object],
    cutoff: datetime,
) -> LocationReference:
    """Select the close of the last H1 bar closed at the explicit cutoff."""

    closed = closed_candles_at_cutoff(h1_candles, "H1", cutoff)
    if not closed:
        _invalid(
            "INSUFFICIENT_HISTORY",
            "h1_candles",
            "no H1 candle was closed at or before cutoff",
        )
    selected = closed[-1]
    close_value = _candle_value(selected.candle, "close", "h1_candles[-1].close")
    _require_positive_number(close_value, "reference.reference_price")
    return LocationReference(close_value, selected.closed_at)


def resolve_location_config(
    overrides: Mapping[str, Any] | None = None,
) -> LocationConfig:
    """Resolve a partial mapping against the one canonical default.

    This boundary deliberately does not coerce or silently repair values.
    Domain validation belongs to Task B02; an explicitly supplied value is
    carried through so invalid configuration cannot be hidden by a fallback.
    """

    if overrides is None:
        return DEFAULT_LOCATION_CONFIG
    if not isinstance(overrides, Mapping):
        raise TypeError("Location config overrides must be a mapping or None")

    allowed = {field.name for field in fields(LocationConfig)}
    unknown = sorted(set(overrides) - allowed)
    if unknown:
        raise KeyError(f"Unknown Location config key(s): {', '.join(unknown)}")
    return replace(DEFAULT_LOCATION_CONFIG, **dict(overrides))


def build_location_context(
    closed_h4: Sequence[Any],
    reference_price: float | LocationReference,
    cutoff: datetime,
    config: LocationConfig,
    tick_size: float | None = None,
    *,
    reference_closed_at: datetime | None = None,
) -> LocationContext:
    """Build one causal, side-neutral Location context.

    ``reference_price`` may be the plain adapter price for backward
    compatibility or a ``LocationReference`` carrying the H1 close time.  No
    broker access or wall-clock lookup happens inside this pure builder.
    """

    if isinstance(reference_price, LocationReference):
        if reference_closed_at is not None:
            _invalid(
                "INVALID_INPUT",
                "reference_closed_at",
                "do not pass a separate timestamp with LocationReference",
            )
        resolved_reference_price = reference_price.reference_price
        resolved_reference_closed_at = reference_price.reference_closed_at
    else:
        resolved_reference_price = reference_price
        resolved_reference_closed_at = reference_closed_at
        if resolved_reference_closed_at is not None:
            _require_utc_datetime(
                resolved_reference_closed_at,
                "reference_closed_at",
            )
    cutoff_dt = _require_utc_datetime(cutoff, "cutoff")
    if (
        resolved_reference_closed_at is not None
        and resolved_reference_closed_at > cutoff_dt
    ):
        _invalid(
            "FUTURE_DATA",
            "reference_closed_at",
            "reference close must not be after cutoff",
        )
    validate_location_inputs(
        closed_h4,
        resolved_reference_price,
        cutoff_dt,
        config,
        tick_size,
    )
    history = closed_h4_history_at_cutoff(closed_h4, cutoff, config)
    atr_values = _atr_values_for_history(history)
    current_atr = atr_values[-1] if atr_values else None
    if current_atr is None or not _is_finite_number(current_atr) or float(current_atr) <= 0:
        _invalid(
            "UNAVAILABLE",
            "context.current_atr_h4",
            "ATR(14) is not available for the current closed H4 history",
        )
    return LocationContext(
        reference_price=float(resolved_reference_price),
        reference_closed_at=resolved_reference_closed_at,
        cutoff=cutoff_dt,
        current_atr_h4=float(current_atr),
        zones=_build_location_zones_from_history(
            history,
            cutoff,
            config,
            tick_size,
        ),
        h4_bars_considered=len(history),
        config=config,
        tick_size=tick_size,
    )


def score_location(side: str, context: Any) -> LocationResult:
    """Score one side from a previously built Location context.

    This is the strict scorer: malformed Location data raises
    :class:`LocationDataError`.  Call :func:`score_location_safe` at a
    pipeline boundary that needs a typed ``UNAVAILABLE`` result instead.
    """

    validate_location_side(side)
    if not isinstance(context, LocationContext):
        _invalid("INVALID_INPUT", "context", "expected LocationContext")
    validate_location_config(context.config)
    _require_positive_number(context.current_atr_h4, "context.current_atr_h4")
    reference_price_dec = Decimal(str(context.reference_price))
    current_atr_dec = Decimal(str(context.current_atr_h4))

    obstacle_selection = select_location_obstacle(side, context)
    anchor = select_location_anchor(side, context)

    if obstacle_selection.conflict:
        return LocationResult(
            side=side,
            raw=0,
            status="CONFLICT",
            reason_codes=("LOCATION_CONFLICT",),
            reference_price=context.reference_price,
            reference_closed_at=context.reference_closed_at,
            anchor=anchor,
            obstacle=obstacle_selection.obstacle,
            distance_atr=None,
            clearance_atr=0.0,
            proximity_factor=None,
            clearance_factor=0.0,
            model_version=context.config.model_version,
            config_used=context.config,
            raw_exact=0.0,
            cutoff=context.cutoff,
            h4_bars_considered=context.h4_bars_considered,
        )

    clearance_atr_dec: Decimal | None = None
    if obstacle_selection.obstacle is None:
        clearance_factor_dec = Decimal(str(context.config.unknown_clearance_factor))
    else:
        clearance_distance_dec = _decimal_forward_clearance(
            side,
            reference_price_dec,
            obstacle_selection.obstacle,
        )
        clearance_atr_dec = clearance_distance_dec / current_atr_dec
        clearance_factor_dec = _decimal_clamp(
            clearance_atr_dec / Decimal(str(context.config.clearance_full_at_atr)),
        )

    if anchor is None:
        return LocationResult(
            side=side,
            raw=0,
            status="NO_VALID_ANCHOR",
            reason_codes=("LOCATION_NO_VALID_ANCHOR",),
            reference_price=context.reference_price,
            reference_closed_at=context.reference_closed_at,
            anchor=None,
            obstacle=obstacle_selection.obstacle,
            distance_atr=None,
            clearance_atr=(
                float(clearance_atr_dec) if clearance_atr_dec is not None else None
            ),
            proximity_factor=None,
            clearance_factor=float(clearance_factor_dec),
            model_version=context.config.model_version,
            config_used=context.config,
            raw_exact=0.0,
            cutoff=context.cutoff,
            h4_bars_considered=context.h4_bars_considered,
        )

    distance_atr_dec = (
        _decimal_distance_to_interval(
            reference_price_dec,
            Decimal(str(anchor.low)),
            Decimal(str(anchor.high)),
        )
        / current_atr_dec
    )
    proximity_factor_dec = _decimal_clamp(
        Decimal("1")
        - distance_atr_dec / Decimal(str(context.config.proximity_zero_at_atr)),
    )
    raw_exact_dec = Decimal("25") * proximity_factor_dec * clearance_factor_dec
    raw = _round_half_up_to_int(raw_exact_dec, context.config.raw_max)
    reason_codes_list: list[str] = []
    status = "LIMITED_CONTEXT" if obstacle_selection.obstacle is None else "EVALUATED"
    if proximity_factor_dec == 0:
        reason_codes_list.append("LOCATION_ANCHOR_TOO_FAR")
    if obstacle_selection.obstacle is None:
        reason_codes_list.append("LOCATION_LIMITED_CONTEXT")

    return LocationResult(
        side=side,
        raw=raw,
        status=status,
        reason_codes=tuple(reason_codes_list),
        reference_price=context.reference_price,
        reference_closed_at=context.reference_closed_at,
        anchor=anchor,
        obstacle=obstacle_selection.obstacle,
        distance_atr=float(distance_atr_dec),
        clearance_atr=(
            float(clearance_atr_dec) if clearance_atr_dec is not None else None
        ),
        proximity_factor=float(proximity_factor_dec),
        clearance_factor=float(clearance_factor_dec),
        model_version=context.config.model_version,
        config_used=context.config,
        raw_exact=float(raw_exact_dec),
        cutoff=context.cutoff,
        h4_bars_considered=context.h4_bars_considered,
    )


def score_location_safe(side: str, context: Any) -> LocationResult:
    """Return ``UNAVAILABLE`` for expected Location-data errors only.

    The input side and context shape are validated before entering the
    boundary.  Only the engine's typed domain errors are converted; ordinary
    programming errors are deliberately allowed to propagate.
    """

    validate_location_side(side)
    if not isinstance(context, LocationContext):
        _invalid("INVALID_INPUT", "context", "expected LocationContext")
    try:
        return score_location(side, context)
    except LocationDataError as error:
        reason_code = (
            "LOCATION_INVALID_CONFIG"
            if error.field.startswith("config")
            else "LOCATION_INVALID_DATA"
        )
        return LocationResult(
            side=side,
            raw=None,
            status="UNAVAILABLE",
            reason_codes=(reason_code,),
            reference_price=context.reference_price,
            reference_closed_at=context.reference_closed_at,
            anchor=None,
            obstacle=None,
            distance_atr=None,
            clearance_atr=None,
            proximity_factor=None,
            clearance_factor=None,
            model_version=context.config.model_version,
            config_used=context.config,
            raw_exact=None,
            cutoff=context.cutoff,
            h4_bars_considered=context.h4_bars_considered,
        )


def _decimal_distance_to_interval(
    price: Decimal,
    low: Decimal,
    high: Decimal,
) -> Decimal:
    if price < low:
        return low - price
    if price > high:
        return price - high
    return Decimal("0")


def _decimal_forward_clearance(
    side: str,
    reference_price: Decimal,
    obstacle: LocationZone,
) -> Decimal:
    if side == "buy":
        return Decimal(str(obstacle.low)) - reference_price
    return reference_price - Decimal(str(obstacle.high))


def _decimal_clamp(value: Decimal) -> Decimal:
    return min(Decimal("1"), max(Decimal("0"), value))


def _round_half_up_to_int(value: Decimal | float, raw_max: int) -> int:
    rounded = int(
        (value if isinstance(value, Decimal) else Decimal(str(value))).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    return max(0, min(raw_max, rounded))


__all__ = [
    "DEFAULT_LOCATION_CONFIG",
    "LOCATION_ROLES",
    "LOCATION_RESULT_STATUSES",
    "LOCATION_STATUSES",
    "LOCATION_CONFIG_VERSION",
    "LOCATION_CONTEXT_SCHEMA_VERSION",
    "LOCATION_DETAIL_SCHEMA_VERSION",
    "LOCATION_TIMEFRAME_INTERVALS",
    "MIN_LOCATION_H4_BARS",
    "LOCATION_MODEL_VERSION",
    "LOCATION_ROUNDING_MODE",
    "LOCATION_ATR_PERIOD",
    "LocationDataError",
    "LocationConfig",
    "LocationContext",
    "LocationReference",
    "LocationResult",
    "LocationObstacleSelection",
    "LocationSwing",
    "LocationZone",
    "ClosedCandle",
    "build_location_context",
    "close_time_from_open_time",
    "closed_candles_at_cutoff",
    "closed_h4_history_at_cutoff",
    "build_location_zones",
    "deduplicate_location_zones",
    "distance_to_interval",
    "location_swing_points",
    "select_location_anchor",
    "select_location_obstacle",
    "update_location_zone_lifecycle",
    "reference_from_closed_h1",
    "resolve_location_config",
    "score_location",
    "score_location_safe",
    "validate_location_candle",
    "validate_location_config",
    "validate_location_inputs",
    "validate_location_side",
    "validate_location_zone",
    "validate_location_zones",
]
