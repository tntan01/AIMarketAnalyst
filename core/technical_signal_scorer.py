"""Pure, target-only Scanner V4 TechnicalSignalScore.

This module is intentionally not wired into the executable scanner.  It owns
only the four locked technical components and projects the canonical SMC
subtotal before any post-subtotal gate evidence is applied.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math
from types import MappingProxyType
from typing import Any, Mapping

from core.reason_codes import TECHNICAL_DATA_UNAVAILABLE
from core.scanner_v4_models import (
    SCANNER_V4_SCORING_VERSION,
    TechnicalBreakdown,
    TechnicalComponent,
)
from core.smc_models import SMC_DOMAIN_VERSION
from core.smc_scoring_result import (
    SMC_SCORING_CONTRACT_VERSION,
    SmcScoringResult,
    SmcSideScoringResult,
)
from core.smc_versions import SMC_SCORER_VERSION, SMC_TECHNICAL_RAW_VERSION


TECHNICAL_WEIGHT_POLICY_VERSION = "technical-signal-weights-v4"

VALID_TECHNICAL_SIDES = frozenset({"buy", "sell"})
VALID_TECHNICAL_REGIMES = frozenset({
    "trending_up",
    "trending_down",
    "ranging",
    "volatile",
    "unknown",
})

TECHNICAL_COMPONENT_RAW_MAX: Mapping[str, int] = MappingProxyType({
    "trend": 25,
    "momentum": 20,
    "location": 25,
    "smc": 15,
})

_TRENDING_WEIGHTS = MappingProxyType({
    "trend": 40,
    "momentum": 20,
    "location": 20,
    "smc": 20,
})
TECHNICAL_REGIME_WEIGHTS: Mapping[str, Mapping[str, int]] = MappingProxyType({
    "trending_up": _TRENDING_WEIGHTS,
    "trending_down": _TRENDING_WEIGHTS,
    "ranging": MappingProxyType({
        "trend": 10,
        "momentum": 10,
        "location": 40,
        "smc": 40,
    }),
    "volatile": MappingProxyType({
        "trend": 20,
        "momentum": 10,
        "location": 40,
        "smc": 30,
    }),
    "unknown": MappingProxyType({
        "trend": 25,
        "momentum": 25,
        "location": 25,
        "smc": 25,
    }),
})

_SMC_COMPONENT_LIMITS: Mapping[str, int] = MappingProxyType({
    "structure_score": 5,
    "zone_score": 5,
    "ltf_confirmation_score": 3,
    "technical_validation_score": 2,
})
_REQUIRED_SMC_BREAKDOWN_FIELDS = frozenset({
    "side",
    "total",
    *_SMC_COMPONENT_LIMITS,
    "subtotal",
    "penalty_points",
    "applied_cap",
    "penalties",
    "caps",
    "selected_zone_id",
    "selected_zone_quality_score",
    "selected_zone_relevance_score",
    "selected_zone_setup_score",
    "reason_codes",
    "scoring_version",
    "domain_version",
})
_SELECTED_ZONE_FIELDS = frozenset({
    "zone_id",
    "direction",
    "timeframe",
    "family",
    "zone_type",
    "low",
    "high",
    "level",
    "zone_quality_score",
    "zone_relevance_score",
    "zone_setup_score",
    "liquidity_sweep_linked",
    "linked_sweep_id",
    "linked_sweep_distance_atr",
    "linked_sweep_time_delta",
    "source",
    "scoring_version",
    "domain_version",
    "selection_reason_codes",
    "type",
})
_VALID_SELECTED_ZONE_TIMEFRAMES = frozenset({"H4", "H1"})
_VALID_SELECTED_ZONE_FAMILIES = frozenset({
    "demand",
    "supply",
    "order_block",
    "fvg",
})
_MISSING = object()


class TechnicalScoreDataError(ValueError):
    """Typed fail-closed error for a missing or invalid technical input."""

    code = TECHNICAL_DATA_UNAVAILABLE

    def __init__(self, path: str, detail: str, *, side: str | None = None) -> None:
        self.path = path
        self.detail = detail
        self.side = side
        location = f" for {side}" if side is not None else ""
        super().__init__(
            f"{self.code}{location} at {path}: {detail}"
        )


@dataclass(frozen=True, slots=True)
class SmcTechnicalEvidence:
    """Canonical SMC metadata retained as evidence, never as a contribution."""

    side: str
    raw_semantics_version: str
    source_scoring_version: str
    source_contract_version: str
    source_domain_version: str
    raw_subtotal: int
    base_components: Mapping[str, int]
    source_score: int
    penalty_points: int
    applied_cap: int | None
    penalties: tuple[str, ...]
    caps: tuple[str, ...]
    reason_codes: tuple[str, ...]
    smc_reason: str
    selected_zone: Mapping[str, Any] | None
    selected_zone_id: str | None
    selected_zone_type: str | None
    selected_zone_timeframe: str | None

    def __post_init__(self) -> None:
        _normalize_smc_technical_evidence(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "raw_semantics_version": self.raw_semantics_version,
            "source_scoring_version": self.source_scoring_version,
            "source_contract_version": self.source_contract_version,
            "source_domain_version": self.source_domain_version,
            "raw_subtotal": self.raw_subtotal,
            "base_components": dict(self.base_components),
            "source_score": self.source_score,
            "penalty_points": self.penalty_points,
            "applied_cap": self.applied_cap,
            "penalties": list(self.penalties),
            "caps": list(self.caps),
            "reason_codes": list(self.reason_codes),
            "smc_reason": self.smc_reason,
            "selected_zone": _thaw_evidence(self.selected_zone),
            "selected_zone_id": self.selected_zone_id,
            "selected_zone_type": self.selected_zone_type,
            "selected_zone_timeframe": self.selected_zone_timeframe,
        }

    @classmethod
    def from_dict(
        cls, value: object, *, path: str = "smc_evidence"
    ) -> SmcTechnicalEvidence:
        """Strict deserializer (Bước 08 reader addition; does not change scoring)."""
        expected = frozenset(
            {
                "side",
                "raw_semantics_version",
                "source_scoring_version",
                "source_contract_version",
                "source_domain_version",
                "raw_subtotal",
                "base_components",
                "source_score",
                "penalty_points",
                "applied_cap",
                "penalties",
                "caps",
                "reason_codes",
                "smc_reason",
                "selected_zone",
                "selected_zone_id",
                "selected_zone_type",
                "selected_zone_timeframe",
            }
        )
        if type(value) is not dict or frozenset(value) != expected:
            raise ValueError(
                f"SMC_EVIDENCE_CONTRACT_INVALID at {path}: expected exactly "
                f"{sorted(expected)}"
            )
        side = _require_side(value["side"])
        base = value["base_components"]
        if type(base) is not dict or any(type(k) is not str for k in base):
            _data_error(f"{path}.base_components", "expected a string-keyed mapping", side=side)
        selected_zone = value["selected_zone"]
        if selected_zone is not None:
            selected_zone = _freeze_evidence(selected_zone, path=f"{path}.selected_zone", side=side)
        return cls(
            side=side,
            raw_semantics_version=_required_text(
                value["raw_semantics_version"], f"{path}.raw_semantics_version", side=side
            ),
            source_scoring_version=_required_text(
                value["source_scoring_version"], f"{path}.source_scoring_version", side=side
            ),
            source_contract_version=_required_text(
                value["source_contract_version"], f"{path}.source_contract_version", side=side
            ),
            source_domain_version=_required_text(
                value["source_domain_version"], f"{path}.source_domain_version", side=side
            ),
            raw_subtotal=_require_raw(
                value["raw_subtotal"],
                f"{path}.raw_subtotal",
                TECHNICAL_COMPONENT_RAW_MAX["smc"],
                side=side,
            ),
            base_components={
                key: _require_raw(
                    base[key],
                    f"{path}.base_components.{key}",
                    TECHNICAL_COMPONENT_RAW_MAX["smc"],
                    side=side,
                )
                for key in base
            },
            source_score=_require_nonnegative_int(
                value["source_score"], f"{path}.source_score", side=side
            ),
            penalty_points=_require_nonnegative_int(
                value["penalty_points"], f"{path}.penalty_points", side=side
            ),
            applied_cap=_optional_bounded_int(
                value["applied_cap"],
                f"{path}.applied_cap",
                0,
                100,
                side=side,
            ),
            penalties=_require_text_tuple(
                value["penalties"], f"{path}.penalties", side=side
            ),
            caps=_require_text_tuple(value["caps"], f"{path}.caps", side=side),
            reason_codes=_require_text_tuple(
                value["reason_codes"], f"{path}.reason_codes", side=side
            ),
            smc_reason=_required_text(
                value["smc_reason"], f"{path}.smc_reason", side=side
            ),
            selected_zone=selected_zone,
            selected_zone_id=_optional_text(
                value["selected_zone_id"], f"{path}.selected_zone_id", side=side
            ),
            selected_zone_type=_optional_text(
                value["selected_zone_type"], f"{path}.selected_zone_type", side=side
            ),
            selected_zone_timeframe=_optional_text(
                value["selected_zone_timeframe"],
                f"{path}.selected_zone_timeframe",
                side=side,
            ),
        )


@dataclass(frozen=True, slots=True)
class SmcTechnicalRawProjection:
    """Strict projection of one canonical SMC side onto the V4 0-15 raw."""

    side: str
    raw: int
    evidence: SmcTechnicalEvidence

    def __post_init__(self) -> None:
        side = _require_side(self.side)
        raw = _require_raw(
            self.raw,
            "smc_projection.raw",
            TECHNICAL_COMPONENT_RAW_MAX["smc"],
            side=side,
        )
        if type(self.evidence) is not SmcTechnicalEvidence:
            _data_error(
                "smc_projection.evidence",
                "expected SmcTechnicalEvidence",
                side=side,
            )
        if raw != self.evidence.raw_subtotal:
            _data_error(
                "smc_projection.raw",
                "must match evidence raw_subtotal",
                side=side,
            )
        if self.evidence.side != side:
            _data_error(
                "smc_projection.evidence.side",
                "must match projection side",
                side=side,
            )


@dataclass(frozen=True, slots=True)
class TechnicalSignalScoreResult:
    """One side's immutable Scanner V4 technical score and provenance."""

    side: str
    regime: str
    scoring_version: str
    weight_policy_version: str
    smc_raw_semantics_version: str
    smc_source_scoring_version: str
    technical_signal_score: int
    technical_breakdown: TechnicalBreakdown
    smc_evidence: SmcTechnicalEvidence

    def __post_init__(self) -> None:
        side = _require_side(self.side)
        regime = _require_regime(self.regime, side=side)
        if self.scoring_version != SCANNER_V4_SCORING_VERSION:
            _data_error(
                "technical_result.scoring_version",
                f"must equal {SCANNER_V4_SCORING_VERSION!r}",
                side=side,
            )
        if self.weight_policy_version != TECHNICAL_WEIGHT_POLICY_VERSION:
            _data_error(
                "technical_result.weight_policy_version",
                f"must equal {TECHNICAL_WEIGHT_POLICY_VERSION!r}",
                side=side,
            )
        if self.smc_raw_semantics_version != SMC_TECHNICAL_RAW_VERSION:
            _data_error(
                "technical_result.smc_raw_semantics_version",
                f"must equal {SMC_TECHNICAL_RAW_VERSION!r}",
                side=side,
            )
        if self.smc_source_scoring_version != SMC_SCORER_VERSION:
            _data_error(
                "technical_result.smc_source_scoring_version",
                f"must equal {SMC_SCORER_VERSION!r}",
                side=side,
            )
        if type(self.technical_breakdown) is not TechnicalBreakdown:
            _data_error(
                "technical_result.technical_breakdown",
                "expected a TechnicalBreakdown",
                side=side,
            )
        if type(self.smc_evidence) is not SmcTechnicalEvidence:
            _data_error(
                "technical_result.smc_evidence",
                "expected SmcTechnicalEvidence",
                side=side,
            )
        if (
            self.smc_evidence.raw_semantics_version
            != self.smc_raw_semantics_version
            or self.smc_evidence.source_scoring_version
            != self.smc_source_scoring_version
        ):
            _data_error(
                "technical_result.smc_evidence",
                "SMC evidence versions must match result provenance",
                side=side,
            )
        if self.smc_evidence.side != side:
            _data_error(
                "technical_result.smc_evidence.side",
                "must match result side",
                side=side,
            )
        components = (
            self.technical_breakdown.trend,
            self.technical_breakdown.momentum,
            self.technical_breakdown.location,
            self.technical_breakdown.smc,
        )
        if any(
            component.raw is None
            or component.weight is None
            or component.contribution is None
            for component in components
        ):
            _data_error(
                "technical_result.technical_breakdown",
                "all four components must be complete",
                side=side,
            )
        expected_weights = tuple(TECHNICAL_REGIME_WEIGHTS[regime].values())
        if tuple(component.weight for component in components) != expected_weights:
            _data_error(
                "technical_result.technical_breakdown",
                "weights must match result regime",
                side=side,
            )
        if self.technical_breakdown.smc.raw != self.smc_evidence.raw_subtotal:
            _data_error(
                "technical_result.technical_breakdown.smc.raw",
                "must match SMC evidence raw subtotal",
                side=side,
            )
        if type(self.technical_signal_score) is not int:
            _data_error(
                "technical_result.technical_signal_score",
                "expected an integer",
                side=side,
            )
        exact_total = sum(
            (
                Fraction(component.raw * component.weight, component.raw_max)
                for component in components
                if component.raw is not None and component.weight is not None
            ),
            Fraction(0, 1),
        )
        expected_score = _round_half_up_once(
            _clamp_fraction(
                exact_total,
                Fraction(0, 1),
                Fraction(100, 1),
            )
        )
        if self.technical_signal_score != expected_score:
            _data_error(
                "technical_result.technical_signal_score",
                "must equal the round-once technical breakdown sum",
                side=side,
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "regime": self.regime,
            "scoring_version": self.scoring_version,
            "weight_policy_version": self.weight_policy_version,
            "smc_raw_semantics_version": self.smc_raw_semantics_version,
            "smc_source_scoring_version": self.smc_source_scoring_version,
            "technical_signal_score": self.technical_signal_score,
            "technical_breakdown": self.technical_breakdown.to_dict(),
            "smc_evidence": self.smc_evidence.to_dict(),
        }

    @classmethod
    def from_dict(
        cls, value: object, *, path: str = "technical_result"
    ) -> TechnicalSignalScoreResult:
        """Strict deserializer (Bước 08 reader addition; does not change scoring)."""
        expected = frozenset(
            {
                "side",
                "regime",
                "scoring_version",
                "weight_policy_version",
                "smc_raw_semantics_version",
                "smc_source_scoring_version",
                "technical_signal_score",
                "technical_breakdown",
                "smc_evidence",
            }
        )
        if type(value) is not dict or frozenset(value) != expected:
            raise ValueError(
                f"TECHNICAL_RESULT_CONTRACT_INVALID at {path}: expected exactly "
                f"{sorted(expected)}"
            )
        return cls(
            side=_require_side(value["side"]),
            regime=_require_regime(value["regime"], side=value["side"]),
            scoring_version=_required_text(
                value["scoring_version"], f"{path}.scoring_version", side=value["side"]
            ),
            weight_policy_version=_required_text(
                value["weight_policy_version"],
                f"{path}.weight_policy_version",
                side=value["side"],
            ),
            smc_raw_semantics_version=_required_text(
                value["smc_raw_semantics_version"],
                f"{path}.smc_raw_semantics_version",
                side=value["side"],
            ),
            smc_source_scoring_version=_required_text(
                value["smc_source_scoring_version"],
                f"{path}.smc_source_scoring_version",
                side=value["side"],
            ),
            technical_signal_score=_require_bounded_int(
                value["technical_signal_score"],
                f"{path}.technical_signal_score",
                0,
                100,
                side=value["side"],
            ),
            technical_breakdown=TechnicalBreakdown.from_dict(
                value["technical_breakdown"],
                path=f"{path}.technical_breakdown",
            ),
            smc_evidence=SmcTechnicalEvidence.from_dict(
                value["smc_evidence"], path=f"{path}.smc_evidence"
            ),
        )


def score_technical_signal(
    side: object = _MISSING,
    *,
    trend_raw: object = _MISSING,
    momentum_raw: object = _MISSING,
    location_raw: object = _MISSING,
    canonical_smc: object = _MISSING,
    regime: object = _MISSING,
) -> TechnicalSignalScoreResult:
    """Return the deterministic four-component TechnicalSignalScore for *side*.

    Inputs are strict.  Invalid or unavailable data raises
    :class:`TechnicalScoreDataError`; no numeric fallback is produced.
    """

    normalized_side = _require_side(side)
    normalized_regime = _require_regime(regime, side=normalized_side)
    raw_values = {
        "trend": _require_raw(
            trend_raw,
            "trend_raw",
            TECHNICAL_COMPONENT_RAW_MAX["trend"],
            side=normalized_side,
        ),
        "momentum": _require_raw(
            momentum_raw,
            "momentum_raw",
            TECHNICAL_COMPONENT_RAW_MAX["momentum"],
            side=normalized_side,
        ),
        "location": _require_raw(
            location_raw,
            "location_raw",
            TECHNICAL_COMPONENT_RAW_MAX["location"],
            side=normalized_side,
        ),
    }
    smc_projection = project_smc_technical_raw(
        canonical_smc,
        normalized_side,
    )
    raw_values["smc"] = smc_projection.raw

    weights = TECHNICAL_REGIME_WEIGHTS[normalized_regime]
    exact_contributions: dict[str, Fraction] = {}
    for component in ("trend", "momentum", "location", "smc"):
        raw_max = TECHNICAL_COMPONENT_RAW_MAX[component]
        # Inputs have already been rejected if out of range.  This clamp keeps
        # the locked formula explicit without turning invalid data into a score.
        clamped_raw = max(0, min(raw_max, raw_values[component]))
        exact_contributions[component] = Fraction(
            clamped_raw * weights[component],
            raw_max,
        )

    exact_total = _clamp_fraction(
        sum(exact_contributions.values(), Fraction(0, 1)),
        Fraction(0, 1),
        Fraction(100, 1),
    )
    technical_score = _round_half_up_once(exact_total)

    breakdown = TechnicalBreakdown(
        trend=TechnicalComponent(
            raw_values["trend"],
            TECHNICAL_COMPONENT_RAW_MAX["trend"],
            weights["trend"],
            float(exact_contributions["trend"]),
        ),
        momentum=TechnicalComponent(
            raw_values["momentum"],
            TECHNICAL_COMPONENT_RAW_MAX["momentum"],
            weights["momentum"],
            float(exact_contributions["momentum"]),
        ),
        location=TechnicalComponent(
            raw_values["location"],
            TECHNICAL_COMPONENT_RAW_MAX["location"],
            weights["location"],
            float(exact_contributions["location"]),
        ),
        smc=TechnicalComponent(
            raw_values["smc"],
            TECHNICAL_COMPONENT_RAW_MAX["smc"],
            weights["smc"],
            float(exact_contributions["smc"]),
        ),
    )
    return TechnicalSignalScoreResult(
        side=normalized_side,
        regime=normalized_regime,
        scoring_version=SCANNER_V4_SCORING_VERSION,
        weight_policy_version=TECHNICAL_WEIGHT_POLICY_VERSION,
        smc_raw_semantics_version=SMC_TECHNICAL_RAW_VERSION,
        smc_source_scoring_version=canonical_smc.scoring_version,
        technical_signal_score=technical_score,
        technical_breakdown=breakdown,
        smc_evidence=smc_projection.evidence,
    )


def project_smc_technical_raw(
    canonical_smc: SmcScoringResult,
    side: str,
) -> SmcTechnicalRawProjection:
    """Validate canonical SMC and return its pre-mutation subtotal for *side*."""

    normalized_side = _require_side(side)
    if type(canonical_smc) is not SmcScoringResult:
        _data_error(
            "canonical_smc",
            "expected an SmcScoringResult",
            side=normalized_side,
        )
    if (
        type(canonical_smc.scoring_version) is not str
        or canonical_smc.scoring_version != SMC_SCORER_VERSION
    ):
        _data_error(
            "canonical_smc.scoring_version",
            f"must equal {SMC_SCORER_VERSION!r}",
            side=normalized_side,
        )
    if (
        type(canonical_smc.contract_version) is not str
        or canonical_smc.contract_version != SMC_SCORING_CONTRACT_VERSION
    ):
        _data_error(
            "canonical_smc.contract_version",
            f"must equal {SMC_SCORING_CONTRACT_VERSION!r}",
            side=normalized_side,
        )
    if not isinstance(canonical_smc.sides, Mapping):
        _data_error(
            "canonical_smc.sides",
            "expected a side mapping",
            side=normalized_side,
        )
    if set(canonical_smc.sides) != VALID_TECHNICAL_SIDES:
        _data_error(
            "canonical_smc.sides",
            "must contain exactly buy and sell",
            side=normalized_side,
        )

    projections = {
        candidate_side: _validate_smc_side(
            canonical_smc.sides[candidate_side],
            candidate_side,
            contract_version=canonical_smc.contract_version,
            scoring_version=canonical_smc.scoring_version,
        )
        for candidate_side in ("buy", "sell")
    }
    return projections[normalized_side]


def technical_signal_score_gap(
    buy: TechnicalSignalScoreResult | None,
    sell: TechnicalSignalScoreResult | None,
) -> int | None:
    """Return the absolute BUY/SELL TechnicalScore gap, or ``None`` if missing."""

    if buy is None or sell is None:
        return None
    if type(buy) is not TechnicalSignalScoreResult:
        _data_error("buy", "expected a TechnicalSignalScoreResult", side="buy")
    if type(sell) is not TechnicalSignalScoreResult:
        _data_error("sell", "expected a TechnicalSignalScoreResult", side="sell")
    if buy.side != "buy":
        _data_error("buy.side", "must equal 'buy'", side="buy")
    if sell.side != "sell":
        _data_error("sell.side", "must equal 'sell'", side="sell")
    return abs(buy.technical_signal_score - sell.technical_signal_score)


def _validate_smc_side(
    value: object,
    side: str,
    *,
    contract_version: str,
    scoring_version: str,
) -> SmcTechnicalRawProjection:
    path = f"canonical_smc.sides.{side}"
    if type(value) is not SmcSideScoringResult:
        _data_error(path, "expected an SmcSideScoringResult", side=side)
    source_score = _require_raw(value.score, f"{path}.score", 15, side=side)
    if type(value.breakdown) is not dict:
        _data_error(f"{path}.breakdown", "expected an object", side=side)
    breakdown = value.breakdown
    if any(type(key) is not str for key in breakdown):
        _data_error(
            f"{path}.breakdown",
            "object keys must be strings",
            side=side,
        )
    actual_breakdown_fields = set(breakdown)
    missing = sorted(_REQUIRED_SMC_BREAKDOWN_FIELDS - actual_breakdown_fields)
    unknown = sorted(actual_breakdown_fields - _REQUIRED_SMC_BREAKDOWN_FIELDS)
    if missing or unknown:
        _data_error(
            f"{path}.breakdown",
            f"must use exact canonical fields; missing={missing}, unknown={unknown}",
            side=side,
        )
    if breakdown["side"] != side or type(breakdown["side"]) is not str:
        _data_error(
            f"{path}.breakdown.side",
            f"must equal {side!r}",
            side=side,
        )
    if (
        type(breakdown["scoring_version"]) is not str
        or breakdown["scoring_version"] != scoring_version
    ):
        _data_error(
            f"{path}.breakdown.scoring_version",
            "must match canonical SMC scoring_version",
            side=side,
        )
    if (
        type(breakdown["domain_version"]) is not str
        or breakdown["domain_version"] != SMC_DOMAIN_VERSION
    ):
        _data_error(
            f"{path}.breakdown.domain_version",
            f"must equal {SMC_DOMAIN_VERSION!r}",
            side=side,
        )

    component_values = {
        component: _require_raw(
            breakdown[component],
            f"{path}.breakdown.{component}",
            maximum,
            side=side,
        )
        for component, maximum in _SMC_COMPONENT_LIMITS.items()
    }
    subtotal = _require_raw(
        breakdown["subtotal"],
        f"{path}.breakdown.subtotal",
        15,
        side=side,
    )
    expected_subtotal = min(15, sum(component_values.values()))
    if subtotal != expected_subtotal:
        _data_error(
            f"{path}.breakdown.subtotal",
            f"must equal component subtotal {expected_subtotal}",
            side=side,
        )

    penalty_points = _require_nonnegative_int(
        breakdown["penalty_points"],
        f"{path}.breakdown.penalty_points",
        side=side,
    )
    applied_cap = _optional_bounded_int(
        breakdown["applied_cap"],
        f"{path}.breakdown.applied_cap",
        0,
        15,
        side=side,
    )
    source_total = _require_raw(
        breakdown["total"],
        f"{path}.breakdown.total",
        15,
        side=side,
    )
    expected_total = max(0, subtotal - penalty_points)
    if applied_cap is not None:
        expected_total = min(expected_total, applied_cap)
    if source_total != expected_total or source_score != expected_total:
        _data_error(
            f"{path}.score",
            "source score/total does not match subtotal, penalties and cap",
            side=side,
        )

    penalties = _require_text_tuple(
        breakdown["penalties"],
        f"{path}.breakdown.penalties",
        side=side,
    )
    caps = _require_text_tuple(
        breakdown["caps"],
        f"{path}.breakdown.caps",
        side=side,
    )
    breakdown_reasons = _require_text_tuple(
        breakdown["reason_codes"],
        f"{path}.breakdown.reason_codes",
        side=side,
    )
    result_reasons = _require_text_tuple(
        value.reason_codes,
        f"{path}.reason_codes",
        side=side,
    )
    if result_reasons != breakdown_reasons:
        _data_error(
            f"{path}.reason_codes",
            "must match breakdown reason_codes",
            side=side,
        )
    if type(value.smc_reason) is not str:
        _data_error(f"{path}.smc_reason", "expected a string", side=side)
    if not value.smc_reason or value.smc_reason != value.smc_reason.strip():
        _data_error(
            f"{path}.smc_reason",
            "expected a non-empty canonical string",
            side=side,
        )
    if not result_reasons:
        _data_error(
            f"{path}.reason_codes",
            "requires at least one canonical reason",
            side=side,
        )
    if bool(penalty_points) != bool(penalties):
        _data_error(
            f"{path}.breakdown.penalties",
            "must be present exactly when penalty_points is positive",
            side=side,
        )
    if applied_cap is not None and not caps:
        _data_error(
            f"{path}.breakdown.caps",
            "an applied cap requires structured cap evidence",
            side=side,
        )
    if applied_cap is None and caps:
        _data_error(
            f"{path}.breakdown.caps",
            "cap evidence requires an applied cap",
            side=side,
        )

    selected_zone = _validated_selected_zone(value, side=side, path=path)
    selected_zone_id = _optional_text(
        value.selected_zone_id,
        f"{path}.selected_zone_id",
        side=side,
    )
    breakdown_zone_id = _optional_text(
        breakdown["selected_zone_id"],
        f"{path}.breakdown.selected_zone_id",
        side=side,
    )
    if selected_zone_id != breakdown_zone_id:
        _data_error(
            f"{path}.selected_zone_id",
            "must match breakdown selected_zone_id",
            side=side,
        )
    if selected_zone is None:
        if selected_zone_id is not None:
            _data_error(
                f"{path}.selected_zone_id",
                "must be null when selected_zone is null",
                side=side,
            )
        if component_values["zone_score"] != 0:
            _data_error(
                f"{path}.breakdown.zone_score",
                "must be zero when no canonical zone is selected",
                side=side,
            )
        if component_values["technical_validation_score"] != 0:
            _data_error(
                f"{path}.breakdown.technical_validation_score",
                "must be zero when no canonical zone is selected",
                side=side,
            )
    else:
        frozen_zone_id = selected_zone.get("zone_id")
        if frozen_zone_id != selected_zone_id:
            _data_error(
                f"{path}.selected_zone.zone_id",
                "must match selected_zone_id",
                side=side,
            )
        if selected_zone.get("direction") != side:
            _data_error(
                f"{path}.selected_zone.direction",
                f"must equal {side!r}",
                side=side,
            )

    selected_zone_type = _optional_text(
        value.selected_zone_type,
        f"{path}.selected_zone_type",
        side=side,
    )
    selected_zone_timeframe = _optional_text(
        value.selected_zone_timeframe,
        f"{path}.selected_zone_timeframe",
        side=side,
    )
    selected_quality = _optional_bounded_int(
        value.selected_zone_quality_score,
        f"{path}.selected_zone_quality_score",
        0,
        100,
        side=side,
    )
    selected_relevance = _optional_bounded_int(
        value.selected_zone_relevance_score,
        f"{path}.selected_zone_relevance_score",
        0,
        100,
        side=side,
    )
    selected_setup = _optional_bounded_int(
        value.selected_zone_setup_score,
        f"{path}.selected_zone_setup_score",
        0,
        100,
        side=side,
    )
    selected_score = _optional_bounded_int(
        value.selected_zone_score,
        f"{path}.selected_zone_score",
        0,
        100,
        side=side,
    )
    breakdown_quality = _optional_bounded_int(
        breakdown.get("selected_zone_quality_score"),
        f"{path}.breakdown.selected_zone_quality_score",
        0,
        100,
        side=side,
    )
    breakdown_relevance = _optional_bounded_int(
        breakdown.get("selected_zone_relevance_score"),
        f"{path}.breakdown.selected_zone_relevance_score",
        0,
        100,
        side=side,
    )
    breakdown_setup = _optional_bounded_int(
        breakdown.get("selected_zone_setup_score"),
        f"{path}.breakdown.selected_zone_setup_score",
        0,
        100,
        side=side,
    )

    optional_zone_values = (
        selected_zone_type,
        selected_zone_timeframe,
        selected_quality,
        selected_relevance,
        selected_setup,
        selected_score,
        breakdown_quality,
        breakdown_relevance,
        breakdown_setup,
    )
    if selected_zone is None:
        if any(item is not None for item in optional_zone_values):
            _data_error(
                path,
                "selected-zone metadata must be null when selected_zone is null",
                side=side,
            )
    else:
        required_metadata = (
            selected_zone_type,
            selected_zone_timeframe,
            selected_quality,
            selected_relevance,
            selected_setup,
            selected_score,
            breakdown_quality,
            breakdown_relevance,
            breakdown_setup,
        )
        if any(item is None for item in required_metadata):
            _data_error(
                path,
                "selected-zone metadata must be complete",
                side=side,
            )
        expected_pairs = (
            (selected_zone.get("zone_type"), selected_zone_type, "zone_type"),
            (selected_zone.get("type"), selected_zone_type, "type"),
            (
                selected_zone.get("timeframe"),
                selected_zone_timeframe,
                "timeframe",
            ),
            (
                selected_zone.get("zone_quality_score"),
                selected_quality,
                "zone_quality_score",
            ),
            (
                selected_zone.get("zone_relevance_score"),
                selected_relevance,
                "zone_relevance_score",
            ),
            (
                selected_zone.get("zone_setup_score"),
                selected_setup,
                "zone_setup_score",
            ),
            (
                selected_zone.get("scoring_version"),
                scoring_version,
                "scoring_version",
            ),
            (
                selected_zone.get("domain_version"),
                SMC_DOMAIN_VERSION,
                "domain_version",
            ),
        )
        for observed, expected, field in expected_pairs:
            if observed != expected or type(observed) is not type(expected):
                _data_error(
                    f"{path}.selected_zone.{field}",
                    "does not match canonical selected-zone metadata",
                    side=side,
                )
        if selected_score != selected_setup:
            _data_error(
                f"{path}.selected_zone_score",
                "must equal selected_zone_setup_score",
                side=side,
            )
        if selected_quality != breakdown_quality:
            _data_error(
                f"{path}.selected_zone_quality_score",
                "must match breakdown selected_zone_quality_score",
                side=side,
            )
        if selected_relevance != breakdown_relevance:
            _data_error(
                f"{path}.selected_zone_relevance_score",
                "must match breakdown selected_zone_relevance_score",
                side=side,
            )
        if selected_setup != breakdown_setup:
            _data_error(
                f"{path}.selected_zone_setup_score",
                "must match breakdown selected_zone_setup_score",
                side=side,
            )
        expected_zone_component = _zone_component_from_setup(selected_setup)
        if component_values["zone_score"] != expected_zone_component:
            _data_error(
                f"{path}.breakdown.zone_score",
                f"must equal selected-zone component {expected_zone_component}",
                side=side,
            )

    evidence = SmcTechnicalEvidence(
        side=side,
        raw_semantics_version=SMC_TECHNICAL_RAW_VERSION,
        source_scoring_version=scoring_version,
        source_contract_version=contract_version,
        source_domain_version=SMC_DOMAIN_VERSION,
        raw_subtotal=subtotal,
        base_components=MappingProxyType(dict(component_values)),
        source_score=source_score,
        penalty_points=penalty_points,
        applied_cap=applied_cap,
        penalties=penalties,
        caps=caps,
        reason_codes=result_reasons,
        smc_reason=value.smc_reason,
        selected_zone=selected_zone,
        selected_zone_id=selected_zone_id,
        selected_zone_type=selected_zone_type,
        selected_zone_timeframe=selected_zone_timeframe,
    )
    return SmcTechnicalRawProjection(side=side, raw=subtotal, evidence=evidence)


def _normalize_smc_technical_evidence(value: SmcTechnicalEvidence) -> None:
    """Validate and deep-freeze the public provenance model itself."""

    side = _require_side(value.side)
    expected_versions = (
        (
            value.raw_semantics_version,
            SMC_TECHNICAL_RAW_VERSION,
            "raw_semantics_version",
        ),
        (
            value.source_scoring_version,
            SMC_SCORER_VERSION,
            "source_scoring_version",
        ),
        (
            value.source_contract_version,
            SMC_SCORING_CONTRACT_VERSION,
            "source_contract_version",
        ),
        (
            value.source_domain_version,
            SMC_DOMAIN_VERSION,
            "source_domain_version",
        ),
    )
    for observed, expected, field in expected_versions:
        if type(observed) is not str or observed != expected:
            _data_error(
                f"smc_evidence.{field}",
                f"must equal {expected!r}",
                side=side,
            )

    if not isinstance(value.base_components, Mapping):
        _data_error(
            "smc_evidence.base_components",
            "expected a component mapping",
            side=side,
        )
    if any(type(key) is not str for key in value.base_components):
        _data_error(
            "smc_evidence.base_components",
            "component keys must be strings",
            side=side,
        )
    actual_component_fields = set(value.base_components)
    missing = sorted(set(_SMC_COMPONENT_LIMITS) - actual_component_fields)
    unknown = sorted(actual_component_fields - set(_SMC_COMPONENT_LIMITS))
    if missing or unknown:
        _data_error(
            "smc_evidence.base_components",
            f"must use exact base fields; missing={missing}, unknown={unknown}",
            side=side,
        )
    components = {
        component: _require_raw(
            value.base_components[component],
            f"smc_evidence.base_components.{component}",
            maximum,
            side=side,
        )
        for component, maximum in _SMC_COMPONENT_LIMITS.items()
    }
    raw_subtotal = _require_raw(
        value.raw_subtotal,
        "smc_evidence.raw_subtotal",
        TECHNICAL_COMPONENT_RAW_MAX["smc"],
        side=side,
    )
    expected_subtotal = min(15, sum(components.values()))
    if raw_subtotal != expected_subtotal:
        _data_error(
            "smc_evidence.raw_subtotal",
            f"must equal component subtotal {expected_subtotal}",
            side=side,
        )

    source_score = _require_raw(
        value.source_score,
        "smc_evidence.source_score",
        15,
        side=side,
    )
    penalty_points = _require_nonnegative_int(
        value.penalty_points,
        "smc_evidence.penalty_points",
        side=side,
    )
    applied_cap = _optional_bounded_int(
        value.applied_cap,
        "smc_evidence.applied_cap",
        0,
        15,
        side=side,
    )
    expected_source_score = max(0, raw_subtotal - penalty_points)
    if applied_cap is not None:
        expected_source_score = min(expected_source_score, applied_cap)
    if source_score != expected_source_score:
        _data_error(
            "smc_evidence.source_score",
            "does not match raw subtotal, penalties and cap",
            side=side,
        )

    penalties = _require_text_tuple(
        value.penalties,
        "smc_evidence.penalties",
        side=side,
    )
    caps = _require_text_tuple(value.caps, "smc_evidence.caps", side=side)
    reasons = _require_text_tuple(
        value.reason_codes,
        "smc_evidence.reason_codes",
        side=side,
    )
    smc_reason = _required_text(
        value.smc_reason,
        "smc_evidence.smc_reason",
        side=side,
    )
    if not reasons:
        _data_error(
            "smc_evidence.reason_codes",
            "requires at least one canonical reason",
            side=side,
        )
    if bool(penalty_points) != bool(penalties):
        _data_error(
            "smc_evidence.penalties",
            "must be present exactly when penalty_points is positive",
            side=side,
        )
    if (applied_cap is not None) != bool(caps):
        _data_error(
            "smc_evidence.caps",
            "must be present exactly when a cap is applied",
            side=side,
        )

    selected_zone = _validated_selected_zone_payload(
        value.selected_zone,
        side=side,
        path="smc_evidence.selected_zone",
        scoring_version=value.source_scoring_version,
    )
    selected_zone_id = _optional_text(
        value.selected_zone_id,
        "smc_evidence.selected_zone_id",
        side=side,
    )
    selected_zone_type = _optional_text(
        value.selected_zone_type,
        "smc_evidence.selected_zone_type",
        side=side,
    )
    selected_zone_timeframe = _optional_text(
        value.selected_zone_timeframe,
        "smc_evidence.selected_zone_timeframe",
        side=side,
    )
    selected_metadata = (
        selected_zone_id,
        selected_zone_type,
        selected_zone_timeframe,
    )
    if selected_zone is None:
        if any(item is not None for item in selected_metadata):
            _data_error(
                "smc_evidence.selected_zone",
                "selected-zone metadata must be null when no zone is selected",
                side=side,
            )
        if components["zone_score"] != 0:
            _data_error(
                "smc_evidence.base_components.zone_score",
                "must be zero when no canonical zone is selected",
                side=side,
            )
        if components["technical_validation_score"] != 0:
            _data_error(
                "smc_evidence.base_components.technical_validation_score",
                "must be zero when no canonical zone is selected",
                side=side,
            )
    else:
        if any(item is None for item in selected_metadata):
            _data_error(
                "smc_evidence.selected_zone",
                "selected-zone metadata must be complete",
                side=side,
            )
        expected_metadata = (
            (selected_zone["zone_id"], selected_zone_id, "selected_zone_id"),
            (selected_zone["zone_type"], selected_zone_type, "selected_zone_type"),
            (
                selected_zone["timeframe"],
                selected_zone_timeframe,
                "selected_zone_timeframe",
            ),
        )
        for observed, expected, field in expected_metadata:
            if observed != expected or type(observed) is not type(expected):
                _data_error(
                    f"smc_evidence.{field}",
                    "must match selected_zone",
                    side=side,
                )
        expected_zone_component = _zone_component_from_setup(
            selected_zone["zone_setup_score"]
        )
        if components["zone_score"] != expected_zone_component:
            _data_error(
                "smc_evidence.base_components.zone_score",
                f"must equal selected-zone component {expected_zone_component}",
                side=side,
            )

    object.__setattr__(value, "side", side)
    object.__setattr__(value, "raw_subtotal", raw_subtotal)
    object.__setattr__(
        value,
        "base_components",
        MappingProxyType(dict(components)),
    )
    object.__setattr__(value, "source_score", source_score)
    object.__setattr__(value, "penalty_points", penalty_points)
    object.__setattr__(value, "applied_cap", applied_cap)
    object.__setattr__(value, "penalties", penalties)
    object.__setattr__(value, "caps", caps)
    object.__setattr__(value, "reason_codes", reasons)
    object.__setattr__(value, "smc_reason", smc_reason)
    object.__setattr__(value, "selected_zone", selected_zone)
    object.__setattr__(value, "selected_zone_id", selected_zone_id)
    object.__setattr__(value, "selected_zone_type", selected_zone_type)
    object.__setattr__(value, "selected_zone_timeframe", selected_zone_timeframe)


def _validated_selected_zone(
    side_result: SmcSideScoringResult,
    *,
    side: str,
    path: str,
) -> Mapping[str, Any] | None:
    return _validated_selected_zone_payload(
        side_result.selected_zone,
        side=side,
        path=f"{path}.selected_zone",
        scoring_version=SMC_SCORER_VERSION,
    )


def _validated_selected_zone_payload(
    payload: object,
    *,
    side: str,
    path: str,
    scoring_version: str,
) -> Mapping[str, Any] | None:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        _data_error(
            path,
            "expected an object or null",
            side=side,
        )
    if any(type(key) is not str for key in payload):
        _data_error(
            path,
            "object keys must be strings",
            side=side,
        )
    actual_fields = set(payload)
    missing_fields = sorted(_SELECTED_ZONE_FIELDS - actual_fields)
    unknown_fields = sorted(actual_fields - _SELECTED_ZONE_FIELDS)
    if missing_fields or unknown_fields:
        _data_error(
            path,
            f"must use exact canonical fields; missing={missing_fields}, unknown={unknown_fields}",
            side=side,
        )
    frozen = _freeze_evidence(
        dict(payload),
        path,
        side=side,
    )
    if not isinstance(frozen, Mapping):
        _data_error(
            path,
            "expected an object",
            side=side,
        )
    zone_id = _required_text(
        frozen["zone_id"],
        f"{path}.zone_id",
        side=side,
    )
    zone_type = _required_text(
        frozen["zone_type"],
        f"{path}.zone_type",
        side=side,
    )
    if frozen["type"] != frozen["zone_type"] or type(frozen["type"]) is not str:
        _data_error(
            f"{path}.type",
            "must equal zone_type",
            side=side,
        )
    if frozen["direction"] != side or type(frozen["direction"]) is not str:
        _data_error(
            f"{path}.direction",
            f"must equal {side!r}",
            side=side,
        )
    timeframe = _required_text(
        frozen["timeframe"],
        f"{path}.timeframe",
        side=side,
    )
    if timeframe not in _VALID_SELECTED_ZONE_TIMEFRAMES:
        _data_error(
            f"{path}.timeframe",
            f"must be one of {sorted(_VALID_SELECTED_ZONE_TIMEFRAMES)}",
            side=side,
        )
    family = _required_text(
        frozen["family"],
        f"{path}.family",
        side=side,
    )
    if family not in _VALID_SELECTED_ZONE_FAMILIES:
        _data_error(
            f"{path}.family",
            f"must be one of {sorted(_VALID_SELECTED_ZONE_FAMILIES)}",
            side=side,
        )
    lowered_type = zone_type.lower()
    family_side = "buy" if family == "demand" else "sell" if family == "supply" else None
    type_side_markers = set()
    if "demand" in lowered_type or "bullish" in lowered_type:
        type_side_markers.add("buy")
    if "supply" in lowered_type or "bearish" in lowered_type:
        type_side_markers.add("sell")
    if len(type_side_markers) > 1:
        _data_error(
            f"{path}.zone_type",
            "zone type contains conflicting direction markers",
            side=side,
        )
    type_side = next(iter(type_side_markers), None)
    if family_side is not None and family_side != side:
        _data_error(
            f"{path}.family",
            "zone family conflicts with direction",
            side=side,
        )
    if type_side is not None and type_side != side:
        _data_error(
            f"{path}.zone_type",
            "zone type/family conflicts with direction",
            side=side,
        )
    source = _required_text(frozen["source"], f"{path}.source", side=side)
    if source != "smc_selected":
        _data_error(
            f"{path}.source",
            "must equal 'smc_selected'",
            side=side,
        )
    low = _require_finite_number(
        frozen["low"],
        f"{path}.low",
        side=side,
    )
    high = _require_finite_number(
        frozen["high"],
        f"{path}.high",
        side=side,
    )
    level = _require_finite_number(
        frozen["level"],
        f"{path}.level",
        side=side,
    )
    if high <= low:
        _data_error(
            f"{path}.high",
            "must be greater than low",
            side=side,
        )
    if level != (low + high) / 2:
        _data_error(
            f"{path}.level",
            "must equal the zone midpoint",
            side=side,
        )
    _require_bounded_int(
        frozen["zone_quality_score"],
        f"{path}.zone_quality_score",
        0,
        100,
        side=side,
    )
    _require_bounded_int(
        frozen["zone_relevance_score"],
        f"{path}.zone_relevance_score",
        0,
        100,
        side=side,
    )
    _require_bounded_int(
        frozen["zone_setup_score"],
        f"{path}.zone_setup_score",
        0,
        100,
        side=side,
    )
    if type(frozen["liquidity_sweep_linked"]) is not bool:
        _data_error(
            f"{path}.liquidity_sweep_linked",
            "expected a boolean",
            side=side,
        )
    linked_id = _optional_text(
        frozen["linked_sweep_id"],
        f"{path}.linked_sweep_id",
        side=side,
    )
    linked_distance = _optional_nonnegative_number(
        frozen["linked_sweep_distance_atr"],
        f"{path}.linked_sweep_distance_atr",
        side=side,
    )
    linked_delta = _optional_bounded_int(
        frozen["linked_sweep_time_delta"],
        f"{path}.linked_sweep_time_delta",
        -(1 << 63),
        (1 << 63) - 1,
        side=side,
    )
    linked_values = (linked_id, linked_distance, linked_delta)
    if frozen["liquidity_sweep_linked"]:
        if any(item is None for item in linked_values):
            _data_error(
                path,
                "linked sweep metadata must be complete when linked",
                side=side,
            )
    elif any(item is not None for item in linked_values):
        _data_error(
            path,
            "linked sweep metadata must be null when not linked",
            side=side,
        )
    selection_reasons = _require_text_tuple(
        frozen["selection_reason_codes"],
        f"{path}.selection_reason_codes",
        side=side,
    )
    if not selection_reasons:
        _data_error(
            f"{path}.selection_reason_codes",
            "requires at least one selection reason",
            side=side,
        )
    if frozen["scoring_version"] != scoring_version or type(frozen["scoring_version"]) is not str:
        _data_error(
            f"{path}.scoring_version",
            "must match canonical SMC scoring_version",
            side=side,
        )
    if frozen["domain_version"] != SMC_DOMAIN_VERSION or type(frozen["domain_version"]) is not str:
        _data_error(
            f"{path}.domain_version",
            f"must equal {SMC_DOMAIN_VERSION!r}",
            side=side,
        )
    if frozen["zone_id"] != zone_id:
        _data_error(f"{path}.zone_id", "invalid zone identity", side=side)
    return frozen


def _require_side(value: object) -> str:
    if type(value) is not str or value not in VALID_TECHNICAL_SIDES:
        _data_error("side", "must be exactly 'buy' or 'sell'")
    return value


def _require_regime(value: object, *, side: str) -> str:
    if type(value) is not str or value not in VALID_TECHNICAL_REGIMES:
        _data_error(
            "regime",
            f"must be one of {sorted(VALID_TECHNICAL_REGIMES)}",
            side=side,
        )
    return value


def _require_raw(
    value: object,
    path: str,
    maximum: int,
    *,
    side: str,
) -> int:
    if type(value) is not int:
        _data_error(path, "expected an integer", side=side)
    if not 0 <= value <= maximum:
        _data_error(path, f"must be between 0 and {maximum}", side=side)
    return value


def _require_nonnegative_int(value: object, path: str, *, side: str) -> int:
    if type(value) is not int:
        _data_error(path, "expected an integer", side=side)
    if value < 0:
        _data_error(path, "must be >= 0", side=side)
    return value


def _optional_bounded_int(
    value: object,
    path: str,
    minimum: int,
    maximum: int,
    *,
    side: str,
) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        _data_error(path, "expected an integer or null", side=side)
    if not minimum <= value <= maximum:
        _data_error(
            path,
            f"must be between {minimum} and {maximum}",
            side=side,
        )
    return value


def _optional_text(value: object, path: str, *, side: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str or not value or value != value.strip():
        _data_error(path, "expected a non-empty canonical string or null", side=side)
    return value


def _required_text(value: object, path: str, *, side: str) -> str:
    result = _optional_text(value, path, side=side)
    if result is None:
        _data_error(path, "expected a non-empty canonical string", side=side)
    return result


def _require_bounded_int(
    value: object,
    path: str,
    minimum: int,
    maximum: int,
    *,
    side: str,
) -> int:
    result = _optional_bounded_int(
        value,
        path,
        minimum,
        maximum,
        side=side,
    )
    if result is None:
        _data_error(path, "expected an integer", side=side)
    return result


def _require_finite_number(value: object, path: str, *, side: str) -> float:
    if type(value) not in {int, float}:
        _data_error(path, "expected a finite number", side=side)
    try:
        number = float(value)
    except (OverflowError, ValueError):
        _data_error(path, "expected a finite representable number", side=side)
    if not math.isfinite(number):
        _data_error(path, "number must be finite", side=side)
    return number


def _optional_nonnegative_number(
    value: object,
    path: str,
    *,
    side: str,
) -> float | None:
    if value is None:
        return None
    number = _require_finite_number(value, path, side=side)
    if number < 0:
        _data_error(path, "must be >= 0", side=side)
    return number


def _zone_component_from_setup(value: int) -> int:
    if value >= 85:
        return 5
    if value >= 70:
        return 4
    if value >= 55:
        return 3
    if value >= 40:
        return 2
    if value >= 25:
        return 1
    return 0


def _require_text_tuple(value: object, path: str, *, side: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        _data_error(path, "expected a text array", side=side)
    result: list[str] = []
    for index, item in enumerate(value):
        if type(item) is not str or not item or item != item.strip():
            _data_error(
                f"{path}[{index}]",
                "expected a non-empty canonical string",
                side=side,
            )
        result.append(item)
    return tuple(result)


def _freeze_evidence(
    value: object,
    path: str,
    *,
    side: str,
    _active: set[int] | None = None,
    _depth: int = 0,
) -> Any:
    if _depth > 32:
        _data_error(path, "evidence nesting exceeds 32 levels", side=side)
    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            _data_error(path, "evidence number must be finite", side=side)
        return value

    active = _active if _active is not None else set()
    if type(value) is dict:
        identity = id(value)
        if identity in active:
            _data_error(path, "cyclic evidence is not allowed", side=side)
        active.add(identity)
        try:
            frozen: dict[str, Any] = {}
            for key, item in value.items():
                if type(key) is not str:
                    _data_error(path, "evidence keys must be strings", side=side)
                frozen[key] = _freeze_evidence(
                    item,
                    f"{path}.{key}",
                    side=side,
                    _active=active,
                    _depth=_depth + 1,
                )
            return MappingProxyType(frozen)
        finally:
            active.remove(identity)
    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in active:
            _data_error(path, "cyclic evidence is not allowed", side=side)
        active.add(identity)
        try:
            return tuple(
                _freeze_evidence(
                    item,
                    f"{path}[{index}]",
                    side=side,
                    _active=active,
                    _depth=_depth + 1,
                )
                for index, item in enumerate(value)
            )
        finally:
            active.remove(identity)
    _data_error(
        path,
        f"unsupported evidence type {type(value).__name__}",
        side=side,
    )


def _thaw_evidence(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_evidence(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_evidence(item) for item in value]
    return value


def _clamp_fraction(
    value: Fraction,
    minimum: Fraction,
    maximum: Fraction,
) -> Fraction:
    return max(minimum, min(maximum, value))


def _round_half_up_once(value: Fraction) -> int:
    """Round one non-negative exact total once with ROUND_HALF_UP semantics."""

    quotient, remainder = divmod(value.numerator, value.denominator)
    return quotient + int(remainder * 2 >= value.denominator)


def _data_error(path: str, detail: str, *, side: str | None = None) -> None:
    raise TechnicalScoreDataError(path, detail, side=side)


__all__ = [
    "SMC_TECHNICAL_RAW_VERSION",
    "TECHNICAL_COMPONENT_RAW_MAX",
    "TECHNICAL_REGIME_WEIGHTS",
    "TECHNICAL_WEIGHT_POLICY_VERSION",
    "TechnicalScoreDataError",
    "SmcTechnicalEvidence",
    "SmcTechnicalRawProjection",
    "TechnicalSignalScoreResult",
    "project_smc_technical_raw",
    "score_technical_signal",
    "technical_signal_score_gap",
]
