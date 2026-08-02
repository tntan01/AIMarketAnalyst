"""Canonical immutable domain models for SMC scoring.

Phase 1 introduces typed identities without changing legacy score semantics.
Dictionaries remain at the public pipeline boundary for now, but every
enriched SMC zone can be losslessly adapted to these models.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import hashlib
from math import isfinite
from typing import Any

from core.smc_sweep_linking import SMC_SWEEP_LINK_VERSION
from core.smc_versions import SMC_CONFLUENCE_VERSION, SMC_SCORER_VERSION


SMC_DOMAIN_VERSION = "smc-domain-v1"
VALID_ZONE_DIRECTIONS = frozenset({"buy", "sell"})
VALID_CONFLUENCE_DIRECTIONS = frozenset({
    "bullish",
    "bearish",
    "mixed",
    "unknown",
})


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


@dataclass(frozen=True, slots=True)
class ZoneVisit:
    visit_id: str
    entered_at: str | None
    exited_at: str | None
    start_index: int | None
    end_index: int | None
    max_penetration_ratio: float | None = None

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

    def to_dict(self, *, include_compatibility: bool = True) -> dict[str, Any]:
        payload = asdict(self)
        payload["visits"] = [visit.to_dict() for visit in self.visits]
        payload["type"] = self.zone_type
        payload["index"] = self.origin_index
        payload["time"] = self.origin_time
        payload["lifecycle_stale"] = self.stale
        payload["lifecycle_broken"] = self.broken
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
                low=low,
                high=high,
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

    def __post_init__(self) -> None:
        if self.direction not in VALID_ZONE_DIRECTIONS:
            raise ValueError(
                f"Invalid selected SMC zone direction: {self.direction}"
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
