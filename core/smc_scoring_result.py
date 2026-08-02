"""Neutral canonical SMC scoring result contract.

The single-runtime contract holds both BUY and SELL side payloads produced by
the one canonical scorer.  Public names here are deliberately free of
v1/v2/legacy/shadow concepts: ``scoring_version`` is immutable formula
provenance, never a mode selector.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.smc_versions import SMC_SCORER_VERSION as _CANONICAL_SCORER_VERSION


SMC_SCORING_CONTRACT_VERSION = "smc-scoring-canonical-2026-08"
VALID_SIDES = frozenset({"buy", "sell"})


@dataclass(frozen=True, slots=True)
class SmcSideScoringResult:
    """One side of the canonical SMC scoring output."""

    score: int | None
    breakdown: dict[str, Any]
    selected_zone: dict[str, Any] | None = None
    selected_zone_id: str | None = None
    selected_zone_type: str | None = None
    selected_zone_timeframe: str | None = None
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "breakdown", dict(self.breakdown))
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "score": self.score,
            "breakdown": dict(self.breakdown),
            "selected_zone": self.selected_zone,
            "selected_zone_id": self.selected_zone_id,
            "selected_zone_type": self.selected_zone_type,
            "selected_zone_timeframe": self.selected_zone_timeframe,
            "reason_codes": list(self.reason_codes),
        }
        return {key: value for key, value in payload.items() if value is not None}

    @classmethod
    def from_dict(cls, value: object) -> "SmcSideScoringResult":
        payload = value if isinstance(value, dict) else {}
        selected_zone = payload.get("selected_zone")
        return cls(
            score=_optional_int(payload.get("score")),
            breakdown=_optional_dict(payload.get("breakdown")),
            selected_zone=(
                dict(selected_zone)
                if isinstance(selected_zone, dict)
                else None
            ),
            selected_zone_id=_optional_text(payload.get("selected_zone_id")),
            selected_zone_type=_optional_text(payload.get("selected_zone_type")),
            selected_zone_timeframe=_optional_text(
                payload.get("selected_zone_timeframe")
            ),
            reason_codes=_tuple_of_text(payload.get("reason_codes")),
        )


@dataclass(frozen=True, slots=True)
class SmcScoringResult:
    """Canonical result containing both BUY and SELL side payloads.

    ``scoring_version`` is immutable provenance of the formula that produced
    this result.  The structure intentionally carries no scorer selection.
    """

    scoring_version: str
    contract_version: str = SMC_SCORING_CONTRACT_VERSION
    sides: Mapping[str, SmcSideScoringResult] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized = {
            side: payload
            for side, payload in self.sides.items()
            if side in VALID_SIDES
        }
        object.__setattr__(self, "sides", dict(normalized))

    def side(self, side: str) -> SmcSideScoringResult | None:
        return self.sides.get(side)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "scoring_version": self.scoring_version,
            "sides": {
                side: self.sides[side].to_dict()
                for side in ("buy", "sell")
                if side in self.sides
            },
        }

    @classmethod
    def from_dict(cls, value: object) -> "SmcScoringResult":
        payload = value if isinstance(value, dict) else {}
        raw_sides = payload.get("sides")
        sides: dict[str, SmcSideScoringResult] = {}
        if isinstance(raw_sides, dict):
            for side in VALID_SIDES:
                side_payload = raw_sides.get(side)
                if isinstance(side_payload, dict):
                    sides[side] = SmcSideScoringResult.from_dict(side_payload)
        return cls(
            scoring_version=(
                _optional_text(payload.get("scoring_version"))
                or _CANONICAL_SCORER_VERSION
            ),
            contract_version=(
                _optional_text(payload.get("contract_version"))
                or SMC_SCORING_CONTRACT_VERSION
            ),
            sides=sides,
        )


def _optional_dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _tuple_of_text(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(
        str(item).strip()
        for item in value
        if str(item).strip()
    )
