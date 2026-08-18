"""Strict, immutable target contract for Scanner.

This module deliberately has no runtime wiring.  The executable scanner remains
on ``scanner-v3`` until the later direct-cutover steps activate this contract.
Creator APIs may stamp the locked identity; external/persisted readers never
default, coerce, upgrade, or relabel a payload.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
from types import MappingProxyType
from typing import Any, Literal, TypeAlias

from core.reason_codes import (
    SCANNER_FORBIDDEN_SCORED_FIELD,
    SCANNER_LEGACY_V3_AUDIT_ONLY,
    SCANNER_SCHEMA_INVALID,
    SCANNER_VERSION_MISMATCH,
    SCANNER_VERSION_MISSING,
)


# These are target identities only.  Do not replace the executable legacy constants
# in scanner_models.py until the atomic activation work is ready.
SCANNER_SCORING_VERSION = "scanner"
SCANNER_V4_FEATURE_VERSION = "scanner-features"
SCANNER_OUTPUT_SCHEMA_VERSION = "scanner-output"
SCANNER_SAFETY_POLICY_VERSION = "scanner-safety-policy"
SCANNER_MACRO_POLICY_VERSION = "scanner-macro-policy"
SCANNER_V4_RANKING_VERSION = "scanner-ranking"
SCANNER_SNAPSHOT_VERSION = "scanner-pair-snapshot"

# Bare names dropped the "v4" moniker on 2026-08-17.  Data written before the
# rename carries the legacy "…-v4" values; readers accept BOTH (see alias
# migration).  Nothing is ever rewritten to the new value automatically.
SCANNER_LEGACY_SCORING_VERSION = "scanner-v4"
SCANNER_LEGACY_FEATURE_VERSION = "scanner-features-v4"
SCANNER_LEGACY_OUTPUT_SCHEMA_VERSION = "scanner-output-v4"
SCANNER_LEGACY_SAFETY_POLICY_VERSION = "scanner-safety-policy-v4"
SCANNER_LEGACY_MACRO_POLICY_VERSION = "scanner-macro-policy-v4"
SCANNER_LEGACY_RANKING_VERSION = "scanner-ranking-v4"
SCANNER_LEGACY_SNAPSHOT_VERSION = "scanner-pair-snapshot-v4"

# Accepted version values per persisted field key: {new} ∪ {legacy}.  Helpers
# check membership (`value in ACCEPTED[field]`) instead of `value != VERSION`.
SCANNER_ACCEPTED_VERSIONS = MappingProxyType({
    "scoring_version": (SCANNER_SCORING_VERSION, SCANNER_LEGACY_SCORING_VERSION),
    "feature_version": (SCANNER_V4_FEATURE_VERSION, SCANNER_LEGACY_FEATURE_VERSION),
    "output_schema_version": (SCANNER_OUTPUT_SCHEMA_VERSION, SCANNER_LEGACY_OUTPUT_SCHEMA_VERSION),
    "safety_policy_version": (SCANNER_SAFETY_POLICY_VERSION, SCANNER_LEGACY_SAFETY_POLICY_VERSION),
    "macro_policy_version": (SCANNER_MACRO_POLICY_VERSION, SCANNER_LEGACY_MACRO_POLICY_VERSION),
    "ranking_version": (SCANNER_V4_RANKING_VERSION, SCANNER_LEGACY_RANKING_VERSION),
    "snapshot_version": (SCANNER_SNAPSHOT_VERSION, SCANNER_LEGACY_SNAPSHOT_VERSION),
})

SCANNER_VERSION_FIELDS = MappingProxyType({
    "scoring_version": SCANNER_SCORING_VERSION,
    "feature_version": SCANNER_V4_FEATURE_VERSION,
    "output_schema_version": SCANNER_OUTPUT_SCHEMA_VERSION,
    "safety_policy_version": SCANNER_SAFETY_POLICY_VERSION,
    "macro_policy_version": SCANNER_MACRO_POLICY_VERSION,
    "ranking_version": SCANNER_V4_RANKING_VERSION,
    "snapshot_version": SCANNER_SNAPSHOT_VERSION,
})

BUY = "buy"
SELL = "sell"
VALID_SIDES = frozenset({BUY, SELL})

PASS = "PASS"
CAUTION = "CAUTION"
BLOCK = "BLOCK"
UNKNOWN = "UNKNOWN"
VALID_GATE_STATUSES = frozenset({PASS, CAUTION, BLOCK, UNKNOWN})

ALIGNED = "aligned"
NEUTRAL = "neutral"
CONFLICT = "conflict"
MACRO_UNKNOWN = "unknown"
VALID_MACRO_STATUSES = frozenset({
    ALIGNED,
    NEUTRAL,
    CONFLICT,
    MACRO_UNKNOWN,
})

READY_NOW = "READY_NOW"
WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
WATCH_ZONE = "WATCH_ZONE"
OUT_OF_STRATEGY = "OUT_OF_STRATEGY"
BLOCKED = "BLOCKED"
DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
VALID_CANDIDATE_STATUSES = frozenset({
    READY_NOW,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
    OUT_OF_STRATEGY,
    BLOCKED,
    DATA_UNAVAILABLE,
})

SAFETY_CHECK_NAMES = (
    "connectivity",
    "data",
    "spread",
    "news",
    "volatility",
)

FORBIDDEN_SCORED_FIELDS = frozenset({
    "risk_condition",
    "macro_alignment",
})

PAYLOAD = "scanner"
PAYLOAD_LEGACY_V3 = "legacy_v3"
PAYLOAD_INVALID = "invalid"

GateStatus: TypeAlias = Literal["PASS", "CAUTION", "BLOCK", "UNKNOWN"]
MacroStatus: TypeAlias = Literal["aligned", "neutral", "conflict", "unknown"]
Side: TypeAlias = Literal["buy", "sell"]

_REASON_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_MAX_JSON_DEPTH = 64
_MAX_JSON_INTEGER = (1 << 63) - 1
_ALLOWED_TECHNICAL_WEIGHT_PROFILES = frozenset({
    (40, 20, 20, 20),
    (10, 10, 40, 40),
    (20, 10, 40, 30),
    (25, 25, 25, 25),
})
_CANONICAL_BLOCK_KEYS = frozenset({
    "market_safety",
    "macro_assessment",
    "macro_gate",
})
_ONLY_VERSION_KEYS = frozenset({
    "output_schema_version",
    "safety_policy_version",
    "macro_policy_version",
    "snapshot_version",
})
_SNAPSHOT_PROVENANCE_IDENTITY_FIELDS = frozenset({
    *SCANNER_VERSION_FIELDS,
    "scorer_version",
    "scanner_scorer_version",
    "scanner_feature_version",
    "scanner_contract_version",
    "output_version",
    "persistence_schema_version",
    "scoring_provenance",
})


class ScannerContractError(ValueError):
    """Fail-closed validation error carrying a stable reason code and path."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.detail = message
        super().__init__(f"{code} at {path}: {message}")


FrozenJson: TypeAlias = Any


def _error(path: str, message: str, *, code: str = SCANNER_SCHEMA_INVALID) -> None:
    raise ScannerContractError(code, path, message)


def _require_mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _error(path, "expected an object")
    for key in value:
        if type(key) is not str:
            _error(path, "object keys must be strings")
    return value


def _require_external_object(value: object, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        _error(path, "external payload must use a JSON object")
    for key in value:
        if type(key) is not str:
            _error(path, "external JSON object keys must be strings")
    return value


def _require_exact_keys(
    value: object,
    expected: set[str] | frozenset[str],
    path: str,
) -> Mapping[str, Any]:
    payload = _require_external_object(value, path)
    actual = set(payload)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        code = (
            SCANNER_VERSION_MISSING
            if any(key in SCANNER_VERSION_FIELDS for key in missing)
            else SCANNER_SCHEMA_INVALID
        )
        _error(path, f"missing required fields: {missing}", code=code)
    if unknown:
        forbidden = sorted(set(unknown) & FORBIDDEN_SCORED_FIELDS)
        code = (
            SCANNER_FORBIDDEN_SCORED_FIELD
            if forbidden
            else SCANNER_SCHEMA_INVALID
        )
        _error(path, f"unknown fields: {unknown}", code=code)
    return payload


def _require_text(value: object, path: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        _error(path, "expected a non-empty canonical string")
    if not _is_unicode_scalar_text(value):
        _error(path, "Unicode surrogate code points are forbidden")
    return value


def _is_unicode_scalar_text(value: str) -> bool:
    return not any(0xD800 <= ord(character) <= 0xDFFF for character in value)


def _optional_text(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, path)


def _require_choice(value: object, choices: frozenset[str], path: str) -> str:
    text = _require_text(value, path)
    if text not in choices:
        _error(path, f"unsupported value {text!r}; expected one of {sorted(choices)}")
    return text


def _optional_int(
    value: object,
    path: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        _error(path, "expected an integer or null")
    if minimum is not None and value < minimum:
        _error(path, f"must be >= {minimum}")
    if maximum is not None and value > maximum:
        _error(path, f"must be <= {maximum}")
    return value


def _require_int(
    value: object,
    path: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    result = _optional_int(value, path, minimum=minimum, maximum=maximum)
    if result is None:
        _error(path, "expected an integer")
    return result


def _optional_number(value: object, path: str) -> float | None:
    if value is None:
        return None
    if type(value) not in {int, float}:
        _error(path, "expected a finite number or null")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        _error(path, f"number cannot be represented safely: {exc}")
    if not math.isfinite(result):
        _error(path, "number must be finite")
    return result


def _require_datetime(value: object, path: str) -> datetime:
    if not isinstance(value, datetime):
        _error(path, "expected datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            _error(path, "datetime must be timezone-aware")
        return value.astimezone(timezone.utc)
    except ScannerContractError:
        raise
    except (OverflowError, ValueError) as exc:
        _error(path, f"datetime cannot be normalized safely: {exc}")


def _parse_datetime(value: object, path: str) -> datetime:
    text = _require_text(value, path)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (OverflowError, ValueError) as exc:
        _error(path, f"invalid ISO-8601 datetime: {exc}")
    return _require_datetime(parsed, path)


def _freeze_reason_codes(value: object, path: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        _error(path, "expected a reason-code array")
    result: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        code = _require_text(item, f"{path}[{index}]")
        if not _REASON_CODE_RE.fullmatch(code):
            _error(f"{path}[{index}]", "reason code must use UPPER_SNAKE_CASE")
        if code in seen:
            _error(f"{path}[{index}]", f"duplicate reason code {code!r}")
        seen.add(code)
        result.append(code)
    return tuple(result)


def _parse_reason_codes(value: object, path: str) -> tuple[str, ...]:
    if type(value) is not list:
        _error(path, "external payload reason codes must be a JSON array")
    return _freeze_reason_codes(value, path)


def _freeze_json(
    value: object,
    path: str,
    *,
    _active: set[int] | None = None,
    _depth: int = 0,
) -> FrozenJson:
    if _depth > _MAX_JSON_DEPTH:
        _error(path, f"JSON nesting exceeds {_MAX_JSON_DEPTH} levels")
    if value is None or type(value) is bool:
        return value
    if type(value) is int:
        if abs(value) > _MAX_JSON_INTEGER:
            _error(path, "JSON integer exceeds signed 64-bit range")
        return value
    if type(value) is str:
        if not _is_unicode_scalar_text(value):
            _error(path, "Unicode surrogate code points are forbidden")
        return value
    if type(value) is float:
        if not math.isfinite(value):
            _error(path, "JSON number must be finite")
        return value

    active = _active if _active is not None else set()
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            _error(path, "cyclic JSON object is not allowed")
        active.add(identity)
        try:
            frozen: dict[str, FrozenJson] = {}
            for key, item in value.items():
                if type(key) is not str:
                    _error(path, "JSON object keys must be strings")
                if not _is_unicode_scalar_text(key):
                    _error(path, "JSON object keys cannot contain Unicode surrogates")
                if key in FORBIDDEN_SCORED_FIELDS:
                    _error(
                        f"{path}.{key}",
                        f"scored field {key!r} is forbidden in V4",
                        code=SCANNER_FORBIDDEN_SCORED_FIELD,
                    )
                frozen[key] = _freeze_json(
                    item,
                    f"{path}.{key}",
                    _active=active,
                    _depth=_depth + 1,
                )
            return MappingProxyType(frozen)
        finally:
            active.remove(identity)

    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in active:
            _error(path, "cyclic JSON array is not allowed")
        active.add(identity)
        try:
            return tuple(
                _freeze_json(
                    item,
                    f"{path}[{index}]",
                    _active=active,
                    _depth=_depth + 1,
                )
                for index, item in enumerate(value)
            )
        finally:
            active.remove(identity)

    _error(path, f"unsupported JSON value type {type(value).__name__}")


def _freeze_external_json(
    value: object,
    path: str,
    *,
    _active: set[int] | None = None,
    _depth: int = 0,
) -> FrozenJson:
    """Freeze a decoded JSON value without accepting Python-only coercions."""

    if _depth > _MAX_JSON_DEPTH:
        _error(path, f"JSON nesting exceeds {_MAX_JSON_DEPTH} levels")
    if value is None or type(value) in {bool, int, float, str}:
        return _freeze_json(value, path, _depth=_depth)

    active = _active if _active is not None else set()
    if type(value) is dict:
        identity = id(value)
        if identity in active:
            _error(path, "cyclic JSON object is not allowed")
        active.add(identity)
        try:
            frozen: dict[str, FrozenJson] = {}
            for key, item in value.items():
                if type(key) is not str:
                    _error(path, "JSON object keys must be strings")
                if not _is_unicode_scalar_text(key):
                    _error(path, "JSON object keys cannot contain Unicode surrogates")
                if key in FORBIDDEN_SCORED_FIELDS:
                    _error(
                        f"{path}.{key}",
                        f"scored field {key!r} is forbidden in V4",
                        code=SCANNER_FORBIDDEN_SCORED_FIELD,
                    )
                frozen[key] = _freeze_external_json(
                    item,
                    f"{path}.{key}",
                    _active=active,
                    _depth=_depth + 1,
                )
            return MappingProxyType(frozen)
        finally:
            active.remove(identity)

    if type(value) is list:
        identity = id(value)
        if identity in active:
            _error(path, "cyclic JSON array is not allowed")
        active.add(identity)
        try:
            return tuple(
                _freeze_external_json(
                    item,
                    f"{path}[{index}]",
                    _active=active,
                    _depth=_depth + 1,
                )
                for index, item in enumerate(value)
            )
        finally:
            active.remove(identity)

    _error(
        path,
        f"external payload contains non-JSON type {type(value).__name__}",
    )


def _validate_external_json_shape(
    value: object,
    path: str,
    *,
    _active: set[int] | None = None,
    _depth: int = 0,
) -> None:
    """Validate decoded JSON shape without interpreting Scanner field names."""

    if _depth > _MAX_JSON_DEPTH:
        _error(path, f"JSON nesting exceeds {_MAX_JSON_DEPTH} levels")
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        if abs(value) > _MAX_JSON_INTEGER:
            _error(path, "JSON integer exceeds signed 64-bit range")
        return
    if type(value) is float:
        if not math.isfinite(value):
            _error(path, "JSON number must be finite")
        return
    if type(value) is str:
        if not _is_unicode_scalar_text(value):
            _error(path, "Unicode surrogate code points are forbidden")
        return

    active = _active if _active is not None else set()
    if type(value) is dict:
        identity = id(value)
        if identity in active:
            _error(path, "cyclic JSON object is not allowed")
        active.add(identity)
        try:
            for key, item in value.items():
                if type(key) is not str:
                    _error(path, "JSON object keys must be strings")
                if not _is_unicode_scalar_text(key):
                    _error(path, "JSON object keys cannot contain Unicode surrogates")
                _validate_external_json_shape(
                    item,
                    f"{path}.{key}",
                    _active=active,
                    _depth=_depth + 1,
                )
        finally:
            active.remove(identity)
        return
    if type(value) is list:
        identity = id(value)
        if identity in active:
            _error(path, "cyclic JSON array is not allowed")
        active.add(identity)
        try:
            for index, item in enumerate(value):
                _validate_external_json_shape(
                    item,
                    f"{path}[{index}]",
                    _active=active,
                    _depth=_depth + 1,
                )
        finally:
            active.remove(identity)
        return
    _error(path, f"external payload contains non-JSON type {type(value).__name__}")


def _freeze_object(value: object, path: str) -> Mapping[str, FrozenJson]:
    _require_mapping(value, path)
    frozen = _freeze_json(value, path)
    if not isinstance(frozen, Mapping):  # pragma: no cover - defensive narrowing
        _error(path, "expected an object")
    return frozen


def _freeze_external_object(value: object, path: str) -> Mapping[str, FrozenJson]:
    _require_external_object(value, path)
    frozen = _freeze_external_json(value, path)
    if not isinstance(frozen, Mapping):  # pragma: no cover - defensive narrowing
        _error(path, "expected an object")
    return frozen


def _thaw_json(value: FrozenJson) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _reject_contract_identity_in_provenance(
    value: FrozenJson,
    path: str,
    *,
    _depth: int = 0,
) -> None:
    """Keep version identity singular at the canonical snapshot boundary."""

    if _depth > _MAX_JSON_DEPTH:  # pragma: no cover - frozen by an earlier guard
        _error(path, f"JSON nesting exceeds {_MAX_JSON_DEPTH} levels")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in _SNAPSHOT_PROVENANCE_IDENTITY_FIELDS:
                _error(
                    f"{path}.{key}",
                    "contract identity fields are forbidden inside provenance",
                )
            _reject_contract_identity_in_provenance(
                item,
                f"{path}.{key}",
                _depth=_depth + 1,
            )
    elif isinstance(value, tuple):
        for index, item in enumerate(value):
            _reject_contract_identity_in_provenance(
                item,
                f"{path}[{index}]",
                _depth=_depth + 1,
            )


def _reject_nonpass_without_reason(
    status: str,
    reason_codes: tuple[str, ...],
    path: str,
) -> None:
    if status != PASS and not reason_codes:
        _error(path, f"{status} requires at least one reason code")


@dataclass(frozen=True, slots=True)
class TechnicalComponent:
    raw: int | None
    raw_max: int
    weight: int | None
    contribution: float | None

    def __post_init__(self) -> None:
        raw_max = _require_int(self.raw_max, "technical_component.raw_max", minimum=1)
        raw = _optional_int(
            self.raw,
            "technical_component.raw",
            minimum=0,
            maximum=raw_max,
        )
        weight = _optional_int(
            self.weight,
            "technical_component.weight",
            minimum=0,
            maximum=100,
        )
        contribution = _optional_number(
            self.contribution,
            "technical_component.contribution",
        )
        if contribution is not None and contribution < 0:
            _error("technical_component.contribution", "must be >= 0")
        if contribution is not None and weight is None:
            _error("technical_component.contribution", "requires a weight")
        if contribution is not None and weight is not None and contribution > weight:
            _error("technical_component.contribution", "cannot exceed weight")
        if (raw is None) != (contribution is None):
            _error(
                "technical_component",
                "raw and contribution must both be present or both be null",
            )
        if raw is not None and weight is not None and contribution is not None:
            expected = float(Fraction(raw * weight, raw_max))
            if contribution != expected:
                _error(
                    "technical_component.contribution",
                    "must equal raw / raw_max * weight without component rounding",
                )
        object.__setattr__(self, "raw", raw)
        object.__setattr__(self, "raw_max", raw_max)
        object.__setattr__(self, "weight", weight)
        object.__setattr__(self, "contribution", contribution)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw,
            "raw_max": self.raw_max,
            "weight": self.weight,
            "contribution": self.contribution,
        }

    @classmethod
    def from_dict(cls, value: object, *, path: str = "technical_component") -> TechnicalComponent:
        payload = _require_exact_keys(
            value,
            {"raw", "raw_max", "weight", "contribution"},
            path,
        )
        return cls(
            raw=_optional_int(payload["raw"], f"{path}.raw"),
            raw_max=_require_int(payload["raw_max"], f"{path}.raw_max", minimum=1),
            weight=_optional_int(
                payload["weight"],
                f"{path}.weight",
                minimum=0,
                maximum=100,
            ),
            contribution=_optional_number(
                payload["contribution"],
                f"{path}.contribution",
            ),
        )


@dataclass(frozen=True, slots=True)
class TechnicalBreakdown:
    trend: TechnicalComponent
    momentum: TechnicalComponent
    location: TechnicalComponent
    smc: TechnicalComponent

    def __post_init__(self) -> None:
        components = {
            "trend": (self.trend, 25),
            "momentum": (self.momentum, 20),
            "location": (self.location, 25),
            "smc": (self.smc, 15),
        }
        for name, (component, expected_max) in components.items():
            if type(component) is not TechnicalComponent:
                _error(f"technical_breakdown.{name}", "expected TechnicalComponent")
            if component.raw_max != expected_max:
                _error(
                    f"technical_breakdown.{name}.raw_max",
                    f"must equal locked raw max {expected_max}",
                )
        weights = [component.weight for component, _ in components.values()]
        if any(weight is None for weight in weights) and any(
            weight is not None for weight in weights
        ):
            _error(
                "technical_breakdown",
                "component weights must be either all present or all null",
            )
        if all(weight is not None for weight in weights):
            weight_profile = tuple(weights)
            if weight_profile not in _ALLOWED_TECHNICAL_WEIGHT_PROFILES:
                _error(
                    "technical_breakdown",
                    "component weights must match a locked V4 regime profile",
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "trend": self.trend.to_dict(),
            "momentum": self.momentum.to_dict(),
            "location": self.location.to_dict(),
            "smc": self.smc.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: object, *, path: str = "technical_breakdown") -> TechnicalBreakdown:
        payload = _require_exact_keys(
            value,
            {"trend", "momentum", "location", "smc"},
            path,
        )
        return cls(
            trend=TechnicalComponent.from_dict(
                payload["trend"], path=f"{path}.trend"
            ),
            momentum=TechnicalComponent.from_dict(
                payload["momentum"], path=f"{path}.momentum"
            ),
            location=TechnicalComponent.from_dict(
                payload["location"], path=f"{path}.location"
            ),
            smc=TechnicalComponent.from_dict(payload["smc"], path=f"{path}.smc"),
        )


@dataclass(frozen=True, slots=True)
class SideScore:
    side: Side
    technical_signal_score: int | None
    technical_breakdown: TechnicalBreakdown
    evidence_score: int | None
    evidence_source: str
    execution_quality_score: int | None
    execution_quality_source: str
    setup_score: int | None
    final_score: int | None
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        side = _require_choice(self.side, VALID_SIDES, "side_score.side")
        if type(self.technical_breakdown) is not TechnicalBreakdown:
            _error("side_score.technical_breakdown", "expected TechnicalBreakdown")
        technical = _optional_int(
            self.technical_signal_score,
            "side_score.technical_signal_score",
            minimum=0,
            maximum=100,
        )
        evidence = _optional_int(
            self.evidence_score,
            "side_score.evidence_score",
            minimum=0,
            maximum=100,
        )
        execution = _optional_int(
            self.execution_quality_score,
            "side_score.execution_quality_score",
            minimum=0,
            maximum=100,
        )
        setup = _optional_int(
            self.setup_score,
            "side_score.setup_score",
            minimum=0,
            maximum=100,
        )
        final = _optional_int(
            self.final_score,
            "side_score.final_score",
            minimum=0,
            maximum=100,
        )
        if final != setup:
            _error("side_score.final_score", "must equal setup_score")
        if technical is None and setup is not None:
            _error(
                "side_score.setup_score",
                "must be null when technical_signal_score is null",
            )
        components = (
            ("trend", self.technical_breakdown.trend),
            ("momentum", self.technical_breakdown.momentum),
            ("location", self.technical_breakdown.location),
            ("smc", self.technical_breakdown.smc),
        )
        if technical is not None:
            for name, component in components:
                if component.raw is None or component.contribution is None:
                    _error(
                        f"side_score.technical_breakdown.{name}",
                        "must be complete when technical score is present",
                    )
                if component.weight is None:
                    _error(
                        f"side_score.technical_breakdown.{name}.weight",
                        "must be present when technical score is present",
                    )
            exact_total = sum(
                (
                    Fraction(
                        component.raw * component.weight,
                        component.raw_max,
                    )
                    for _, component in components
                    if component.raw is not None and component.weight is not None
                ),
                Fraction(0, 1),
            )
            exact_total = max(Fraction(0, 1), min(Fraction(100, 1), exact_total))
            quotient, remainder = divmod(
                exact_total.numerator,
                exact_total.denominator,
            )
            expected_technical = quotient + int(
                remainder * 2 >= exact_total.denominator
            )
            if technical != expected_technical:
                _error(
                    "side_score.technical_signal_score",
                    "must equal the round-once ROUND_HALF_UP technical breakdown sum",
                )
        else:
            for name, component in components:
                if component.raw is not None or component.contribution is not None:
                    _error(
                        f"side_score.technical_breakdown.{name}",
                        "must keep raw and contribution null when technical score is null",
                    )
        reasons = _freeze_reason_codes(self.reason_codes, "side_score.reason_codes")
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "technical_signal_score", technical)
        object.__setattr__(self, "evidence_score", evidence)
        object.__setattr__(self, "execution_quality_score", execution)
        object.__setattr__(self, "setup_score", setup)
        object.__setattr__(self, "final_score", final)
        object.__setattr__(
            self,
            "evidence_source",
            _require_text(self.evidence_source, "side_score.evidence_source"),
        )
        object.__setattr__(
            self,
            "execution_quality_source",
            _require_text(
                self.execution_quality_source,
                "side_score.execution_quality_source",
            ),
        )
        object.__setattr__(self, "reason_codes", reasons)

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "technical_signal_score": self.technical_signal_score,
            "technical_breakdown": self.technical_breakdown.to_dict(),
            "evidence_score": self.evidence_score,
            "evidence_source": self.evidence_source,
            "execution_quality_score": self.execution_quality_score,
            "execution_quality_source": self.execution_quality_source,
            "setup_score": self.setup_score,
            "final_score": self.final_score,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_dict(cls, value: object, *, path: str = "side_score") -> SideScore:
        payload = _require_exact_keys(
            value,
            {
                "side",
                "technical_signal_score",
                "technical_breakdown",
                "evidence_score",
                "evidence_source",
                "execution_quality_score",
                "execution_quality_source",
                "setup_score",
                "final_score",
                "reason_codes",
            },
            path,
        )
        return cls(
            side=_require_choice(payload["side"], VALID_SIDES, f"{path}.side"),
            technical_signal_score=_optional_int(
                payload["technical_signal_score"],
                f"{path}.technical_signal_score",
                minimum=0,
                maximum=100,
            ),
            technical_breakdown=TechnicalBreakdown.from_dict(
                payload["technical_breakdown"],
                path=f"{path}.technical_breakdown",
            ),
            evidence_score=_optional_int(
                payload["evidence_score"],
                f"{path}.evidence_score",
                minimum=0,
                maximum=100,
            ),
            evidence_source=_require_text(
                payload["evidence_source"], f"{path}.evidence_source"
            ),
            execution_quality_score=_optional_int(
                payload["execution_quality_score"],
                f"{path}.execution_quality_score",
                minimum=0,
                maximum=100,
            ),
            execution_quality_source=_require_text(
                payload["execution_quality_source"],
                f"{path}.execution_quality_source",
            ),
            setup_score=_optional_int(
                payload["setup_score"],
                f"{path}.setup_score",
                minimum=0,
                maximum=100,
            ),
            final_score=_optional_int(
                payload["final_score"],
                f"{path}.final_score",
                minimum=0,
                maximum=100,
            ),
            reason_codes=_parse_reason_codes(
                payload["reason_codes"], f"{path}.reason_codes"
            ),
        )


@dataclass(frozen=True, slots=True)
class GateCheck:
    name: str
    status: GateStatus
    reason_codes: tuple[str, ...]
    observed_value: FrozenJson
    threshold: FrozenJson
    policy_version: str
    checked_at: datetime
    source: str
    provenance: Mapping[str, FrozenJson]

    def __post_init__(self) -> None:
        name = _require_choice(self.name, frozenset(SAFETY_CHECK_NAMES), "gate_check.name")
        status = _require_choice(self.status, VALID_GATE_STATUSES, "gate_check.status")
        reasons = _freeze_reason_codes(self.reason_codes, "gate_check.reason_codes")
        _reject_nonpass_without_reason(status, reasons, "gate_check.reason_codes")
        observed_value = _freeze_json(
            self.observed_value, "gate_check.observed_value"
        )
        provenance = _freeze_object(self.provenance, "gate_check.provenance")
        _reject_contract_identity_in_provenance(
            provenance, "gate_check.provenance"
        )
        if status == PASS and observed_value is None:
            _error(
                "gate_check.observed_value",
                "PASS requires an explicit observed value; missing data must be UNKNOWN",
            )
        if status == PASS and not provenance:
            _error(
                "gate_check.provenance",
                "PASS requires non-empty evidence provenance",
            )
        policy = _require_text(self.policy_version, "gate_check.policy_version")
        if policy not in (SCANNER_SAFETY_POLICY_VERSION, SCANNER_LEGACY_SAFETY_POLICY_VERSION):
            _error(
                "gate_check.policy_version",
                f"expected {SCANNER_SAFETY_POLICY_VERSION!r}",
                code=SCANNER_VERSION_MISMATCH,
            )
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reason_codes", reasons)
        object.__setattr__(
            self,
            "observed_value",
            observed_value,
        )
        object.__setattr__(
            self,
            "threshold",
            _freeze_json(self.threshold, "gate_check.threshold"),
        )
        object.__setattr__(self, "policy_version", policy)
        object.__setattr__(
            self,
            "checked_at",
            _require_datetime(self.checked_at, "gate_check.checked_at"),
        )
        object.__setattr__(self, "source", _require_text(self.source, "gate_check.source"))
        object.__setattr__(
            self,
            "provenance",
            provenance,
        )

    def to_dict(self, *, include_name: bool = True) -> dict[str, Any]:
        payload = {
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "observed_value": _thaw_json(self.observed_value),
            "threshold": _thaw_json(self.threshold),
            "policy_version": self.policy_version,
            "checked_at": self.checked_at.isoformat(),
            "source": self.source,
            "provenance": _thaw_json(self.provenance),
        }
        if include_name:
            return {"name": self.name, **payload}
        return payload

    @classmethod
    def from_dict(
        cls,
        value: object,
        *,
        name: str | None = None,
        path: str = "gate_check",
    ) -> GateCheck:
        fields = {
            "status",
            "reason_codes",
            "observed_value",
            "threshold",
            "policy_version",
            "checked_at",
            "source",
            "provenance",
        }
        payload = _require_exact_keys(
            value,
            fields if name is not None else fields | {"name"},
            path,
        )
        check_name = name if name is not None else payload["name"]
        return cls(
            name=_require_choice(
                check_name,
                frozenset(SAFETY_CHECK_NAMES),
                f"{path}.name",
            ),
            status=_require_choice(
                payload["status"], VALID_GATE_STATUSES, f"{path}.status"
            ),
            reason_codes=_parse_reason_codes(
                payload["reason_codes"], f"{path}.reason_codes"
            ),
            observed_value=_freeze_external_json(
                payload["observed_value"], f"{path}.observed_value"
            ),
            threshold=_freeze_external_json(
                payload["threshold"], f"{path}.threshold"
            ),
            policy_version=_require_text(
                payload["policy_version"], f"{path}.policy_version"
            ),
            checked_at=_parse_datetime(payload["checked_at"], f"{path}.checked_at"),
            source=_require_text(payload["source"], f"{path}.source"),
            provenance=_freeze_external_object(
                payload["provenance"], f"{path}.provenance"
            ),
        )


@dataclass(frozen=True, slots=True)
class MarketSafetyResult:
    status: GateStatus
    checks: tuple[GateCheck, ...]
    reason_codes: tuple[str, ...]
    policy_version: str

    def __post_init__(self) -> None:
        status = _require_choice(
            self.status, VALID_GATE_STATUSES, "market_safety.status"
        )
        if not isinstance(self.checks, (list, tuple)):
            _error("market_safety.checks", "expected GateCheck collection")
        by_name: dict[str, GateCheck] = {}
        for index, check in enumerate(self.checks):
            if type(check) is not GateCheck:
                _error(f"market_safety.checks[{index}]", "expected GateCheck")
            if check.name in by_name:
                _error("market_safety.checks", f"duplicate check {check.name!r}")
            by_name[check.name] = check
        if set(by_name) != set(SAFETY_CHECK_NAMES):
            _error(
                "market_safety.checks",
                f"must contain exactly {list(SAFETY_CHECK_NAMES)}",
            )
        policy = _require_text(self.policy_version, "market_safety.policy_version")
        if policy not in (SCANNER_SAFETY_POLICY_VERSION, SCANNER_LEGACY_SAFETY_POLICY_VERSION):
            _error(
                "market_safety.policy_version",
                f"expected {SCANNER_SAFETY_POLICY_VERSION!r}",
                code=SCANNER_VERSION_MISMATCH,
            )
        if any(check.policy_version != policy for check in by_name.values()):
            _error(
                "market_safety.checks",
                "all check policy versions must match aggregate policy version",
                code=SCANNER_VERSION_MISMATCH,
            )
        reasons = _freeze_reason_codes(
            self.reason_codes, "market_safety.reason_codes"
        )
        _reject_nonpass_without_reason(status, reasons, "market_safety.reason_codes")
        check_statuses = tuple(check.status for check in by_name.values())
        unique_check_statuses = frozenset(check_statuses)
        if unique_check_statuses == {PASS} and status != PASS:
            _error(
                "market_safety.status",
                "all PASS sub-checks require aggregate PASS",
            )
        if BLOCK in unique_check_statuses and status != BLOCK:
            _error(
                "market_safety.status",
                "a BLOCK sub-check requires aggregate BLOCK",
            )
        if BLOCK not in unique_check_statuses and status == BLOCK:
            _error(
                "market_safety.status",
                "aggregate BLOCK requires a BLOCK sub-check",
            )
        if status == PASS and unique_check_statuses != {PASS}:
            _error(
                "market_safety.status",
                "aggregate PASS requires every safety sub-check to PASS",
            )
        if (
            unique_check_statuses != {PASS}
            and BLOCK not in unique_check_statuses
            and status not in unique_check_statuses
        ):
            _error(
                "market_safety.status",
                "aggregate status must reflect a non-PASS sub-check",
            )
        object.__setattr__(self, "status", status)
        object.__setattr__(
            self,
            "checks",
            tuple(by_name[name] for name in SAFETY_CHECK_NAMES),
        )
        object.__setattr__(self, "reason_codes", reasons)
        object.__setattr__(self, "policy_version", policy)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checks": {
                check.name: check.to_dict(include_name=False) for check in self.checks
            },
            "reason_codes": list(self.reason_codes),
            "policy_version": self.policy_version,
        }

    @classmethod
    def from_dict(cls, value: object, *, path: str = "market_safety") -> MarketSafetyResult:
        payload = _require_exact_keys(
            value,
            {"status", "checks", "reason_codes", "policy_version"},
            path,
        )
        checks_payload = _require_exact_keys(
            payload["checks"], set(SAFETY_CHECK_NAMES), f"{path}.checks"
        )
        return cls(
            status=_require_choice(
                payload["status"], VALID_GATE_STATUSES, f"{path}.status"
            ),
            checks=tuple(
                GateCheck.from_dict(
                    checks_payload[name],
                    name=name,
                    path=f"{path}.checks.{name}",
                )
                for name in SAFETY_CHECK_NAMES
            ),
            reason_codes=_parse_reason_codes(
                payload["reason_codes"], f"{path}.reason_codes"
            ),
            policy_version=_require_text(
                payload["policy_version"], f"{path}.policy_version"
            ),
        )


@dataclass(frozen=True, slots=True)
class MacroAssessment:
    raw_buy: int | None
    raw_sell: int | None
    confidence: float | None
    status: MacroStatus
    correlation_context: Mapping[str, FrozenJson]
    provenance: Mapping[str, FrozenJson]

    def __post_init__(self) -> None:
        confidence = _optional_number(self.confidence, "macro_assessment.confidence")
        if confidence is not None and not 0 <= confidence <= 1:
            _error("macro_assessment.confidence", "must be within 0..1")
        raw_buy = _optional_int(
            self.raw_buy,
            "macro_assessment.raw_buy",
            minimum=0,
            maximum=30,
        )
        raw_sell = _optional_int(
            self.raw_sell,
            "macro_assessment.raw_sell",
            minimum=0,
            maximum=30,
        )
        status = _require_choice(
            self.status, VALID_MACRO_STATUSES, "macro_assessment.status"
        )
        correlation_context = _freeze_object(
            self.correlation_context,
            "macro_assessment.correlation_context",
        )
        provenance = _freeze_object(
            self.provenance, "macro_assessment.provenance"
        )
        _reject_contract_identity_in_provenance(
            provenance, "macro_assessment.provenance"
        )
        if (
            raw_buy is None
            or raw_sell is None
            or confidence is None
            or not provenance
        ) and status != MACRO_UNKNOWN:
            _error(
                "macro_assessment.status",
                "missing raw/confidence/provenance data requires status 'unknown'",
            )
        object.__setattr__(self, "raw_buy", raw_buy)
        object.__setattr__(self, "raw_sell", raw_sell)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "correlation_context", correlation_context)
        object.__setattr__(self, "provenance", provenance)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_buy": self.raw_buy,
            "raw_sell": self.raw_sell,
            "confidence": self.confidence,
            "status": self.status,
            "correlation_context": _thaw_json(self.correlation_context),
            "provenance": _thaw_json(self.provenance),
        }

    @classmethod
    def from_dict(cls, value: object, *, path: str = "macro_assessment") -> MacroAssessment:
        payload = _require_exact_keys(
            value,
            {
                "raw_buy",
                "raw_sell",
                "confidence",
                "status",
                "correlation_context",
                "provenance",
            },
            path,
        )
        return cls(
            raw_buy=_optional_int(
                payload["raw_buy"], f"{path}.raw_buy", minimum=0, maximum=30
            ),
            raw_sell=_optional_int(
                payload["raw_sell"], f"{path}.raw_sell", minimum=0, maximum=30
            ),
            confidence=_optional_number(payload["confidence"], f"{path}.confidence"),
            status=_require_choice(
                payload["status"], VALID_MACRO_STATUSES, f"{path}.status"
            ),
            correlation_context=_freeze_external_object(
                payload["correlation_context"], f"{path}.correlation_context"
            ),
            provenance=_freeze_external_object(
                payload["provenance"], f"{path}.provenance"
            ),
        )


@dataclass(frozen=True, slots=True)
class MacroGateResult:
    assessed_side: Side | None
    status: GateStatus
    decision_cap: str | None
    reason_codes: tuple[str, ...]
    policy_version: str
    checked_at: datetime
    provenance: Mapping[str, FrozenJson]

    def __post_init__(self) -> None:
        side = (
            None
            if self.assessed_side is None
            else _require_choice(
                self.assessed_side, VALID_SIDES, "macro_gate.assessed_side"
            )
        )
        status = _require_choice(self.status, VALID_GATE_STATUSES, "macro_gate.status")
        reasons = _freeze_reason_codes(self.reason_codes, "macro_gate.reason_codes")
        _reject_nonpass_without_reason(status, reasons, "macro_gate.reason_codes")
        decision_cap = _optional_text(self.decision_cap, "macro_gate.decision_cap")
        provenance = _freeze_object(self.provenance, "macro_gate.provenance")
        _reject_contract_identity_in_provenance(
            provenance, "macro_gate.provenance"
        )
        if status == PASS and side is None:
            _error(
                "macro_gate.assessed_side",
                "PASS requires an explicit assessed side",
            )
        if status == PASS and decision_cap is not None:
            _error(
                "macro_gate.decision_cap",
                "PASS cannot carry a decision cap",
            )
        if status == PASS and not provenance:
            _error(
                "macro_gate.provenance",
                "PASS requires non-empty assessment provenance",
            )
        policy = _require_text(self.policy_version, "macro_gate.policy_version")
        if policy not in (SCANNER_MACRO_POLICY_VERSION, SCANNER_LEGACY_MACRO_POLICY_VERSION):
            _error(
                "macro_gate.policy_version",
                f"expected {SCANNER_MACRO_POLICY_VERSION!r}",
                code=SCANNER_VERSION_MISMATCH,
            )
        object.__setattr__(self, "assessed_side", side)
        object.__setattr__(self, "status", status)
        object.__setattr__(
            self,
            "decision_cap",
            decision_cap,
        )
        object.__setattr__(self, "reason_codes", reasons)
        object.__setattr__(self, "policy_version", policy)
        object.__setattr__(
            self,
            "checked_at",
            _require_datetime(self.checked_at, "macro_gate.checked_at"),
        )
        object.__setattr__(
            self,
            "provenance",
            provenance,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "assessed_side": self.assessed_side,
            "status": self.status,
            "decision_cap": self.decision_cap,
            "reason_codes": list(self.reason_codes),
            "policy_version": self.policy_version,
            "checked_at": self.checked_at.isoformat(),
            "provenance": _thaw_json(self.provenance),
        }

    @classmethod
    def from_dict(cls, value: object, *, path: str = "macro_gate") -> MacroGateResult:
        payload = _require_exact_keys(
            value,
            {
                "assessed_side",
                "status",
                "decision_cap",
                "reason_codes",
                "policy_version",
                "checked_at",
                "provenance",
            },
            path,
        )
        side_value = payload["assessed_side"]
        return cls(
            assessed_side=(
                None
                if side_value is None
                else _require_choice(side_value, VALID_SIDES, f"{path}.assessed_side")
            ),
            status=_require_choice(
                payload["status"], VALID_GATE_STATUSES, f"{path}.status"
            ),
            decision_cap=_optional_text(
                payload["decision_cap"], f"{path}.decision_cap"
            ),
            reason_codes=_parse_reason_codes(
                payload["reason_codes"], f"{path}.reason_codes"
            ),
            policy_version=_require_text(
                payload["policy_version"], f"{path}.policy_version"
            ),
            checked_at=_parse_datetime(payload["checked_at"], f"{path}.checked_at"),
            provenance=_freeze_external_object(
                payload["provenance"], f"{path}.provenance"
            ),
        )


@dataclass(frozen=True, slots=True)
class DecisionResult:
    selected_side: Side | None
    score_gap: int | None
    candidate_status: str
    decision_cap: str | None
    gate_codes: tuple[str, ...]
    reason_codes: tuple[str, ...]
    block_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        side = (
            None
            if self.selected_side is None
            else _require_choice(self.selected_side, VALID_SIDES, "decision.selected_side")
        )
        object.__setattr__(self, "selected_side", side)
        object.__setattr__(
            self,
            "score_gap",
            _optional_int(
                self.score_gap,
                "decision.score_gap",
                minimum=0,
                maximum=100,
            ),
        )
        candidate_status = _require_choice(
            self.candidate_status,
            VALID_CANDIDATE_STATUSES,
            "decision.candidate_status",
        )
        if candidate_status == READY_NOW and side is None:
            _error(
                "decision.selected_side",
                "READY_NOW requires an explicit selected side",
            )
        decision_cap = _optional_text(self.decision_cap, "decision.decision_cap")
        gate_codes = _freeze_reason_codes(self.gate_codes, "decision.gate_codes")
        reason_codes = _freeze_reason_codes(self.reason_codes, "decision.reason_codes")
        block_codes = _freeze_reason_codes(self.block_codes, "decision.block_codes")
        if candidate_status == READY_NOW and decision_cap is not None:
            _error(
                "decision.decision_cap",
                "READY_NOW cannot carry a decision cap",
            )
        if candidate_status == READY_NOW and block_codes:
            _error(
                "decision.block_codes",
                "READY_NOW cannot carry block codes",
            )
        object.__setattr__(self, "candidate_status", candidate_status)
        object.__setattr__(self, "decision_cap", decision_cap)
        object.__setattr__(self, "gate_codes", gate_codes)
        object.__setattr__(self, "reason_codes", reason_codes)
        object.__setattr__(self, "block_codes", block_codes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_side": self.selected_side,
            "score_gap": self.score_gap,
            "candidate_status": self.candidate_status,
            "decision_cap": self.decision_cap,
            "gate_codes": list(self.gate_codes),
            "reason_codes": list(self.reason_codes),
            "block_codes": list(self.block_codes),
        }

    @classmethod
    def from_dict(cls, value: object, *, path: str = "decision") -> DecisionResult:
        payload = _require_exact_keys(
            value,
            {
                "selected_side",
                "score_gap",
                "candidate_status",
                "decision_cap",
                "gate_codes",
                "reason_codes",
                "block_codes",
            },
            path,
        )
        side_value = payload["selected_side"]
        return cls(
            selected_side=(
                None
                if side_value is None
                else _require_choice(side_value, VALID_SIDES, f"{path}.selected_side")
            ),
            score_gap=_optional_int(
                payload["score_gap"],
                f"{path}.score_gap",
                minimum=0,
                maximum=100,
            ),
            candidate_status=_require_choice(
                payload["candidate_status"],
                VALID_CANDIDATE_STATUSES,
                f"{path}.candidate_status",
            ),
            decision_cap=_optional_text(
                payload["decision_cap"], f"{path}.decision_cap"
            ),
            gate_codes=_parse_reason_codes(
                payload["gate_codes"], f"{path}.gate_codes"
            ),
            reason_codes=_parse_reason_codes(
                payload["reason_codes"], f"{path}.reason_codes"
            ),
            block_codes=_parse_reason_codes(
                payload["block_codes"], f"{path}.block_codes"
            ),
        )


@dataclass(frozen=True, slots=True)
class CanonicalPairSnapshot:
    scoring_version: str
    feature_version: str
    output_schema_version: str
    safety_policy_version: str
    macro_policy_version: str
    ranking_version: str
    snapshot_version: str
    snapshot_id: str
    symbol: str
    captured_at: datetime
    side_scores: tuple[SideScore, ...]
    market_safety: MarketSafetyResult
    macro_assessment: MacroAssessment
    macro_gate: MacroGateResult
    decision: DecisionResult
    provenance: Mapping[str, FrozenJson]

    def __post_init__(self) -> None:
        for field, expected in SCANNER_VERSION_FIELDS.items():
            actual = _require_text(getattr(self, field), f"snapshot.{field}")
            if actual != expected:
                _error(
                    f"snapshot.{field}",
                    f"expected {expected!r}, got {actual!r}",
                    code=SCANNER_VERSION_MISMATCH,
                )
            object.__setattr__(self, field, actual)
        object.__setattr__(
            self,
            "snapshot_id",
            _require_text(self.snapshot_id, "snapshot.snapshot_id"),
        )
        object.__setattr__(self, "symbol", _require_text(self.symbol, "snapshot.symbol"))
        object.__setattr__(
            self,
            "captured_at",
            _require_datetime(self.captured_at, "snapshot.captured_at"),
        )
        if not isinstance(self.side_scores, (list, tuple)):
            _error("snapshot.side_scores", "expected SideScore collection")
        by_side: dict[str, SideScore] = {}
        for index, score in enumerate(self.side_scores):
            if type(score) is not SideScore:
                _error(f"snapshot.side_scores[{index}]", "expected SideScore")
            if score.side in by_side:
                _error("snapshot.side_scores", f"duplicate side {score.side!r}")
            by_side[score.side] = score
        if set(by_side) != VALID_SIDES:
            _error("snapshot.side_scores", "must contain exactly buy and sell")
        if type(self.market_safety) is not MarketSafetyResult:
            _error("snapshot.market_safety", "expected MarketSafetyResult")
        if type(self.macro_assessment) is not MacroAssessment:
            _error("snapshot.macro_assessment", "expected MacroAssessment")
        if type(self.macro_gate) is not MacroGateResult:
            _error("snapshot.macro_gate", "expected MacroGateResult")
        if type(self.decision) is not DecisionResult:
            _error("snapshot.decision", "expected DecisionResult")
        if self.market_safety.policy_version != self.safety_policy_version:
            _error(
                "snapshot.market_safety.policy_version",
                "does not match top-level safety_policy_version",
                code=SCANNER_VERSION_MISMATCH,
            )
        if self.macro_gate.policy_version != self.macro_policy_version:
            _error(
                "snapshot.macro_gate.policy_version",
                "does not match top-level macro_policy_version",
                code=SCANNER_VERSION_MISMATCH,
            )
        buy_technical = by_side[BUY].technical_signal_score
        sell_technical = by_side[SELL].technical_signal_score
        expected_gap = (
            abs(buy_technical - sell_technical)
            if buy_technical is not None and sell_technical is not None
            else None
        )
        if self.decision.score_gap != expected_gap:
            _error(
                "snapshot.decision.score_gap",
                "must equal the absolute BUY/SELL TechnicalSignalScore gap",
            )
        if (
            self.decision.selected_side is not None
            and buy_technical is not None
            and sell_technical is not None
            and buy_technical != sell_technical
        ):
            expected_side = BUY if buy_technical > sell_technical else SELL
            if self.decision.selected_side != expected_side:
                _error(
                    "snapshot.decision.selected_side",
                    "must select the side with the higher TechnicalSignalScore",
                )
        if buy_technical is None or sell_technical is None:
            if (
                self.decision.candidate_status != DATA_UNAVAILABLE
                or self.decision.selected_side is not None
            ):
                _error(
                    "snapshot.decision",
                    "missing TechnicalSignalScore requires DATA_UNAVAILABLE with no selected side",
                )
        if self.decision.candidate_status == READY_NOW:
            selected = by_side[self.decision.selected_side]
            if (
                selected.technical_signal_score is None
                or selected.setup_score is None
            ):
                _error(
                    "snapshot.decision.candidate_status",
                    "READY_NOW requires valid selected-side Technical and Setup scores",
                )
            if self.market_safety.status != PASS or self.macro_gate.status != PASS:
                _error(
                    "snapshot.decision.candidate_status",
                    "READY_NOW requires PASS market-safety and Macro gates",
                )
        if (
            self.market_safety.status == BLOCK
            or self.macro_gate.status == BLOCK
        ) and self.decision.candidate_status not in {BLOCKED, DATA_UNAVAILABLE}:
            _error(
                "snapshot.decision.candidate_status",
                "a BLOCK gate requires BLOCKED or DATA_UNAVAILABLE",
            )
        if (
            self.market_safety.status in {CAUTION, UNKNOWN}
            or self.macro_gate.status in {CAUTION, UNKNOWN}
        ) and self.decision.candidate_status == READY_NOW:
            _error(
                "snapshot.decision.candidate_status",
                "CAUTION/UNKNOWN gate cannot produce READY_NOW",
            )
        if (
            self.macro_assessment.status in {CONFLICT, MACRO_UNKNOWN}
            and self.macro_gate.status == PASS
        ):
            _error(
                "snapshot.macro_gate.status",
                "conflict/unknown MacroAssessment cannot produce a PASS gate",
            )
        if self.macro_gate.assessed_side != self.decision.selected_side:
            _error(
                "snapshot.macro_gate.assessed_side",
                "must be present exactly when, and match, decision.selected_side",
            )
        provenance = _freeze_object(self.provenance, "snapshot.provenance")
        _reject_contract_identity_in_provenance(provenance, "snapshot.provenance")
        object.__setattr__(self, "side_scores", (by_side[BUY], by_side[SELL]))
        object.__setattr__(self, "provenance", provenance)

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: str,
        symbol: str,
        captured_at: datetime,
        side_scores: tuple[SideScore, SideScore] | list[SideScore],
        market_safety: MarketSafetyResult,
        macro_assessment: MacroAssessment,
        macro_gate: MacroGateResult,
        decision: DecisionResult,
        provenance: Mapping[str, Any],
    ) -> CanonicalPairSnapshot:
        """Create a new artifact and stamp the locked target identity."""

        return cls(
            **dict(SCANNER_VERSION_FIELDS),
            snapshot_id=snapshot_id,
            symbol=symbol,
            captured_at=captured_at,
            side_scores=tuple(side_scores),
            market_safety=market_safety,
            macro_assessment=macro_assessment,
            macro_gate=macro_gate,
            decision=decision,
            provenance=provenance,
        )

    def side_score(self, side: Side) -> SideScore:
        valid_side = _require_choice(side, VALID_SIDES, "side")
        return self.side_scores[0] if valid_side == BUY else self.side_scores[1]

    def to_dict(self) -> dict[str, Any]:
        if type(self) is not CanonicalPairSnapshot:
            _error("snapshot", "canonical serializer rejects model subclasses")
        return {
            **{
                field: getattr(self, field)
                for field in SCANNER_VERSION_FIELDS
            },
            "snapshot_id": self.snapshot_id,
            "symbol": self.symbol,
            "captured_at": self.captured_at.isoformat(),
            "side_scores": {
                score.side: score.to_dict() for score in self.side_scores
            },
            "market_safety": self.market_safety.to_dict(),
            "macro_assessment": self.macro_assessment.to_dict(),
            "macro_gate": self.macro_gate.to_dict(),
            "decision": self.decision.to_dict(),
            "provenance": _thaw_json(self.provenance),
        }

    def to_json(self) -> str:
        if type(self) is not CanonicalPairSnapshot:
            _error("snapshot", "canonical serializer rejects model subclasses")
        payload = CanonicalPairSnapshot.to_dict(self)
        CanonicalPairSnapshot.from_dict(payload)
        try:
            return json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError) as exc:
            _error("snapshot", f"cannot serialize canonical JSON: {exc}")

    @classmethod
    def from_dict(cls, value: object) -> CanonicalPairSnapshot:
        if cls is not CanonicalPairSnapshot:
            _error("snapshot", "canonical dict reader rejects model subclasses")
        return deserialize_canonical_pair_snapshot(value)

    @classmethod
    def _from_dict_unclassified(cls, value: object) -> CanonicalPairSnapshot:
        """Parse an exact target object after classification selected the target path."""

        expected = set(SCANNER_VERSION_FIELDS) | {
            "snapshot_id",
            "symbol",
            "captured_at",
            "side_scores",
            "market_safety",
            "macro_assessment",
            "macro_gate",
            "decision",
            "provenance",
        }
        payload = _require_exact_keys(value, expected, "snapshot")
        for field, expected_version in SCANNER_VERSION_FIELDS.items():
            actual = payload[field]
            if actual is None or (type(actual) is str and not actual):
                _error(
                    f"snapshot.{field}",
                    "required version must be a non-empty string",
                    code=SCANNER_VERSION_MISSING,
                )
            if type(actual) is not str or actual != expected_version:
                _error(
                    f"snapshot.{field}",
                    f"expected {expected_version!r}, got {actual!r}",
                    code=SCANNER_VERSION_MISMATCH,
                )
        scores_payload = _require_exact_keys(
            payload["side_scores"], {BUY, SELL}, "snapshot.side_scores"
        )
        scores = tuple(
            SideScore.from_dict(
                scores_payload[side], path=f"snapshot.side_scores.{side}"
            )
            for side in (BUY, SELL)
        )
        for side, score in zip((BUY, SELL), scores):
            if score.side != side:
                _error(
                    f"snapshot.side_scores.{side}.side",
                    f"must match containing key {side!r}",
                )
        return cls(
            **{field: payload[field] for field in SCANNER_VERSION_FIELDS},
            snapshot_id=_require_text(payload["snapshot_id"], "snapshot.snapshot_id"),
            symbol=_require_text(payload["symbol"], "snapshot.symbol"),
            captured_at=_parse_datetime(payload["captured_at"], "snapshot.captured_at"),
            side_scores=scores,
            market_safety=MarketSafetyResult.from_dict(
                payload["market_safety"], path="snapshot.market_safety"
            ),
            macro_assessment=MacroAssessment.from_dict(
                payload["macro_assessment"], path="snapshot.macro_assessment"
            ),
            macro_gate=MacroGateResult.from_dict(
                payload["macro_gate"], path="snapshot.macro_gate"
            ),
            decision=DecisionResult.from_dict(
                payload["decision"], path="snapshot.decision"
            ),
            provenance=_freeze_external_object(
                payload["provenance"], "snapshot.provenance"
            ),
        )

    @classmethod
    def from_json(cls, value: str) -> CanonicalPairSnapshot:
        if cls is not CanonicalPairSnapshot:
            _error("snapshot", "canonical JSON reader rejects model subclasses")
        return deserialize_canonical_pair_snapshot(_decode_strict_json(value))


@dataclass(frozen=True, slots=True)
class ScannerPayloadClassification:
    kind: Literal["scanner", "legacy_v3", "invalid"]
    audit_only: bool
    replayable: bool
    reason_codes: tuple[str, ...]
    observed_versions: Mapping[str, FrozenJson]

    def __post_init__(self) -> None:
        if type(self.kind) is not str or self.kind not in {
            PAYLOAD,
            PAYLOAD_LEGACY_V3,
            PAYLOAD_INVALID,
        }:
            _error("classification.kind", "unsupported classification")
        if type(self.audit_only) is not bool or type(self.replayable) is not bool:
            _error("classification", "audit_only and replayable must be booleans")
        reasons = _freeze_reason_codes(
            self.reason_codes, "classification.reason_codes"
        )
        if self.kind == PAYLOAD_LEGACY_V3 and (
            not self.audit_only or self.replayable
        ):
            _error("classification", "legacy V3 must be audit-only/non-replayable")
        if (
            self.kind == PAYLOAD_LEGACY_V3
            and SCANNER_LEGACY_V3_AUDIT_ONLY not in reasons
        ):
            _error("classification.reason_codes", "legacy V3 reason is required")
        if self.kind == PAYLOAD and (
            self.audit_only or not self.replayable or reasons
        ):
            _error("classification", "valid V4 must be accepted/replayable without errors")
        if self.kind == PAYLOAD_INVALID and (
            self.audit_only or self.replayable or not reasons
        ):
            _error("classification", "invalid payload must be non-replayable with a reason")
        object.__setattr__(self, "reason_codes", reasons)
        object.__setattr__(
            self,
            "observed_versions",
            _freeze_object(self.observed_versions, "classification.observed_versions"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "audit_only": self.audit_only,
            "replayable": self.replayable,
            "reason_codes": list(self.reason_codes),
            "observed_versions": _thaw_json(self.observed_versions),
        }


def _contains_forbidden_scored_field(
    value: object,
    *,
    _seen: set[int] | None = None,
    _depth: int = 0,
) -> bool:
    if _depth > _MAX_JSON_DEPTH:
        return False
    seen = _seen if _seen is not None else set()
    if type(value) is dict:
        identity = id(value)
        if identity in seen:
            return False
        seen.add(identity)
        try:
            for key, item in value.items():
                if key in FORBIDDEN_SCORED_FIELDS:
                    return True
                if _contains_forbidden_scored_field(
                    item, _seen=seen, _depth=_depth + 1
                ):
                    return True
        finally:
            seen.remove(identity)
    elif type(value) is list:
        identity = id(value)
        if identity in seen:
            return False
        seen.add(identity)
        try:
            return any(
                _contains_forbidden_scored_field(
                    item, _seen=seen, _depth=_depth + 1
                )
                for item in value
            )
        finally:
            seen.remove(identity)
    return False


def _decode_strict_json(value: object) -> object:
    if type(value) is not str:
        _error("json", "expected JSON text")

    def reject_constant(token: str) -> None:
        _error("json", f"non-finite JSON number {token!r} is forbidden")

    def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                _error(f"json.{key}", "duplicate JSON key")
            result[key] = item
        return result

    try:
        return json.loads(
            value,
            object_pairs_hook=strict_object,
            parse_constant=reject_constant,
        )
    except ScannerContractError:
        raise
    except (
        TypeError,
        ValueError,
        OverflowError,
        RecursionError,
        json.JSONDecodeError,
    ) as exc:
        _error("json", f"invalid JSON: {exc}")


def _version_identity_candidates(value: dict[str, Any]) -> dict[str, tuple[object, ...]]:
    scoring_provenance = value.get("scoring_provenance")
    scoring_provenance = (
        scoring_provenance if type(scoring_provenance) is dict else {}
    )
    snapshot_provenance = value.get("provenance")
    snapshot_provenance = (
        snapshot_provenance if type(snapshot_provenance) is dict else {}
    )
    return {
        "scoring_version": (
            value.get("scoring_version"),
            value.get("scorer_version"),
            value.get("scanner_scorer_version"),
            scoring_provenance.get("scanner_scorer_version"),
            snapshot_provenance.get("scoring_version"),
            snapshot_provenance.get("scorer_version"),
            snapshot_provenance.get("scanner_scorer_version"),
        ),
        "feature_version": (
            value.get("feature_version"),
            value.get("scanner_feature_version"),
            scoring_provenance.get("scanner_feature_version"),
            snapshot_provenance.get("feature_version"),
            snapshot_provenance.get("scanner_feature_version"),
        ),
        "output_schema_version": (
            value.get("output_schema_version"),
            snapshot_provenance.get("output_schema_version"),
            snapshot_provenance.get("output_version"),
        ),
        "safety_policy_version": (
            value.get("safety_policy_version"),
            snapshot_provenance.get("safety_policy_version"),
        ),
        "macro_policy_version": (
            value.get("macro_policy_version"),
            snapshot_provenance.get("macro_policy_version"),
        ),
        "ranking_version": (
            value.get("ranking_version"),
            snapshot_provenance.get("ranking_version"),
        ),
        "snapshot_version": (
            value.get("snapshot_version"),
            value.get("persistence_schema_version"),
            snapshot_provenance.get("snapshot_version"),
            snapshot_provenance.get("persistence_schema_version"),
        ),
    }


def _observed_versions(value: object) -> dict[str, Any]:
    if type(value) is not dict:
        return {}

    def safe_versions(candidates: tuple[object, ...]) -> str | None:
        present = tuple(
            candidate
            for candidate in candidates
            if candidate is not None
            and (type(candidate) is not str or candidate != "")
        )
        if not present:
            return None
        safe = tuple(
            candidate
            if type(candidate) is str and _is_unicode_scalar_text(candidate)
            else f"<invalid:{type(candidate).__name__}>"
            for candidate in present
        )
        return safe[0] if all(item == safe[0] for item in safe) else "<conflict>"

    return {
        field: safe_versions(candidates)
        for field, candidates in _version_identity_candidates(value).items()
    }


def _invalid_classification(
    code: str,
    observed: Mapping[str, Any],
) -> ScannerPayloadClassification:
    return ScannerPayloadClassification(
        kind=PAYLOAD_INVALID,
        audit_only=False,
        replayable=False,
        reason_codes=(code,),
        observed_versions=observed,
    )


def _has_envelope_intent(
    value: dict[str, Any],
    candidates: Mapping[str, tuple[object, ...]],
) -> bool:
    keys = set(value)
    if keys & (_ONLY_VERSION_KEYS | _CANONICAL_BLOCK_KEYS):
        return True
    if "scoring_version" in value and value.get("scoring_version") != "scanner-v3":
        return True
    target_identities = frozenset(SCANNER_VERSION_FIELDS.values())
    return any(
        candidate in target_identities
        for values in candidates.values()
        for candidate in values
        if type(candidate) is str
    )


def _has_mixed_v3_identity(
    candidates: Mapping[str, tuple[object, ...]],
) -> bool:
    values = {
        candidate
        for group in candidates.values()
        for candidate in group
        if type(candidate) is str and candidate
    }
    has_v3 = bool(values & {"scanner-v3", "scanner-features-v3"})
    has_v4 = bool(values & set(SCANNER_VERSION_FIELDS.values()))
    return has_v3 and has_v4


def classify_scanner_payload(value: object) -> ScannerPayloadClassification:
    """Classify without ever upgrading or executing the supplied artifact."""

    if type(value) is not dict:
        return _invalid_classification(SCANNER_SCHEMA_INVALID, {})

    try:
        _validate_external_json_shape(value, "snapshot")
    except ScannerContractError as exc:
        return _invalid_classification(exc.code, {})

    observed = _observed_versions(value)
    candidates = _version_identity_candidates(value)
    if _has_mixed_v3_identity(candidates):
        return _invalid_classification(SCANNER_VERSION_MISMATCH, observed)

    candidate_values = tuple(
        candidate
        for group in candidates.values()
        for candidate in group
        if type(candidate) is str
    )
    explicit_v3 = bool(
        set(candidate_values) & {"scanner-v3", "scanner-features-v3"}
    )
    structural_v3 = _contains_forbidden_scored_field(value)
    has_intent = _has_envelope_intent(value, candidates)

    if not has_intent and (explicit_v3 or structural_v3):
        reasons = [SCANNER_LEGACY_V3_AUDIT_ONLY]
        if structural_v3:
            reasons.append(SCANNER_FORBIDDEN_SCORED_FIELD)
        return ScannerPayloadClassification(
            kind=PAYLOAD_LEGACY_V3,
            audit_only=True,
            replayable=False,
            reason_codes=tuple(reasons),
            observed_versions=observed,
        )

    try:
        CanonicalPairSnapshot._from_dict_unclassified(value)
    except ScannerContractError as exc:
        return _invalid_classification(exc.code, observed)
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError):
        return _invalid_classification(SCANNER_SCHEMA_INVALID, observed)
    return ScannerPayloadClassification(
        kind=PAYLOAD,
        audit_only=False,
        replayable=True,
        reason_codes=(),
        observed_versions=observed,
    )


def classify_scanner_payload_json(value: object) -> ScannerPayloadClassification:
    """Decode and classify JSON with the same rules as the decoded-dict reader."""

    try:
        payload = _decode_strict_json(value)
    except ScannerContractError as exc:
        return _invalid_classification(exc.code, {})
    return classify_scanner_payload(payload)


def serialize_canonical_pair_snapshot(snapshot: CanonicalPairSnapshot) -> dict[str, Any]:
    if type(snapshot) is not CanonicalPairSnapshot:
        _error("snapshot", "expected CanonicalPairSnapshot")
    payload = CanonicalPairSnapshot.to_dict(snapshot)
    CanonicalPairSnapshot.from_dict(payload)
    return payload


def deserialize_canonical_pair_snapshot(value: object) -> CanonicalPairSnapshot:
    classification = classify_scanner_payload(value)
    if classification.kind == PAYLOAD_LEGACY_V3:
        _error(
            "snapshot",
            "Scanner V3 artifact is audit-only and non-replayable",
            code=SCANNER_LEGACY_V3_AUDIT_ONLY,
        )
    if classification.kind == PAYLOAD_INVALID:
        _error(
            "snapshot",
            "payload is invalid and non-replayable",
            code=classification.reason_codes[0],
        )
    return CanonicalPairSnapshot._from_dict_unclassified(value)


def validate_canonical_pair_snapshot(value: object) -> CanonicalPairSnapshot:
    """Validate strictly and return the immutable typed representation."""

    return deserialize_canonical_pair_snapshot(value)


__all__ = [
    "ALIGNED",
    "BLOCK",
    "BLOCKED",
    "BUY",
    "CAUTION",
    "CanonicalPairSnapshot",
    "CONFLICT",
    "DATA_UNAVAILABLE",
    "DecisionResult",
    "FORBIDDEN_SCORED_FIELDS",
    "GateCheck",
    "MacroAssessment",
    "MacroGateResult",
    "MarketSafetyResult",
    "NEUTRAL",
    "OUT_OF_STRATEGY",
    "PASS",
    "PAYLOAD_INVALID",
    "PAYLOAD_LEGACY_V3",
    "PAYLOAD",
    "READY_NOW",
    "SAFETY_CHECK_NAMES",
    "SCANNER_V4_FEATURE_VERSION",
    "SCANNER_MACRO_POLICY_VERSION",
    "SCANNER_OUTPUT_SCHEMA_VERSION",
    "SCANNER_V4_RANKING_VERSION",
    "SCANNER_SAFETY_POLICY_VERSION",
    "SCANNER_SCORING_VERSION",
    "SCANNER_SNAPSHOT_VERSION",
    "SCANNER_VERSION_FIELDS",
    "SELL",
    "ScannerPayloadClassification",
    "ScannerContractError",
    "SideScore",
    "TechnicalBreakdown",
    "TechnicalComponent",
    "UNKNOWN",
    "WAITING_CONFIRMATION",
    "WATCH_ZONE",
    "classify_scanner_payload",
    "classify_scanner_payload_json",
    "deserialize_canonical_pair_snapshot",
    "serialize_canonical_pair_snapshot",
    "validate_canonical_pair_snapshot",
]
