"""Deterministic identity for SMC snapshot/cache inputs.

This module is deliberately a pure seam.  It does not cache, score, detect
zones, or change the production SMC route.  Callers can use the returned key
to decide whether a previously computed SMC result is reusable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from math import isfinite
from typing import Any, Mapping, Sequence

from core.market_models import Candle
from core.smc_models import (
    SMC_CONFLUENCE_VERSION,
    SMC_DOMAIN_VERSION,
    SMC_SNAPSHOT_CONTRACT_VERSION,
    SMC_SCORER_VERSION,
)
from core.smc_sweep_linking import SMC_SWEEP_LINK_VERSION
from core.smc_versions import SMC_SELECTION_VERSION


# Task 118: the identity payload now also carries the *selection* policy of the
# candidate coordinator/plan seam.  Before that, two runs that differed only in
# how the final candidate was chosen hashed the same, so a cached result could be
# reused as if it had been produced by the current selection rules.  The shape of
# the identity record changed, so the label changes with it instead of keeping
# ``v1`` and silently reusing old keys (compatibility spec §4.1: "Khi bất kỳ
# policy/parameter/contract nào đổi, rule identity đổi ... Không đổi nhãn UI để
# lách cache compatibility").
SMC_CACHE_IDENTITY_VERSION = "smc-cache-key-v2"
# Bump this internal rule identity when cache-relevant SMC semantics change.
SMC_RULE_IDENTITY = "smc-rules-v1"
_VALID_TIMEFRAMES = frozenset({"D1", "H4", "H1", "M15"})


def smc_rule_versions() -> dict[str, str]:
    """Every internal policy identity a cached SMC result depends on.

    ``selection`` is the coordinator/plan policy of tasks 92–107: it decides
    WHICH candidate the result reports, so a change there must invalidate a
    cached result exactly like a scorer or zone-policy change does.
    """

    return {
        "domain": SMC_DOMAIN_VERSION,
        "snapshot_contract": SMC_SNAPSHOT_CONTRACT_VERSION,
        "scorer": SMC_SCORER_VERSION,
        "confluence": SMC_CONFLUENCE_VERSION,
        "sweep_link": SMC_SWEEP_LINK_VERSION,
        "selection": SMC_SELECTION_VERSION,
    }


def smc_rule_identity(
    *,
    rule_identity: str = SMC_RULE_IDENTITY,
) -> dict[str, Any]:
    """The internal rule-identity record of compatibility spec §4.1.

    It is metadata a reader can compare against the running identity to decide
    whether a stored result may be reused, so it carries every version constant
    that participates in the decision — never a UI-facing generation label.
    """

    normalized = str(rule_identity or "").strip()
    if not normalized:
        raise ValueError("SMC rule identity is required")
    return {
        "cache_identity_version": SMC_CACHE_IDENTITY_VERSION,
        "rule_identity": normalized,
        "rule_versions": smc_rule_versions(),
    }


def smc_rule_identity_digest(
    *,
    rule_identity: str = SMC_RULE_IDENTITY,
) -> str:
    """Deterministic digest of the rule identity, for equality checks."""

    canonical = json.dumps(
        smc_rule_identity(rule_identity=rule_identity),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def smc_snapshot_identity_payload(
    *,
    symbol: str,
    as_of: datetime | str,
    candles_by_timeframe: Mapping[str, Sequence[Candle]],
    metadata: Mapping[str, Any] | None = None,
    rule_identity: str = SMC_RULE_IDENTITY,
) -> dict[str, Any]:
    """Return the canonical, hashable identity payload for one SMC input.

    Candle order is retained because detector consumers may use the ordered
    history.  Every OHLCV field is included, so a broker correction cannot
    reuse the old key.  Metadata is canonicalized recursively and the internal
    rule/version block is always present, even when callers provide no extra
    metadata.
    """

    normalized_symbol = "".join(
        character for character in str(symbol or "").upper() if character.isalnum()
    )
    if not normalized_symbol:
        raise ValueError("SMC snapshot identity symbol is required")
    normalized_rule = str(rule_identity or "").strip()
    if not normalized_rule:
        raise ValueError("SMC snapshot identity rule_identity is required")
    if not isinstance(candles_by_timeframe, Mapping):
        raise ValueError("candles_by_timeframe must be a mapping")

    canonical_candles: dict[str, list[dict[str, Any]]] = {}
    seen_timeframes: set[str] = set()
    for raw_timeframe, candles in candles_by_timeframe.items():
        timeframe = str(raw_timeframe or "").strip().upper()
        if timeframe not in _VALID_TIMEFRAMES:
            raise ValueError(f"Unsupported SMC timeframe: {raw_timeframe}")
        if timeframe in seen_timeframes:
            raise ValueError(f"Duplicate SMC timeframe: {timeframe}")
        seen_timeframes.add(timeframe)
        if isinstance(candles, (str, bytes)) or not isinstance(candles, Sequence):
            raise ValueError(f"Candles for {timeframe} must be a sequence")
        canonical_candles[timeframe] = [
            _canonical_candle(candle, timeframe=timeframe, index=index)
            for index, candle in enumerate(candles)
        ]

    return {
        "identity_version": SMC_CACHE_IDENTITY_VERSION,
        "rule_identity": normalized_rule,
        "rule_versions": smc_rule_versions(),
        "symbol": normalized_symbol,
        "as_of": _canonical_timestamp(as_of, field_name="as_of"),
        "metadata": _canonical_value(dict(metadata or {}), field_name="metadata"),
        "candles": {
            timeframe: canonical_candles[timeframe]
            for timeframe in sorted(canonical_candles)
        },
    }


def smc_snapshot_identity(
    *,
    symbol: str,
    as_of: datetime | str,
    candles_by_timeframe: Mapping[str, Sequence[Candle]],
    metadata: Mapping[str, Any] | None = None,
    rule_identity: str = SMC_RULE_IDENTITY,
) -> str:
    """Return a deterministic cache key for the complete SMC input identity."""

    payload = smc_snapshot_identity_payload(
        symbol=symbol,
        as_of=as_of,
        candles_by_timeframe=candles_by_timeframe,
        metadata=metadata,
        rule_identity=rule_identity,
    )
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{SMC_CACHE_IDENTITY_VERSION}:{hashlib.sha256(canonical).hexdigest()}"


def _canonical_candle(
    candle: Candle,
    *,
    timeframe: str,
    index: int,
) -> dict[str, Any]:
    if not isinstance(candle, Candle):
        raise ValueError(f"{timeframe}[{index}] must be a Candle")
    return {
        "time": _canonical_timestamp(candle.time, field_name=f"{timeframe}[{index}].time"),
        "open": _canonical_number(candle.open, field_name=f"{timeframe}[{index}].open"),
        "high": _canonical_number(candle.high, field_name=f"{timeframe}[{index}].high"),
        "low": _canonical_number(candle.low, field_name=f"{timeframe}[{index}].low"),
        "close": _canonical_number(candle.close, field_name=f"{timeframe}[{index}].close"),
        "volume": _canonical_number(candle.volume, field_name=f"{timeframe}[{index}].volume"),
    }


def _canonical_timestamp(value: datetime | str, *, field_name: str) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            raise ValueError(f"{field_name} must be an ISO timestamp") from None
    else:
        raise ValueError(f"{field_name} must be a timezone-aware timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat()


def _canonical_number(value: object, *, field_name: str) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field_name} must be numeric") from None
    if not number.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if number == 0:
        return "0"
    return format(number.normalize(), "f")


def _canonical_value(value: object, *, field_name: str) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, datetime):
        return _canonical_timestamp(value, field_name=field_name)
    if isinstance(value, int) and not isinstance(value, bool):
        return {"type": "int", "value": str(value)}
    if isinstance(value, float):
        return {
            "type": "float",
            "value": _canonical_number(value, field_name=field_name),
        }
    if isinstance(value, Decimal):
        return {
            "type": "decimal",
            "value": _canonical_number(value, field_name=field_name),
        }
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item, field_name=f"{field_name}.{key}")
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [
            _canonical_value(item, field_name=f"{field_name}[{index}]")
            for index, item in enumerate(value)
        ]
    raise ValueError(f"{field_name} contains an unsupported metadata value")


__all__ = [
    "SMC_CACHE_IDENTITY_VERSION",
    "SMC_RULE_IDENTITY",
    "smc_rule_identity",
    "smc_rule_identity_digest",
    "smc_rule_versions",
    "smc_snapshot_identity",
    "smc_snapshot_identity_payload",
]
